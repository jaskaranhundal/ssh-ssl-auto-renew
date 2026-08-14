"""Tests for the multi-cloud certificate targets.

No cloud SDK is required: each provider imports its SDK lazily inside deploy(),
so the tests inject fakes through sys.modules.
"""
import sys
import types

import pytest

from cloud import (
    ADVISORY,
    REQUIRED,
    AwsAcmTarget,
    DeployResult,
    build_targets,
    deploy_to_targets,
)
from cloud.base import CertificateTarget

CERT = "-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----\n"
KEY = "-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----\n"


# --- policy semantics (D5) ---------------------------------------------------

class _Stub(CertificateTarget):
    provider = "stub"

    def __init__(self, name, policy=REQUIRED, succeed=True):
        super().__init__(name, policy)
        self.succeed = succeed

    def deploy(self, cert_name, cert_pem, key_pem, chain_pem=None):
        return self._ok("done") if self.succeed else self._fail("boom")


def test_required_failure_is_fatal():
    r = _Stub("t", REQUIRED, succeed=False).deploy("d", CERT, KEY)
    assert r.fatal is True and r.advisory is False


def test_advisory_failure_is_not_fatal():
    r = _Stub("t", ADVISORY, succeed=False).deploy("d", CERT, KEY)
    assert r.fatal is False and r.advisory is True


def test_policy_defaults_to_required():
    """A target with no policy must fail the run, not be quietly best-effort."""
    assert _Stub("t").policy == REQUIRED


def test_invalid_policy_rejected_at_construction():
    with pytest.raises(ValueError, match="policy must be one of"):
        _Stub("t", "best-effort")


def test_advisory_failure_does_not_mask_a_required_failure():
    results = deploy_to_targets(
        [_Stub("a", ADVISORY, succeed=False), _Stub("b", REQUIRED, succeed=False)],
        "d", CERT, KEY,
    )
    assert [r.fatal for r in results] == [False, True]
    assert any(r.fatal for r in results)


def test_one_target_raising_does_not_skip_the_others():
    class Exploding(CertificateTarget):
        provider = "boom"

        def deploy(self, *a, **k):
            raise RuntimeError("provider bug")

    results = deploy_to_targets([Exploding("x"), _Stub("y")], "d", CERT, KEY)
    assert results[0].success is False and "provider bug" in results[0].message
    assert results[1].success is True


def test_result_dict_shape_matches_existing_consumers():
    d = DeployResult("s", False, "m", ADVISORY).to_dict()
    assert d["server"] == "s" and d["success"] is False and d["advisory"] is True


# --- config construction -----------------------------------------------------

def test_build_targets_rejects_unknown_provider():
    """A typo must fail loudly, never mean 'endpoint silently not updated'."""
    with pytest.raises(ValueError, match="unknown cloud provider"):
        build_targets([{"provider": "awss", "name": "x"}])


def test_build_targets_constructs_aws():
    t = build_targets([{
        "provider": "aws", "name": "edge", "region": "eu-central-1",
        "listener_arn": "arn:listener", "policy": ADVISORY,
    }])[0]
    assert isinstance(t, AwsAcmTarget) and t.policy == ADVISORY


# --- AWS provider (D6: bind, then verify) ------------------------------------

def _fake_boto3(listener_certs_after_modify, import_arn="arn:acm:new"):
    calls = {"import": [], "modify": []}

    class Acm:
        def import_certificate(self, **kw):
            calls["import"].append(kw)
            return {"CertificateArn": import_arn}

    class Elbv2:
        def modify_listener(self, **kw):
            calls["modify"].append(kw)
            return {}

        def describe_listeners(self, ListenerArns):
            return {"Listeners": [{"Certificates": [
                {"CertificateArn": a} for a in listener_certs_after_modify]}]}

    mod = types.ModuleType("boto3")
    mod.client = lambda svc, region_name=None: Acm() if svc == "acm" else Elbv2()
    return mod, calls


def test_aws_deploy_binds_and_verifies(monkeypatch):
    mod, calls = _fake_boto3(["arn:acm:new"])
    monkeypatch.setitem(sys.modules, "boto3", mod)
    r = AwsAcmTarget("edge", "arn:listener", "eu-central-1").deploy("d.example.com", CERT, KEY)
    assert r.success is True
    assert calls["modify"][0]["Certificates"] == [{"CertificateArn": "arn:acm:new"}]


def test_aws_fails_when_listener_does_not_report_the_new_cert(monkeypatch):
    """ModifyListener returning 200 is not proof the listener actually swapped."""
    mod, _ = _fake_boto3(["arn:acm:OLD"])
    monkeypatch.setitem(sys.modules, "boto3", mod)
    r = AwsAcmTarget("edge", "arn:listener", "eu-central-1").deploy("d.example.com", CERT, KEY)
    assert r.success is False and "did not report the new certificate" in r.message


def test_aws_reimports_in_place_when_certificate_arn_given(monkeypatch):
    mod, calls = _fake_boto3(["arn:acm:new"])
    monkeypatch.setitem(sys.modules, "boto3", mod)
    AwsAcmTarget("edge", "arn:listener", "eu-central-1",
                 certificate_arn="arn:acm:existing").deploy("d", CERT, KEY)
    assert calls["import"][0]["CertificateArn"] == "arn:acm:existing"


def test_aws_missing_sdk_is_a_clean_failure(monkeypatch):
    monkeypatch.setitem(sys.modules, "boto3", None)
    r = AwsAcmTarget("edge", "arn:listener", "eu-central-1").deploy("d", CERT, KEY)
    assert r.success is False and "boto3" in r.message


def test_aws_provider_never_exposes_delete():
    """D2: the deploy path must not carry a delete capability."""
    assert not [m for m in dir(AwsAcmTarget) if "delete" in m.lower()]
