import time
import logging
from functools import wraps

log = logging.getLogger(__name__)

def retry(tries: int = 3, delay: float = 1.0, backoff: float = 2.0, exceptions=(Exception,)):
    """
    Decorator to retry a function call multiple times with exponential backoff.

    Args:
        tries (int): Maximum number of attempts (including the first one).
        delay (float): Initial delay in seconds before the first retry.
        backoff (float): Factor by which the delay increases after each retry.
        exceptions (tuple): A tuple of exception types to catch and retry on.
    """
    def deco_retry(f):
        @wraps(f)
        def f_retry(*args, **kwargs):
            mtries, mdelay = tries, delay
            while mtries > 1:
                try:
                    return f(*args, **kwargs)
                except exceptions as e:
                    log.warning(f"Retrying {f.__name__} after {mdelay:.2f}s due to {type(e).__name__}: {e}")
                    time.sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
            
            # Final attempt outside the loop; if this fails, let the exception propagate
            return f(*args, **kwargs)

        return f_retry
    return deco_retry

if __name__ == "__main__":
    # Example Usage for Testing
    logging.basicConfig(level=logging.INFO) # Set basic logging for decorator output

    test_state = {"attempt": 0} # Use a mutable dictionary for state

    @retry(tries=4, delay=0.5, backoff=2, exceptions=(ValueError,))
    def flaky_function(should_fail_n_times):
        test_state["attempt"] += 1
        if test_state["attempt"] <= should_fail_n_times:
            log.info(f"Flaky function attempt {test_state['attempt']}: Failing intentionally.")
            raise ValueError("Intentional failure")
        log.info(f"Flaky function attempt {test_state['attempt']}: Succeeded!")
        return "Success!"

    print("\n--- Test Case 1: Succeeds after retries ---")
    test_state["attempt"] = 0 # Reset attempt for each test case
    try:
        result = flaky_function(2) # Fails 2 times, succeeds on 3rd attempt (within 4 tries)
        print(f"Result: {result}")
    except ValueError as e:
        print(f"Function finally failed: {e}")

    print("\n--- Test Case 2: Fails after all retries ---")
    test_state["attempt"] = 0 # Reset attempt for each test case
    try:
        result = flaky_function(5) # Fails 5 times, exceeds 4 tries
        print(f"Result: {result}")
    except ValueError as e:
        print(f"Function finally failed: {e}")

    print("\n--- Test Case 3: Succeeds on first attempt ---")
    test_state["attempt"] = 0 # Reset attempt for each test case
    try:
        result = flaky_function(0) # Succeeds immediately
        print(f"Result: {result}")
    except ValueError as e:
        print(f"Function finally failed: {e}")
