"""
SSE broadcaster liveness tests (R3/R4 audit 2026-10-25).

events.py had NO tests at all; these drive the real generator against a
hand-built listener (no Flask app needed).
"""
import threading
import time

from app.utils import events


def _registered_listener():
    """A REAL registered listener (module-private factory, exact shape)."""
    return events._new_listener()


def test_broadcast_not_blocked_by_suspended_yield():
    """A generator frozen at yield (slow client) must not block broadcasts.

    Regression R3: the old code yielded INSIDE `with listener['lock']`;
    the suspended frame kept the lock, and disconnecting/hung clients
    stalled every broadcast() in the app, checkout included.
    """
    listener = _registered_listener()
    gen = events._event_stream(listener)
    listener['queue'].append('event: tick\ndata: {}\n\n')

    first = next(gen)  # pops the event, suspends at yield — outside the lock
    assert first == 'event: tick\ndata: {}\n\n'

    done = threading.Event()

    def _broadcast():
        events.broadcast('tick', {'n': 1})  # must NOT wait on the lock
        done.set()

    t = threading.Thread(target=_broadcast, daemon=True)
    t.start()
    assert done.wait(2), 'broadcast blocked while a listener sat at yield'
    assert listener['queue'] == ['event: tick\ndata: {"n": 1}\n\n']

    gen.close()  # GeneratorExit → listener unregistered
    assert events.listener_count() == 0
