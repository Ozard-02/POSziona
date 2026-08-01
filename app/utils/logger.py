"""
Logging configuration for Party POS.
"""
import logging
import os
from .config import BASE_DIR

LOG_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, 'pos.log')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('pos')


def get_logger(name):
    """Get a logger instance with the given name."""
    return logging.getLogger(f'pos.{name}')
