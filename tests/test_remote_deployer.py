import pytest
import socket
import paramiko
from unittest.mock import MagicMock, patch

from cert_automation.remote_deployer import RemoteDeployer

# Define custom exception classes for mocking to avoid "catching classes that do not inherit from BaseException"
class MockSSHException(Exception): pass
class MockSocketError(Exception): pass

@pytest.fixture
def mock_paramiko():
    """Fixture to mock the entire paramiko library."""
    with patch('cert_automation.remote_deployer.paramiko') as mock_paramiko_lib:
        # Make the mocked SSHException an actual exception class
        mock_paramiko_lib.SSHException = MockSSHException
        yield mock_paramiko_lib

@pytest.fixture
def mock_socket():
    """Fixture to mock the socket library."""
    with patch('cert_automation.remote_deployer.socket') as mock_socket_lib:
        # Make the mocked error an actual exception class
        mock_socket_lib.error = MockSocketError
        yield mock_socket_lib

@pytest.fixture
def deployer(mock_paramiko, mock_socket):
    """Fixture to create a RemoteDeployer instance with a mocked paramiko and socket."""
    return RemoteDeployer(host="test.host", user="testuser", ssh_key_path="/path/to/key")

def test_connect_success(deployer, mock_paramiko):
    """Test successful SSH connection."""
    mock_ssh_client = mock_paramiko.SSHClient.return_value
    mock_transport = mock_ssh_client.get_transport.return_value
    mock_transport.is_active.return_value = False # Force a new connection attempt

    deployer.close() 
    assert deployer._connect() is True
    
    mock_ssh_client.connect.assert_called_once_with(
        hostname="test.host",
        username="testuser",
        key_filename="/path/to/key",
        timeout=10
    )
    mock_ssh_client.open_sftp.assert_called_once()

def test_upload_file_success(deployer, mock_paramiko):
    """Test successful file upload using the staging approach."""
    mock_ssh_client = mock_paramiko.SSHClient.return_value
    mock_sftp_client = mock_ssh_client.open_sftp.return_value
    
    # Mock exec_command to return 3 values (stdin, stdout, stderr)
    mock_stdout = MagicMock()
    mock_stdout.read.return_value = b"Success"
    mock_stdout.channel.recv_exit_status.return_value = 0
    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""
    mock_ssh_client.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)
    
    deployer.upload_file("local/path", "remote/path")
    
    # The staging path is now uuid-based so we can't assert the exact string —
    # capture the actual call and verify the path pattern instead.
    put_call_args = mock_sftp_client.put.call_args
    assert put_call_args is not None, "sftp.put was never called"
    actual_local, actual_temp_path = put_call_args[0]
    assert actual_local == "local/path"
    assert actual_temp_path.startswith("/tmp/")
    assert actual_temp_path.endswith("_path.tmp")
    # Check that the move command was called with the same temp path
    mock_ssh_client.exec_command.assert_any_call(f"sudo mv {actual_temp_path} remote/path")

def test_execute_command_success(deployer, mock_paramiko):
    """Test successful command execution."""
    mock_ssh_client = mock_paramiko.SSHClient.return_value
    mock_stdout = MagicMock()
    mock_stdout.read.return_value = b"Success"
    mock_stdout.channel.recv_exit_status.return_value = 0
    mock_ssh_client.exec_command.return_value = (None, mock_stdout, MagicMock(read=lambda: b''))

    stdout = deployer.execute_command("echo 'hello'")
    
    assert stdout == "Success"
    mock_ssh_client.exec_command.assert_called_with("echo 'hello'")

def test_execute_command_failure_exit_code(deployer, mock_paramiko):
    """Test command execution that fails with a non-zero exit code."""
    mock_ssh_client = mock_paramiko.SSHClient.return_value
    mock_stdout = MagicMock()
    mock_stdout.read.return_value = b""
    mock_stdout.channel.recv_exit_status.return_value = 1
    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b"Error message"
    mock_ssh_client.exec_command.return_value = (None, mock_stdout, mock_stderr)

    with pytest.raises(Exception, match="failed with exit code 1"):
        deployer.execute_command("failing_command")

def test_validate_nginx_config_success(deployer, mocker):
    """Test successful nginx config validation."""
    mocker.patch.object(deployer, 'execute_command', return_value="nginx: test is successful")
    
    assert deployer.validate_nginx_config() is True
    deployer.execute_command.assert_called_once_with("sudo nginx -t")

def test_validate_nginx_config_failure(deployer, mocker):
    """Test failed nginx config validation."""
    # To test failure, we need execute_command to raise an exception or the logic to find no success keywords
    # If the command itself fails (exit code != 0), execute_command will raise an exception.
    mocker.patch.object(deployer, 'execute_command', side_effect=Exception("Validation failed"))
    
    assert deployer.validate_nginx_config() is False

def test_reload_nginx_success(deployer, mocker):
    """Test successful nginx reload."""
    mocker.patch.object(deployer, 'execute_command')
    
    assert deployer.reload_nginx("sudo systemctl reload nginx") is True
    deployer.execute_command.assert_called_once_with("sudo systemctl reload nginx")

def test_dry_run_does_not_connect(mock_paramiko):
    """Test that in dry_run mode, no actual SSH connection is made."""
    dry_run_deployer = RemoteDeployer(host="test.host", user="testuser", ssh_key_path="/path/to/key", dry_run=True)
    
    dry_run_deployer.execute_command("any command")
    
    mock_paramiko.SSHClient.return_value.connect.assert_not_called()
