"""Put cert_automation on sys.path so the tests import its modules by bare name.

Previously this only worked because the pipeline exported PYTHONPATH before
calling pytest, so a plain `pytest tests/` outside that pipeline failed at
collection. Doing it here keeps the suite runnable from a clean checkout.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent / "cert_automation"))
