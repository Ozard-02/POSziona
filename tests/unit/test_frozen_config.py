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
