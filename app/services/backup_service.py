"""
Snapshot backups for Posziona.

Implements the `snapshot_interval_minutes` setting (previously shown in
the admin UI but never wired up): a background scheduler snapshots every
party database plus the shared templates database, keeps a bounded number
of snapshots, and offers restore for disaster recovery.

Snapshots use SQLite `VACUUM INTO`, which produces a consistent,
defragmented copy even while the live database is being written to.
Only stdlib is used (sqlite3, shutil, threading).
"""

import os
import shutil
import sqlite3
import threading
import time

from app.utils.config import DATA_DIR, PARTY_DB_DIR, TEMPLATES_DB
from app.utils.logger import get_logger

logger = get_logger('services.backups')

BACKUP_DIR = os.path.join(DATA_DIR, 'backups')
DEFAULT_KEEP_COUNT = 12


def _snapshot_name():
    """Snapshot directory name (filesystem-safe UTC timestamp)."""
    return time.strftime('%Y%m%d-%H%M%S', time.gmtime())


def validate_snapshot_name(name):
    """Snapshot names are server-generated timestamps — reject anything else."""
    import re
    if not isinstance(name, str) or not re.fullmatch(r'\d{8}-\d{6}', name):
        raise ValueError(f'Invalid snapshot name: {name!r}')
    return name


def _vacuum_into(src_path, dst_path):
    """Copy a live SQLite DB to dst_path via VACUUM INTO (consistent copy)."""
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    # Path is server-generated; quote single quotes defensively.
    safe_dst = dst_path.replace("'", "''")
    conn = sqlite3.connect(f'file:{src_path}?mode=ro', uri=True)
    try:
        conn.execute(f"VACUUM INTO '{safe_dst}'")
    finally:
        conn.close()
    # Verify the snapshot itself is healthy; delete + fail loudly otherwise
    check = sqlite3.connect(dst_path)
    try:
        row = check.execute("PRAGMA integrity_check").fetchone()
        if not row or row[0] != 'ok':
            raise RuntimeError(f'Snapshot failed integrity check: {dst_path}')
    finally:
        check.close()


