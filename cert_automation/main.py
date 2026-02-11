import os
import logging
from dotenv import load_dotenv
import socket
import ipaddress
import argparse
from datetime import datetime
from typing import Tuple

from cert_manager import is_certificate_due_for_renewal
from acme_client_wrapper import issue_certificate
from config_loader import load_yaml_config
from remote_deployer import RemoteDeployer
from health_checker import HealthChecker
from logger import setup_logging
from report_generator import generate_markdown_report

# Set up centralized logging at the very beginning
setup_logging()
log = logging.getLogger(__name__)

load_dotenv() # Load environment variables from .env file

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

def deploy_certificate(server_config: dict, domain_name: str, local_cert_path: str, local_key_path: str, dry_run: bool = False) -> Tuple[bool, str]:
    """
    Deploys the new certificate to a single server with a robust, atomic process.
    Returns (True, "Success message") or (False, "Error message").
    """
    host = server_config.get("host")
    user = server_config.get("user")
    ssh_key = server_config.get("ssh_key_path")
    remote_cert_path = server_config.get("cert_path")
    reload_command = server_config.get("nginx_reload_command")
    server_name = server_config.get("name", host) # Use name if available, else host

    if not all([host, user, ssh_key, remote_cert_path, reload_command]):
        error_msg = f"Server config for '{server_name}' is incomplete. Skipping deployment."
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
        except Exception as e:
            log.warning(f"Backup on {server_name} failed (might be first deploy, or certs missing): {e}")
        
        # 2. Upload new certificates
        deployer.upload_file(local_cert_path, remote_fullchain_path) # Now raises exception on failure
        deployer.upload_file(local_key_path, remote_key_path) # Now raises exception on failure

        # 3. Validate Nginx config with new certs
        deployer.validate_nginx_config() # Now raises exception on failure

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
            deployer.execute_command(f"sudo rm {backup_fullchain_path} {backup_key_path}")
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
    
    if not target_domain:
        log.warning("Skipping domain entry with no 'domain' field.")
        results["domains_processed"] += 1 # Still count as processed, even if invalid
        results["failed_renewals"].append({"domain": "N/A", "error": "Domain entry missing 'domain' field."})
        return
    
    results["domains_processed"] += 1
    log.info(f"--- Processing domain: {target_domain} ---")
    
    local_cert_dir = os.path.join(results["global_config"]['cert_base_path'], target_domain)
    local_cert_path = os.path.join(local_cert_dir, "fullchain.cer")
    local_key_path = os.path.join(local_cert_dir, "domain.key")

    ip_type = get_domain_ip_type(target_domain)
    domain_to_issue = target_domain
    
    if ip_type == "private":
        domain_to_issue = get_wildcard_domain(target_domain)
    
    if is_certificate_due_for_renewal(local_cert_path, results["global_config"]['renewal_threshold_days']) or dry_run:
        if dry_run and not is_certificate_due_for_renewal(local_cert_path, results["global_config"]['renewal_threshold_days']):
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
                email=results["global_config"]['acme_email'],
                cert_storage_path=local_cert_dir,
                dry_run=dry_run
            )
            log.info(f"Certificate issuance for {domain_to_issue} successful.")
            issuance_successful = True

        except Exception as e:
            domain_result["issue_error"] = str(e)
            log.error(f"An error occurred during certificate issuance for {domain_to_issue}: {e}")
        
        if issuance_successful:
            # Deployment to servers
            servers_for_domain = domain_info.get("servers", [])
            
            if not servers_for_domain:
                log.warning(f"No servers configured for domain {target_domain}. Certificate issued but no deployment targets.")
                domain_result["deployment_results"].append({"server": "N/A", "success": True, "message": "No deployment targets configured."})
            else:
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
            
            # Categorize the domain's overall outcome for deployment
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
    args = parser.parse_args()

    results = {
        "start_time": datetime.now(),
        "end_time": None,
        "duration": None,
        "total_domains_configured": 0,
        "domains_processed": 0,
        "successful_renewals": [],
        "skipped_renewals": [],
        "failed_renewals": [],
        "dry_run": args.dry_run
    }

    results["global_config"] = {
        "renewal_threshold_days": int(os.getenv("RENEWAL_THRESHOLD_DAYS", "30")),
        "acme_email": os.getenv("ACME_EMAIL"),
        "acme_home_dir": os.getenv("ACME_HOME_DIR", "/tmp/acme_home"),
        "ionos_api_key": os.getenv("IONOS_API_KEY"),
        "cert_base_path": os.getenv("CERT_BASE_PATH", "/tmp/certs"),
        "report_file_path": os.getenv("REPORT_FILE_PATH", "renewal_report.md"), # New report file path
    }
    # Add dry_run from args to global_config for easier access in report_generator
    results["global_config"]["dry_run"] = args.dry_run

    if results["global_config"]["dry_run"]:
        log.info("--- Performing a DRY RUN. No actual changes will be made. ---")

    if not all([results["global_config"]['acme_email'], results["global_config"]['ionos_api_key']]):
        log.error("Missing critical environment variables: ACME_EMAIL, IONOS_API_KEY. Aborting.")
        return

    log.info("Starting scalable SSL certificate renewal process...")

    domains_config = load_yaml_config("config/domains.yaml")
    servers_config = load_yaml_config("config/servers.yaml")

    if not domains_config or not servers_config:
        log.error("Could not load domains.yaml or servers.yaml. Aborting process.")
        return
    
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
        with open(report_file_path, 'w') as f:
            f.write(markdown_report_content)
        log.info(f"Renewal report saved to: {report_file_path}")
    except IOError as e:
        log.error(f"Failed to write renewal report to {report_file_path}: {e}")
    
if __name__ == "__main__":
    main()