from typing import Union
import OpenSSL.crypto
from datetime import datetime, timedelta
import logging

log = logging.getLogger(__name__)

def get_certificate_expiry_date(cert_path: str) -> Union[datetime, None]:
    """
    Reads a certificate file and extracts its expiry date.

    Args:
        cert_path: The path to the certificate file (e.g., fullchain.pem).

    Returns:
        A datetime object representing the certificate's expiry date, or None if an error occurs.
    """
    try:
        with open(cert_path, 'rb') as f:
            cert_data = f.read()
        cert = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, cert_data)
        
        # Get the 'Not After' date, which is in YYYYMMDDhhmmssZ format
        not_after_bytes = cert.get_notAfter()
        if not_after_bytes is None:
            logging.error(f"Certificate at {cert_path} has no 'Not After' date.")
            return None
        
        # Decode from bytes and remove the 'Z' at the end for UTC
        not_after_str = not_after_bytes.decode('ascii').rstrip('Z')
        
        # Parse the datetime string
        expiry_date = datetime.strptime(not_after_str, '%Y%m%d%H%M%S')
        return expiry_date
    except FileNotFoundError:
        logging.error(f"Certificate file not found at: {cert_path}")
        return None
    except OpenSSL.crypto.Error as e:
        logging.error(f"Error loading or parsing certificate {cert_path}: {e}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred while processing {cert_path}: {e}")
        return None

def is_certificate_due_for_renewal(cert_path: str, renewal_threshold_days: int) -> bool:
    """
    Checks if a certificate is due for renewal based on a given threshold.

    Args:
        cert_path: The path to the certificate file.
        renewal_threshold_days: The number of days before expiry to consider a certificate due for renewal.

    Returns:
        True if the certificate is due for renewal, False otherwise.
    """
    expiry_date = get_certificate_expiry_date(cert_path)
    if expiry_date is None:
        logging.warning(f"Could not determine expiry date for {cert_path}. Assuming not due for renewal.")
        return False

    now = datetime.now()
    renewal_date = expiry_date - timedelta(days=renewal_threshold_days)

    if now >= renewal_date:
        logging.info(f"Certificate {cert_path} expires on {expiry_date.strftime('%Y-%m-%d')}. Due for renewal (within {renewal_threshold_days} days).")
        return True
    else:
        logging.info(f"Certificate {cert_path} expires on {expiry_date.strftime('%Y-%m-%d')}. Not due for renewal yet.")
        return False

if __name__ == "__main__":
    # Example usage (for testing)
    # This requires a dummy certificate file for testing.
    # You can generate one with:
    # openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem -days 365
    
    # Create a dummy certificate for testing purposes.
    # In a real scenario, this would be an existing certificate.
    DUMMY_CERT_PATH = "dummy_cert.pem"
    try:
        # Generate a self-signed certificate for testing purposes
        # This is a minimal example and not suitable for production
        k = OpenSSL.crypto.PKey()
        k.generate_key(OpenSSL.crypto.TYPE_RSA, 2048)

        cert = OpenSSL.crypto.X509()
        cert.get_subject().C = "US"
        cert.get_subject().ST = "CA"
        cert.get_subject().L = "San Francisco"
        cert.get_subject().O = "MyOrg"
        cert.get_subject().OU = "MyUnit"
        cert.get_subject().CN = "localhost"
        cert.set_serial_number(1000)
        cert.gmtime_adj_notBefore(0)
        cert.gmtime_adj_notAfter(365 * 24 * 60 * 60) # Valid for 1 year
        cert.set_issuer(cert.get_subject())
        cert.set_pubkey(k)
        cert.sign(k, 'sha256')

        with open(DUMMY_CERT_PATH, "wb") as f:
            f.write(OpenSSL.crypto.dump_certificate(OpenSSL.crypto.FILETYPE_PEM, cert))
        
        logging.info(f"Dummy certificate created at {DUMMY_CERT_PATH}")

        # Test cases
        print("\n--- Testing Certificate Expiry Check ---")
        
        # Test with dummy cert, far from expiry
        print(f"Is dummy cert ({DUMMY_CERT_PATH}) due for renewal (90 days threshold)? "
              f"{is_certificate_due_for_renewal(DUMMY_CERT_PATH, 90)}")

        # Test with dummy cert, close to expiry (simulated)
        # To simulate, we'll temporarily set a very high threshold
        print(f"Is dummy cert ({DUMMY_CERT_PATH}) due for renewal (360 days threshold)? "
              f"{is_certificate_due_for_renewal(DUMMY_CERT_PATH, 360)}")
        
        # Test with a non-existent file
        print(f"Is non-existent.pem due for renewal (30 days threshold)? "
              f"{is_certificate_due_for_renewal('non-existent.pem', 30)}")

    except Exception as e:
        logging.error(f"Error during dummy certificate generation or testing: {e}")
    finally:
        # Clean up dummy cert
        import os
        if os.path.exists(DUMMY_CERT_PATH):
            os.remove(DUMMY_CERT_PATH)
            logging.info(f"Cleaned up dummy certificate at {DUMMY_CERT_PATH}")
