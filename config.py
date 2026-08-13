"""
Configuration module for the Ecotricity consumption tracker.
"""

from pathlib import Path
import json
from typing import Dict, Any

CONFIG_FILE = Path(__file__).parent / "config.json"

DEFAULT_CONFIG = {
    "scheduler": {
        "enabled": False,
        "hour": 23,
        "minute": 0,
        "description": "Time to run daily consumption fetch (24-hour format)"
    },
    "database": {
        "path": "consumption.db",
        "description": "SQLite database file path"
    },
    "web_ui": {
        "host": "127.0.0.1",
        "port": 5000,
        "debug": False,
        "description": "Web UI server configuration"
    },
    "api": {
        "timeout": 30,
        "max_retries": 3,
        "description": "API connection settings"
    }
}


def load_config() -> Dict[str, Any]:
    """Load configuration from file, or create default if not exists."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}. Using defaults.")
            return DEFAULT_CONFIG
    else:
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG


def save_config(config: Dict[str, Any]) -> None:
    """Save configuration to file."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


def get_config_value(key_path: str, default: Any = None) -> Any:
    """
    Get a configuration value using dot notation.
    
    Example: get_config_value('scheduler.hour') returns 23
    """
    config = load_config()
    keys = key_path.split('.')
    value = config
    
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    
    return value


def set_config_value(key_path: str, value: Any) -> None:
    """
    Set a configuration value using dot notation.
    
    Example: set_config_value('scheduler.hour', 22)
    """
    config = load_config()
    keys = key_path.split('.')
    
    # Navigate to the parent of the final key
    current = config
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    
    # Set the final key
    current[keys[-1]] = value
    save_config(config)


if __name__ == "__main__":
    # Create default config if it doesn't exist
    config = load_config()
    print(json.dumps(config, indent=2))
