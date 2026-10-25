"""
Tiny in-memory rate limiter (stdlib only).

Fixed-window counters keyed by an arbitrary string (e.g. client IP +
endpoint). Used to slow PIN brute-forcing: a 4-digit PIN falls quickly
to unlimited guessing, so login endpoints are throttled.
Thread-safe; state resets on restart (acceptable — the goal is to make
sustained guessing impractical, not to keep cross-restart history).
"""
import threading
import time

_counters = {}  # key -> [window_start_epoch, count]
_lock = threading.Lock()

# Safety valve against unbounded growth (many client IPs over weeks):
# whenever the table grows past this, expired windows are swept.
_SWEEP_THRESHOLD = 1024


def _sweep_locked(now, window_seconds):
    """Drop counters whose window has expired (caller holds the lock)."""
    expired = [k for k, v in _counters.items()
               if now - v[0] >= window_seconds]
    for key in expired:
        del _counters[key]


def check(key, limit, window_seconds):
    """Return True if the attempt is allowed, False if rate-limited."""
    now = time.time()
    with _lock:
        if len(_counters) >= _SWEEP_THRESHOLD:
            # Successful logins never revisit their key, so without this
            # the table would grow with every new client IP forever (R16).
            _sweep_locked(now, window_seconds)
        entry = _counters.get(key)
        if entry is None or now - entry[0] >= window_seconds:
            _counters[key] = [now, 1]
            return True
        if entry[1] < limit:
            entry[1] += 1
            return True
        return False


def reset(key=None):
    """Clear counters (single key or all). Used in tests."""
    with _lock:
        if key is None:
            _counters.clear()
        else:
            _counters.pop(key, None)
