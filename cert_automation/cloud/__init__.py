"""Cloud certificate targets, built from config.

A domain's `cloud_targets:` list in domains.yaml becomes CertificateTarget
instances here. Each entry names a provider and carries its own failure policy:

    cloud_targets:
      - provider: aws
        name: edge-alb
        region: eu-central-1
        listener_arn: arn:aws:elasticloadbalancing:...:listener/app/edge/...
        certificate_arn: arn:aws:acm:...        # optional, rotates in place
        policy: required                        # default

      - provider: gcp
        name: eu-lb
        project_id: my-project
        target_https_proxy: my-https-proxy
        policy: advisory                        # logged, does not fail the run
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List

from .aws_acm import AwsAcmTarget
from .azure_appgw import AzureAppGatewayTarget
from .base import ADVISORY, REQUIRED, CertificateTarget, DeployResult
from .gcp_certmanager import GcpCertificateManagerTarget

log = logging.getLogger(__name__)

PROVIDERS = {
    AwsAcmTarget.provider: AwsAcmTarget,
    AzureAppGatewayTarget.provider: AzureAppGatewayTarget,
    GcpCertificateManagerTarget.provider: GcpCertificateManagerTarget,
}

__all__ = [
    "ADVISORY",
    "REQUIRED",
    "PROVIDERS",
    "CertificateTarget",
    "DeployResult",
    "AwsAcmTarget",
    "AzureAppGatewayTarget",
    "GcpCertificateManagerTarget",
    "build_targets",
    "deploy_to_targets",
]


def build_targets(entries: Iterable[Dict[str, Any]]) -> List[CertificateTarget]:
    """Instantiate targets from config. Unknown providers are a hard error.

    Failing here rather than skipping is deliberate: a typo'd provider must not
    silently mean "this endpoint was not updated".
    """
    targets: List[CertificateTarget] = []
    for entry in entries or []:
        cfg = dict(entry)
        provider = cfg.pop("provider", None)
        if provider not in PROVIDERS:
            raise ValueError(
                f"unknown cloud provider {provider!r}; expected one of {sorted(PROVIDERS)}"
            )
        cfg.setdefault("name", f"{provider}-target")
        targets.append(PROVIDERS[provider](**cfg))
    return targets


def deploy_to_targets(targets, cert_name, cert_pem, key_pem, chain_pem=None) -> List[DeployResult]:
    """Deploy to every target. One target's failure never skips the rest."""
    results: List[DeployResult] = []
    for target in targets:
        try:
            results.append(target.deploy(cert_name, cert_pem, key_pem, chain_pem))
        except Exception as e:
            # A provider raising instead of returning is a bug in that provider;
            # contain it so the remaining targets still get the certificate.
            log.exception("%s: unexpected error, containing", target.name)
            results.append(DeployResult(target.name, False, f"unexpected error: {e}", target.policy))
    return results
