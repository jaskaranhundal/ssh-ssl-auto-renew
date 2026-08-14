from unittest.mock import patch

import pytest

from cert_automation.retry_decorator import retry


class Transient(Exception):
    pass


class Permanent(Transient):
    """A retryable-category exception that is actually permanent."""


def test_non_retryable_raises_immediately():
    calls = {"n": 0}

    @retry(tries=5, delay=1, exceptions=(Transient,), non_retryable=(Permanent,))
    def f():
        calls["n"] += 1
        raise Permanent("nope")

    with patch("cert_automation.retry_decorator.time.sleep") as sleep:
        with pytest.raises(Permanent):
            f()
    assert calls["n"] == 1          # no retries
    sleep.assert_not_called()        # and no backoff sleep


def test_retryable_exhausts_then_raises():
    calls = {"n": 0}

    @retry(tries=3, delay=1, backoff=2, exceptions=(Transient,))
    def f():
        calls["n"] += 1
        raise Transient("flaky")

    with patch("cert_automation.retry_decorator.time.sleep"):
        with pytest.raises(Transient):
            f()
    assert calls["n"] == 3           # tries total


def test_jitter_within_bounds_and_capped():
    sleeps = []

    @retry(tries=4, delay=10, backoff=10, exceptions=(Transient,), max_delay=15, jitter=2.0)
    def f():
        raise Transient("x")

    with patch("cert_automation.retry_decorator.time.sleep", side_effect=lambda s: sleeps.append(s)), \
         patch("cert_automation.retry_decorator.random.uniform", return_value=1.5):
        with pytest.raises(Transient):
            f()

    # base delay min(delay, max_delay) + jitter(1.5); 2nd delay 100 capped to 15 + 1.5
    assert sleeps[0] == pytest.approx(10 + 1.5)
    assert sleeps[1] == pytest.approx(15 + 1.5)
    assert all(s <= 15 + 2.0 for s in sleeps)
