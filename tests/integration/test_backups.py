"""
Backups, restore, ?db= sanitization, and corruption-recovery tests.
"""
import os
import sqlite3

import pytest

import app.services.backup_service as backups
from app.utils.config import PARTY_DB_DIR


@pytest.fixture
def isolated_backups(tmp_path, monkeypatch):
    """Point the snapshot directory at a tmp dir (never touch prod backups)."""
    monkeypatch.setattr(backups, 'BACKUP_DIR', str(tmp_path / 'backups'))
    return str(tmp_path / 'backups')


def _setup_sale(client, db_name):
    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})
    client.post(f'/api/products/sections?db={db_name}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db_name}',
                json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db_name}', json={
        'name': 'Coffee', 'price': 2.50, 'section_id': 1, 'subsection_id': 1})
    client.post(f'/api/cart/add?db={db_name}', json={'product_id': 1, 'quantity': 1})
    r = client.post(f'/api/orders/checkout?db={db_name}', json={'payment_method': 'cash'})
    assert r.status_code == 201


def test_snapshot_lists_and_prunes(clean_db, client, isolated_backups):
    db_name = clean_db
    _setup_sale(client, db_name)

    name = backups.run_snapshots(keep=10)
    assert os.path.isdir(os.path.join(isolated_backups, name))

    snaps = backups.list_snapshots()
    assert len(snaps) == 1
    assert snaps[0]['name'] == name
    assert f'{db_name}.db' in snaps[0]['files']

    # Snapshot copy is itself healthy
    check = sqlite3.connect(os.path.join(isolated_backups, name, f'{db_name}.db'))
    assert check.execute("PRAGMA integrity_check").fetchone()[0] == 'ok'
    check.close()

    # Prune keeps only the newest N
    backups.prune_snapshots(keep=0)
    assert backups.list_snapshots() == []


def test_backup_api_list_and_trigger(clean_db, client, isolated_backups):
    db_name = clean_db
    _setup_sale(client, db_name)

    r = client.get('/api/parties/backups')
    assert r.status_code == 200
    assert r.get_json() == []

    client.post(f'/api/auth/logout?db={db_name}')
    r = client.post('/api/parties/backups')
    assert r.status_code == 403  # admin only
    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})
    r = client.post('/api/parties/backups')
    assert r.status_code == 201
    assert 'snapshot' in r.get_json()

    r = client.get('/api/parties/backups')
    assert len(r.get_json()) == 1


def test_restore_round_trip(clean_db, client, isolated_backups):
    """Snapshot with 1 order → sell more → restore → back to 1 order."""
    db_name = clean_db
    _setup_sale(client, db_name)

    name = backups.run_snapshots(keep=10)

    # Sell one more (now 2 orders live)
    client.post(f'/api/cart/add?db={db_name}', json={'product_id': 1, 'quantity': 1})
    r = client.post(f'/api/orders/checkout?db={db_name}', json={'payment_method': 'cash'})
    assert r.status_code == 201
    assert client.get(f'/api/orders/report/summary?db={db_name}').get_json()['total_orders'] == 2

    # Restore requires admin — login first (already admin from _setup_sale)
    r = client.post(f'/api/parties/{db_name}/restore', json={'snapshot': name})
    assert r.status_code == 200

    summary = client.get(f'/api/orders/report/summary?db={db_name}').get_json()
    assert summary['total_orders'] == 1

    # Unknown snapshot → 404, bad name → 400
    r = client.post(f'/api/parties/{db_name}/restore', json={'snapshot': '20990101-000000'})
    assert r.status_code == 404
    r = client.post(f'/api/parties/{db_name}/restore', json={'snapshot': '../evil'})
    assert r.status_code == 400


def test_db_param_traversal_rejected(client):
    """?db= must not escape the party directory."""
    for evil in ('../templates', '..', '/etc/passwd', '/abs/path',
                 '..\\windows', 'a/b', '', 'x\x00y'):
        r = client.get(f'/api/products/?db={evil}')
        assert r.status_code == 400, evil
        assert 'error' in r.get_json()

    # Sane names still work (DB auto-created)
    r = client.get('/api/products/?db=festa-2026_party')
    assert r.status_code == 200


def test_corrupt_db_quarantined_and_recreated(client):
    """A corrupt DB file is quarantined aside and a fresh DB takes over."""
    from app.database.connection import PartyDatabase, _get_party_db_path
    from app.database import connection as conn_mod

    db_name = 'corrupt_recovery_test'
    with PartyDatabase(db_name):
        pass
    path = _get_party_db_path(db_name)
    assert os.path.exists(path)

    # Trash the file
    with open(path, 'wb') as f:
        f.write(b'\x00\x01GARBAGE-NOT-SQLITE' * 100)

    with PartyDatabase(db_name) as conn:
        # Fresh DB works — settings table exists
        conn.execute("SELECT key, value FROM settings LIMIT 1").fetchall()

    # Original bytes preserved under a .corrupt-* name
    siblings = os.listdir(PARTY_DB_DIR)
    assert any(s.startswith(os.path.basename(path) + '.corrupt-') for s in siblings)

    # Cleanup (live + quarantine), reset checked-paths for this db
    for s in list(siblings):
        if s.startswith(os.path.basename(path)):
            for ext in ('', '-wal', '-shm', '-journal'):
                p = os.path.join(PARTY_DB_DIR, s + ext) if ext else os.path.join(PARTY_DB_DIR, s)
                if os.path.exists(p):
                    os.remove(p)
    with conn_mod._checked_paths_lock:
        conn_mod._checked_paths.discard(path)
