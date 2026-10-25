"""
Per-session write serialization for cookie-backed server state.

The cart lives in the signed-cookie session. Two writes from the same
logged-in screen arriving in parallel (double tap on a product button,
checkout racing a late add) would last-writer-wins: a losing `add`
silently vanishes from the cart, so the operator charges for one coffee
instead of two.

A plain lock is NOT enough: every parallel request carries the SAME
pre-burst cookie (the browser only updates it when a response lands),
so even serialized handlers each compute from the same stale cart.
@session_write_lock therefore does two things while holding one lock
per operator:

1. re-centers the request's cart/cart_discount onto the server-known
   truth produced by the most recent completed mutation for that
   operator (stale cookies may not de-write committed cart state);
2. snapshots the handler's result back as the new truth.

Lock key = operator id (stable across requests for one login; the
session cookie VALUE itself changes whenever the cart changes). An
unauthenticated request has no cart state to guard and skips the lock.
"""
import copy
import threading
from functools import wraps

from flask import request, session

_CART_KEYS = ('cart', 'cart_discount')
_MISSING = object()

_cart_truth = {}   # (party db, operator_id) -> {key: value or _MISSING (not set)}
_truth_guard = threading.Lock()

_locks = {}        # (party db, operator_id) -> threading.Lock
_locks_guard = threading.Lock()


def _lock_for(op):
    """One lock per (party, operator) — a handful of sessions on a LAN at most."""
    with _locks_guard:
        lock = _locks.get(op)
        if lock is None:
            lock = _locks[op] = threading.Lock()
        return lock


def forget_session(op):
    """Drop server-known cart truth for a (party, operator) on logout."""
    with _truth_guard:
        _cart_truth.pop(op, None)


def session_write_lock(view):
    """Serialize concurrent session mutations for the logged-in operator."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        # Operator ids are per-party (an id=1 exists in every party DB),
        # so the key spans both the party and the operator.
        op = (request.args.get('db', 'default'), session.get('operator_id'))
        if op[1] is None:
            # Never logged in: no shared cart state to guard
            return view(*args, **kwargs)
        with _lock_for(op):
            # Re-center: the incoming cookie may predate the operator's
            # last completed mutation (parallel requests share one cookie).
            with _truth_guard:
                stored = dict(_cart_truth.get(op) or {})
            for key in _CART_KEYS:
                value = stored.get(key, _MISSING)
                if value is _MISSING:
                    session.pop(key, None)
                else:
                    session[key] = copy.deepcopy(value)
            try:
                return view(*args, **kwargs)
            finally:
                # This handler's outcome is the new server truth.
                snapshot = {k: session.get(k, _MISSING) for k in _CART_KEYS}
                with _truth_guard:
                    _cart_truth[op] = snapshot
    return wrapper
