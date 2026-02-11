import subprocess
import os
import logging
from typing import Dict, Optional, List, Tuple
from retry_decorator import retry

log = logging.getLogger(__name__)

_acme_sh_actual_installed = False # Global flag to remember actual acme.sh status

def _check_acme_sh_installed(dry_run: bool = False) -> bool:
    """Checks if acme.sh is installed and executable.
    In dry_run mode, if not found, it logs a warning but returns True to allow simulation."""
    global _acme_sh_actual_installed
    try:
        subprocess.run(["acme.sh", "--version"], check=True, capture_output=True)
        _acme_sh_actual_installed = True
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        if dry_run:
            log.warning("acme.sh not found, but dry_run is active. Simulating acme.sh's presence.")
            _acme_sh_actual_installed = False # Still not actually installed
            return True # Allow dry-run to proceed
        else:
            log.error("acme.sh is not installed or not in PATH. Please install it first.")
            _acme_sh_actual_installed = False
            return False

@retry(tries=5, delay=2, backoff=2, exceptions=(subprocess.CalledProcessError,))
def _run_acme_command_retriable(cmd: List[str], full_env: Dict[str, str]) -> str:
    """Internal helper for run_acme_command that can be retried."""
    result = subprocess.run(cmd, env=full_env, check=True, capture_output=True, text=True)
    return result.stdout.strip()

def run_acme_command(command_args: List[str], env_vars: Optional[Dict[str, str]] = None, dry_run: bool = False) -> str:
    """
    Runs an acme.sh command with specified arguments and environment variables.
    If in dry_run mode and acme.sh is not actually installed, it simulates success.

    Args:
        command_args: List of arguments for the acme.sh command.
        env_vars: Dictionary of environment variables to set for the command.
        dry_run: If True, simulates the command by adding --staging.

    Returns:
        The stdout of the command if successful.

    Raises:
        FileNotFoundError: If acme.sh command is not found and not in dry_run.
        subprocess.CalledProcessError: If the acme.sh command exits with a non-zero code.
        Exception: For any other unexpected errors.
    """
    # Check if acme.sh is installed (or being mocked for dry_run)
    if not _check_acme_sh_installed(dry_run=dry_run):
        # This branch is only taken if not dry_run and acme.sh is truly missing
        raise FileNotFoundError("acme.sh is not installed or not in PATH.")

    # If it's a dry run and acme.sh was NOT actually found, simulate success
    if dry_run and not _acme_sh_actual_installed:
        log.warning(f"[DRY RUN] Simulating successful acme.sh command: {' '.join(command_args)}")
        return f"Mocked acme.sh dry run success for: {' '.join(command_args)}"

    full_env = os.environ.copy()
    if env_vars:
        full_env.update(env_vars)

    cmd = ["acme.sh"] + command_args
    
    if dry_run:
        cmd.append("--staging")
        log.info(f"[DRY RUN] Executing acme.sh command with staging flag: {' '.join(cmd)}")
    else:
        log.info(f"Running acme.sh command: {' '.join(cmd)}")

    try:
        stdout = _run_acme_command_retriable(cmd, full_env)
        log.info(f"acme.sh stdout:\n{stdout}")
        return stdout
    except subprocess.CalledProcessError as e:
        error_msg = f"acme.sh command failed with exit code {e.returncode}. " \
                    f"Stdout: {e.stdout.strip()}. Stderr: {e.stderr.strip()}"
        log.error(error_msg)
        raise # Re-raise the exception after logging
    except FileNotFoundError: # This will catch the specific error if _acme_sh_actual_installed is False after check
        error_msg = "acme.sh command not found. Ensure it's in your PATH."
        log.error(error_msg)
        raise # Re-raise
    except Exception as e:
        error_msg = f"An unexpected error occurred while running acme.sh: {e}"
        log.error(error_msg)
        raise # Re-raise

def register_acme_account(email: str, acme_home_dir: str, dry_run: bool = False) -> None:
    """Registers an ACME account with acme.sh."""
    log.info(f"Registering ACME account with email: {email}")
    # run_acme_command now raises exceptions directly
    run_acme_command(
        ["--register-account", "-m", email, "--home", acme_home_dir],
        dry_run=dry_run
    )
    # No need to check success, exception will be raised on failure

def issue_certificate(
    domain: str,
    acme_home_dir: str,
    ionos_api_key: str,
    email: str,
    cert_storage_path: str,
    dry_run: bool = False,
    key_length: str = "2048"
) -> None:
    """
    Issues a new SSL certificate for the given domain using acme.sh and IONOS DNS-01 challenge.
    Raises an Exception with detailed error message on failure.
    """
    log.info(f"Attempting to issue certificate for domain: {domain}")

    try:
        # register_acme_account now raises Exception on failure
        register_acme_account(email, acme_home_dir, dry_run=dry_run)
    except Exception as e:
        raise Exception(f"ACME account registration failed: {e}")

    if not dry_run:
        os.makedirs(cert_storage_path, exist_ok=True)

    env_vars = {"IONOS_TOKEN": ionos_api_key}

    command_args = [
        "--issue",
        "-d", domain,
        "--dns", "dns_ionos",
        "--home", acme_home_dir,
        "--keylength", key_length,
        "--fullchain-file", os.path.join(cert_storage_path, "fullchain.cer"),
        "--key-file", os.path.join(cert_storage_path, "domain.key"),
        "--reload-cmd", "echo 'Certificate issued.'"
    ]

    try:
        run_acme_command(command_args, env_vars=env_vars, dry_run=dry_run)
    except Exception as e:
        raise Exception(f"acme.sh certificate issuance failed: {e}")

if __name__ == "__main__":
    # Example Usage
    pass
