import os
import pytest
from datetime import datetime, timedelta
import OpenSSL.crypto

from cert_automation.cert_manager import get_certificate_expiry_date, is_certificate_due_for_renewal

# Fixture to create a dummy certificate for testing
@pytest.fixture(scope="module")
def dummy_cert():
    """Creates a dummy self-signed certificate valid for 1 year and returns its path."""
    cert_path = "dummy_cert.pem"
    
    # Generate a key
    k = OpenSSL.crypto.PKey()
    k.generate_key(OpenSSL.crypto.TYPE_RSA, 2048)

    # Create a self-signed cert
    cert = OpenSSL.crypto.X509()
    cert.get_subject().C = "US"
    cert.get_subject().ST = "California"
    cert.get_subject().L = "San Francisco"
    cert.get_subject().O = "Test Org"
    cert.get_subject().OU = "Test Unit"
    cert.get_subject().CN = "localhost"
    cert.set_serial_number(1000)
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(365 * 24 * 60 * 60) # Valid for 365 days
    cert.set_issuer(cert.get_subject())
    cert.set_pubkey(k)
    cert.sign(k, 'sha256')

    with open(cert_path, "wb") as f:
        f.write(OpenSSL.crypto.dump_certificate(OpenSSL.crypto.FILETYPE_PEM, cert))

    yield cert_path

    # Teardown: remove the dummy cert file
    os.remove(cert_path)

def test_get_certificate_expiry_date_success(dummy_cert):
    """Test that get_certificate_expiry_date correctly parses a valid certificate."""
    expiry_date = get_certificate_expiry_date(dummy_cert)
    assert expiry_date is not None
    assert isinstance(expiry_date, datetime)
    # Check that expiry is roughly 1 year from now
    assert datetime.now() + timedelta(days=364) < expiry_date < datetime.now() + timedelta(days=366)

def test_get_certificate_expiry_date_file_not_found():
    """Test that get_certificate_expiry_date returns None for a non-existent file."""
    assert get_certificate_expiry_date("non_existent_file.pem") is None

def test_is_certificate_due_for_renewal_true(dummy_cert):
    """Test that is_certificate_due_for_renewal returns True when the cert is due."""
    # With a 360-day threshold, a 365-day cert should be due for renewal
    assert is_certificate_due_for_renewal(dummy_cert, renewal_threshold_days=360) is True

def test_is_certificate_due_for_renewal_false(dummy_cert):
    """Test that is_certificate_due_for_renewal returns False when the cert is not due."""
    # With a 30-day threshold, a 365-day cert should not be due
    assert is_certificate_due_for_renewal(dummy_cert, renewal_threshold_days=30) is False

def test_is_certificate_due_for_renewal_on_threshold(dummy_cert):
    """Test the edge case where the renewal date is exactly today."""
    # This is tricky to test exactly, but we can simulate by using a high threshold
    # that places the renewal date in the past
    assert is_certificate_due_for_renewal(dummy_cert, renewal_threshold_days=366) is True
