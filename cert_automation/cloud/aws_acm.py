"""AWS: import into ACM, bind to an ELBv2 HTTPS listener.

Credentials come from the boto3 default chain (D1) — in CI that should be an
OIDC-federated role assumed via sts:AssumeRoleWithWebIdentity, so no long-lived
access key is stored anywhere.

Required IAM on the deploy role (D3), and nothing more:
    acm:ImportCertificate, acm:AddTagsToCertificate, acm:DescribeCertificate
    elasticloadbalancing:DescribeListeners, elasticloadbalancing:ModifyListener

Constrain acm:ImportCertificate by resource ARN or tag. Unconstrained, it can
overwrite any certificate in the account by ARN, which makes the deploy role
effectively account-wide over TLS.
"""
from __future__ import annotations

import logging
from typing import Optional

from .base import REQUIRED, CertificateTarget, DeployResult

log = logging.getLogger(__name__)


class AwsAcmTarget(CertificateTarget):
    provider = "aws"

    def __init__(
        self,
        name: str,
        listener_arn: str,
        region: str,
        certificate_arn: Optional[str] = None,
        policy: str = REQUIRED,
        **kwargs,
    ) -> None:
        super().__init__(name, policy, **kwargs)
        self.listener_arn = listener_arn
        self.region = region
        # Reimporting into an existing ARN rotates in place and keeps the
        # listener binding valid; without it a new certificate is created.
        self.certificate_arn = certificate_arn

    def _clients(self):
        import boto3  # imported lazily so the SDK is optional per provider

        return boto3.client("acm", region_name=self.region), boto3.client(
            "elbv2", region_name=self.region
        )

    def deploy(self, cert_name, cert_pem, key_pem, chain_pem=None) -> DeployResult:
        try:
            acm, elbv2 = self._clients()
        except ImportError:
            return self._fail("boto3 is not installed; `pip install boto3` to use an aws target")
        except Exception as e:  # credential chain resolution failure
            return self._fail(f"could not initialise AWS clients: {e}")

        try:
            kwargs = {"Certificate": cert_pem.encode(), "PrivateKey": key_pem.encode()}
            if chain_pem:
                kwargs["CertificateChain"] = chain_pem.encode()
            if self.certificate_arn:
                kwargs["CertificateArn"] = self.certificate_arn

            cert_arn = acm.import_certificate(**kwargs)["CertificateArn"]
            log.info("%s: imported certificate %s", self.name, cert_arn)

            # D6: bind only after the import returned an ARN. On any failure the
            # listener still serves the previous certificate.
            elbv2.modify_listener(
                ListenerArn=self.listener_arn,
                Certificates=[{"CertificateArn": cert_arn}],
            )

            bound = elbv2.describe_listeners(ListenerArns=[self.listener_arn])["Listeners"][0]
            bound_arns = {c["CertificateArn"] for c in bound.get("Certificates", [])}
            if cert_arn not in bound_arns:
                return self._fail(
                    f"listener did not report the new certificate after ModifyListener "
                    f"(expected {cert_arn}, listener has {sorted(bound_arns)})"
                )

            return self._ok(f"bound {cert_arn} to listener", certificate_arn=cert_arn)
        except Exception as e:
            return self._fail(f"AWS deployment failed: {e}")
