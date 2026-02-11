import dns.resolver
import dns.exception
import time
import logging
from typing import List

log = logging.getLogger(__name__)

def check_dns_propagation(
    domain: str,
    record_name: str,
    expected_value: str,
    timeout_seconds: int = 300,  # 5 minutes default
    interval_seconds: int = 15, # Check every 15 seconds
    nameservers: List[str] = ["8.8.8.8", "8.8.4.4"] # Google Public DNS
) -> bool:
    """
    Checks for the propagation of a specific TXT DNS record on public DNS servers.

    Args:
        domain: The base domain (e.g., "example.com").
        record_name: The specific record name to check (e.g., "_acme-challenge.subdomain").
                     The full query name will be f"{record_name}.{domain}".
        expected_value: The expected value of the TXT record.
        timeout_seconds: Maximum time to wait for propagation in seconds.
        interval_seconds: Time to wait between checks in seconds.
        nameservers: List of DNS servers to query.

    Returns:
        True if the record propagates within the timeout, False otherwise.
    """
    full_record_name = f"{record_name}.{domain}"
    resolver = dns.resolver.Resolver()
    resolver.nameservers = nameservers

    start_time = time.time()
    logging.info(f"Checking DNS propagation for TXT record: {full_record_name} with value '{expected_value}'")

    while (time.time() - start_time) < timeout_seconds:
        try:
            # Query TXT records for the full record name
            answers = resolver.resolve(full_record_name, 'TXT')
            
            for rdata in answers:
                # rdata.strings is a list of byte strings (TXT records can be split)
                # Join them and decode to compare with expected_value
                txt_value = b"".join(rdata.strings).decode('utf-8')
                if txt_value == expected_value:
                    logging.info(f"DNS propagation successful for {full_record_name}. Value matched.")
                    return True
            
            logging.debug(f"Record {full_record_name} found but value '{txt_value}' did not match expected '{expected_value}'. Retrying...")

        except dns.resolver.NXDOMAIN:
            logging.debug(f"Record {full_record_name} not found yet. Retrying...")
        except dns.resolver.NoAnswer:
            logging.debug(f"No TXT record found for {full_record_name}. Retrying...")
        except dns.exception.Timeout:
            logging.debug(f"DNS query for {full_record_name} timed out. Retrying...")
        except Exception as e:
            logging.error(f"An unexpected error occurred during DNS check for {full_record_name}: {e}. Retrying...")

        time.sleep(interval_seconds)

    logging.warning(f"DNS propagation failed for {full_record_name} within {timeout_seconds} seconds.")
    return False

if __name__ == "__main__":
    # --- Example Usage for Testing ---
    # This requires a dummy TXT record to be set up manually on a public DNS server
    # for a test domain, or a mock DNS server.

    # Example 1: Simulate success (you would need to set this TXT record manually)
    TEST_DOMAIN_SUCCESS = "example.com" # Replace with a domain you can control
    TEST_RECORD_NAME_SUCCESS = "_acme-challenge.testsuccess"
    TEST_EXPECTED_VALUE_SUCCESS = "successful-challenge-value-123"
    
    # Example 2: Simulate failure (record not existing or value not matching)
    TEST_DOMAIN_FAIL = "example.com" # Replace with a domain you can control
    TEST_RECORD_NAME_FAIL = "_acme-challenge.testfail"
    TEST_EXPECTED_VALUE_FAIL = "failure-challenge-value-456"

    print("\n--- Testing DNS Propagation Check ---")
    
    # Mocking for demonstration purposes, as real DNS changes take time and user setup.
    # In a real scenario, you would run this against actual DNS.

    # Test case 1: Successful propagation (conceptual)
    # If you were to run this live, you'd manually add TEST_RECORD_NAME_SUCCESS
    # with TEST_EXPECTED_VALUE_SUCCESS to TEST_DOMAIN_SUCCESS's DNS.
    # For now, this will likely timeout unless a real record exists.
    print(f"\nTesting successful propagation for {TEST_RECORD_NAME_SUCCESS}.{TEST_DOMAIN_SUCCESS}...")
    # result_success = check_dns_propagation(
    #     TEST_DOMAIN_SUCCESS,
    #     TEST_RECORD_NAME_SUCCESS,
    #     TEST_EXPECTED_VALUE_SUCCESS,
    #     timeout_seconds=60, # Shorter timeout for example
    #     interval_seconds=5
    # )
    # print(f"Propagation successful (simulated): {result_success}")

    # Test case 2: Failed propagation (conceptual)
    print(f"\nTesting failed propagation for {TEST_RECORD_NAME_FAIL}.{TEST_DOMAIN_FAIL}...")
    result_fail = check_dns_propagation(
        TEST_DOMAIN_FAIL,
        TEST_RECORD_NAME_FAIL,
        TEST_EXPECTED_VALUE_FAIL,
        timeout_seconds=10, # Very short timeout for quick failure
        interval_seconds=2
    )
    print(f"Propagation successful (simulated): {result_fail}")

    print("\n--- End of DNS Propagation Check Test ---")
