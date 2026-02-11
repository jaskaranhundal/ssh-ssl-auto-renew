import ssl
import socket
import requests
import logging
from datetime import datetime, timedelta

from cert_manager import get_certificate_expiry_date

log = logging.getLogger(__name__)

class HealthChecker:
    """
    Performs health checks on a domain after certificate deployment.
    """
    def __init__(self, domain: str):
        self.domain = domain
        logging.info(f"HealthChecker initialized for domain: {domain}")

    def check_https_status(self, timeout: int = 10) -> bool:
        """
        Makes an HTTPS request to the domain and checks for a 2xx or 3xx status code.

        Args:
            timeout: Request timeout in seconds.

        Returns:
            True if the status code is in the 2xx/3xx range, False otherwise.
        """
        url = f"https://{self.domain}"
        logging.info(f"Performing HTTPS status check on {url}...")
        try:
            response = requests.get(url, timeout=timeout, verify=True) # verify=True is important
            if response.ok:
                logging.info(f"HTTPS status check PASSED for {url}. Status code: {response.status_code}")
                return True
            else:
                logging.warning(f"HTTPS status check FAILED for {url}. Status code: {response.status_code}")
                return False
        except requests.exceptions.SSLError as e:
            logging.error(f"HTTPS status check FAILED for {url} with SSL Error: {e}")
            return False
        except requests.exceptions.RequestException as e:
            logging.error(f"HTTPS status check FAILED for {url} with Request Error: {e}")
            return False

    def verify_cert_expiry(self, expected_min_expiry_days: int = 85) -> bool:
        """
        Connects to the server, fetches the certificate, and verifies it's a new cert
        by checking that its expiry date is in the future by at least a certain number of days.

        Args:
            expected_min_expiry_days: The minimum number of days until the new cert should expire.
                                      Let's Encrypt certs are valid for 90 days.

        Returns:
            True if the certificate is new and valid, False otherwise.
        """
        logging.info(f"Verifying the live certificate for {self.domain}...")
        try:
            context = ssl.create_default_context()
            with socket.create_connection((self.domain, 443)) as sock:
                with context.wrap_socket(sock, server_hostname=self.domain) as ssock:
                    cert_pem = ssl.DER_cert_to_PEM_cert(ssock.getpeercert(True))
            
            # Write temp cert to parse with our existing function
            temp_cert_path = "/tmp/health_check_cert.pem"
            with open(temp_cert_path, "w") as f:
                f.write(cert_pem)
            
            expiry_date = get_certificate_expiry_date(temp_cert_path)
            if not expiry_date:
                raise ValueError("Could not parse expiry date from live certificate.")

            days_to_expiry = (expiry_date - datetime.now()).days
            logging.info(f"Live certificate for {self.domain} expires on {expiry_date.strftime('%Y-%m-%d')} ({days_to_expiry} days).")

            if days_to_expiry >= expected_min_expiry_days:
                logging.info(f"Certificate verification PASSED. The new certificate is being served.")
                return True
            else:
                logging.warning(f"Certificate verification FAILED. The certificate expires in {days_to_expiry} days, which is less than the expected {expected_min_expiry_days} days. The old certificate might still be active.")
                return False
        except Exception as e:
            logging.error(f"An error occurred during live certificate verification for {self.domain}: {e}")
            return False

if __name__ == "__main__":
    # --- Example Usage for Testing ---
    # Replace with a domain you want to test
    TEST_DOMAIN = "google.com"

    print(f"\n--- Testing HealthChecker for {TEST_DOMAIN} ---")
    checker = HealthChecker(TEST_DOMAIN)
    
    # Test 1: HTTPS Status Check
    checker.check_https_status()

    # Test 2: Certificate Expiry Verification
    # A healthy Google cert should be valid for less than 85 days in this case, so this might "fail"
    checker.verify_cert_expiry()
