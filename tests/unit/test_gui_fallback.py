"""
GUI fallback: missing GTK/Qt must not kill the server.

Regression test for the v0.1.1 Linux binary dying with a pywebview
traceback on machines without GUI system libraries.
"""
import pytest

import app.main as main_mod


def _no_gui(monkeypatch):
    """Stub out everything except the webview.start failure."""
    monkeypatch.setattr(main_mod, 'start_server', lambda: None)
    monkeypatch.setattr(main_mod, 'check_server_ready', lambda *a, **k: True)
    monkeypatch.setattr(main_mod.webview, 'create_window', lambda **kw: object())

    def boom(*a, **k):
        raise Exception('You must have either QT or GTK')
    monkeypatch.setattr(main_mod.webview, 'start', boom)


def test_all_mode_falls_back_to_server(monkeypatch, capsys):
    """'all' without GUI libs keeps serving instead of tracebacks."""
    _no_gui(monkeypatch)

    def stop_at_once(s):
        raise KeyboardInterrupt
    monkeypatch.setattr(main_mod.time, 'sleep', stop_at_once)

    main_mod.run_server_and_client()  # must not raise

    out = capsys.readouterr().out
    assert 'browser' in out
    assert f"{main_mod.HOST}:{main_mod.PORT}" in out


def test_client_mode_clean_error(monkeypatch, capsys):
    """'client' without GUI libs exits(1) with a hint, no traceback."""
    _no_gui(monkeypatch)

    with pytest.raises(SystemExit) as exc_info:
        main_mod.run_client_only(server_url='http://127.0.0.1:5000/')

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert 'browser' in out
