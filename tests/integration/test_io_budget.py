"""Background I/O budget: snapshots and SSE must not work harder than needed.

These behaviours are invisible in normal use and expensive in the field:
a party box left on for a month on an SD card.
"""
import os
import sqlite3

import pytest

import app.services.backup_service as backups


def _make_db(path):
    conn = sqlite3.connect(str(path))
    conn.execute('CREATE TABLE IF NOT EXISTS t (x INTEGER)')
    conn.execute('INSERT INTO t VALUES (1)')
    conn.commit()
    conn.close()
    return str(path)


def test_scheduler_snapshots_only_the_due_parties(tmp_path, monkeypatch):
    """One party's interval elapsing must not rewrite every party DB."""
    calls = []
    (tmp_path / 'due.db').write_bytes(b'')
    (tmp_path / 'fresh.db').write_bytes(b'')
    monkeypatch.setattr(backups, 'PARTY_DB_DIR', str(tmp_path))
    monkeypatch.setattr(backups, 'run_snapshots',
                        lambda keep=None, only=None: calls.append(only) or 'snap')
    monkeypatch.setattr(backups, '_interval_minutes', lambda name: 5)
    monkeypatch.setattr(backups, '_prune_idempotency_keys', lambda: None)

    backups._last_snapshot.clear()
    backups._last_snapshot['fresh.db'] = 10_000
    name = backups.scheduler_tick(now=10_001)

    assert name == 'snap'
    assert calls == [['due.db']]  # fresh.db is not due, templates not here


def test_prune_runs_hourly_not_every_tick(tmp_path, monkeypatch):
    """The key/snapshot prune opens every DB: once an hour, not once a minute."""
    calls = []
    monkeypatch.setattr(backups, 'PARTY_DB_DIR', str(tmp_path))  # empty
    monkeypatch.setattr(backups, 'prune_snapshots',
                        lambda keep=None: calls.append('snapshots'))
    monkeypatch.setattr(backups, '_prune_idempotency_keys',
                        lambda: calls.append('keys'))
    backups._last_prune = 0.0

    backups.scheduler_tick(now=1000)
    backups.scheduler_tick(now=1060)
    assert calls == ['snapshots', 'keys']

    backups.scheduler_tick(now=1000 + backups._PRUNE_INTERVAL + 1)
    assert calls == ['snapshots', 'keys', 'snapshots', 'keys']


def test_partial_snapshot_contains_only_the_requested_db(tmp_path, monkeypatch):
    """`only=` writes the asked-for party plus the tiny templates DB."""
    parties = tmp_path / 'parties'
    parties.mkdir()
    _make_db(parties / 'one.db')
    _make_db(parties / 'two.db')
    templates = _make_db(tmp_path / 'templates.db')
    monkeypatch.setattr(backups, 'PARTY_DB_DIR', str(parties))
    monkeypatch.setattr(backups, 'TEMPLATES_DB', templates)
    monkeypatch.setattr(backups, 'BACKUP_DIR', str(tmp_path / 'backups'))

    name = backups.run_snapshots(only=['one.db'])

    files = sorted(os.listdir(os.path.join(backups.BACKUP_DIR, name)))
    assert files == ['one.db', 'templates.db']


def test_order_lookup_indexes_exist(clean_db):
    from app.database.connection import PartyDatabase
    with PartyDatabase(clean_db) as conn:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
    assert {'idx_order_items_product', 'idx_payments_order'} <= names


def test_sse_listener_cap(app, monkeypatch):
    """Each listener is a thread polling at 10 Hz: cap the total and answer
    the extra screen with a plain 503 instead of spawning it."""
    from app.utils import events
    events._listeners.clear()
    try:
        for _ in range(events._MAX_LISTENERS):
            events._new_listener()
        with pytest.raises(events.ListenerLimitError):
            events._new_listener()
    finally:
        events._listeners.clear()

    def _full():
        raise events.ListenerLimitError('full')

    monkeypatch.setattr(events, '_new_listener', _full)
    with app.test_request_context('/api/events'):
        body, status = events.sse_response()
    assert status == 503
    assert 'error' in body.get_json()
