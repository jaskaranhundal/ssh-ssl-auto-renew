import requests
import logging
import time
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

class OTCELBClient:
    """
    Client for interacting with the Open Telekom Cloud (OTC) Elastic Load Balancer (ELB) REST API.
    Handles certificate management and listener binding.
    """
    def __init__(self, auth_url: str, username: str, password: str, domain_name: str, project_id: str, region: str = "eu-de"):
        self.auth_url = auth_url
        self.username = username
        self.password = password
        self.domain_name = domain_name
        self.project_id = project_id
        self.region = region
        self.base_url = f"https://elb.{region}.otc.t-systems.com/v2.0/lbaas"
        self.token = None
        self.token_expiry = 0

    def _get_token(self) -> str:
        """Obtains a Keystone token for authentication."""
        if self.token and time.time() < self.token_expiry - 300:
            return self.token

        log.info("Requesting new Keystone token from OTC...")
        url = f"{self.auth_url}/auth/tokens"
        payload = {
            "auth": {
                "identity": {
                    "methods": ["password"],
                    "password": {
                        "user": {
                            "name": self.username,
                            "password": self.password,
                            "domain": {"name": self.domain_name}
                        }
                    }
                },
                "scope": {
                    "project": {"id": self.project_id}
                }
            }
        }
        
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        
        self.token = response.headers.get("X-Subject-Token")
        # Tokens typically last 24h, we'll refresh well before that
        self.token_expiry = time.time() + 3600 
        return self.token

    def upload_certificate(self, name: str, cert_content: str, key_content: str) -> str:
        """
        Uploads a new certificate to the OTC ELB Console.
        Returns the unique ID of the created certificate.
        """
        token = self._get_token()
        url = f"{self.base_url}/certificates"
        
        payload = {
            "certificate": cert_content,
            "private_key": key_content,
            "name": name,
            "type": "server"
        }
        
        log.info(f"Uploading certificate '{name}' to OTC ELB...")
        response = requests.post(url, json=payload, headers={"X-Auth-Token": token}, timeout=30)
        response.raise_for_status()
        
        cert_id = response.json().get("id")
        log.info(f"Successfully uploaded certificate. ID: {cert_id}")
        return cert_id

    def get_listener_id_by_name(self, listener_name: str) -> Optional[str]:
        """Looks up a listener ID by its name. Returns None if not found."""
        token = self._get_token()
        url = f"{self.base_url}/listeners"
        response = requests.get(url, headers={"X-Auth-Token": token}, params={"name": listener_name}, timeout=30)
        response.raise_for_status()
        # Filter client-side as safety net in case OTC ignores the ?name= param
        listeners = [l for l in response.json().get("listeners", []) if l.get("name") == listener_name]
        if not listeners:
            log.warning(f"No OTC ELB listener found with name '{listener_name}'.")
            return None
        if len(listeners) > 1:
            log.warning(f"Multiple listeners found with name '{listener_name}', using first match.")
        listener_id = listeners[0].get("id")
        log.info(f"Resolved listener name '{listener_name}' to ID '{listener_id}'.")
        return listener_id

    def get_listener_current_cert(self, listener_id: str) -> Optional[str]:
        """Returns the ID of the certificate currently bound to a listener.
        
        Returns None if the listener does not exist (404) instead of raising,
        so the caller can decide whether to abort or continue.
        """
        token = self._get_token()
        url = f"{self.base_url}/listeners/{listener_id}"

        response = requests.get(url, headers={"X-Auth-Token": token}, timeout=30)
        if response.status_code == 404:
            log.warning(
                f"OTC ELB listener '{listener_id}' not found (404). "
                f"It may have been deleted or replaced. Update the listener ID in domains.yaml."
            )
            return None
        response.raise_for_status()

        return response.json().get("listener", {}).get("default_tls_container_ref")

    def update_listener_cert(self, listener_id: str, cert_id: str) -> bool:
        """Binds a certificate to a specific ELB listener."""
        token = self._get_token()
        url = f"{self.base_url}/listeners/{listener_id}"

        payload = {
            "listener": {
                "default_tls_container_ref": cert_id
            }
        }

        log.info(f"Binding certificate {cert_id} to listener {listener_id}...")
        response = requests.put(url, json=payload, headers={"X-Auth-Token": token}, timeout=30)

        if response.status_code == 200:
            log.info(f"Successfully updated listener {listener_id}")
            return True
        elif response.status_code == 404:
            raise ValueError(
                f"OTC ELB listener '{listener_id}' returned 404 — it no longer exists. "
                f"Please find the current listener ID in the OTC Console (ELB → Listeners) "
                f"and update 'id' under the 'otc_elb.listeners' entry in domains.yaml."
            )
        else:
            log.error(f"Failed to update listener {listener_id}: {response.text}")
            return False

    def delete_certificate(self, cert_id: str) -> bool:
        """Deletes a certificate resource from the OTC Console."""
        token = self._get_token()
        url = f"{self.base_url}/certificates/{cert_id}"
        
        log.info(f"Deleting unused certificate {cert_id} from OTC ELB...")
        response = requests.delete(url, headers={"X-Auth-Token": token}, timeout=30)
        
        if response.status_code in [200, 204]:
            log.info(f"Certificate {cert_id} deleted.")
            return True
        else:
            log.warning(f"Could not delete certificate {cert_id} (might still be in use): {response.text}")
            return False
