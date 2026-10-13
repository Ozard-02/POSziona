"""
GUI fallback: missing GTK/Qt must not kill the server.

Regression test for the v0.1.1 Linux binary dying with a pywebview
traceback on machines without GUI system libraries.
"""
import threading

import pytest

import app.main as main_mod


def _no_gui(monkeypatch):
    """Stub out everything except the webview.start failure."""
    # Blocking stub: a real server thread stays alive; _wait_for_server
    # treats a dead thread as a startup failure.
    main_mod._server_failed.clear()
    main_mod._shutdown_requested.clear()
    stop = threading.Event()
    monkeypatch.setattr(main_mod, 'start_server', lambda: stop.wait(30))
    monkeypatch.setattr(main_mod, 'check_server_ready', lambda *a, **k: True)
    monkeypatch.setattr(main_mod.webview, 'create_window', lambda **kw: object())
    main_mod._server_serving.set()
    monkeypatch.setattr('webbrowser.open', lambda *a, **k: False)

    def boom(*a, **k):
        raise Exception('You must have either QT or GTK')
    monkeypatch.setattr(main_mod.webview, 'start', boom)


import pytest


@pytest.mark.parametrize('no_browser,expected_opened', [
    (False, 'open'),
    (True, 'skip'),
])
def test_all_mode_fallback(monkeypatch, capsys, no_browser, expected_opened):
    """'all' without GUI keeps serving; browser auto-opens unless opted out."""
    _no_gui(monkeypatch)
    if no_browser:
        monkeypatch.setenv('POSZIONA_NO_BROWSER', '1')
    opened = []
    monkeypatch.setattr('webbrowser.open',
                        lambda url, new=0: opened.append(url) or True)

    def stop_at_once(timeout=None):
        raise KeyboardInterrupt
    monkeypatch.setattr(main_mod._shutdown_requested, 'wait', stop_at_once)

    main_mod.run_server_and_client()  # must not raise

    out = capsys.readouterr().out
    assert 'browser' in out
    assert f"{main_mod.HOST}:{main_mod.PORT}" in out
    if expected_opened == 'open':
        assert opened == [f'http://{main_mod.HOST}:{main_mod.PORT}/']
    else:
        assert opened == []


def test_client_mode_no_gui(monkeypatch, capsys):
    """'client' without GUI: courtesy browser open, then exit(1) with a hint."""
    _no_gui(monkeypatch)
    opened = []
    monkeypatch.setattr('webbrowser.open',
                        lambda url, new=0: opened.append(url) or True)

    with pytest.raises(SystemExit) as exc_info:
        main_mod.run_client_only(server_url='http://127.0.0.1:5000/')

    assert exc_info.value.code == 1
    assert opened == ['http://127.0.0.1:5000/']
    assert 'browser' in capsys.readouterr().out


def test_gui_missing_message_has_source_recipe(monkeypatch, capsys):
    """Fallback prints the exact source-window recipe (copy-paste ready)."""
    main_mod._gui_missing_message(Exception('no GUI'), 'http://x:5000/')
    out = capsys.readouterr().out
    assert 'system-site-packages' in out
    assert 'scripts/run_pos.py' in out


def test_second_server_exits_on_lock(monkeypatch, capsys):
    """Lock held → clean exit(1), no lingering server-less process."""
    import time as _time

    main_mod._server_failed.clear()
    main_mod._server_serving.clear()

    def lock_fail():
        # Slow refusal: reproduces the ready/lock race — the other
        # server's open port answers check_server_ready immediately,
        # before this thread reports the refusal.
        _time.sleep(0.5)
        print("ERROR: Another POSziona server is already running (lock held).")
        main_mod._server_failed.set()
    monkeypatch.setattr(main_mod, 'start_server', lock_fail)
    monkeypatch.setattr(main_mod, 'check_server_ready', lambda *a, **k: True)

    with pytest.raises(SystemExit) as exc_info:
        main_mod.run_server_only()

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert 'already running' in out
    assert 'Server ready' not in out


def test_dead_server_thread_exits(monkeypatch, capsys):
    """Server thread dying at startup → exit(1), not 'Server ready'."""
    main_mod._server_failed.clear()
    main_mod._server_serving.clear()
    monkeypatch.setattr(main_mod, 'start_server', lambda: None)
    monkeypatch.setattr(main_mod, 'check_server_ready', lambda *a, **k: False)

    with pytest.raises(SystemExit) as exc_info:
        main_mod.run_server_only()

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert 'died during startup' in out
    assert 'Server ready' not in out


def test_shutdown_flag_stops_server_loop(monkeypatch, capsys):
    """SIGTERM handler path: flag set → _serve_forever exits cleanly."""
    main_mod._shutdown_requested.clear()
    main_mod._shutdown_requested.set()
    main_mod._serve_forever()  # must return immediately, not hang
    assert 'Shutting down' in capsys.readouterr().out
    main_mod._shutdown_requested.clear()


def test_gui_install_hint_per_distro(tmp_path):
    """Distro-specific install commands; generic fallback otherwise."""
    ubuntu = tmp_path / 'os-ubuntu'
    ubuntu.write_text('NAME="Ubuntu"\nID=ubuntu\n')
    assert 'apt install' in main_mod._gui_install_hint(str(ubuntu))

    fedora = tmp_path / 'os-fedora'
    fedora.write_text('ID=fedora\n')
    assert 'dnf install' in main_mod._gui_install_hint(str(fedora))

    arch = tmp_path / 'os-arch'
    arch.write_text('ID="arch"\n')
    assert 'pacman' in main_mod._gui_install_hint(str(arch))

    assert 'distro' in main_mod._gui_install_hint(str(tmp_path / 'nope')).lower()
