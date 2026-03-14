import os
import logging
import sys
import tempfile
from dotenv import load_dotenv
import socket
import ipaddress
import argparse
from datetime import datetime
from typing import Tuple, List

from cert_manager import is_certificate_due_for_renewal
from acme_client_wrapper import issue_certificate
from config_loader import load_yaml_config
from remote_deployer import RemoteDeployer
from otc_elb_client import OTCELBClient
from health_checker import HealthChecker
from logger import setup_logging
from report_generator import generate_markdown_report

# Global logger instance, to be initialized after dynamic setup in main()
log = logging.getLogger(__name__)

def get_domain_ip_type(domain: str) -> str:
    """
    Resolves a domain's IP address and determines if it is public or private.
    """
    try:
        ip_str = socket.gethostbyname(domain)
        ip = ipaddress.ip_address(ip_str)
        if ip.is_private:
            log.info(f"Domain '{domain}' resolves to private IP: {ip_str}")
            return "private"
        else:
            log.info(f"Domain '{domain}' resolves to public IP: {ip_str}")
            return "public"
    except socket.gaierror:
        log.error(f"Could not resolve IP for domain: {domain}")
        return "unknown"
    except Exception as e:
        log.error(f"An unexpected error occurred while checking IP for {domain}: {e}")
        return "unknown"

def get_wildcard_domain(domain: str) -> str:
    """
    Generates a wildcard domain from a given domain.
    """
    parts = domain.split('.')
    if len(parts) > 2:
        wildcard_base = '.'.join(parts[1:])
    else:
        wildcard_base = domain
    return f"*.{wildcard_base}"

def deploy_to_otc_elb(elb_config: dict, domain_name: str, local_cert_path: str, local_key_path: str, global_config: dict) -> List[dict]:
    """
    Uploads certificate to OTC Console and updates all configured listeners.
    """
    dry_run = global_config.get("dry_run", False)
    deployment_results = []
    
    listeners = elb_config.get("listeners", [])
    if not listeners:
        return [{"server": "OTC ELB", "success": True, "message": "No listeners configured for OTC ELB."}]

    log.info(f"--- Starting deployment to OTC ELB for {domain_name} ---")
    
    if dry_run:
        for listener in listeners:
            log.info(f"[DRY RUN] Would update OTC ELB listener {listener.get('name')} ({listener.get('id')})")
            deployment_results.append({
                "server": f"OTC ELB: {listener.get('name')}",
                "success": True,
                "message": "[DRY RUN] Simulated success."
            })
        return deployment_results

    try:
        # Initialize OTC Client
        client = OTCELBClient(
            auth_url=os.getenv("OS_AUTH_URL"),
            username=os.getenv("OS_USERNAME"),
            password=os.getenv("OS_PASSWORD"),
            domain_name=os.getenv("OS_USER_DOMAIN_NAME"),
            project_id=os.getenv("OS_PROJECT_ID")
        )

        with open(local_cert_path, 'r') as f:
            cert_content = f.read()
        with open(local_key_path, 'r') as f:
            key_content = f.read()

        # 1. Upload new cert
        cert_name = f"{domain_name.replace('*', 'wildcard')}-{datetime.now().strftime('%Y%m%d')}"
        new_cert_id = client.upload_certificate(cert_name, cert_content, key_content)

        # 2. Update each listener
        for listener in listeners:
            l_name = listener.get("name")
            l_id = listener.get("id")
            
            # Capture old cert ID for optional cleanup later
            old_cert_id = client.get_listener_current_cert(l_id)
            
            success = client.update_listener_cert(l_id, new_cert_id)
            msg = f"Updated listener {l_name} to new cert {new_cert_id}." if success else f"Failed to update listener {l_name}."
            
            deployment_results.append({
                "server": f"OTC ELB: {l_name}",
                "success": success,
                "message": msg
            })
            
            # 3. Optional: Cleanup old cert if it's different and was previously managed
            if success and old_cert_id and old_cert_id != new_cert_id:
                log.info(f"Listener {l_name} was previously using cert {old_cert_id}. (Cleanup skip for safety in this version)")

        return deployment_results

    except Exception as e:
        log.error(f"OTC ELB Deployment FAILED: {e}")
        return [{"server": "OTC ELB", "success": False, "message": str(e)}]

