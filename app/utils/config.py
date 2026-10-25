"""
Configuration for Posziona.
"""
import os
import sys

# Base directories
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# True when running as a PyInstaller bundle / AppImage / .exe. In that
# case __file__ points inside a temp extraction dir (sys._MEIPASS) that
# is wiped on exit — so runtime data must NOT live under BASE_DIR.
FROZEN = getattr(sys, 'frozen', False)


def _default_data_dir(frozen):
    if frozen:
        # Persistent, per-user location shared by all frozen builds
        # (Linux binary, AppImage, Windows .exe).
        return os.path.join(os.path.expanduser('~'), '.posziona')
    return os.path.join(BASE_DIR, 'data')


# POSZIONA_DATA_DIR env var wins (containers, tests, custom installs).
DATA_DIR = os.environ.get('POSZIONA_DATA_DIR') or _default_data_dir(FROZEN)
PARTY_DB_DIR = os.path.join(DATA_DIR, 'parties')
TEMPLATES_DB = os.path.join(DATA_DIR, 'templates.db')

# Server settings
HOST = '127.0.0.1'
PORT = 5000

# Single source of truth for the release version (used by /api/status and
# LAN beacons; the JS bundle and packaging files carry their own copies —
# bump them together, see docs/connection.md).
APP_VERSION = '0.2.0'

# Interface the server binds to. 0.0.0.0 = reachable from other devices
# on the same Wi-Fi/hotspot (the whole point of client mode + LAN
# discovery). Local URLs/checks keep using HOST (loopback).
# Override for locked-down boxes: POSZIONA_BIND_HOST=127.0.0.1.
BIND_HOST = os.environ.get('POSZIONA_BIND_HOST', '0.0.0.0')

# Session signing key: unique per install, persisted in the data dir
# (gitignored). POSZIONA_SECRET_KEY env var wins when set (containers).
SECRET_KEY_FILE = os.path.join(DATA_DIR, '.secret_key')


def get_secret_key():
    """Load or create this install's Flask secret key.

    Creation is race-safe: exclusive create (O_CREAT|O_EXCL) plus a
    read-back, so two processes booting on the same data dir for the
    first time end up with the SAME key. With check-then-create each
    could write its own and then reject the other's session cookies
    (R15 audit 2026-10-25).

    Falls back to a throwaway dev key only when the data dir is not
    writable — sessions then don't survive restarts, but the app stays up.
    """
    import secrets

    env_key = os.environ.get('POSZIONA_SECRET_KEY')
    if env_key:
        return env_key
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        try:
            fd = os.open(SECRET_KEY_FILE,
                         os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass  # another boot won the race: read its key below
        else:
            with os.fdopen(fd, 'w') as f:
                f.write(secrets.token_hex(32))
        # ALWAYS trust the file, never the in-memory value: whoever
        # created it first owns the install key.
        with open(SECRET_KEY_FILE, 'r') as f:
            stored = f.read().strip()
        if stored:
            return stored
        # Empty file (process killed mid-write): rewrite atomically.
        fresh = secrets.token_hex(32)
        tmp_path = SECRET_KEY_FILE + '.tmp'
        fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(fresh)
        os.replace(tmp_path, SECRET_KEY_FILE)
        with open(SECRET_KEY_FILE, 'r') as f:
            return f.read().strip() or fresh
    except OSError:
        return 'dev-secret-key-change-in-production'

# Ensure directories exist
os.makedirs(PARTY_DB_DIR, exist_ok=True)
