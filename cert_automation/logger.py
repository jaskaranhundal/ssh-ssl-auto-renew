import logging
import os
import sys

def setup_logging(log_file_path: str = None):
    """
    Sets up a centralized, configurable logger for the application.
    Accepts an optional log_file_path to override default or environment variable.
    """
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    log_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Get the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove any existing handlers to avoid duplicate logs
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console handler
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(log_formatter)
    root_logger.addHandler(stream_handler)

    # File handler
    final_log_file_path = log_file_path if log_file_path else os.getenv("LOG_FILE_PATH", "renewal.log")
    try:
        # Ensure directory exists for the log file
        os.makedirs(os.path.dirname(final_log_file_path), exist_ok=True)
        file_handler = logging.FileHandler(final_log_file_path)
        file_handler.setFormatter(log_formatter)
        root_logger.addHandler(file_handler)
        logging.info(f"Logging configured. Level: {log_level_str}. Log file: {final_log_file_path}")
    except Exception as e:
        logging.error(f"Failed to configure file logger at {final_log_file_path}: {e}")

if __name__ == "__main__":
    # Example usage
    os.environ["LOG_LEVEL"] = "DEBUG"
    setup_logging()
    
    # Create logger instances in different modules as you would normally
    logger1 = logging.getLogger("module1")
    logger2 = logging.getLogger("module2.sub")

    logger1.debug("This is a debug message.")
    logger1.info("This is an info message.")
    logger2.warning("This is a warning from a submodule.")
    logger2.error("This is an error from a submodule.")
