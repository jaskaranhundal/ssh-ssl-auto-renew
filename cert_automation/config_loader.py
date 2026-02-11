import yaml
import logging
from typing import Dict, Any, Optional

log = logging.getLogger(__name__)

def load_yaml_config(file_path: str) -> Optional[Dict[str, Any]]:
    """
    Loads a YAML configuration file.

    Args:
        file_path: The path to the YAML file.

    Returns:
        A dictionary representing the YAML content, or None if an error occurs.
    """
    try:
        with open(file_path, 'r') as f:
            config = yaml.safe_load(f)
            logging.info(f"Successfully loaded configuration from {file_path}")
            return config
    except FileNotFoundError:
        logging.error(f"Configuration file not found at: {file_path}. Please create it from the .example file.")
        return None
    except yaml.YAMLError as e:
        logging.error(f"Error parsing YAML file {file_path}: {e}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred while loading {file_path}: {e}")
        return None

if __name__ == "__main__":
    # --- Example Usage for Testing ---
    # To run this, you need to have cert_automation/config/servers.yaml and 
    # cert_automation/config/domains.yaml files (copied from the .example files)

    print("\n--- Testing YAML Configuration Loader ---")
    
    # Create dummy config files for testing
    SERVERS_CONFIG_PATH = "config/servers.yaml"
    DOMAINS_CONFIG_PATH = "config/domains.yaml"

    try:
        import os
        os.makedirs("config", exist_ok=True)
        with open(SERVERS_CONFIG_PATH, "w") as f:
            f.write("""
servers:
  - name: web-01
    host: 1.1.1.1
""")
        with open(DOMAINS_CONFIG_PATH, "w") as f:
            f.write("""
domains:
  - domain: test.com
    servers:
      - web-01
""")
        
        print("\nLoading servers configuration...")
        servers_config = load_yaml_config(SERVERS_CONFIG_PATH)
        if servers_config:
            print("Servers config loaded successfully:")
            print(servers_config)

        print("\nLoading domains configuration...")
        domains_config = load_yaml_config(DOMAINS_CONFIG_PATH)
        if domains_config:
            print("Domains config loaded successfully:")
            print(domains_config)
            
        print("\nTesting with a non-existent file...")
        load_yaml_config("non-existent-config.yaml")

    except Exception as e:
        print(f"An error occurred during testing: {e}")
    finally:
        # Clean up dummy files
        import shutil
        if os.path.exists("config"):
            shutil.rmtree("config")