def deploy_certificate(server_config: dict, domain_name: str, local_cert_path: str, local_key_path: str, dry_run: bool = False) -> Tuple[bool, str]:
    """
    Deploys the new certificate to a single server with a robust, atomic process.
    Returns (True, "Success message") or (False, "Error message").
    """
    host = server_config.get("host")
    user = server_config.get("user")
    
    # Allow environment variable to override the SSH key path for CI environments
    ssh_key = os.getenv("SSH_KEY_PATH") or server_config.get("ssh_key_path")
    
    remote_cert_path = server_config.get("cert_path")
    reload_command = server_config.get("nginx_reload_command")
    validation_command = server_config.get("validation_command", "sudo nginx -t") # Optional validation command
    server_name = server_config.get("name", host) # Use name if available, else host

    if not all([host, user, ssh_key, remote_cert_path, reload_command]):
        missing = [k for k, v in {
            "host": host, "user": user, "ssh_key": ssh_key, 
            "cert_path": remote_cert_path, "reload_cmd": reload_command
        }.items() if not v]
        error_msg = f"Server config for '{server_name}' is incomplete (Missing: {', '.join(missing)}). Skipping deployment."
        log.error(error_msg)
        return False, error_msg

    log.info(f"--- Starting deployment to server: {server_name} ({host}) ---")
    deployer = RemoteDeployer(host, user, ssh_key, dry_run=dry_run)

    try:
        # Define remote paths
        remote_fullchain_path = os.path.join(remote_cert_path, "fullchain.pem")
        remote_key_path = os.path.join(remote_cert_path, "privkey.pem")

        # Backup paths
        backup_fullchain_path = remote_fullchain_path + ".bak"
        backup_key_path = remote_key_path + ".bak"

        # 1. Backup existing certificates on the remote server
        try:
            deployer.execute_command(f"sudo cp {remote_fullchain_path} {backup_fullchain_path}", check_exit_code=False)
            deployer.execute_command(f"sudo cp {remote_key_path} {backup_key_path}", check_exit_code=False)
        except Exception as e:
            log.warning(f"Backup on {server_name} failed (might be first deploy, or certs missing): {e}")

        # 2. Upload new certificates
        deployer.upload_file(local_cert_path, remote_fullchain_path) # Now raises exception on failure
        deployer.upload_file(local_key_path, remote_key_path) # Now raises exception on failure

        # 3. Validate Nginx config with new certs
        deployer.validate_nginx_config(validation_command) # Now raises exception on failure

        # 4. Gracefully reload Nginx
        deployer.reload_nginx(reload_command) # Now raises exception on failure

        # 5. Perform Health Check
        health_checker = HealthChecker(domain_name)
        if not dry_run: # Only perform live health check if not dry run
            health_checker.check_https_status() # Now raises exception on failure
            health_checker.verify_cert_expiry() # Now raises exception on failure

        log.info(f"Deployment to {server_name} successful and health checks passed!")
        # 6. Clean up backups on success
        try:
            deployer.execute_command(f"sudo rm -f {backup_fullchain_path} {backup_key_path}")
        except Exception as e:
            log.warning(f"Failed to clean up backup files on {server_name}: {e}")

        return True, f"Deployment to {server_name} successful."

    except Exception as e:
        error_msg = f"Deployment to {server_name} FAILED: {e}"
        log.error(error_msg)
        if not dry_run:
            log.info(f"Attempting to roll back on {server_name}...")
            try:
                deployer.execute_command(f"sudo mv {backup_fullchain_path} {remote_fullchain_path}")
                deployer.execute_command(f"sudo mv {backup_key_path} {remote_key_path}")
                deployer.reload_nginx(reload_command)
                log.info(f"Rollback on {server_name} successful. Nginx reloaded with old certificate.")
            except Exception as rollback_e:
                log.critical(f"CRITICAL: Rollback on {server_name} FAILED: {rollback_e}. Nginx may be in a broken state.")
        return False, error_msg
    finally:
        deployer.close()

