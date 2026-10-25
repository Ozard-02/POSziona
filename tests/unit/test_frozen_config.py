"""
Frozen-build config: DATA_DIR must survive outside the PyInstaller bundle.

Regression test for the v0.1.1 Linux binary storing parties/templates/
secret key/lock file inside sys._MEIPASS (wiped on exit).
"""
import importlib
import os
import sys

import pytest

import app.utils.config as config


def test_default_data_dir_source_mode():
    assert config._default_data_dir(False) == os.path.join(config.BASE_DIR, 'data')


def test_default_data_dir_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(os.path, 'expanduser', lambda p: str(tmp_path))
    assert config._default_data_dir(True) == os.path.join(str(tmp_path), '.posziona')


def test_env_override_wins(monkeypatch, tmp_path):
    """POSZIONA_DATA_DIR redirects all derived paths (frozen or not)."""
    target = tmp_path / 'custom-data'
    monkeypatch.setenv('POSZIONA_DATA_DIR', str(target))
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    try:
        reloaded = importlib.reload(config)
        assert reloaded.DATA_DIR == str(target)
        assert reloaded.PARTY_DB_DIR == os.path.join(str(target), 'parties')
        assert reloaded.TEMPLATES_DB == os.path.join(str(target), 'templates.db')
        assert reloaded.SECRET_KEY_FILE == os.path.join(str(target), '.secret_key')
        assert os.path.isdir(reloaded.PARTY_DB_DIR)
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_source_mode_unchanged():
    """Dev/test runs still use <repo>/app/data (no override active)."""
    if os.environ.get('POSZIONA_DATA_DIR'):
        pytest.skip('POSZIONA_DATA_DIR override active')
    assert config.DATA_DIR == os.path.join(config.BASE_DIR, 'data')


def test_secret_key_stable_and_owner_only(monkeypatch, tmp_path):
    """First boot creates the key once (0600); later boots reuse it (R15)."""
    path = tmp_path / '.secret_key'
    monkeypatch.setattr(config, 'SECRET_KEY_FILE', str(path))
    monkeypatch.delenv('POSZIONA_SECRET_KEY', raising=False)

    first = config.get_secret_key()
    assert path.exists()
    assert (path.stat().st_mode & 0o777) == 0o600
    assert config.get_secret_key() == first


def test_secret_key_never_overwrites_a_concurrent_first_boot(monkeypatch, tmp_path):
    """Our stale 'missing' check must not clobber the winner's key (R15).

    Simulates the race window: this process checked the file before the
    other boot created it. Exclusive create + read-back keeps both
    processes on the SAME key instead of silently diverging.
    """
    path = tmp_path / '.secret_key'
    path.write_text('winner-key\n')
    monkeypatch.setattr(config, 'SECRET_KEY_FILE', str(path))
    monkeypatch.delenv('POSZIONA_SECRET_KEY', raising=False)
    # Stale view of the world, as in the old check-then-create race
    monkeypatch.setattr(os.path, 'exists', lambda p: False)

    assert config.get_secret_key() == 'winner-key'
    assert path.read_text().strip() == 'winner-key'
