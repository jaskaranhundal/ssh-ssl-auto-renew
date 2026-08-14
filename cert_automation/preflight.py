"""Pre-flight SSH/deploy diagnostics.

Probes every target host BEFORE the renewal deploys, so a failure is attributed
precisely ("host X: port open, account expired Jun 1") instead of surfacing as a
cryptic error deep in the deploy. Two uses:

  * Gate: main.py runs this before the deploy loop and skips hosts that fail a
    BLOCKING check (cert still issued) with a clear reason.
  * Standalone: `python3 main.py --preflight` runs the checks only and reports.

When SSH/TCP fails, `diagnose_network` escalates (DNS -> ping -> telnet-style TCP
probe -> traceroute) so the report shows *which layer* breaks.
"""
import os
import re
import socket
import shutil
import subprocess
import logging
from datetime import datetime
from typing import Dict, List

from remote_deployer import RemoteDeployer

log = logging.getLogger(__name__)

CONNECT_TIMEOUT = 8
PASS, FAIL, WARN, SKIP = "PASS", "FAIL", "WARN", "SKIP"

# Order checks appear in the report table. (No sudo/nginx-t: the deploy uses only
# specific whitelisted sudo commands, so a generic sudo probe is a false positive.)
CHECK_ORDER = ["tcp_22", "host_key", "ssh_auth",
               "account_expiry", "cert_path", "nginx_ssl_path"]


def _tcp_open(host: str, port: int, timeout: int = CONNECT_TIMEOUT) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _is_ip(host: str) -> bool:
    for fam in (socket.AF_INET, socket.AF_INET6):
        try:
            socket.inet_pton(fam, host)
            return True
        except OSError:
            continue
    return False


def diagnose_network(host: str, ports=(22, 80, 443), timeout: int = CONNECT_TIMEOUT) -> str:
    """Escalating 'where does it break' probe; every sub-probe is best-effort."""
    lines: List[str] = []

    if not _is_ip(host):
        try:
            socket.getaddrinfo(host, None)
            lines.append("dns: resolves")
        except socket.gaierror as e:
            lines.append(f"dns: FAILS ({e})")

    if shutil.which("ping"):
        try:
            rc = subprocess.run(["ping", "-c", "2", "-W", "2", host],
                                capture_output=True, text=True, timeout=12)
            lines.append("ping: reachable" if rc.returncode == 0 else "ping: NO reply")
        except Exception as e:  # noqa: BLE001
            lines.append(f"ping: n/a ({e})")
    else:
        lines.append("ping: n/a (no binary)")

    open_ports = [p for p in ports if _tcp_open(host, p, timeout)]
    lines.append(f"tcp open: {open_ports or 'none'}")

    tr = shutil.which("traceroute") or shutil.which("tracepath")
    if tr:
        try:
            cmd = ([tr, "-n", "-m", "15", "-w", "2", host]
                   if tr.endswith("traceroute") else [tr, host])
            rc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            hops = [ln for ln in rc.stdout.strip().splitlines() if ln.strip()]
            lines.append("traceroute last hop: " + (hops[-1].strip() if hops else "n/a"))
        except Exception as e:  # noqa: BLE001
            lines.append(f"traceroute: n/a ({e})")
    else:
        lines.append("traceroute: n/a (no binary)")

    return " | ".join(lines)


def _parse_expiry(chage_output: str):
    m = re.search(r'Password expires\s*:\s*(.+)', chage_output or "", re.I)
    if not m:
        return WARN, "could not parse password expiry"
    val = m.group(1).strip()
    if val.lower() == "never":
        return PASS, "password never expires"
    try:
        days = (datetime.strptime(val, "%b %d, %Y") - datetime.now()).days
    except ValueError:
        return WARN, f"expires {val} (unparsed)"
    if days < 0:
        return FAIL, f"password EXPIRED ({val})"
    if days < 14:
        return WARN, f"password expires in {days}d ({val})"
    return PASS, f"expires {val}"


