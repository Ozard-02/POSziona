"""
GUI fallback: missing GTK/Qt must not kill the server.

Regression test for the v0.1.1 Linux binary dying with a pywebview
traceback on machines without GUI system libraries.
"""
import os
import threading

import pytest

import app.main as main_mod


def _no_gui(monkeypatch):
    """Stub everything except the webview.start failure."""
    # Blocking stub: a real server thread stays alive; _wait_for_server
    # treats a dead thread as a startup failure.
    main_mod._server_failed.clear()
    main_mod._shutdown_requested.clear()
    stop = threading.Event()
    monkeypatch.setattr(main_mod, 'start_server', lambda: stop.wait(30))
    monkeypatch.setattr(main_mod, 'check_server_ready', lambda *a, **k: True)
    monkeypatch.setattr('app.utils.discovery.discover', lambda *a, **k: [])
    main_mod._server_serving.set()
    monkeypatch.setattr('webbrowser.open', lambda *a, **k: False)

    class FakeWebview:
        settings = {}

        def create_window(self, **kw):
            return object()

        def start(self, **kw):
            raise Exception('You must have either QT or GTK')

    # Non-None global: _get_webview() uses it without a real import
    monkeypatch.setattr(main_mod, 'webview', FakeWebview())


def _no_webview_at_all(monkeypatch):
    """pywebview PACKAGE missing: the lazy import itself raises (G1)."""
    main_mod._server_failed.clear()
    main_mod._shutdown_requested.clear()
    stop = threading.Event()
    monkeypatch.setattr(main_mod, 'start_server', lambda: stop.wait(30))
    monkeypatch.setattr(main_mod, 'check_server_ready', lambda *a, **k: True)
    monkeypatch.setattr('app.utils.discovery.discover', lambda *a, **k: [])
    main_mod._server_serving.set()
    monkeypatch.setattr(main_mod, 'webview', None)

    def _import_boom():
        raise ImportError("No module named 'webview'")
    monkeypatch.setattr(main_mod, '_get_webview', _import_boom)


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


def test_all_mode_pywebview_missing_degrades(monkeypatch, capsys):
    """No pywebview package at all: server keeps serving, browser opens (G1).

    Regression: a top-level `import webview` used to kill the process
    before any mode decision — even plain server mode died.
    """
    _no_webview_at_all(monkeypatch)
    opened = []
    monkeypatch.setattr('webbrowser.open',
                        lambda url, new=0: opened.append(url) or True)

    def stop_at_once(timeout=None):
        raise KeyboardInterrupt
    monkeypatch.setattr(main_mod._shutdown_requested, 'wait', stop_at_once)

    main_mod.run_server_and_client()  # must not raise

    out = capsys.readouterr().out
    assert 'server-only' in out
    assert 'browser' in out
    assert opened == [f'http://{main_mod.HOST}:{main_mod.PORT}/']


def test_client_mode_pywebview_missing_exits_with_hint(monkeypatch, capsys):
    """No pywebview package in client mode: browser + exit(1) + recipe (G1)."""
    _no_webview_at_all(monkeypatch)
    opened = []
    monkeypatch.setattr('webbrowser.open',
                        lambda url, new=0: opened.append(url) or True)

    with pytest.raises(SystemExit) as exc_info:
        main_mod.run_client_only(server_url='http://127.0.0.1:5000/')

    assert exc_info.value.code == 1
    assert opened == ['http://127.0.0.1:5000/']
    out = capsys.readouterr().out
    assert 'browser' in out
    assert 'system-site-packages' in out  # the one-time setup recipe


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


def test_start_window_retries_qt_when_default_fails(monkeypatch, capsys):
    """Broken default backend → exactly one retry with PYWEBVIEW_GUI=qt (G2)."""
    attempts = []

    class View:
        def start(self, debug=False, private_mode=False):
            attempts.append(os.environ.get('PYWEBVIEW_GUI'))
            if len(attempts) == 1:
                raise Exception('GTK backend exploded')

    monkeypatch.delenv('PYWEBVIEW_GUI', raising=False)
    monkeypatch.setattr(main_mod, '_qt_backend_available', lambda: True)

    ok, exc = main_mod._start_window(View())

    assert ok is True and exc is None
    assert attempts == [None, 'qt']
    assert 'PYWEBVIEW_GUI' not in os.environ  # environment restored
    assert 'backend' in capsys.readouterr().out  # failure is reported


def test_start_window_no_retry_without_qt(monkeypatch):
    """Without Qt installed there is nothing to retry: fail straight away."""
    attempts = []

    class View:
        def start(self, debug=False, private_mode=False):
            attempts.append(True)
            raise Exception('no GUI at all')

    monkeypatch.delenv('PYWEBVIEW_GUI', raising=False)
    monkeypatch.setattr(main_mod, '_qt_backend_available', lambda: False)

    ok, exc = main_mod._start_window(View())

    assert ok is False
    assert isinstance(exc, Exception)
    assert len(attempts) == 1


