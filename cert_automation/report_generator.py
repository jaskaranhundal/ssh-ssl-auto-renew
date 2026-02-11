import logging
from typing import Dict, List, Any
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

def generate_markdown_report(results: Dict[str, Any]) -> str:
    """
    Generates a Markdown-formatted report based on the processing results.

    Args:
        results: A dictionary containing the summary and detailed results of the run.
                 Example structure (as modified in main.py):
                 {
                     "start_time": datetime_obj,
                     "end_time": datetime_obj,
                     "duration": str,
                     "total_domains_configured": int,
                     "domains_processed": int,
                     "successful_renewals": List[str], # Simple list of domain names
                     "skipped_renewals": List[str],     # Simple list of domain names
                     "failed_renewals": [
                         {
                             "domain": str,
                             "issue_error": str or None,
                             "deployment_results": [
                                 {"server": str, "success": bool, "message": str}
                             ]
                         }
                     ],
                     "dry_run": bool
                 }

    Returns:
        A string containing the Markdown-formatted report.
    """
    report_lines = []
    
    # Determine overall status
    overall_status = "SUCCESS"
    if results.get('failed_renewals'):
        if len(results.get('failed_renewals', [])) == results.get('total_domains_configured', 0):
            overall_status = "FAILURE"
        else:
            overall_status = "PARTIAL_SUCCESS"
    elif results.get('total_domains_configured', 0) == 0 and results.get('domains_processed', 0) == 0:
        overall_status = "NO_DOMAINS_CONFIGURED"

    # Header
    report_lines.append(f"# SSL Certificate Renewal Report ({'DRY RUN' if results.get('dry_run') else 'LIVE RUN'}) - Status: {overall_status}\n")
    report_lines.append(f"Generated: {results.get('end_time', datetime.now()).strftime('%Y-%m-%d %H:%M:%S')}\n")
    report_lines.append(f"Duration: {results.get('duration', 'N/A')}\n\n")

    # Summary
    report_lines.append("## Summary\n")
    report_lines.append(f"- **Total Domains Configured:** {results.get('total_domains_configured', 0)}\n")
    report_lines.append(f"- **Domains Processed:** {results.get('domains_processed', 0)}\n")
    report_lines.append(f"- **Successful Renewals (Issuance & Deployment):** {len(results.get('successful_renewals', []))}\n")
    report_lines.append(f"- **Skipped (Not Due for Renewal):** {len(results.get('skipped_renewals', []))}\n")
    report_lines.append(f"- **Failed Domains:** {len(results.get('failed_renewals', []))}\n\n")

    # Detailed Successes
    if results.get('successful_renewals'):
        report_lines.append("## Successful Renewals (Issuance & Deployment)\n")
        for domain in results['successful_renewals']:
            report_lines.append(f"- **`{domain}`**: Successfully issued and deployed to all target servers.\n")
        report_lines.append("\n")

    # Detailed Skipped
    if results.get('skipped_renewals'):
        report_lines.append("## Skipped Domains (Not Due for Renewal)\n")
        for domain in results['skipped_renewals']:
            report_lines.append(f"- `{domain}`\n")
        report_lines.append("\n")

    # Detailed Failures
    if results.get('failed_renewals'):
        report_lines.append("## Failed Domains (Issuance or Deployment Failures)\n")
        for failure_details in results['failed_renewals']:
            domain = failure_details.get('domain', 'Unknown')
            issue_error = failure_details.get('issue_error')
            deployment_results = failure_details.get('deployment_results', [])

            report_lines.append(f"### Domain: `{domain}`\n")

            if issue_error:
                report_lines.append(f"**Issuance Error:** {issue_error}\n\n")
            
            if deployment_results:
                report_lines.append(f"**Deployment Status:**\n")
                for deploy_res in deployment_results:
                    server_name = deploy_res.get('server', 'Unknown Server')
                    success = deploy_res.get('success', False)
                    message = deploy_res.get('message', 'No message.')
                    status_icon = "✅" if success else "❌"
                    report_lines.append(f"- {status_icon} `{server_name}`: {message}\n")
                report_lines.append("\n") # Blank line after deployment details

            report_lines.append("---\n") # Separator between failed domains
        report_lines.append("\n") # Add a blank line for spacing

    report_lines.append("---\n") # Final separator
    report_lines.append("End of Report")

    return "".join(report_lines)

if __name__ == "__main__":
    
    # Mock data for testing
    mock_results = {
        "start_time": datetime.now() - timedelta(minutes=5),
        "end_time": datetime.now(),
        "duration": "0h 5m 0s",
        "total_domains_configured": 5,
        "domains_processed": 5,
        "successful_renewals": ["success.com", "another-success.org"],
        "skipped_renewals": ["skip.net"],
        "failed_renewals": [
            {
                "domain": "issuefail.com",
                "issue_error": "acme.sh certificate issuance failed: DNS-01 challenge for _acme-challenge.issuefail.com failed: Record not found.",
                "deployment_results": []
            },
            {
                "domain": "deployfail.io",
                "issue_error": None, # Issuance was successful
                "deployment_results": [
                    {"server": "webserver-01", "success": False, "message": "Nginx configuration validation failed with new certificates. Stdout: ... Stderr: ..."},
                    {"server": "webserver-02", "success": True, "message": "Deployment to webserver-02 successful."},
                    {"server": "webserver-03", "success": False, "message": "Server 'webserver-03' not found in servers.yaml. Cannot deploy."}
                ]
            },
             {
                "domain": "partial.example.com",
                "issue_error": None,
                "deployment_results": [
                    {"server": "server-a", "success": True, "message": "Deployment to server-a successful."},
                    {"server": "server-b", "success": False, "message": "Health check failed after Nginx reload."}
                ]
            }
        ],
        "dry_run": True
    }

    report = generate_markdown_report(mock_results)
    print(report)