def process_domain(domain_info: dict, servers_map: dict, results: dict):
    """
    Processes a single domain entry, including issuance and deployment.
    Updates the results dictionary with the outcome.
    """
    target_domain = domain_info.get("domain")
    dry_run = results["global_config"].get("dry_run", False)
    force_renewal = results["global_config"].get("force_renewal", False)

    if not target_domain:
        log.warning("Skipping domain entry with no 'domain' field.")
        results["domains_processed"] += 1 # Still count as processed, even if invalid
        results["failed_renewals"].append({"domain": "N/A", "error": "Domain entry missing 'domain' field."})
        return

    results["domains_processed"] += 1
    log.info(f"--- Processing domain: {target_domain} ---")

    local_cert_dir = os.path.join(results["global_config"]['cert_base_path'], target_domain)
    # Ensure local directory exists before issuance
    os.makedirs(local_cert_dir, exist_ok=True)
    
    local_cert_path = os.path.join(local_cert_dir, "fullchain.cer")
    local_key_path = os.path.join(local_cert_dir, "domain.key")

    # Issue for the exact domain requested, regardless of IP type
    domain_to_issue = target_domain

    is_due = is_certificate_due_for_renewal(local_cert_path, results["global_config"]['renewal_threshold_days'])

    if is_due or force_renewal or dry_run:
        if force_renewal:
             log.info(f"Renewal forced for {target_domain}.")
        elif dry_run and not is_due:
             log.info(f"[DRY RUN] Certificate for {target_domain} is not due, but proceeding for simulation.")

        log.info(f"Attempting to issue/renew certificate for {domain_to_issue}...")

        domain_result = {
            "domain": target_domain,
            "issue_error": None,
            "deployment_results": [] # [{"server": str, "success": bool, "message": str}]
        }
        issuance_successful = False

        try:
            # issue_certificate now raises an exception on failure
            issue_certificate(
                domain=domain_to_issue,
                acme_home_dir=results["global_config"]['acme_home_dir'],
                ionos_api_key=results["global_config"]['ionos_api_key'],
                ionos_api_secret=results["global_config"]['ionos_api_secret'],
                email=results["global_config"]['acme_email'],
                cert_storage_path=local_cert_dir,
                dry_run=dry_run,
                force_renewal=force_renewal
            )
            log.info(f"Certificate issuance for {domain_to_issue} successful.")
            issuance_successful = True

        except Exception as e:
            domain_result["issue_error"] = str(e)
            log.error(f"An error occurred during certificate issuance for {domain_to_issue}: {e}")
            if dry_run:
                log.warning(f"[DRY RUN] Issuance failed, but creating dummy files to continue simulation.")
                with open(local_cert_path, 'w') as f: f.write("dummy cert")
                with open(local_key_path, 'w') as f: f.write("dummy key")
                issuance_successful = True

        if issuance_successful:
            # 1. SSH Deployment to servers
            servers_for_domain = domain_info.get("servers", [])
            for server_name in servers_for_domain:
                server_config = servers_map.get(server_name)
                if server_config:
                    deploy_success, deploy_message = deploy_certificate(
                        server_config, target_domain, local_cert_path, local_key_path, dry_run=dry_run
                    )
                    domain_result["deployment_results"].append({
                        "server": server_name,
                        "success": deploy_success,
                        "message": deploy_message
                    })
                else:
                    error_msg = f"Server '{server_name}' not found in servers.yaml. Cannot deploy."
                    log.warning(error_msg)
                    domain_result["deployment_results"].append({
                        "server": server_name,
                        "success": False,
                        "message": error_msg
                    })

            # 2. Cloud Console Deployment (OTC ELB)
            if "otc_elb" in domain_info:
                elb_results = deploy_to_otc_elb(
                    domain_info["otc_elb"], target_domain, local_cert_path, local_key_path, results["global_config"]
                )
                domain_result["deployment_results"].extend(elb_results)

            # Categorize the domain's overall outcome
            all_deployments_successful = all(res["success"] for res in domain_result["deployment_results"])

            if domain_result["issue_error"] is None and all_deployments_successful:
                results["successful_renewals"].append(target_domain)
            else:
                results["failed_renewals"].append(domain_result)
        else: # Issuance failed, no deployment attempted
            results["failed_renewals"].append(domain_result)

    else:
        log.info(f"Certificate for {target_domain} is not yet due for renewal. Skipping.")
        results["skipped_renewals"].append(target_domain)

