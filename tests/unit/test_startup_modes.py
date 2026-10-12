"""
Startup-sequence audit (Phase 7f): mode prompt, no silent servers, identity.
"""
import builtins

import pytest

import app.main as main_mod


def test_select_mode_choices(monkeypatch):
    import app.main as m
    monkeypatch.setattr(builtins, 'input', lambda *a: '2')
    assert m.select_mode() == 'server'
    monkeypatch.setattr(builtins, 'input', lambda *a: '')
    assert m.select_mode() == 'all'


def test_select_mode_eof_defaults_all(monkeypatch):
    import app.main as m

    def boom(*a):
        raise EOFError
    monkeypatch.setattr(builtins, 'input', boom)
    assert m.select_mode() == 'all'


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


def test_blank_manual_entry_reprompts_no_hybrid(monkeypatch, capsys):
    """Blank must NOT start a silent local server (split-brain guard)."""
    monkeypatch.setattr('app.utils.discovery.discover', lambda *a, **k: [])
    answers = iter(['', '192.168.1.5'])
    monkeypatch.setattr(builtins, 'input', lambda *a: next(answers))
    monkeypatch.setattr(main_mod, '_server_reachable', lambda *a, **k: True)

    assert main_mod._discover_or_ask_server() == 'http://192.168.1.5:5000/'
    assert 'Ctrl-C' in capsys.readouterr().out


def test_client_auto_localhost_names_override(monkeypatch, capsys):
    """Silent localhost attach now tells how to pick another server."""
    monkeypatch.setattr(main_mod, 'check_server_ready', lambda *a, **k: True)
    monkeypatch.setattr(main_mod.webview, 'create_window', lambda **kw: object())
    monkeypatch.setattr(main_mod.webview, 'start', lambda **kw: None)
    main_mod.run_client_only()
    out = capsys.readouterr().out
    assert 'this machine' in out
    assert '--server-url' in out


def test_login_identity_markers(client):
    """Mode screen shows WHICH server this page comes from."""
    html = client.get('/').get_data(as_text=True)
    assert 'id="server-identity"' in html
    assert "t('this_server')" in html
