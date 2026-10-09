"""
Crash-safety: accidental closures lose nothing and break nothing.

- Login cookie survives browser restarts (permanent session), so the
  operator and the unsent cart are still there after a client close.
- SIGTERM checkpoints WALs and exits 0 (systemd/docker/kill).
- Snapshots are atomic: kill mid-snapshot leaves .tmp debris that is
  never listed for restore and gets pruned.
"""
import os
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_login_cookie_survives_browser_restart(client, clean_db):
    """Session cookie carries Expires (not a browser-session cookie)."""
    r = client.post(f'/api/auth/login?db={clean_db}', json={'pin': '1234'})
    assert r.status_code == 200
    cookies = r.headers.getlist('Set-Cookie')
    assert cookies, 'login must set a session cookie'
    assert any('Expires=' in c for c in cookies), cookies


def test_checkpoint_all_truncates_wal():
    """Kill -9 a writer holding an open connection, then checkpoint.

    Mirrors the shutdown path: -wal left behind with no live connections
    must fold back into the main file, committed rows intact.
    """
    from app.database.connection import _get_party_db_path
    from app.services.backup_service import checkpoint_all

    path = os.path.normpath(_get_party_db_path('ckpt_test'))
    for ext in ('', '-wal', '-shm', '-journal'):
        if os.path.exists(path + ext):
            os.remove(path + ext)

    worker = (
        "import sys, time; sys.path.insert(0, '.');"
        "import sqlite3;"
        "from app.database.connection import _get_party_db_path;"
        "from app.database.schema import get_party_schema;"
        "p = _get_party_db_path('ckpt_test');"
        "c = sqlite3.connect(p);"
        "c.execute('PRAGMA journal_mode=WAL');"
        "c.executescript(get_party_schema());"
        "c.execute(\"INSERT INTO sections (name) VALUES ('CkptSurvivor')\");"
        "c.commit();"  # committed, connection kept open -> -wal lingers
        "time.sleep(30)"
    )
    proc = subprocess.Popen(
        [sys.executable, '-c', worker],
        cwd=REPO_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(4.0)  # imports + one committed write, then idle with -wal
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=30)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

    try:
        assert os.path.exists(path + '-wal'), 'kill should leave a -wal behind'
        checkpoint_all()
        assert not os.path.exists(path + '-wal'), 'WAL must fold back'
        conn = sqlite3.connect(path)
        try:
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == 'ok'
            assert conn.execute(
                "SELECT COUNT(*) FROM sections WHERE name = 'CkptSurvivor'"
            ).fetchone()[0] == 1
        finally:
            conn.close()
    finally:
        for ext in ('', '-wal', '-shm', '-journal'):
            if os.path.exists(path + ext):
                os.remove(path + ext)


def test_snapshot_is_atomic_and_tmp_invisible(client, clean_db):
    """run_snapshots publishes complete dirs only; .tmp never listed."""
    from app.services.backup_service import (
        BACKUP_DIR, list_snapshots, prune_snapshots, run_snapshots,
    )

    os.makedirs(os.path.join(BACKUP_DIR, '20990101-000000.tmp'))
    try:
        name = run_snapshots()
        assert os.path.isdir(os.path.join(BACKUP_DIR, name))
        leftovers = [n for n in os.listdir(BACKUP_DIR) if n.endswith('.tmp')]
        assert leftovers == [], leftovers
        assert all(not s['name'].endswith('.tmp') for s in list_snapshots())
    finally:
        shutil.rmtree(os.path.join(BACKUP_DIR, name), ignore_errors=True)
        prune_snapshots()


def _wait_port(port, timeout=15):
    start = time.time()
    while time.time() - start < timeout:
        try:
            sock = socket.create_connection(('127.0.0.1', port), timeout=1)
            sock.close()
            return True
        except OSError:
            time.sleep(0.3)
    return False


def test_sigterm_checkpoints_and_exits_zero(tmp_path):
    """Real server: SIGTERM → checkpoint message + exit code 0."""
    data_dir = tmp_path / 'sigterm-data'
    env = dict(os.environ, POSZIONA_DATA_DIR=str(data_dir))
    proc = subprocess.Popen(
        [sys.executable, 'scripts/run_pos.py', '--mode', 'server'],
        cwd=REPO_ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        assert _wait_port(5000), 'server did not come up in time'
        proc.send_signal(signal.SIGTERM)
        out = proc.communicate(timeout=20)[0]
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    assert proc.returncode == 0, out
    assert 'Checkpoint' in out, out
