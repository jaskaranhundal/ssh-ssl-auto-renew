"""Pre-flight host-key population.

Builds the SSH ``known_hosts`` file from the hosts defined in ``servers.yaml`` BEFORE
any deployment connects. This keeps ``paramiko.RejectPolicy()`` (no insecure auto-add)
while ensuring every server we are about to deploy to has a verified host key — so
adding a server to ``servers.yaml`` can never again silently break renewal on a stale
manually-maintained host list.

Run once from ``main.py`` after configs load and before the deploy loop.
"""
import os
import subprocess
import logging
from typing import Dict, List

log = logging.getLogger(__name__)


def default_known_hosts_path() -> str:
    """Resolve the known_hosts path (env override, else ~/.ssh/known_hosts)."""
    return os.getenv("KNOWN_HOSTS_PATH") or os.path.join(
        os.path.expanduser("~"), ".ssh", "known_hosts"
    )


def hosts_from_servers_config(servers_config: dict) -> List[str]:
    """Return the unique, sorted list of host addresses from a parsed servers.yaml."""
    hosts = {
        s["host"]
        for s in (servers_config or {}).get("servers", [])
        if s.get("host")
    }
    return sorted(hosts)


def build_known_hosts(hosts: List[str], known_hosts_path: str, timeout: int = 10) -> Dict[str, bool]:
    """ssh-keyscan every host and (over)write known_hosts_path with the results.

    Returns a mapping ``{host: scanned_ok}``. A host that cannot be scanned is recorded
    as ``False`` (not fatal) — its later deploy will fail fast with a clear host-key error
    rather than aborting the whole run.
    """
    results: Dict[str, bool] = {}
    entries: List[str] = []

    for host in hosts:
        try:
            proc = subprocess.run(
                ["ssh-keyscan", "-H", "-T", str(timeout), host],
                capture_output=True, text=True, timeout=timeout + 5,
            )
            scanned = proc.returncode == 0 and proc.stdout.strip() != ""
            results[host] = scanned
            if scanned:
                entries.append(proc.stdout.strip())
                log.info(f"known_hosts: scanned host key for {host}")
            else:
                log.warning(f"known_hosts: no key returned for {host} "
                            f"(rc={proc.returncode}, stderr={proc.stderr.strip()})")
        except FileNotFoundError:
            log.error("known_hosts: 'ssh-keyscan' not found — install openssh-client.")
            results[host] = False
        except subprocess.TimeoutExpired:
            log.warning(f"known_hosts: ssh-keyscan timed out for {host}")
            results[host] = False
        except Exception as e:  # noqa: BLE001 - best-effort pre-flight, never abort the run
            log.warning(f"known_hosts: unexpected error scanning {host}: {e}")
            results[host] = False

    os.makedirs(os.path.dirname(known_hosts_path), exist_ok=True)
    with open(known_hosts_path, "w") as f:
        f.write("\n".join(entries) + ("\n" if entries else ""))
    os.chmod(known_hosts_path, 0o644)

    ok = sum(1 for v in results.values() if v)
    log.info(f"known_hosts: wrote {ok}/{len(hosts)} host keys to {known_hosts_path}")
    return results


def populate_from_servers_config(servers_config: dict, known_hosts_path: str = None) -> Dict[str, bool]:
    """Convenience entry point: derive hosts from servers.yaml and build known_hosts."""
    path = known_hosts_path or default_known_hosts_path()
    hosts = hosts_from_servers_config(servers_config)
    if not hosts:
        log.warning("known_hosts: no hosts found in servers config — skipping pre-flight.")
        return {}
    return build_known_hosts(hosts, path)
