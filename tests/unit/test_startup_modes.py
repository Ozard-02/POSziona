"""
Startup-sequence audit (Phase 7f): mode prompt, no silent servers, identity.
"""
import builtins

import pytest

import app.main as main_mod


@pytest.mark.parametrize('answer,expected', [('2', 'server'), ('', 'all'), ('EOF', 'all')])
def test_select_mode(monkeypatch, answer, expected):
    """Choices map to modes; blank and EOF fall back to 'all'."""
    if answer == 'EOF':
        def boom(*a):
            raise EOFError
        monkeypatch.setattr(builtins, 'input', boom)
    else:
        monkeypatch.setattr(builtins, 'input', lambda *a: answer)
    assert main_mod.select_mode() == expected


def test_main_no_mode_non_tty_defaults_all(monkeypatch, capsys):
    """Double-clicked binary / pipe: no prompt, straight to 'all'."""
    called = []
    monkeypatch.setattr(main_mod, 'run_server_and_client',
                        lambda: called.append(True))
    monkeypatch.setattr('sys.stdin.isatty', lambda: False)
    main_mod.main(mode=None)
    assert called == [True]
    assert 'Mode: all' in capsys.readouterr().out


def test_main_no_mode_tty_prompts(monkeypatch):
    """Terminal without flags: the (previously dead) prompt is used."""
    called = []
    monkeypatch.setattr(main_mod, 'run_server_only',
                        lambda: called.append(True))
    monkeypatch.setattr('sys.stdin.isatty', lambda: True)
    monkeypatch.setattr(builtins, 'input', lambda *a: '2')
    main_mod.main(mode=None)
    assert called == [True]


def test_client_auto_localhost_names_override(monkeypatch, capsys):
    """Silent localhost attach now tells how to pick another server."""
    class FakeWebview:
        settings = {}

        def create_window(self, **kw):
            return object()

        def start(self, **kw):
            return None

    monkeypatch.setattr(main_mod, 'webview', FakeWebview())
    monkeypatch.setattr(main_mod, 'check_server_ready', lambda *a, **k: True)
    main_mod.run_client_only()
    out = capsys.readouterr().out
    assert 'this machine' in out
    assert '--server-url' in out


def test_login_identity_markers(client):
    """Mode screen shows WHICH server this page comes from."""
    html = client.get('/').get_data(as_text=True)
    assert 'id="server-identity"' in html
    assert "t('this_server')" in html


def test_server_start_warns_about_live_network_server(monkeypatch, capsys):
    """Second box starting up warns (split-brain) instead of silently forking sales."""
    import time as _time
    monkeypatch.setattr('app.utils.discovery.discover', lambda *a, **k: [
        {'name': 'CASSA-1', 'host': '192.168.1.10', 'port': 5000,
         'url': 'http://192.168.1.10:5000/', 'version': '0.1.6'}])
    monkeypatch.setattr(_time, 'sleep', lambda *a: None)

    main_mod._warn_if_other_server_live()

    out = capsys.readouterr().out
    assert 'another POSziona server' in out
    assert 'CASSA-1' in out and 'http://192.168.1.10:5000/' in out
    assert 'two different places' in out


def test_server_start_quiet_when_alone(monkeypatch, capsys):
    """No beacons → no warning, no delay."""
    import time as _time
    calls = []
    monkeypatch.setattr('app.utils.discovery.discover',
                        lambda *a, **k: [])
    monkeypatch.setattr(_time, 'sleep', lambda s: calls.append(s))

    main_mod._warn_if_other_server_live()

    assert capsys.readouterr().out == ''
    assert calls == []


def test_server_check_opt_out(monkeypatch):
    """POSZIONA_NO_SERVER_CHECK=1 skips the listen (scripts, tests)."""
    monkeypatch.setenv('POSZIONA_NO_SERVER_CHECK', '1')
    monkeypatch.setattr('app.utils.discovery.discover',
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    main_mod._warn_if_other_server_live()  # must not raise
