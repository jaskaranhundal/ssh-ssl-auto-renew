from types import SimpleNamespace
from unittest.mock import patch

from cert_automation import known_hosts_builder as khb


def test_hosts_from_servers_config_unique_sorted():
    cfg = {"servers": [
        {"name": "a", "host": "192.0.2.9"},
        {"name": "b", "host": "192.0.2.4"},
        {"name": "c", "host": "192.0.2.9"},   # duplicate host
        {"name": "d"},                        # no host -> ignored
    ]}
    assert khb.hosts_from_servers_config(cfg) == ["192.0.2.4", "192.0.2.9"]


def test_build_known_hosts_writes_one_entry_per_host(tmp_path):
    kh = tmp_path / "known_hosts"

    def fake_run(cmd, **kwargs):
        host = cmd[-1]
        return SimpleNamespace(returncode=0, stdout=f"{host} ssh-rsa AAAAKEY", stderr="")

    with patch("cert_automation.known_hosts_builder.subprocess.run", side_effect=fake_run):
        res = khb.build_known_hosts(["192.0.2.4", "192.0.2.9"], str(kh))

    assert res == {"192.0.2.4": True, "192.0.2.9": True}
    content = kh.read_text()
    assert "192.0.2.4 ssh-rsa" in content and "192.0.2.9 ssh-rsa" in content


def test_build_known_hosts_records_failure_not_fatal(tmp_path):
    kh = tmp_path / "known_hosts"

    def fake_run(cmd, **kwargs):
        host = cmd[-1]
        if host == "192.0.2.4":
            return SimpleNamespace(returncode=1, stdout="", stderr="timeout")
        return SimpleNamespace(returncode=0, stdout=f"{host} ssh-rsa AAAAKEY", stderr="")

    with patch("cert_automation.known_hosts_builder.subprocess.run", side_effect=fake_run):
        res = khb.build_known_hosts(["192.0.2.4", "192.0.2.9"], str(kh))

    assert res == {"192.0.2.4": False, "192.0.2.9": True}
    assert "192.0.2.9 ssh-rsa" in kh.read_text()
