"""
Logging configuration for Posziona.
"""
import logging
import os
from logging.handlers import RotatingFileHandler
from .config import BASE_DIR, DATA_DIR, FROZEN

# In frozen builds BASE_DIR is a temp extraction dir wiped on exit,
# so logs go next to the other persistent runtime data.
LOG_DIR = os.path.join(DATA_DIR if FROZEN else BASE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, 'pos.log')

# Rotating logs: a kiosk can run for days, and an unbounded log file
# would eventually fill the disk and take SQLite down with it.
# 5 MB x 4 files is plenty for diagnostics, tiny for storage.
file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        file_handler,
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('pos')


def get_logger(name):
    """Get a logger instance with the given name."""
    return logging.getLogger(f'pos.{name}')