def _finalize(name, host, cert_path, checks, blocking_fail):
    return {"name": name, "host": host, "cert_path": cert_path, "checks": checks,
            "ok": blocking_fail is None, "reason": blocking_fail or ""}


def check_host(server: dict, ssh_key_path: str, domains_for_host: List[str],
               known_hosts_result: Dict[str, bool], timeout: int = CONNECT_TIMEOUT) -> dict:
    """Run the ordered per-host checks, short-circuiting when a prerequisite fails."""
    name = server.get("name")
    host = server.get("host")
    cert_path = (server.get("cert_path") or "").rstrip()
    user = os.getenv("SSH_USER") or server.get("user")
    use_pty = server.get("use_pty", False)
    checks: List[dict] = []
    blocking = None

    def add(n, status, detail=""):
        checks.append({"name": n, "status": status, "detail": detail})

    # 1. TCP :22
    if _tcp_open(host, 22, timeout):
        add("tcp_22", PASS, "port 22 open")
    else:
        add("tcp_22", FAIL, f"port 22 unreachable — {diagnose_network(host, timeout=timeout)}")
        blocking = blocking or "tcp_22: port 22 unreachable"

    # 2. host key
    hk = known_hosts_result.get(host)
    if hk:
        add("host_key", PASS, "in known_hosts")
    elif hk is None:
        add("host_key", WARN, "not scanned (no known_hosts result)")
    else:
        add("host_key", FAIL, "ssh-keyscan failed — host key unavailable")
        blocking = blocking or "host_key: not in known_hosts"

    if checks[0]["status"] == FAIL:
        for n in ("ssh_auth", "account_expiry", "cert_path", "nginx_ssl_path"):
            add(n, SKIP, "skipped (host unreachable)")
        return _finalize(name, host, cert_path, checks, blocking)

    # 3. SSH auth
    deployer = RemoteDeployer(host, user, ssh_key_path, dry_run=False, use_pty=use_pty)
    try:
        deployer._connect()
        add("ssh_auth", PASS, f"key auth ok as {user}")
        auth_ok = True
    except Exception as e:  # noqa: BLE001
        add("ssh_auth", FAIL, f"port open, auth/session failed: {e}")
        blocking = blocking or f"ssh_auth: {e}"
        auth_ok = False

    if not auth_ok:
        for n in ("account_expiry", "cert_path", "nginx_ssl_path"):
            add(n, SKIP, "skipped (no ssh session)")
        deployer.close()
        return _finalize(name, host, cert_path, checks, blocking)

    # The remaining checks are ADVISORY (never blocking) and use NO sudo — the deploy's
    # sudoers only whitelists specific commands (cp/mv/nginx -t/systemctl), so a generic
    # `sudo` probe is a false positive. Reachability + auth already decide deploy viability.

    # 4. account expiry (own account — readable without sudo on most systems)
    out = deployer.execute_command("chage -l $(id -un) 2>/dev/null", check_exit_code=False)
    if not out.strip():
        add("account_expiry", WARN, "could not read (no permission)")
    else:
        status, detail = _parse_expiry(out)
        # An expired account surfaces as an ssh_auth/EOF failure anyway — keep advisory.
        add("account_expiry", WARN if status == FAIL else status, detail)

    # 5. cert_path exists (best-effort, no sudo)
    if cert_path:
        out = deployer.execute_command(
            f"test -d {cert_path} && echo EXISTS || echo NO", check_exit_code=False).strip()
        if "EXISTS" in out:
            add("cert_path", PASS, f"{cert_path} exists")
        elif "NO" in out:
            add("cert_path", WARN, f"{cert_path} missing (deploy will mkdir -p)")
        else:
            add("cert_path", WARN, f"{cert_path} unverified (no read permission)")
    else:
        add("cert_path", SKIP, "no cert_path configured")

    # 6. nginx ssl-path matches cert_path (best-effort, no sudo)
    mismatches, checked = [], False
    for dom in (domains_for_host or []):
        if dom.startswith("*."):
            continue
        conf = deployer.execute_command(
            f"grep -RlE 'server_name[^;]*{re.escape(dom)}' /etc/nginx/ 2>/dev/null | head -1",
            check_exit_code=False).strip()
        if not conf:
            continue
        checked = True
        sslp = deployer.execute_command(
            f"grep -hE 'ssl_certificate ' {conf} 2>/dev/null | head -1",
            check_exit_code=False).strip()
        m = re.search(r'ssl_certificate\s+(\S+);', sslp)
        if m:
            nginx_dir = os.path.dirname(m.group(1)).rstrip("/")
            if nginx_dir != cert_path.rstrip("/"):
                mismatches.append(f"{dom}: nginx={nginx_dir} cfg={cert_path}")
    if mismatches:
        add("nginx_ssl_path", WARN, "; ".join(mismatches))
    elif checked:
        add("nginx_ssl_path", PASS, "cert_path matches nginx")
    else:
        add("nginx_ssl_path", SKIP, "vhost not readable / no domains")

    deployer.close()
    return _finalize(name, host, cert_path, checks, blocking)


