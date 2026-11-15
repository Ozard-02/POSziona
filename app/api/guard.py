"""Shared auth guards for API blueprints (leaf module — no app imports)."""
from functools import wraps

from flask import jsonify, session


def is_admin():
    """True when the current session belongs to an admin operator."""
    return session.get('operator_role') == 'admin'


def require_operator(fn):
    """Route decorator: 403 unless someone is logged in.

    One decorator instead of a hand-written session check per route:
    when the check is copy-pasted it eventually gets forgotten on a new
    endpoint (that is how the party recap stayed open to the LAN).
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('operator_id'):
            return jsonify({'error': 'Operator not logged in'}), 403
        return fn(*args, **kwargs)
    return wrapper


def require_admin(fn):
    """Route decorator: 403 unless the session is an admin.

    (functools.wraps keeps the original function name — Flask needs
    unique endpoint names per blueprint.)
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not is_admin():
            return jsonify({'error': 'Admin access required'}), 403
        return fn(*args, **kwargs)
    return wrapper