def test_start_window_respects_explicit_backend(monkeypatch):
    """An explicit PYWEBVIEW_GUI is respected: single attempt, env intact."""
    attempts = []

    class View:
        def start(self, debug=False, private_mode=False):
            attempts.append(os.environ.get('PYWEBVIEW_GUI'))
            raise Exception('forced backend failed')

    monkeypatch.setenv('PYWEBVIEW_GUI', 'gtk')
    monkeypatch.setattr(main_mod, '_qt_backend_available', lambda: True)

    ok, _ = main_mod._start_window(View())

    assert ok is False
    assert attempts == ['gtk']
    assert os.environ['PYWEBVIEW_GUI'] == 'gtk'


def test_gui_check_ok(capsys):
    """Doctor: pywebview + GTK + display → exit 0, no install recipe (G3)."""
    state = {
        'webview': '5.0',
        'gtk': (True, 'Gtk 3.0 + WebKit2 4.1'),
        'qt': [],
        'cef': False,
        'display': 'DISPLAY=:0',
    }
    assert main_mod.gui_check(state) == 0
    out = capsys.readouterr().out
    assert 'installed (5.0)' in out
    assert 'GTK backend:     OK' in out
    assert 'DISPLAY=:0' in out
    assert 'can open' in out
    assert 'system-site-packages' not in out


def test_gui_check_no_backend_falls_back(capsys):
    """Doctor: no backend → exit 1 with distro hint + source recipe (G3)."""
    state = {
        'webview': '5.0',
        'gtk': (False, 'PyGObject (python3-gi) not installed'),
        'qt': [],
        'cef': False,
        'display': 'DISPLAY=:0',
    }
    assert main_mod.gui_check(state) == 1
    out = capsys.readouterr().out
    assert 'fall back to the browser' in out
    assert 'To enable the desktop window' in out
    assert 'system-site-packages' in out


def test_gui_check_missing_display(capsys):
    """Doctor: backend present but no display → exit 1, says why (G3)."""
    state = {
        'webview': '5.0',
        'gtk': (True, 'Gtk 3.0 + WebKit2 4.1'),
        'qt': ['qtpy'],
        'cef': False,
        'display': None,
    }
    assert main_mod.gui_check(state) == 1
    out = capsys.readouterr().out
    assert 'MISSING (no DISPLAY/WAYLAND_DISPLAY)' in out
    assert 'fall back to the browser' in out


def test_cli_gui_check_exits_with_doctor_code(monkeypatch):
    """--gui-check runs the doctor and exits with its code (G3)."""
    codes = []
    monkeypatch.setattr(main_mod, 'gui_check', lambda: codes.append(1) or 1)
    with pytest.raises(SystemExit) as exc_info:
        main_mod.parse_args(['--gui-check'])
    assert exc_info.value.code == 1
    assert codes == [1]


def _impossible_state():
    """This Python cannot open a window: no GTK/Qt/CEF, display present."""
    return {
        'webview': '5.0',
        'gtk': (False, 'PyGObject (python3-gi) not installed'),
        'qt': [],
        'cef': False,
        'display': 'DISPLAY=:0',
    }


def test_auto_setup_skips_when_disabled_or_pointless(monkeypatch):
    """Opt-out, working Python and headless boxes never touch disk (G6)."""
    for var in ('POSZIONA_NO_AUTO_WINDOW_SETUP',
                'POSZIONA_AUTO_WINDOW_SETUP_TRIED'):
        monkeypatch.delenv(var, raising=False)
    calls = []
    monkeypatch.setattr(main_mod.subprocess, 'run',
                        lambda *a, **k: calls.append(a) or object())

    monkeypatch.setenv('POSZIONA_NO_AUTO_WINDOW_SETUP', '1')
    assert main_mod._maybe_auto_setup_window() is False
    assert calls == []

    monkeypatch.delenv('POSZIONA_NO_AUTO_WINDOW_SETUP')
    monkeypatch.setattr(main_mod, '_gui_detect_state',
                        lambda: dict(_impossible_state(),
                                    gtk=(True, 'Gtk 3.0 + WebKit2 4.1')))
    assert main_mod._maybe_auto_setup_window() is False
    assert calls == []

    monkeypatch.setattr(main_mod, '_gui_detect_state',
                        lambda: dict(_impossible_state(), display=None))
    assert main_mod._maybe_auto_setup_window() is False
    assert calls == []


