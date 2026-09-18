"""
Configuration for Posziona.
"""
import os

# Base directories
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
PARTY_DB_DIR = os.path.join(DATA_DIR, 'parties')
TEMPLATES_DB = os.path.join(DATA_DIR, 'templates.db')

# Server settings
HOST = '127.0.0.1'
PORT = 5000
DEBUG = False

# App settings
DEFAULT_CURRENCY = '€'

# Session signing key: unique per install, persisted in the data dir
# (gitignored). POSZIONA_SECRET_KEY env var wins when set (containers).
SECRET_KEY_FILE = os.path.join(DATA_DIR, '.secret_key')


def get_secret_key():
    """Load or create this install's Flask secret key.

    Falls back to a throwaway dev key only when the data dir is not
    writable — sessions then don't survive restarts, but the app stays up.
    """
    import secrets

    env_key = os.environ.get('POSZIONA_SECRET_KEY')
    if env_key:
        return env_key
    try:
        if os.path.exists(SECRET_KEY_FILE):
            with open(SECRET_KEY_FILE, 'r') as f:
                stored = f.read().strip()
            if stored:
                return stored
        os.makedirs(DATA_DIR, exist_ok=True)
        fresh = secrets.token_hex(32)
        # Best effort: restrict to owner (POS kiosk = single user box)
        fd = os.open(SECRET_KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(fresh)
        return fresh
    except OSError:
        return 'dev-secret-key-change-in-production'

# Ensure directories exist
os.makedirs(PARTY_DB_DIR, exist_ok=True)
