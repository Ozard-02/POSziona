"""
SSE (Server-Sent Events) broadcaster for live updates.

Provides a simple in-memory pub/sub mechanism so that POS client
windows receive live product-availability changes made by an admin,
without needing to refresh the page or poll the server.

Usage:

  from app.utils.events import broadcast

  # On the client side (pos.js):
  #   const evtSource = new EventSource('/api/events');
  #   evtSource.addEventListener('product_update', function(event) {
  #       const data = JSON.parse(event.data);
  #       // update the affected product button in the DOM
  #   });

  # From a route handler (admin product update):
  #   broadcast('product_update', {'product_id': 42, 'is_active': 0})
"""
import json
import threading
import time


# ── Subscription management ──────────────────────────────────
# Each listener is a dict: {'queue': [...], 'lock': threading.Lock}
_listeners = []
_listeners_lock = threading.Lock()


def _new_listener():
    """Create and register a new SSE listener."""
    listener = {
        'queue': [],
        'lock': threading.Lock(),
        'connected_at': time.time(),
    }
    with _listeners_lock:
        _listeners.append(listener)
    return listener


def _remove_listener(listener):
    """Remove a listener (called when the client disconnects)."""
    with _listeners_lock:
        if listener in _listeners:
            _listeners.remove(listener)


def broadcast(event_type, data):
    """Push an event to all connected SSE listeners.

    Args:
        event_type: Event name (e.g. 'product_update').
        data: JSON-serializable dict with event payload.
    """
    payload = json.dumps(data)
    sse_message = f"event: {event_type}\ndata: {payload}\n\n"
    with _listeners_lock:
        for listener in _listeners:
            with listener['lock']:
                listener['queue'].append(sse_message)


def _event_stream(listener):
    """Generator that yields SSE-formatted messages to the client."""
    # Send a comment line every 15s to keep proxies from buffering
    last_heartbeat = time.time()
    while True:
        with listener['lock']:
            if listener['queue']:
                msg = listener['queue'].pop(0)
                yield msg
            else:
                # No events — check for heartbeat
                if time.time() - last_heartbeat > 15:
                    yield ": heartbeat\n\n"
                    last_heartbeat = time.time()
        time.sleep(0.1)


def sse_response():
    """Flask response that streams events to the connected client.

    Call this from a route handler to register a new SSE listener.
    The generator cleans up the listener when the client disconnects.
    """
    from flask import Response  # late import to avoid circular deps

    listener = _new_listener()
    try:
        return Response(
            _event_stream(listener),
            mimetype='text/event-stream',
            headers={'Cache-Control': 'no-cache'},
        )
    except GeneratorExit:
        _remove_listener(listener)
