"""Azure: import into Key Vault, point an Application Gateway listener at it.

Credentials come from DefaultAzureCredential (D1) — in CI that resolves workload
identity federation, so no client secret is stored.

Required role assignments on the deploy identity (D3), scoped to the one vault
and the one gateway, never subscription-wide:
    Microsoft.KeyVault/vaults/certificates/import/action
    Microsoft.KeyVault/vaults/secrets/read
    Microsoft.Network/applicationGateways/read
    Microsoft.Network/applicationGateways/write

The gateway references the certificate by Key Vault secret id, so rotation is a
Key Vault import plus a gateway update that re-points at the new version.
"""
from __future__ import annotations

import logging
from typing import Optional

from .base import REQUIRED, CertificateTarget, DeployResult

log = logging.getLogger(__name__)


class AzureAppGatewayTarget(CertificateTarget):
    provider = "azure"

    def __init__(
        self,
        name: str,
        vault_url: str,
        certificate_name: str,
        subscription_id: str,
        resource_group: str,
        gateway_name: str,
        ssl_certificate_name: Optional[str] = None,
        policy: str = REQUIRED,
        **kwargs,
    ) -> None:
        super().__init__(name, policy, **kwargs)
        self.vault_url = vault_url
        self.certificate_name = certificate_name
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.gateway_name = gateway_name
        self.ssl_certificate_name = ssl_certificate_name or certificate_name

    @staticmethod
    def _to_pkcs12(cert_pem: str, key_pem: str, chain_pem: Optional[str]) -> bytes:
        """Key Vault imports PKCS#12; acme.sh gives us PEM."""
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.serialization import pkcs12
        from cryptography import x509

        key = serialization.load_pem_private_key(key_pem.encode(), password=None)
        cert = x509.load_pem_x509_certificate(cert_pem.encode())
        cas = None
        if chain_pem:
            cas = x509.load_pem_x509_certificates(chain_pem.encode()) or None
        return pkcs12.serialize_key_and_certificates(
            name=None, key=key, cert=cert, cas=cas,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def deploy(self, cert_name, cert_pem, key_pem, chain_pem=None) -> DeployResult:
        try:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.certificates import CertificateClient
            from azure.mgmt.network import NetworkManagementClient
        except ImportError:
            return self._fail(
                "azure SDK not installed; `pip install azure-identity "
                "azure-keyvault-certificates azure-mgmt-network cryptography`"
            )

        try:
            credential = DefaultAzureCredential()
            certs = CertificateClient(vault_url=self.vault_url, credential=credential)
            pfx = self._to_pkcs12(cert_pem, key_pem, chain_pem)
            imported = certs.import_certificate(
                certificate_name=self.certificate_name, certificate_bytes=pfx
            )
            secret_id = imported.secret_id
            log.info("%s: imported into Key Vault as %s", self.name, secret_id)

            network = NetworkManagementClient(credential, self.subscription_id)
            gateway = network.application_gateways.get(self.resource_group, self.gateway_name)

            target = next(
                (c for c in (gateway.ssl_certificates or []) if c.name == self.ssl_certificate_name),
                None,
            )
            if target is None:
                return self._fail(
                    f"application gateway {self.gateway_name} has no ssl_certificate "
                    f"named {self.ssl_certificate_name!r}"
                )

            # Version-less secret id lets the gateway follow future rotations.
            target.key_vault_secret_id = secret_id.rsplit("/", 1)[0]
            network.application_gateways.begin_create_or_update(
                self.resource_group, self.gateway_name, gateway
            ).result()

            return self._ok(
                f"bound Key Vault certificate to {self.gateway_name}", secret_id=secret_id
            )
        except Exception as e:
            return self._fail(f"Azure deployment failed: {e}")
