"""GCP: upload to Certificate Manager, swap it onto a target HTTPS proxy.

Credentials come from google.auth.default() (D1) — in CI that resolves Workload
Identity Federation, so no service-account key file is stored.

Required IAM on the deploy service account (D3), nothing more:
    certificatemanager.certs.create, certificatemanager.certs.get
    compute.targetHttpsProxies.get, compute.targetHttpsProxies.setSslCertificates

Certificate Manager certificates are immutable, so rotation creates a new one
and re-points the proxy. The superseded certificate is left in place for the
separate, gated reaper (D2/D6) — this module never deletes.
"""
from __future__ import annotations

import logging
from typing import Optional

from .base import REQUIRED, CertificateTarget, DeployResult

log = logging.getLogger(__name__)


class GcpCertificateManagerTarget(CertificateTarget):
    provider = "gcp"

    def __init__(
        self,
        name: str,
        project_id: str,
        location: str = "global",
        target_https_proxy: Optional[str] = None,
        policy: str = REQUIRED,
        **kwargs,
    ) -> None:
        super().__init__(name, policy, **kwargs)
        self.project_id = project_id
        self.location = location
        self.target_https_proxy = target_https_proxy

    def _certificate_id(self, cert_name: str, fingerprint: str) -> str:
        # Immutable resources need a unique id per rotation; the cert fingerprint
        # makes the same material map to the same id (so a retry is idempotent).
        slug = cert_name.replace(".", "-").replace("*", "wildcard").strip("-")
        return f"{slug}-{fingerprint[:12]}"[:63]

    @staticmethod
    def _fingerprint(cert_pem: str) -> str:
        import hashlib

        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import Encoding

        cert = x509.load_pem_x509_certificate(cert_pem.encode())
        return hashlib.sha256(cert.public_bytes(encoding=Encoding.DER)).hexdigest()

    def deploy(self, cert_name, cert_pem, key_pem, chain_pem=None) -> DeployResult:
        try:
            from google.cloud import certificate_manager_v1 as cm
            import googleapiclient.discovery  # for the compute proxy swap
        except ImportError:
            return self._fail(
                "google SDK not installed; `pip install google-cloud-certificate-manager "
                "google-api-python-client cryptography`"
            )

        try:
            full_chain = cert_pem if not chain_pem else cert_pem.rstrip() + "\n" + chain_pem.lstrip()
            cert_id = self._certificate_id(cert_name, self._fingerprint(cert_pem))
            parent = f"projects/{self.project_id}/locations/{self.location}"

            client = cm.CertificateManagerClient()
            certificate = cm.Certificate(
                self_managed=cm.Certificate.SelfManagedCertificate(
                    pem_certificate=full_chain, pem_private_key=key_pem
                )
            )
            try:
                created = client.create_certificate(
                    parent=parent, certificate_id=cert_id, certificate=certificate
                ).result()
                cert_resource = created.name
            except Exception as e:
                # Same material re-uploaded: the id already exists, which is a
                # successful no-op rather than a failure.
                if "ALREADY_EXISTS" not in str(e) and "already exists" not in str(e).lower():
                    raise
                cert_resource = f"{parent}/certificates/{cert_id}"
                log.info("%s: certificate %s already present, reusing", self.name, cert_id)

            if not self.target_https_proxy:
                return self._ok(f"uploaded {cert_resource} (no proxy configured)",
                                certificate=cert_resource)

            # D6: bind only after the certificate resource exists.
            compute = googleapiclient.discovery.build("compute", "v1", cache_discovery=False)
            compute.targetHttpsProxies().setSslCertificates(
                project=self.project_id,
                targetHttpsProxy=self.target_https_proxy,
                body={"sslCertificates": [cert_resource]},
            ).execute()

            return self._ok(
                f"bound {cert_resource} to {self.target_https_proxy}", certificate=cert_resource
            )
        except Exception as e:
            return self._fail(f"GCP deployment failed: {e}")
