import paramiko
import logging
import os
import socket # Added for network error handling
from typing import Tuple, Optional
from retry_decorator import retry # Added for retry logic

log = logging.getLogger(__name__)

class RemoteDeployer:
    """
    Handles secure SSH connections, SCP file transfers, and remote command execution.
    """
    def __init__(self, host: str, user: str, ssh_key_path: str, dry_run: bool = False):
        self.host = host
        self.user = user
        self.ssh_key_path = ssh_key_path
        self.dry_run = dry_run
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
            self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            self._ssh_client.connect(
                hostname=self.host,
                username=self.user,
                key_filename=self.ssh_key_path,
                timeout=10
            )
            self._sftp_client = self._ssh_client.open_sftp()
            log.info(f"Successfully connected to {self.user}@{self.host}")
            return True
        except paramiko.SSHException as e:
            log.error(f"SSH connection to {self.host} failed: {e}")
            raise # Re-raise for decorator
        except socket.error as e:
            log.error(f"Network error during SSH connection to {self.host}: {e}")
            raise # Re-raise for decorator
        except Exception as e:
            log.error(f"An unexpected error during SSH connection to {self.host}: {e}")
            raise # Re-raise for decorator

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
        """Uploads a file to the remote server. Raises Exception on failure."""
        if self.dry_run:
            log.info(f"[DRY RUN] Would upload {local_path} to {self.host}:{remote_path}")
            return # Simulate success
            
        # Ensure connected. _connect now raises exceptions on failure.
        self._connect()
        
        try:
            log.info(f"Uploading {local_path} to {self.host}:{remote_path}")
            self._sftp_client.put(local_path, remote_path)
            if remote_permissions is not None:
                self._sftp_client.chmod(remote_path, remote_permissions)
            return # Indicate success by not raising an exception
        except (paramiko.SSHException, IOError, socket.error) as e:
            log.error(f"File upload to {self.host} failed: {e}")
            raise # Re-raise for decorator and calling function
        except Exception as e:
            log.error(f"An unexpected error during file upload to {self.host}: {e}")
            raise # Re-raise for decorator and calling function

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
            stdin, stdout, stderr = self._ssh_client.exec_command(command)
            output = stdout.read().decode().strip()
            error = stderr.read().decode().strip()
            exit_code = stdout.channel.recv_exit_status()

            if check_exit_code and exit_code != 0:
                error_msg = f"Command '{command}' failed with exit code {exit_code}. Stderr: {error}. Stdout: {output}"
                log.error(error_msg)
                raise Exception(error_msg) # Raise an exception for decorator to catch
            
            return output
        except (paramiko.SSHException, socket.error) as e:
            log.error(f"SSH or network error during command '{command}' execution on {self.host}: {e}")
            raise # Re-raise for decorator and calling function
        except Exception as e:
            log.error(f"An unexpected error occurred during command '{command}' execution on {self.host}: {e}")
            raise # Re-raise for decorator and calling function

    def validate_nginx_config(self) -> bool:
        """Validates the Nginx configuration on the remote server."""
        log.info(f"Validating Nginx configuration on {self.host}...")
        try:
            output = self.execute_command("sudo nginx -t")
            if "test is successful" in output: # Nginx -t often prints to stderr, but subprocess.run captures it.
                log.info(f"Nginx configuration on {self.host} is valid.")
                return True
            else:
                log.error(f"Nginx configuration on {self.host} is INVALID. Output:\n{output}")
                return False
        except Exception as e:
            log.error(f"Failed to validate Nginx configuration on {self.host}: {e}")
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
