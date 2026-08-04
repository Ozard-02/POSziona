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

# Ensure directories exist
os.makedirs(PARTY_DB_DIR, exist_ok=True)
