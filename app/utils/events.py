"""
SSE (Server-Sent Events) broadcaster for live updates.

Provides a simple in-memory pub/sub mechanism so that POS client
windows receive live product-availability and stock changes without
needing to refresh the page or poll the server.

Usage:

  from app.utils.events import broadcast

  # From a route handler:
  #   broadcast('product_update', {'product_id': 42, 'is_active': 0})
"""
import json
import threading
import time


# ── Subscription management ──────────────────────────────────
# Each listener is a dict: {'queue': [...], 'lock': threading.Lock}
_listeners = []
_listeners_lock = threading.Lock()

# Maximum events buffered per listener before old events are dropped.
# Prevents unbounded memory growth when clients are slow or disconnected.
_MAX_QUEUE_SIZE = 100

# Listener is considered stale if no client activity (popping events)
# for this many seconds. Prevents zombie SSE connections from leaking
# memory over long-running multi-hour sessions.
_STALE_TIMEOUT = 120  # 2 minutes

# Track last cleanup time for periodic stale-listener pruning
_last_prune = 0.0


def _new_listener():
    """Create and register a new SSE listener."""
    listener = {
        'queue': [],
        'lock': threading.Lock(),
        'last_active': time.time(),
    }
    with _listeners_lock:
        _listeners.append(listener)
    return listener


def _remove_listener(listener):
    """Remove a listener (called when the client disconnects)."""
    with _listeners_lock:
        try:
            _listeners.remove(listener)
        except ValueError:
            pass  # Already removed — ignore


def broadcast(event_type, data):
    """Push an event to all connected SSE listeners.

    Args:
        event_type: Event name (e.g. 'product_update').
        data: JSON-serializable dict with event payload.
    """
    payload = json.dumps(data)
    sse_message = f"event: {event_type}\ndata: {payload}\n\n"
    global _last_prune
    with _listeners_lock:
        # Periodically prune stale listeners (connected but never properly
        # closed) to prevent unbounded memory growth over long-running sessions.
        now = time.time()
        if now - _last_prune > 60:
            _listeners[:] = [l for l in _listeners if now - l['last_active'] < _STALE_TIMEOUT]
            _last_prune = now
        for listener in _listeners:
            with listener['lock']:
                # Drop oldest events if queue exceeds max size —
                # this prevents memory growth from slow/disconnected clients
                if len(listener['queue']) >= _MAX_QUEUE_SIZE:
                    del listener['queue'][:_MAX_QUEUE_SIZE // 2]
                listener['queue'].append(sse_message)


def _event_stream(listener):
    """Generator that yields SSE-formatted messages to the client.

    The generator exits (triggering GeneratorExit) when the client
    disconnects or the response is cancelled. This is the natural
    cleanup point for listener removal.
    """
    last_heartbeat = time.time()
    try:
        while True:
            with listener['lock']:
                if listener['queue']:
                    msg = listener['queue'].pop(0)
                    listener['last_active'] = time.time()
                    yield msg
                else:
                    # No events — send a heartbeat comment every 15s to
                    # keep proxies from buffering and to detect dead clients
                    if time.time() - last_heartbeat > 15:
                        yield ": heartbeat\n\n"
                        last_heartbeat = time.time()
            time.sleep(0.1)
    finally:
        # This block runs on GeneratorExit (client disconnect) or
        # when the generator is garbage-collected.
        _remove_listener(listener)


def sse_response():
    """Flask response that streams events to the connected client.

    Call this from a route handler to register a new SSE listener.
    The listener is automatically removed when the client disconnects
    (via the generator's finally block).
    """
    from flask import Response  # late import to avoid circular deps

    listener = _new_listener()
    return Response(
        _event_stream(listener),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache'},
    )