def test_auto_setup_creates_venv_and_reexecs(monkeypatch, tmp_path):
    """No window backend → syswin venv created once, then execv into it (G6)."""
    root = tmp_path
    (root / 'scripts').mkdir()
    (root / 'scripts' / 'run_pos.py').write_text('# stub\n')
    monkeypatch.setattr(main_mod, '_APP_ROOT', str(root))
    for var in ('POSZIONA_NO_AUTO_WINDOW_SETUP',
                'POSZIONA_AUTO_WINDOW_SETUP_TRIED'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(main_mod, '_running_inside_syswin', lambda: False)
    monkeypatch.setattr(main_mod, '_gui_detect_state', _impossible_state)
    monkeypatch.setattr(main_mod.shutil, 'which',
                        lambda name: '/usr/bin/python3')
    monkeypatch.setattr(main_mod.sys, 'argv',
                        ['run_pos.py', '--mode', 'all'])

    commands = []

    class Proc:
        returncode = 0

    def fake_run(cmd, **kw):
        commands.append(cmd)
        return Proc()

    monkeypatch.setattr(main_mod.subprocess, 'run', fake_run)

    exec_calls = []

    def fake_execv(path, argv):
        exec_calls.append((path, argv))
        raise SystemExit(0)

    monkeypatch.setattr(main_mod.os, 'execv', fake_execv)

    with pytest.raises(SystemExit):
        main_mod._maybe_auto_setup_window()

    syswin = str(root / 'syswin')
    venv_python = str(root / 'syswin' / 'bin' / 'python')
    script = str(root / 'scripts' / 'run_pos.py')
    assert commands[0] == ['/usr/bin/python3', '-m', 'venv',
                           '--system-site-packages', syswin]
    assert commands[1][0] == venv_python          # dependency probe
    assert len(commands) == 2                     # probe OK → no pip run
    assert exec_calls == [(venv_python,
                           [venv_python, script, '--mode', 'all'])]
    assert os.environ['POSZIONA_AUTO_WINDOW_SETUP_TRIED'] == '1'
    monkeypatch.delenv('POSZIONA_AUTO_WINDOW_SETUP_TRIED')


def test_auto_setup_installs_deps_when_probe_fails(monkeypatch, tmp_path):
    """Existing venv without flask/pywebview → pip install, then execv (G6)."""
    root = tmp_path
    (root / 'scripts').mkdir()
    (root / 'scripts' / 'run_pos.py').write_text('# stub\n')
    venv_bin = root / 'syswin' / 'bin'
    venv_bin.mkdir(parents=True)
    (venv_bin / 'python').write_text('')  # venv already exists
    monkeypatch.setattr(main_mod, '_APP_ROOT', str(root))
    for var in ('POSZIONA_NO_AUTO_WINDOW_SETUP',
                'POSZIONA_AUTO_WINDOW_SETUP_TRIED'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(main_mod, '_running_inside_syswin', lambda: False)
    monkeypatch.setattr(main_mod, '_gui_detect_state', _impossible_state)
    monkeypatch.setattr(main_mod.shutil, 'which',
                        lambda name: '/usr/bin/python3')

    commands = []

    class Proc:
        def __init__(self, returncode):
            self.returncode = returncode

    def fake_run(cmd, **kw):
        commands.append(cmd)
        if cmd[1:3] == ['-c', 'import flask, webview']:
            return Proc(1)  # deps missing
        return Proc(0)

    monkeypatch.setattr(main_mod.subprocess, 'run', fake_run)
    exec_calls = []
    monkeypatch.setattr(main_mod.os, 'execv',
                        lambda path, argv: exec_calls.append((path, argv)))

    assert main_mod._maybe_auto_setup_window() is False  # execv stub returns

    assert commands[0][1:3] == ['-c', 'import flask, webview']  # probe
    pip = commands[1]
    assert pip[1:4] == ['-m', 'pip', 'install']
    assert 'flask' in pip and 'pywebview' in pip
    assert len(exec_calls) == 1
    monkeypatch.delenv('POSZIONA_AUTO_WINDOW_SETUP_TRIED')


def test_auto_setup_failure_falls_back_to_browser(monkeypatch, tmp_path, capsys):
    """Any setup failure: no execv, clear message, browser fallback (G6)."""
    root = tmp_path
    (root / 'scripts').mkdir()
    (root / 'scripts' / 'run_pos.py').write_text('# stub\n')
    monkeypatch.setattr(main_mod, '_APP_ROOT', str(root))
    for var in ('POSZIONA_NO_AUTO_WINDOW_SETUP',
                'POSZIONA_AUTO_WINDOW_SETUP_TRIED'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(main_mod, '_running_inside_syswin', lambda: False)
    monkeypatch.setattr(main_mod, '_gui_detect_state', _impossible_state)
    monkeypatch.setattr(main_mod.shutil, 'which',
                        lambda name: '/usr/bin/python3')

    def boom(cmd, **kw):
        raise main_mod.subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(main_mod.subprocess, 'run', boom)
    exec_calls = []
    monkeypatch.setattr(main_mod.os, 'execv',
                        lambda path, argv: exec_calls.append((path, argv)))

    assert main_mod._maybe_auto_setup_window() is False
    assert exec_calls == []
    assert 'using the browser instead' in capsys.readouterr().out
