"""
Configuration management for Party POS.
"""
import os

# Base directories
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
PARTY_DB_DIR = os.path.join(DATA_DIR, 'parties')
BACKUP_DIR = os.path.join(DATA_DIR, 'backups')
TEMPLATES_DB = os.path.join(DATA_DIR, 'templates.db')

# Server settings
HOST = '127.0.0.1'
PORT = 5000
DEBUG = False

# App settings
DEFAULT_CURRENCY = '€'
DEFAULT_TAX_RATE = 0.0  # Tax deferred to v2

# Backup settings
SNAPSHOT_INTERVAL_MINUTES = 5  # Configurable

# Ensure directories exist
for dir_path in [DATA_DIR, PARTY_DB_DIR, BACKUP_DIR]:
    os.makedirs(dir_path, exist_ok=True)


class Config:
    """Application configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    DATABASE_DIR = DATA_DIR
    TEMPLATES_DB = TEMPLATES_DB
    PARTY_DB_DIR = PARTY_DB_DIR
    BACKUP_DIR = BACKUP_DIR
    HOST = HOST
    PORT = PORT
    DEFAULT_CURRENCY = DEFAULT_CURRENCY
    DEFAULT_TAX_RATE = DEFAULT_TAX_RATE
    SNAPSHOT_INTERVAL_MINUTES = SNAPSHOT_INTERVAL_MINUTES
