from typing import Dict, Any, Optional, List
import requests
import os
import logging
from dotenv import load_dotenv
from retry_decorator import retry

log = logging.getLogger(__name__)

load_dotenv() # Load environment variables from .env file

class IonosDnsClient:
    """
    Client for interacting with the IONOS DNS API to manage DNS records.
    """
    IONOS_API_BASE_URL = "https://dns.de-fra.ionos.com/v1"

    def __init__(self):
        self.api_key = os.getenv("IONOS_API_KEY")
        self.api_secret = os.getenv("IONOS_API_SECRET") # Currently not used as per doc, but good to have.

        if not self.api_key:
            raise ValueError("IONOS_API_KEY environment variable not set.")
        
        # The IONOS API seems to use X-API-Key for authentication
        self.headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }
        logging.info("IonosDnsClient initialized.")

    @retry(tries=4, delay=5, backoff=2, exceptions=(requests.exceptions.RequestException,))
    def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        """
        Helper method to make authenticated requests to the IONOS DNS API.

        Args:
            method: HTTP method (e.g., 'GET', 'POST', 'DELETE').
            path: API endpoint path (e.g., '/zones').
            **kwargs: Additional arguments for requests.request().

        Returns:
            The JSON response from the API.

        Raises:
            requests.exceptions.RequestException: If the API request fails.
        """
        url = f"{self.IONOS_API_BASE_URL}{path}"
        logging.debug(f"Making {method} request to {url}")
        try:
            response = requests.request(method, url, headers=self.headers, **kwargs)
            response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
            return response.json()
        except requests.exceptions.HTTPError as e:
            logging.error(f"HTTP error for {method} {url}: {e.response.status_code} - {e.response.text}")
            raise
        except requests.exceptions.RequestException as e:
            logging.error(f"Request error for {method} {url}: {e}")
            raise

    def _get_zone_id(self, domain: str) -> Optional[str]:
        """
        Retrieves the zone ID (UUID) for a given domain name.

        Args:
            domain: The domain name (e.g., "example.com").

        Returns:
            The UUID of the zone, or None if the zone is not found.
        """
        path = "/zones"
        try:
            zones_data = self._request("GET", path)
            for item in zones_data.get("items", []):
                if item.get("properties", {}).get("zoneName") == domain:
                    logging.info(f"Found zone ID '{item['id']}' for domain '{domain}'.")
                    return item["id"]
            logging.warning(f"Zone ID not found for domain '{domain}'.")
            return None
        except requests.exceptions.RequestException:
            logging.error(f"Failed to retrieve zone ID for domain '{domain}'.")
            return None

    def create_txt_record(self, domain: str, record_name: str, record_value: str, ttl: int = 60) -> Optional[Dict[str, Any]]:
        """
        Creates an _acme-challenge TXT record for a given domain.

        Args:
            domain: The domain for which to create the TXT record.
            record_name: The name of the TXT record (e.g., "_acme-challenge").
            record_value: The value of the TXT record.
            ttl: The Time-To-Live for the record in seconds.

        Returns:
            The created record's data if successful, None otherwise.
        """
        zone_id = self._get_zone_id(domain)
        if not zone_id:
            logging.error(f"Cannot create TXT record: Zone ID not found for domain '{domain}'.")
            return None

        path = f"/zones/{zone_id}/records"
        data = {
            "name": record_name,
            "type": "TXT",
            "content": record_value,
            "ttl": ttl,
            "enabled": True,
        }
        try:
            response = self._request("POST", path, json=data)
            logging.info(f"Successfully created TXT record for '{record_name}.{domain}'.")
            return response
        except requests.exceptions.RequestException:
            logging.error(f"Failed to create TXT record for '{record_name}.{domain}'.")
            return None

    def delete_txt_record(self, domain: str, record_id: str) -> bool:
        """
        Deletes a specific DNS record by its ID.

        Args:
            domain: The domain name where the record resides.
            record_id: The UUID of the record to delete.

        Returns:
            True if deletion was successful, False otherwise.
        """
        zone_id = self._get_zone_id(domain)
        if not zone_id:
            logging.error(f"Cannot delete TXT record: Zone ID not found for domain '{domain}'.")
            return False

        path = f"/zones/{zone_id}/records/{record_id}"
        try:
            self._request("DELETE", path)
            logging.info(f"Successfully deleted record '{record_id}' from domain '{domain}'.")
            return True
        except requests.exceptions.RequestException:
            logging.error(f"Failed to delete record '{record_id}' from domain '{domain}'.")
            return False

if __name__ == "__main__":
    # --- Example Usage for Testing ---
    # To run this, ensure you have:
    # 1. An .env file in the cert_automation/ directory with:
    #    IONOS_API_KEY="your_ionos_api_key_here"
    # 2. Replace "your-test-domain.com" with an actual domain managed by your IONOS account.
    # 3. Replace "acme-challenge-test" and "dummy-value" with actual challenge data.
    
    # Note: This will attempt to make actual API calls. Use with caution and
    # ideally with a test domain and temporary API key.

    TEST_DOMAIN = "your-test-domain.com" # !!! REPLACE WITH YOUR ACTUAL DOMAIN !!!
    TEST_RECORD_NAME = "_acme-challenge.testsub"
    TEST_RECORD_VALUE = "dummy-acme-challenge-value"

    print("\n--- Testing IonosDnsClient ---")
    client = None
    try:
        client = IonosDnsClient()

        # Test _get_zone_id
        print(f"\nAttempting to get Zone ID for {TEST_DOMAIN}...")
        zone_id = client._get_zone_id(TEST_DOMAIN)
        if zone_id:
            print(f"Zone ID for {TEST_DOMAIN}: {zone_id}")

            # Test create_txt_record
            print(f"\nAttempting to create TXT record '{TEST_RECORD_NAME}' for {TEST_DOMAIN}...")
            created_record = client.create_txt_record(TEST_DOMAIN, TEST_RECORD_NAME, TEST_RECORD_VALUE)
            if created_record and "id" in created_record:
                record_id = created_record["id"]
                print(f"TXT record created with ID: {record_id}")
                
                # Test delete_txt_record
                print(f"\nAttempting to delete TXT record '{record_id}' from {TEST_DOMAIN}...")
                if client.delete_txt_record(TEST_DOMAIN, record_id):
                    print("TXT record deleted successfully.")
                else:
                    print("Failed to delete TXT record.")
            else:
                print("Failed to create TXT record.")
        else:
            print(f"Skipping record operations as Zone ID for {TEST_DOMAIN} was not found.")

    except ValueError as e:
        print(f"Configuration Error: {e}")
    except requests.exceptions.RequestException as e:
        print(f"API Request Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    