def main():
    parser = argparse.ArgumentParser(description="Automated SSL certificate renewal and deployment script.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the renewal and deployment process without making any actual changes."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force the renewal of certificates even if they are not yet due."
    )
    args = parser.parse_args()

    # Generate a timestamp for unique log and report file names
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Load environment variables after logging setup
    load_dotenv() 

    # Dynamically determine log file path
    default_log_file = os.path.join("logs", f"renewal_{timestamp}.log")
    final_log_file_path = os.getenv("LOG_FILE_PATH") or default_log_file
    
    try:
        setup_logging(final_log_file_path) # Call setup_logging with the determined path
    except Exception as e:
        print(f"CRITICAL: Failed to initialize logging: {e}")
        sys.exit(1)

    log = logging.getLogger(__name__) # Re-get the logger after setup

    results = {
        "start_time": datetime.now(),
        "end_time": None,
        "duration": None,
        "total_domains_configured": 0,
        "domains_processed": 0,
        "successful_renewals": [],
        "skipped_renewals": [],
        "failed_renewals": [],
        "dry_run": args.dry_run,
        "force_renewal": args.force
    }

    # Secure base paths by defaulting to current workdir subfolders rather than /tmp
    default_acme_home = os.path.join(os.getcwd(), ".acme_home")
    default_cert_base = os.path.join(os.getcwd(), ".certs")

    results["global_config"] = {
        "renewal_threshold_days": int(os.getenv("RENEWAL_THRESHOLD_DAYS", "30")),
        "acme_email": os.getenv("ACME_EMAIL"),
        "acme_home_dir": os.getenv("ACME_HOME_DIR") or default_acme_home,
        "ionos_api_key": os.getenv("IONOS_API_KEY"),
        "ionos_api_secret": os.getenv("IONOS_API_SECRET"),
        "cert_base_path": os.getenv("CERT_BASE_PATH") or default_cert_base,
        "report_file_path": os.getenv("REPORT_FILE_PATH") or os.path.join("reports", f"renewal_report_{timestamp}.md"),
        "log_file_path": final_log_file_path,
        "dry_run": args.dry_run,
        "force_renewal": args.force
    }
    
    if results["global_config"]["dry_run"]:
        log.info("--- Performing a DRY RUN. No actual changes will be made. ---")
    if results["global_config"]["force_renewal"]:
        log.info("--- FORCE RENEWAL active. Certificates will be renewed regardless of expiry. ---")

    if not all([results["global_config"]['acme_email'], results["global_config"]['ionos_api_key'], results["global_config"]['ionos_api_secret']]):
        log.error("Missing critical environment variables: ACME_EMAIL, IONOS_API_KEY, IONOS_API_SECRET. Aborting.")
        sys.exit(1)

    log.info("Starting SSL certificate renewal process...")

    domains_config = load_yaml_config("config/domains.yaml")
    servers_config = load_yaml_config("config/servers.yaml")

    if not domains_config or not servers_config:
        log.error("Could not load domains.yaml or servers.yaml. Aborting process.")
        sys.exit(1)

    results["total_domains_configured"] = len(domains_config.get("domains", []))

    servers_map = {s['name']: s for s in servers_config.get("servers", [])}

    for domain_info in domains_config.get("domains", []):
        process_domain(domain_info, servers_map, results)

    results["end_time"] = datetime.now()
    time_taken = results["end_time"] - results["start_time"]
    minutes, seconds = divmod(time_taken.total_seconds(), 60)
    hours, minutes = divmod(minutes, 60)
    results["duration"] = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"

    log.info("All domains processed. Script finished.")

    markdown_report_content = generate_markdown_report(results)
    report_file_path = results["global_config"]["report_file_path"]

    try:
        # Ensure report directory exists
        os.makedirs(os.path.dirname(report_file_path), exist_ok=True)
        with open(report_file_path, 'w') as f:
            f.write(markdown_report_content)
        log.info(f"Renewal report saved to: {report_file_path}")
    except IOError as e:
        log.error(f"Failed to write renewal report to {report_file_path}: {e}")

    # Final status check for CI
    if results["failed_renewals"]:
        log.error(f"Process finished with {len(results['failed_renewals'])} failures.")
        sys.exit(1)
    
    sys.exit(0)

if __name__ == "__main__":
    main()