def run_snapshots(keep=DEFAULT_KEEP_COUNT):
    """Snapshot all party DBs + templates DB into a timestamped directory.

    Returns the snapshot name. Prunes older snapshots beyond `keep`.
    """
    os.makedirs(PARTY_DB_DIR, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    name = _snapshot_name()
    dest_dir = os.path.join(BACKUP_DIR, name)

    copied = []
    if os.path.exists(TEMPLATES_DB):
        _vacuum_into(TEMPLATES_DB, os.path.join(dest_dir, 'templates.db'))
        copied.append('templates.db')

    for filename in sorted(os.listdir(PARTY_DB_DIR)):
        if not filename.endswith('.db'):
            continue
        src = os.path.join(PARTY_DB_DIR, filename)
        if not os.path.isfile(src):
            continue
        _vacuum_into(src, os.path.join(dest_dir, filename))
        copied.append(filename)

    prune_snapshots(keep)
    logger.info(f"Snapshot {name}: backed up {len(copied)} database(s)")
    return name


def prune_snapshots(keep=DEFAULT_KEEP_COUNT):
    """Delete oldest snapshots, keeping the newest `keep`."""
    if not os.path.isdir(BACKUP_DIR):
        return
    names = sorted(
        n for n in os.listdir(BACKUP_DIR)
        if os.path.isdir(os.path.join(BACKUP_DIR, n))
    )
    for stale in names[:max(0, len(names) - keep)]:
        shutil.rmtree(os.path.join(BACKUP_DIR, stale), ignore_errors=True)
        logger.info(f"Pruned old snapshot: {stale}")


def list_snapshots():
    """List snapshots newest-first with file counts and sizes."""
    if not os.path.isdir(BACKUP_DIR):
        return []
    result = []
    for name in sorted(os.listdir(BACKUP_DIR), reverse=True):
        path = os.path.join(BACKUP_DIR, name)
        if not os.path.isdir(path):
            continue
        files = sorted(os.listdir(path))
        size = sum(
            os.path.getsize(os.path.join(path, f))
            for f in files if os.path.isfile(os.path.join(path, f))
        )
        result.append({'name': name, 'files': files, 'size': size})
    return result


def restore_party_db(db_name, snapshot):
    """Restore one party DB from a snapshot (admin-initiated disaster recovery).

    The live WAL is checkpointed first, then the snapshot copy replaces the
    live file and stale WAL/SHM sidecars are removed. Raises ValueError for
    bad names, FileNotFoundError for missing snapshots.
    """
    from app.database.connection import validate_db_name, _get_party_db_path
    validate_db_name(db_name)
    validate_snapshot_name(snapshot)

    base = db_name[:-3] if db_name.endswith('.db') else db_name
    src = os.path.join(BACKUP_DIR, snapshot, f"{base}.db")
    if not os.path.isfile(src):
        raise FileNotFoundError(f"Snapshot '{snapshot}' has no backup of '{db_name}'")

    dst = _get_party_db_path(db_name)

    from app.database.connection import _lifecycle_lock
    with _lifecycle_lock:
        # Checkpoint the live DB so no committed data lingers only in the WAL
        if os.path.exists(dst):
            conn = sqlite3.connect(dst)
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                conn.close()

        shutil.copyfile(src, dst)
        for ext in ['-wal', '-shm', '-journal']:
            p = dst + ext
            if os.path.exists(p):
                os.remove(p)

    # Force a fresh integrity verification on next open
    from app.database import connection as _conn_mod
    with _conn_mod._checked_paths_lock:
        _conn_mod._checked_paths.discard(dst)

    logger.info(f"Restored party '{db_name}' from snapshot '{snapshot}'")
    return db_name


# ============================================================
# Background scheduler
# ============================================================

_scheduler_thread = None
_scheduler_stop = threading.Event()
_last_snapshot = {}  # db filename -> epoch of last snapshot
_scheduler_lock = threading.Lock()


def _interval_minutes(db_name):
    """Per-party snapshot interval (0/None/invalid = disabled)."""
    try:
        from app.services.party_service import get_party_settings
        raw = get_party_settings(db_name).get('snapshot_interval_minutes', 5)
        minutes = float(raw)
        return minutes if minutes > 0 else 0
    except Exception:
        return 0


def _keep_count():
    """How many snapshots to retain (bounded, low-end friendly)."""
    try:
        from app.services.party_service import get_party_settings
        raw = get_party_settings('default').get('snapshot_keep_count',
                                                 DEFAULT_KEEP_COUNT)
        return max(1, int(float(raw)))
    except Exception:
        return DEFAULT_KEEP_COUNT


def scheduler_tick(now=None):
    """One scheduler pass: snapshot every party DB whose interval elapsed.

    Always includes templates.db when anything is due. Called every minute
    by the background thread; also directly callable in tests.
    """
    now = now if now is not None else time.time()
    if not os.path.isdir(PARTY_DB_DIR):
        return None

    due = []
    for filename in sorted(os.listdir(PARTY_DB_DIR)):
        if not filename.endswith('.db') or not os.path.isfile(os.path.join(PARTY_DB_DIR, filename)):
            continue
        last = _last_snapshot.get(filename, 0)
        interval = _interval_minutes(filename[:-3]) * 60
        if interval and now - last >= interval:
            due.append(filename)

    if not due:
        return None

    name = run_snapshots(keep=_keep_count())
    with _scheduler_lock:
        for filename in due:
            _last_snapshot[filename] = now
    return name


def _scheduler_loop(poll_seconds=60):
    logger.info('Backup scheduler started')
    while not _scheduler_stop.wait(poll_seconds):
        try:
            scheduler_tick()
        except Exception as e:
            # The scheduler must never take down the server
            logger.error(f"Backup scheduler tick failed: {e}")


def start_backup_scheduler():
    """Start the daemon snapshot thread (idempotent). Called by start_server()."""
    global _scheduler_thread
    with _scheduler_lock:
        if _scheduler_thread and _scheduler_thread.is_alive():
            return
        _scheduler_stop.clear()
        _scheduler_thread = threading.Thread(
            target=_scheduler_loop, name='backup-scheduler', daemon=True
        )
        _scheduler_thread.start()
