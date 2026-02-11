# Testing Strategy for Automated SSL Certificate Renewal System

This document outlines the testing strategy for the `cert_automation` project, including how to set up the environment, run tests, and the overall approach to ensuring code quality and reliability.

## Testing Framework

The project uses the **pytest** framework for writing and running tests. `pytest` is a mature, feature-rich testing framework for Python that makes it easy to write small, readable tests, and can scale to support complex functional testing.

We also use the **pytest-mock** plugin, which provides a simple `mocker` fixture to mock objects and behaviors, allowing us to test functions in isolation and simulate external dependencies.

## Testing Approach

The testing strategy is centered around **unit tests with extensive mocking**. Given that the application's core function is to interact with external services (Let's Encrypt via `acme.sh`, IONOS DNS API, remote SSH servers), it is impractical and unreliable to run tests against live systems in an automated testing environment.

The key principles are:
1.  **Isolate Logic**: Each module's internal logic is tested independently.
2.  **Mock External Dependencies**: All interactions with external systems are mocked. This includes:
    -   `subprocess.run` calls to `acme.sh`.
    -   `requests` calls to the IONOS DNS API.
    -   `paramiko` SSH/SCP connections and commands.
3.  **Test Both Success and Failure Paths**: Tests are written to cover both expected successful outcomes and various failure scenarios (e.g., API errors, non-zero exit codes from commands, failed deployments).
4.  **Self-Contained Tests**: Tests for pure logic (like `report_generator.py`) and those that can use fixtures (like `cert_manager.py` with a dummy certificate) are self-contained and do not require external configuration.

## Test Suite Structure

All test files are located in the `tests/` directory and follow the naming convention `test_*.py`.

-   `tests/test_cert_manager.py`:
    -   **Purpose**: Tests the logic for parsing certificate files and checking their expiry dates.
    -   **Method**: Uses a pytest fixture to generate a real, temporary self-signed certificate on the fly. It then tests the parsing and date comparison logic against this known certificate.

-   `tests/test_report_generator.py`:
    -   **Purpose**: Tests the generation of the final Markdown report.
    -   **Method**: Uses pytest fixtures to create mock `results` dictionaries representing various scenarios (full success, partial failure, etc.). It then asserts that the generated Markdown string contains the expected headers, summaries, and detailed error messages.

-   `tests/test_acme_client_wrapper.py`:
    -   **Purpose**: Tests the wrapper around the `acme.sh` command-line tool.
    -   **Method**: Uses the `mocker` fixture to patch `subprocess.run`. This allows simulating `acme.sh`'s behavior, including successful execution, `CalledProcessError` (for non-zero exit codes), and `FileNotFoundError`. It also tests the retry logic by providing a sequence of failing and successful side effects to the mock.

-   `tests/test_remote_deployer.py`:
    -   **Purpose**: Tests the module responsible for SSH/SCP connections and remote command execution.
    -   **Method**: Uses the `mocker` fixture to patch the entire `paramiko` library. This allows simulating SSH connections, file uploads, and command executions without any actual network traffic. Tests verify that the correct `paramiko` methods are called with the expected arguments and that both success and failure paths are handled correctly.

## How to Run Tests

### 1. Setup

First, ensure you have navigated to the `cert_automation/` directory and installed all dependencies, including the testing libraries:

```bash
cd cert_automation
pip3 install -r requirements.txt
```
This will install `pytest` and `pytest-mock` along with the other project dependencies.

### 2. Running All Tests

To run the entire test suite, simply execute the `pytest` command from the project's root directory:

```bash
pytest
```
`pytest` will automatically discover and run all files named `test_*.py` or `*_test.py` in the current directory and its subdirectories.

### 3. Running Specific Tests

You can run tests for a specific file or even a specific test function.

```bash
# Run all tests in a specific file
pytest tests/test_remote_deployer.py

# Run a specific test function within a file
pytest tests/test_remote_deployer.py::test_validate_nginx_config_success

# Run tests using a keyword expression
pytest -k "nginx" # Runs all tests with "nginx" in their name
```

### 4. Verbose Output

For more detailed output, use the `-v` flag:

```bash
pytest -v
```
This will show the status of each individual test function.
