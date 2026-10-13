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
