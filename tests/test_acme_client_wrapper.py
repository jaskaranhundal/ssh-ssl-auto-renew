import pytest
import subprocess
from unittest.mock import MagicMock, patch

from cert_automation.acme_client_wrapper import _check_acme_sh_installed, run_acme_command, issue_certificate, _run_acme_command_retriable

# We don't want tests to actually run retry delays
@pytest.fixture(autouse=True)
def no_sleep(mocker):
    """Fixture to patch time.sleep to do nothing."""
    mocker.patch('time.sleep')

# --- Tests for _check_acme_sh_installed ---
def test_check_acme_sh_installed_success(mocker):
    """Test that _check_acme_sh_installed returns True when acme.sh is found."""
    mocker.patch('subprocess.run', return_value=MagicMock())
    assert _check_acme_sh_installed() is True

def test_check_acme_sh_installed_failure(mocker):
    """Test that _check_acme_sh_installed returns False when acme.sh is not found."""
    mocker.patch('subprocess.run', side_effect=FileNotFoundError("acme.sh not found"))
    assert _check_acme_sh_installed() is False

def test_check_acme_sh_installed_dry_run_mocking(mocker):
    """Test that in dry_run mode, it returns True even if acme.sh is not found."""
    mocker.patch('subprocess.run', side_effect=FileNotFoundError("acme.sh not found"))
    # In dry_run mode, it should simulate success and log a warning
    assert _check_acme_sh_installed(dry_run=True) is True


# --- Tests for _run_acme_command_retriable ---
def test_run_acme_command_retriable_success(mocker):
    """Test that the retriable helper returns stdout on success."""
    mock_run = mocker.patch('subprocess.run', return_value=MagicMock(stdout="Success!"))
    result = _run_acme_command_retriable(["--test"], {})
    assert result == "Success!"
    mock_run.assert_called_once()

def test_run_acme_command_retriable_failure_retries(mocker):
    """Test that the retriable helper retries on CalledProcessError."""
    # It should fail 3 times, then succeed on the 4th attempt
    side_effects = [
        subprocess.CalledProcessError(1, "cmd", stderr="Fail 1"),
        subprocess.CalledProcessError(1, "cmd", stderr="Fail 2"),
        subprocess.CalledProcessError(1, "cmd", stderr="Fail 3"),
        MagicMock(stdout="Final Success")
    ]
    mock_run = mocker.patch('subprocess.run', side_effect=side_effects)
    
    # The decorator is set to 5 tries in the source file
    result = _run_acme_command_retriable(["--test"], {})
    assert result == "Final Success"
    assert mock_run.call_count == 4


# --- Tests for issue_certificate ---
def test_issue_certificate_success(mocker):
    """Test the full issue_certificate flow on success."""
    # Mock both run_acme_command calls (register and issue) to simulate success
    mock_run_acme = mocker.patch('cert_automation.acme_client_wrapper.run_acme_command', return_value="Mocked success")
    
    issue_certificate(
        domain="test.com",
        acme_home_dir="/tmp",
        ionos_api_key="test_key",
        email="test@test.com",
        cert_storage_path="/tmp/certs"
    )
    
    assert mock_run_acme.call_count == 2 # Called for register and issue
    
    # Check that the issue command was called with the right arguments
    issue_call_args = mock_run_acme.call_args_list[1]
    command_args = issue_call_args[0][0]
    assert "--issue" in command_args
    assert "-d" in command_args
    assert "test.com" in command_args

def test_issue_certificate_registration_fails(mocker):
    """Test that issue_certificate raises an exception if account registration fails."""
    # Make the first call (register) fail, and the second (issue) succeed
    side_effects = [
        FileNotFoundError("acme.sh not found on registration"), # This will be wrapped
        "Mocked success for issue"
    ]
    mocker.patch('cert_automation.acme_client_wrapper.run_acme_command', side_effect=side_effects)

    with pytest.raises(Exception, match="ACME account registration failed"):
        issue_certificate(
            domain="test.com",
            acme_home_dir="/tmp",
            ionos_api_key="test_key",
            email="test@test.com",
            cert_storage_path="/tmp/certs"
        )

def test_issue_certificate_issuance_fails(mocker):
    """Test that issue_certificate raises an exception if the issue command fails."""
    # Make the first call (register) succeed, and the second (issue) fail
    side_effects = [
        "Mocked success for register",
        subprocess.CalledProcessError(1, "cmd", stderr="Invalid response from ACME server")
    ]
    mocker.patch('cert_automation.acme_client_wrapper.run_acme_command', side_effect=side_effects)

    with pytest.raises(Exception, match="acme.sh certificate issuance failed"):
        issue_certificate(
            domain="test.com",
            acme_home_dir="/tmp",
            ionos_api_key="test_key",
            email="test@test.com",
            cert_storage_path="/tmp/certs"
        )
