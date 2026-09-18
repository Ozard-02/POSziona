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


def check(key, limit, window_seconds):
    """Return True if the attempt is allowed, False if rate-limited."""
    now = time.time()
    with _lock:
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
