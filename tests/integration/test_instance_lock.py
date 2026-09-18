"""
Instance-lock tests: a second server process must fail to take the lock.
"""
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_second_process_cannot_acquire():
    from app.utils.instance_lock import acquire, owner_pid

    assert acquire() is True
    assert owner_pid() == str(os.getpid())

    # A separate process attempting the same lock must fail
    proc = subprocess.run(
        [sys.executable, '-c',
         "import sys; sys.path.insert(0, '.'); "
         "from app.utils.instance_lock import acquire; "
         "sys.exit(0 if acquire() else 3)"],
        cwd=REPO_ROOT,
        capture_output=True,
        timeout=60,
    )
    assert proc.returncode == 3
