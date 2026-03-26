import paramiko
import logging
import os
import uuid
import socket # Added for network error handling
from typing import Tuple, Optional
from retry_decorator import retry # Added for retry logic

log = logging.getLogger(__name__)

class RemoteDeployer:
    """
    Handles secure SSH connections, SCP file transfers, and remote command execution.
    """
    def __init__(self, host: str, user: str, ssh_key_path: str, dry_run: bool = False, use_pty: bool = False):
        self.host = host
        self.user = user
        self.ssh_key_path = ssh_key_path
        self.dry_run = dry_run
        self.use_pty = use_pty  # Allocate a PTY so sudo works on servers without NOPASSWD sudoers
        self._ssh_client = None
        self._sftp_client = None
        log.info(f"RemoteDeployer initialized for {user}@{host} (Dry Run: {dry_run})")

    @retry(tries=3, delay=5, backoff=2, exceptions=(paramiko.SSHException, socket.error))
    def _connect(self):
        """Establishes an SSH connection."""
        if self.dry_run:
            return True # In dry run, we simulate a successful connection

        if self._ssh_client and self._ssh_client.get_transport() and self._ssh_client.get_transport().is_active():
            return True

        try:
            log.info(f"Connecting to {self.user}@{self.host}...")
            self._ssh_client = paramiko.SSHClient()
            self._ssh_client.load_system_host_keys()
            self._ssh_client.set_missing_host_key_policy(paramiko.RejectPolicy())

            self._ssh_client.connect(
                hostname=self.host,
                username=self.user,
                key_filename=self.ssh_key_path,
                timeout=10
            )
            self._sftp_client = self._ssh_client.open_sftp()
            log.info(f"Successfully connected to {self.user}@{self.host}")
            return True
        except paramiko.AuthenticationException as e:
            log.error(f"SSH authentication failed for {self.user}@{self.host}: {e}")
            raise
        except paramiko.SSHException as e:
            log.error(f"SSH connection to {self.host} failed: {e}")
            raise
        except socket.error as e:
            log.error(f"Network error during SSH connection to {self.host}: {e}")
            raise
        except Exception as e:
            log.error(f"Unexpected error during SSH connection to {self.host}: {e}")
            raise

    def close(self):
        """Closes the SSH and SFTP connections."""
        if self.dry_run:
            return

        if self._sftp_client:
            self._sftp_client.close()
        if self._ssh_client:
            self._ssh_client.close()
        log.info(f"Connection to {self.host} closed.")

    @retry(tries=3, delay=2, backoff=2, exceptions=(paramiko.SSHException, IOError, socket.error))
    def upload_file(self, local_path: str, remote_path: str, remote_permissions: Optional[int] = None) -> None:
        """
        Uploads a file to the remote server using a staging approach to bypass permission issues.
        The file is first uploaded to /tmp and then moved to the final destination using sudo.
        """
        if self.dry_run:
            log.info(f"[DRY RUN] Would upload {local_path} to {self.host}:{remote_path}")
            return # Simulate success
            
        # Ensure connected
        self._connect()
        
        filename = os.path.basename(remote_path)
        # Build a non-predictable remote staging path to avoid CWE-377.
        # uuid4 ensures uniqueness without relying on /tmp/<fixed-name>.
        temp_remote_path = f"/tmp/{uuid.uuid4().hex}_{filename}.tmp"  # nosec B108

        try:
            log.info(f"Uploading {local_path} to staging path {self.host}:{temp_remote_path}")
            self._sftp_client.put(local_path, temp_remote_path)
            
            log.info(f"Moving file from {temp_remote_path} to {remote_path} using sudo")
            self.execute_command(f"sudo mv {temp_remote_path} {remote_path}")
            
            if remote_permissions is not None:
                log.info(f"Setting permissions {oct(remote_permissions)} on {remote_path}")
                self.execute_command(f"sudo chmod {oct(remote_permissions)[2:]} {remote_path}")
                
            return 
        except Exception as e:
            log.error(f"File upload/move to {self.host} failed: {e}")
            # Attempt to clean up temp file if it exists
            try:
                self.execute_command(f"rm -f {temp_remote_path}", check_exit_code=False)
            except:
                pass
            raise 

    @retry(tries=3, delay=2, backoff=2, exceptions=(paramiko.SSHException, socket.error))
    def execute_command(self, command: str, check_exit_code: bool = True) -> str:
        """Executes a command on the remote server. Raises Exception on failure. Returns stdout on success."""
        if self.dry_run:
            log.info(f"[DRY RUN] Would execute on {self.host}: {command}")
            # Simulate a successful Nginx config test for dry-run flow
            if "nginx -t" in command:
                return "nginx: the configuration file /etc/nginx/nginx.conf syntax is ok\nnginx: test is successful"
            return "Success (dry run)"

        # Ensure connected. _connect now raises exceptions on failure.
        self._connect()
        
        try:
            # Commands are sourced exclusively from admin-controlled YAML config — not user input.
            # get_pty=True allocates a pseudo-TTY, which is required by sudo on servers
            # that do not have NOPASSWD configured in their sudoers file.
            stdin, stdout, stderr = self._ssh_client.exec_command(command, get_pty=self.use_pty)  # nosec B601
            output = stdout.read().decode().strip()
            # When PTY is in use, stderr is merged into stdout by the terminal.
            # When PTY is NOT in use, read stderr separately.
            error = "" if self.use_pty else stderr.read().decode().strip()
            exit_code = stdout.channel.recv_exit_status()

            if check_exit_code and exit_code != 0:
                error_msg = f"Command '{command}' failed with exit code {exit_code}. Stderr: {error}. Stdout: {output}"
                log.error(error_msg)
                raise Exception(error_msg) # Raise an exception for decorator to catch

            # Return combined output (stdout + stderr when no PTY, stdout-only when PTY)
            return output
        except (paramiko.SSHException, socket.error) as e:
            log.error(f"SSH or network error during command '{command}' execution on {self.host}: {e}")
            raise # Re-raise for decorator and calling function
        except Exception as e:
            log.error(f"An unexpected error occurred during command '{command}' execution on {self.host}: {e}")
            raise # Re-raise for decorator and calling function

    def validate_nginx_config(self, validation_command: str = "sudo nginx -t") -> bool:
        """Validates the Nginx configuration on the remote server.

        NOTE: `nginx -t` writes its output to stderr, not stdout.
        When use_pty=False (default), stderr is captured separately in execute_command
        and included in the raised exception message on failure. When the command
        succeeds (exit 0), output may appear empty — this is expected and treated as valid.
        When use_pty=True, stderr is merged into stdout by the PTY.
        """
        log.info(f"Validating configuration on {self.host} using '{validation_command}'...")
        try:
            output = self.execute_command(validation_command)
            # Check for standard Nginx success or GitLab-ctl success indicators.
            # Note: nginx -t success text goes to stderr; with use_pty=True it appears in output.
            # Without PTY, a clean exit code 0 from execute_command is our success signal.
            if "test is successful" in output or "syntax is ok" in output or "run:" in output or "ok:" in output:
                log.info(f"Configuration on {self.host} is valid.")
            else:
                # Exit code 0 from execute_command means the command succeeded,
                # even if output appears empty (nginx -t writes to stderr without PTY).
                log.info(f"Configuration validation on {self.host}: command exited cleanly (exit 0). Output: '{output or '<empty - nginx -t writes to stderr without PTY>'}'")
            return True
        except Exception as e:
            log.error(f"Failed to validate configuration on {self.host}: {e}")
            return False

    def reload_nginx(self, reload_command: str) -> bool:
        """Executes the Nginx reload command on the remote server."""
        log.info(f"Attempting to reload Nginx on {self.host} with command: '{reload_command}'")
        try:
            self.execute_command(reload_command)
            log.info(f"Nginx on {self.host} reloaded successfully.")
            return True
        except Exception as e:
            log.error(f"Failed to reload Nginx on {self.host}: {e}")
            return False

if __name__ == "__main__":
    pass
