import pytest
from unittest.mock import MagicMock, patch

from cert_automation.remote_deployer import RemoteDeployer

@pytest.fixture
def mock_paramiko():
    """Fixture to mock the entire paramiko library."""
    with patch('cert_automation.remote_deployer.paramiko') as mock_paramiko_lib:
        yield mock_paramiko_lib

@pytest.fixture
def deployer(mock_paramiko):
    """Fixture to create a RemoteDeployer instance with a mocked paramiko."""
    # We can initialize with dummy data as paramiko is mocked
    return RemoteDeployer(host="test.host", user="testuser", ssh_key_path="/path/to/key")

def test_connect_success(deployer, mock_paramiko):
    """Test successful SSH connection."""
    # _connect is implicitly called by other methods, but we can test it directly
    # for clarity, although it's decorated. Let's test a method that uses it.
    
    # Mock the return values of the client
    mock_ssh_client = mock_paramiko.SSHClient.return_value
    mock_transport = mock_ssh_client.get_transport.return_value
    mock_transport.is_active.return_value = False # Force a new connection attempt

    # Call a method that requires connection
    deployer.close() # To ensure we are not already connected from a previous test
    assert deployer._connect() is True
    
    mock_ssh_client.connect.assert_called_once_with(
        hostname="test.host",
        username="testuser",
        key_filename="/path/to/key",
        timeout=10
    )
    mock_ssh_client.open_sftp.assert_called_once()

def test_upload_file_success(deployer, mock_paramiko):
    """Test successful file upload."""
    mock_sftp_client = mock_paramiko.SSHClient.return_value.open_sftp.return_value
    
    deployer.upload_file("local/path", "remote/path")
    
    mock_sftp_client.put.assert_called_once_with("local/path", "remote/path")

def test_execute_command_success(deployer, mock_paramiko):
    """Test successful command execution."""
    mock_ssh_client = mock_paramiko.SSHClient.return_value
    mock_ssh_client.exec_command.return_value = (None, MagicMock(read=lambda: b'Success'), MagicMock(read=lambda: b''))
    mock_ssh_client.exec_command.return_value[1].channel.recv_exit_status.return_value = 0 # Exit code 0

    stdout = deployer.execute_command("echo 'hello'")
    
    assert stdout == "Success"
    mock_ssh_client.exec_command.assert_called_once_with("echo 'hello'")

def test_execute_command_failure_exit_code(deployer, mock_paramiko):
    """Test command execution that fails with a non-zero exit code."""
    mock_ssh_client = mock_paramiko.SSHClient.return_value
    mock_ssh_client.exec_command.return_value = (None, MagicMock(read=lambda: b''), MagicMock(read=lambda: b'Error message'))
    mock_ssh_client.exec_command.return_value[1].channel.recv_exit_status.return_value = 1 # Non-zero exit code

    with pytest.raises(Exception, match="failed with exit code 1"):
        deployer.execute_command("failing_command")

def test_validate_nginx_config_success(deployer, mocker):
    """Test successful nginx config validation."""
    # Mock the execute_command method of the deployer instance
    mocker.patch.object(deployer, 'execute_command', return_value="nginx: test is successful")
    
    assert deployer.validate_nginx_config() is True
    deployer.execute_command.assert_called_once_with("sudo nginx -t")

def test_validate_nginx_config_failure(deployer, mocker):
    """Test failed nginx config validation."""
    mocker.patch.object(deployer, 'execute_command', return_value="nginx: [emerg] invalid directive")
    
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
