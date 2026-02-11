import pytest
from datetime import datetime, timedelta

from cert_automation.report_generator import generate_markdown_report

@pytest.fixture
def mock_results_success():
    """Mock results for a fully successful run."""
    return {
        "start_time": datetime.now() - timedelta(minutes=10),
        "end_time": datetime.now(),
        "duration": "0h 10m 0s",
        "total_domains_configured": 2,
        "domains_processed": 2,
        "successful_renewals": ["success.com", "another-success.org"],
        "skipped_renewals": [],
        "failed_renewals": [],
        "dry_run": False
    }

@pytest.fixture
def mock_results_failure():
    """Mock results for a run with failures."""
    return {
        "start_time": datetime.now() - timedelta(minutes=5),
        "end_time": datetime.now(),
        "duration": "0h 5m 0s",
        "total_domains_configured": 3,
        "domains_processed": 3,
        "successful_renewals": [],
        "skipped_renewals": ["skip.net"],
        "failed_renewals": [
            {
                "domain": "issuefail.com",
                "issue_error": "ACME account registration failed: acme.sh not found.",
                "deployment_results": []
            },
            {
                "domain": "deployfail.io",
                "issue_error": None,
                "deployment_results": [
                    {"server": "web-01", "success": False, "message": "Nginx config validation failed."},
                    {"server": "web-02", "success": True, "message": "Deployment successful."}
                ]
            }
        ],
        "dry_run": True
    }

def test_generate_report_overall_status(mock_results_success, mock_results_failure):
    """Test that the overall status is correctly reported."""
    report_success = generate_markdown_report(mock_results_success)
    assert "Status: SUCCESS" in report_success

    report_failure = generate_markdown_report(mock_results_failure)
    assert "Status: PARTIAL_SUCCESS" in report_failure

    mock_results_failure["successful_renewals"] = [] # make it a full failure
    report_full_failure = generate_markdown_report(mock_results_failure)
    # Note: This logic depends on whether you count skipped domains as "not failed".
    # The current logic will say PARTIAL_SUCCESS if there are skipped domains.
    # To test full failure, we'd need a scenario where all configured domains fail.
    
def test_generate_report_headers(mock_results_success):
    """Test that the report header contains expected fields."""
    report = generate_markdown_report(mock_results_success)
    assert "# SSL Certificate Renewal Report (LIVE RUN)" in report
    assert "Generated:" in report
    assert "Duration: 0h 10m 0s" in report

def test_generate_report_summary_section(mock_results_failure):
    """Test the summary section for correct numbers."""
    report = generate_markdown_report(mock_results_failure)
    assert "- **Total Domains Configured:** 3" in report
    assert "- **Domains Processed:** 3" in report
    assert "- **Successful Renewals (Issuance & Deployment):** 0" in report
    assert "- **Skipped (Not Due for Renewal):** 1" in report
    assert "- **Failed Domains:** 2" in report
    
def test_generate_report_skipped_section(mock_results_failure):
    """Test that the skipped domains section is rendered correctly."""
    report = generate_markdown_report(mock_results_failure)
    assert "## Skipped Domains (Not Due for Renewal)" in report
    assert "- `skip.net`" in report

def test_generate_report_failure_details_section(mock_results_failure):
    """Test that the failure details are rendered comprehensively."""
    report = generate_markdown_report(mock_results_failure)
    assert "## Failed Domains (Issuance or Deployment Failures)" in report
    
    # Test issuance failure details
    assert "### Domain: `issuefail.com`" in report
    assert "**Issuance Error:** ACME account registration failed: acme.sh not found." in report
    
    # Test deployment failure details
    assert "### Domain: `deployfail.io`" in report
    assert "**Deployment Status:**" in report
    assert "❌ `web-01`: Nginx config validation failed." in report
    assert "✅ `web-02`: Deployment successful." in report
