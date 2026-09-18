"""
Single-server instance lock.

SQLite is safe for one server process, but nothing stops an operator
from launching a SECOND server against the same data/ dir (wrong
shortcut, double-click) — two writers silently diverging the party DB,
bypassing every other guarantee in this codebase. The server therefore
takes an OS-level exclusive lock on startup and refuses to start if held.

Implemented with fcntl (POSIX) / msvcrt (Windows), stdlib only. OS file
locks release automatically on process death — including kill -9 — so a
crashed server can never leave a stale lock behind. The lock file also
carries the owner's PID purely for the refusal message.
"""
import os

_lock_handle = None


def _lock_path():
    from app.utils.config import DATA_DIR
    os.makedirs(DATA_DIR, exist_ok=True)
    return os.path.join(DATA_DIR, '.server.lock')


def acquire():
    """Take the instance lock. Returns True if this process owns it."""
    global _lock_handle
    path = _lock_path()
    fh = open(path, 'a+b')
    try:
        try:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except ImportError:
            import msvcrt
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    except (BlockingIOError, OSError, IOError):
        fh.close()
        return False
    fh.seek(0)
    fh.truncate()
    fh.write(str(os.getpid()).encode('ascii'))
    fh.flush()
    _lock_handle = fh  # kept open for process lifetime = lock held
    return True


def owner_pid():
    """PID recorded in the lock file (best effort, for messages only)."""
    try:
        with open(_lock_path(), 'r') as f:
            return f.read().strip() or '?'
    except OSError:
        return '?'
