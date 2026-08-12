"""Application configuration - reads from config.ini only"""
from typing import List
from functools import lru_cache
import configparser
import os


# Load config.ini
config = configparser.ConfigParser()
config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config.ini')

if os.path.exists(config_path):
    config.read(config_path)
    print(f"[CONFIG] Loaded config from: {config_path}")
else:
    print(f"[CONFIG] WARNING: config.ini not found at {config_path}")


def get_config(section: str, key: str, default: str = "") -> str:
    """Get config value from config.ini"""
    try:
        value = config.get(section, key)
        # Strip quotes if present
        if value and len(value) >= 2:
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
        return value
    except (configparser.NoSectionError, configparser.NoOptionError):
        return default


def get_config_bool(section: str, key: str, default: bool = False) -> bool:
    """Get boolean config value"""
    try:
        return config.getboolean(section, key)
    except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
        return default


def get_config_int(section: str, key: str, default: int = 0) -> int:
    """Get integer config value"""
    try:
        return config.getint(section, key)
    except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
        return default


class Settings:
    """Application settings from config.ini"""

    def __init__(self):
        # Application
        self.APP_NAME: str = get_config('application', 'APP_NAME', 'Maker-Checker Platform')
        self.APP_VERSION: str = get_config('application', 'APP_VERSION', '1.0.0')
        self.DEBUG: bool = get_config_bool('application', 'DEBUG', False)

        # API
        self.API_PREFIX: str = get_config('api', 'API_PREFIX', '/api/v1')
        self.CORS_ORIGINS: List[str] = get_config('api', 'CORS_ORIGINS', 'http://localhost:5000').split(',')

        # Database
        self.DATABASE_URL: str = get_config('database', 'DATABASE_URL', 'sqlite:///./makerchecker.db')

        # Flask settings
        self.FLASK_SECRET_KEY: str = get_config('flask', 'FLASK_SECRET_KEY', 'flask-secret-key')
        self.FLASK_DEBUG: bool = get_config_bool('flask', 'FLASK_DEBUG', True)
        self.FLASK_HOST: str = get_config('flask', 'FLASK_HOST', '0.0.0.0')
        self.FLASK_PORT: int = get_config_int('flask', 'FLASK_PORT', 5000)

        # FastAPI settings
        self.FASTAPI_HOST: str = get_config('fastapi', 'FASTAPI_HOST', '127.0.0.1')
        self.FASTAPI_PORT: int = get_config_int('fastapi', 'FASTAPI_PORT', 8000)

        # ServiceNow Integration
        self.SERVICENOW_INSTANCE: str = get_config('servicenow', 'SERVICENOW_INSTANCE', '')
        self.SERVICENOW_USERNAME: str = get_config('servicenow', 'SERVICENOW_USERNAME', '')
        self.SERVICENOW_PASSWORD: str = get_config('servicenow', 'SERVICENOW_PASSWORD', '')
        self.SERVICENOW_INCIDENT_TABLE: str = get_config('servicenow', 'SERVICENOW_INCIDENT_TABLE', 'incident')
        self.SERVICENOW_CHANGE_TABLE: str = get_config('servicenow', 'SERVICENOW_CHANGE_TABLE', 'change_request')
        self.SERVICENOW_REQUEST_TABLE: str = get_config('servicenow', 'SERVICENOW_REQUEST_TABLE', 'sc_request')
        self.SERVICENOW_APPROVAL_FIELD: str = get_config('servicenow', 'SERVICENOW_APPROVAL_FIELD', 'u_owner_approval')
        self.SERVICENOW_ASSIGNMENT_GROUP: str = get_config('servicenow', 'SERVICENOW_ASSIGNMENT_GROUP', '')
        self.SERVICENOW_ENABLED: bool = get_config_bool('servicenow', 'SERVICENOW_ENABLED', False)

        # AI / Groq settings
        self.GROQ_API_KEY: str = get_config('ai', 'GROQ_API_KEY', '')
        self.AI_BASE_URL: str = get_config('ai', 'BASE_URL', 'https://api.groq.com/openai/v1')
        self.AI_MODEL: str = get_config('ai', 'MODEL', 'llama-3.3-70b-versatile')
        self.AI_TIMEOUT_SECONDS: int = get_config_int('ai', 'TIMEOUT_SECONDS', 60)

        # SSH Settings
        self.DEFAULT_SSH_PORT: int = get_config_int('ssh', 'DEFAULT_SSH_PORT', 22)
        self.SSH_TIMEOUT: int = get_config_int('ssh', 'SSH_TIMEOUT', 30)
        self.SSH_KEY_PATH: str = get_config('ssh', 'SSH_KEY_PATH', '')

        # WinRM Settings
        self.DEFAULT_WINRM_PORT: int = get_config_int('winrm', 'DEFAULT_WINRM_PORT', 5985)
        self.WINRM_TRANSPORT: str = get_config('winrm', 'WINRM_TRANSPORT', 'ntlm')
        self.WINRM_TIMEOUT: int = get_config_int('winrm', 'WINRM_TIMEOUT', 30)

        # Logging
        self.LOG_LEVEL: str = get_config('logging', 'LOG_LEVEL', 'INFO')
        self.LOG_FORMAT: str = get_config('logging', 'LOG_FORMAT', 'json')
        self.LOG_FILE: str = get_config('logging', 'LOG_FILE', 'logs/makerchecker.log')

        # Print loaded ServiceNow config for debugging
        print(f"[CONFIG] ServiceNow Instance: {self.SERVICENOW_INSTANCE}")
        print(f"[CONFIG] ServiceNow Enabled: {self.SERVICENOW_ENABLED}")


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


settings = get_settings()
