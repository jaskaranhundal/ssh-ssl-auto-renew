from unittest.mock import MagicMock, patch

import pytest

from cert_automation.remote_deployer import RemoteDeployer, PermanentSSHError


class MockSSHException(Exception):
    pass


@pytest.fixture
def mock_paramiko():
    with patch("cert_automation.remote_deployer.paramiko") as mp:
        mp.SSHException = MockSSHException
        mp.AuthenticationException = type("AuthErr", (Exception,), {})
        yield mp


@pytest.fixture
def deployer(mock_paramiko):
    return RemoteDeployer(host="h", user="u", ssh_key_path="/k")


def test_connect_reopens_sftp_when_none(deployer):
    """Active SSH transport but sftp went None -> _connect must reopen sftp (the NoneType.put fix)."""
    client = MagicMock()
    client.get_transport.return_value.is_active.return_value = True
    deployer._ssh_client = client
    deployer._sftp_client = None

    assert deployer._connect() is True
    assert deployer._sftp_client is client.open_sftp.return_value


def test_upload_file_raises_when_sftp_unavailable(deployer):
    """If connect leaves sftp None, upload_file must raise clearly, not AttributeError on .put()."""
    deployer._sftp_client = None
    with patch.object(deployer, "_connect", return_value=True):
        with pytest.raises(MockSSHException):
            deployer.upload_file("/local/file", "/remote/file")


def test_missing_known_hosts_is_permanent(deployer, mock_paramiko):
    """A 'not found in known_hosts' SSHException is reclassified as PermanentSSHError (fail-fast)."""
    client = mock_paramiko.SSHClient.return_value
    client.get_transport.return_value.is_active.return_value = False
    client.connect.side_effect = MockSSHException("Server '192.0.2.4' not found in known_hosts")
    deployer._ssh_client = None

    # PermanentSSHError is non_retryable -> re-raised immediately, no backoff sleep.
    with pytest.raises(PermanentSSHError):
        deployer._connect()
    assert client.connect.call_count == 1  # no wasted retries