def run_preflight(servers_config: dict, domains_config: dict,
                  ssh_key_path: str, known_hosts_result: Dict[str, bool]) -> List[dict]:
    """Check every server actually referenced by a domain."""
    servers = {s["name"]: s for s in (servers_config or {}).get("servers", [])}
    server_domains: Dict[str, List[str]] = {}
    for d in (domains_config or {}).get("domains", []):
        for sv in d.get("servers", []):
            server_domains.setdefault(sv, []).append(d.get("domain"))

    results = []
    for name in sorted(server_domains):
        server = servers.get(name)
        if not server:
            results.append(_finalize(name, "?", "",
                [{"name": "config", "status": FAIL, "detail": "server not defined in servers.yaml"}],
                "config: server not defined"))
            continue
        log.info(f"preflight: checking {name} ({server.get('host')})")
        results.append(check_host(server, ssh_key_path, server_domains[name], known_hosts_result))
    return results


def blocking_failed_hosts(results: List[dict]) -> set:
    """Server names whose blocking checks failed (used to skip them in the renewal)."""
    return {r["name"] for r in results if not r["ok"]}


def generate_preflight_report(results: List[dict]) -> str:
    n_fail = sum(1 for r in results if not r["ok"])
    n_warn = sum(1 for r in results
                 if r["ok"] and any(c["status"] == WARN for c in r["checks"]))
    out = ["# SSL Renewal — Pre-flight Diagnostics\n",
           f"Hosts checked: {len(results)} | Blocking failures: {n_fail} | With warnings: {n_warn}\n\n",
           "| Server | Host | " + " | ".join(CHECK_ORDER) + " | Verdict |\n",
           "|" + "---|" * (len(CHECK_ORDER) + 3) + "\n"]
    for r in results:
        cmap = {c["name"]: c["status"] for c in r["checks"]}
        row = [r["name"], r["host"]] + [cmap.get(c, "-") for c in CHECK_ORDER]
        row.append("OK" if r["ok"] else f"FAIL: {r['reason']}")
        out.append("| " + " | ".join(row) + " |\n")

    out.append("\n## Details (failures & warnings)\n")
    any_detail = False
    for r in results:
        flagged = [c for c in r["checks"] if c["status"] in (FAIL, WARN)]
        if not flagged:
            continue
        any_detail = True
        out.append(f"\n### {r['name']} ({r['host']})\n")
        for c in flagged:
            out.append(f"- **{c['name']}** [{c['status']}]: {c['detail']}\n")
    if not any_detail:
        out.append("\n_All checks passed._\n")
    return "".join(out)
