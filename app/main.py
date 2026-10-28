"""
Entry point for Posziona application with pywebview.
Launches the Flask server in a background thread and wraps it
in a native pywebview desktop window.

Startup modes (selectable at startup):
  1. server+client — Start Flask in background thread, then open pywebview window (default)
  2. server          — Start Flask only, no pywebview window (for remote/browser access)
  3. client          — Open pywebview window only, connecting to an already-running server
"""
import os
import shutil
import subprocess
import sys
import threading
import time
import socket

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.utils.config import HOST, PORT, BIND_HOST

# pywebview is imported LAZILY (G1 audit 2026-10-25): a top-level import
# kills the whole process at startup wherever the package or its GUI
# libraries are missing — server mode and the browser fallback must work
# there. Module-global so tests can stub it (a non-None value is used
# as-is, no real import).
webview = None


def _get_webview():
    """Import pywebview on first window use (G1). Raises when unavailable."""
    global webview
    if webview is None:
        import webview as module  # local import: see note above
        module.settings['ALLOW_DOWNLOADS'] = True
        webview = module
    return webview

# Create Flask app (shared across modes)
app = create_app()


def _port_bindable(host, port):
    """True when the serving port can be bound right now (R14).

    Best-effort pre-flight: without it the LAN beacon would announce a
    server whose app.run() then dies on a busy port (some other program
    already listening), so every client menu would offer a dead server.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def start_server():
    """Start Flask server in a background thread."""
    from app.services.backup_service import start_backup_scheduler
    from app.utils.instance_lock import acquire, owner_pid
    _server_failed.clear()
    _server_serving.clear()
    if not acquire():
        print(f"ERROR: Another POSziona server is already running "
              f"(lock held, owner PID {owner_pid()}).", flush=True)
        print("Stop it first — two servers on the same data directory "
              "would silently diverge the database.", flush=True)
        _server_failed.set()
        return
    if not _port_bindable(BIND_HOST, PORT):
        print(f"ERROR: port {PORT} is already in use by another program.",
              flush=True)
        print("Stop that program (or free the port) and start again.",
              flush=True)
        _server_failed.set()
        return
    # Lock acquired AND port ours: only now signal readiness (the main
    # thread must not mistake someone else's open port for ours), start
    # announcing and schedule snapshots.
    _server_serving.set()
    from app.utils.discovery import start_beacon_loop
    beacon_stop = start_beacon_loop(PORT)
    start_backup_scheduler()
    print(f"Starting Flask server on {BIND_HOST}:{PORT}...")
    try:
        app.run(host=BIND_HOST, port=PORT, threaded=True, use_reloader=False)
    except OSError as exc:
        # Rare TOCTOU: the port was taken between the probe and app.run.
        print(f"ERROR: could not start the server on port {PORT}: {exc}",
              flush=True)
        try:
            beacon_stop.set()  # never keep advertising a dead server
        except Exception:
            pass
        _server_failed.set()


# Threading events shared between start_server (daemon thread) and the
# main thread's _wait_for_server(). Module-level (not function attrs)
# so tests can stub start_server and still drive the handshake.
_server_failed = threading.Event()   # lock refused by another server
_server_serving = threading.Event()  # lock acquired, Flask binding next


def check_server_ready(host, port, timeout=5):
    """Check if the Flask server is ready to accept connections."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def _wait_for_server(server_thread, timeout=10):
    """Wait for the daemon server thread to serve, fail, or time out.

    Returns 'ready' (this process owns the lock AND the port answers),
    'failed' (lock held by another server — reason already printed — or
    thread died), or 'timeout'.

    'ready' is gated on the serving event, not just the open port: when
    a second instance starts, the first server's open port would
    otherwise win the race against the lock-refusal report.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _server_failed.is_set():
            return 'failed'
        if not server_thread.is_alive():
            print("ERROR: Server thread died during startup")
            return 'failed'
        if _server_serving.is_set() and check_server_ready(HOST, PORT, timeout=1):
            return 'ready'
        time.sleep(0.2)
    return 'timeout'


def _serve_forever():
    """Keep the main thread alive while the server runs in a daemon thread."""
    try:
        while not _shutdown_requested.wait(1):
            pass
    except KeyboardInterrupt:
        pass
    print("\nShutting down server...")


# Set when SIGTERM asks for shutdown (systemd, docker, kill): the main
# loop exits cleanly after checkpointing instead of dying mid-request.
_shutdown_requested = threading.Event()


def _install_shutdown_handler():
    """SIGTERM → checkpoint DBs, then clean exit. Best effort, never fatal."""
    import signal

    def _on_term(signum, frame):
        print("\nShutdown requested — checkpointing databases...", flush=True)
        try:
            from app.services.backup_service import checkpoint_all
            checkpoint_all()
        except Exception as exc:
            print(f"Checkpoint failed: {exc}", flush=True)
        _shutdown_requested.set()

    try:
        signal.signal(signal.SIGTERM, _on_term)
    except (OSError, ValueError):
        pass  # not main thread / platform without SIGTERM


def _gui_install_hint(os_release='/etc/os-release'):
    """Distro-specific command to install pywebview GUI libs.

    Best effort: unknown distros (or unreadable os-release) get a generic
    pointer. Testable via the path parameter.
    """
    distro = ''
    try:
        with open(os_release, 'r') as f:
            for line in f:
                if line.startswith('ID='):
                    distro = line.split('=', 1)[1].strip().strip('"').lower()
                    break
    except OSError:
        pass
    apt_like = {'debian', 'ubuntu', 'linuxmint', 'pop', 'raspbian'}
    if distro in apt_like:
        return ('  To enable the desktop window instead:\n'
                '    sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-webkit2gtk-4.1\n'
                '  (then run from source — the standalone binary may not see\n'
                '  distro packages: it embeds its own Python)')
    if distro in {'fedora', 'rhel', 'centos', 'rocky', 'almalinux'}:
        return ('  To enable the desktop window instead:\n'
                '    sudo dnf install python3-gobject gtk3 webkit2gtk4.1\n'
                '  (then run from source — the standalone binary may not see\n'
                '  distro packages: it embeds its own Python)')
    if distro in {'arch', 'manjaro', 'endeavouros'}:
        return ('  To enable the desktop window instead:\n'
                '    sudo pacman -S python-gobject gtk3 webkit2gtk\n'
                '  (then run from source — the standalone binary may not see\n'
                '  distro packages: it embeds its own Python)')
    return ('  To enable the desktop window, install your distro\'s\n'
          '  GTK+WebKit2GTK (or Qt) packages, then run from source.')


def _native_install_hint(platform):
    """How to get the window on macOS/Windows (pywebview's own backends)."""
    if platform == 'darwin':
        return ('  To enable the desktop window instead:\n'
                '    pip install --upgrade pywebview\n'
                '  (on macOS it pulls the pyobjc Cocoa/WebKit bindings)')
    return ('  To enable the desktop window instead:\n'
            '    pip install --upgrade pywebview\n'
            '  (on Windows it pulls pythonnet; the Microsoft Edge WebView2\n'
            '  Runtime must be installed — Windows 10/11 ship it)')


def _gui_detect_state():
    """Probe this machine for the pieces the desktop window needs (G3).

    Returns a plain dict (injectable into gui_check for tests):
      webview     pywebview version string, or None when not installed
      gtk         (bool, detail) — GTK 3 + WebKit2 importable?
      qt          list of Qt bindings found (qtpy is what pywebview uses)
      cef         bool — cefpython3 importable?
      native      (bool, detail) — macOS/Windows native backend usable?
                  (None detail on Linux, where GTK/Qt are the backends)
      display     display description, or None when missing (Linux only)
      platform    sys.platform
    """
    import importlib.util
    import platform

    def _spec(name):
        try:
            return importlib.util.find_spec(name)
        except (ImportError, ValueError):
            return None

    webview_version = None
    if _spec('webview'):
        try:
            from importlib.metadata import version
            webview_version = version('pywebview')
        except Exception:
            webview_version = 'unknown'

    gtk_ok = False
    gtk_detail = 'PyGObject (python3-gi) not installed'
    if _spec('gi'):
        gtk_detail = 'Gtk 3.0/WebKit2 typelib missing'
        for ver in ('4.1', '4.0'):
            try:
                import gi
                gi.require_version('Gtk', '3.0')
                gi.require_version('WebKit2', ver)
                from gi.repository import Gtk, WebKit2  # noqa: F401
                gtk_ok = True
                gtk_detail = f'Gtk 3.0 + WebKit2 {ver}'
                break
            except Exception as exc:
                gtk_detail = str(exc)

    qt = [n for n in ('qtpy', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6')
          if _spec(n)]

    # macOS/Windows: pywebview's default backends are native — Cocoa via
    # pyobjc, EdgeChromium/WinForms via pythonnet (`clr`) — not GTK/Qt.
    # Without this the doctor said "NO desktop window" on every Mac/PC.
    native = (False, None)
    if sys.platform == 'darwin':
        found = bool(_spec('AppKit') and _spec('WebKit'))
        native = (found, 'Cocoa + WebKit (pyobjc)' if found
                  else 'pyobjc Cocoa/WebKit bindings not installed')
    elif sys.platform == 'win32':
        found = bool(_spec('clr'))
        native = (found, 'EdgeChromium/WinForms (pythonnet)' if found
                  else 'pythonnet not installed')

    display = None
    if sys.platform.startswith('linux'):
        parts = []
        if os.environ.get('DISPLAY'):
            parts.append(f"DISPLAY={os.environ['DISPLAY']}")
        if os.environ.get('WAYLAND_DISPLAY'):
            parts.append(f"WAYLAND_DISPLAY={os.environ['WAYLAND_DISPLAY']}")
        display = ' '.join(parts) or None
    else:
        display = platform.system()  # no X/Wayland concept: never missing

    return {
        'webview': webview_version,
        'gtk': (gtk_ok, gtk_detail),
        'qt': qt,
        'cef': bool(_spec('cefpython3')),
        'native': native,
        'display': display,
        'platform': sys.platform,
    }


def gui_check(state=None):
    """Doctor for the desktop window (`--gui-check`). Returns an exit code.

    0 = the window should open on this machine, 1 = POSziona will fall
    back to the browser (still fully usable). Plain language, one line
    per check, actionable — this is what the IT person reads during
    first setup (G3 audit 2026-10-25).
    """
    if state is None:
        state = _gui_detect_state()
    linux = state.get('platform', sys.platform).startswith('linux')

    lines = [f"Posziona GUI check — Python "
             f"{sys.version.split()[0]} ({sys.executable})"]

    if state['webview']:
        lines.append(f"  pywebview:       installed ({state['webview']})")
    else:
        lines.append("  pywebview:       MISSING (pip install pywebview)")

    native_ok, native_detail = state.get('native', (False, None))
    if native_detail:
        lines.append("  Native backend:  "
                     + (f"OK ({native_detail})" if native_ok
                        else f"not usable: {native_detail}"))

    if linux:
        gtk_ok, gtk_detail = state['gtk']
        lines.append("  GTK backend:     "
                     + (f"OK ({gtk_detail})" if gtk_ok
                        else f"not usable: {gtk_detail}"))

    qt = state['qt']
    lines.append("  Qt backend:      "
                 + (f"OK ({', '.join(qt)})" if qt else 'not installed (optional)'))

    if linux:
        lines.append("  CEF backend:     "
                     + ('OK' if state['cef'] else 'not installed (optional)'))

    if state['display']:
        lines.append(f"  Display:         {state['display']}")
    else:
        lines.append("  Display:         MISSING (no DISPLAY/WAYLAND_DISPLAY)")

    ok = _window_possible(state)

    if ok:
        lines.append("  Result:          the desktop window can open on this machine.")
    elif not linux:
        lines.append("  Result:          NO desktop window here — POSziona will")
        lines.append("                   fall back to the browser (it still works).")
        lines.append(_native_install_hint(state.get('platform', sys.platform)))
    else:
        lines.append("  Result:          NO desktop window here — POSziona will")
        lines.append("                   fall back to the browser (it still works).")
        lines.append(_gui_install_hint())
        lines.append("  One-time window setup from source (the system Python")
        lines.append("  sees distro GUI packages; the frozen binary may not):")
        lines.append("    python3 -m venv --system-site-packages syswin")
        lines.append("    syswin/bin/pip install flask pywebview flask-cors")
        lines.append("    syswin/bin/python scripts/run_pos.py")

    print('\n'.join(lines))
    return 0 if ok else 1


_APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Auto-setup of the window environment (G6): the syswin venv from the
# documented recipe, created once and reused. Env knobs:
#   POSZIONA_NO_AUTO_WINDOW_SETUP=1   never touch the network / create it
#   POSZIONA_AUTO_WINDOW_SETUP_TRIED=1 set before the re-exec so a broken
#                                     window env can never loop
_SYSWIN_DIR_NAME = 'syswin'


def _window_possible(state=None):
    """True when the desktop window can open with THIS Python.

    Only backends pywebview actually tries on the platform count:
    Linux = GTK/Qt; macOS = Cocoa/Qt; Windows = WinForms/Qt (the app
    retries with PYWEBVIEW_GUI=qt). GTK/CEF on macOS/Windows are
    installed Python packages pywebview never uses there.
    """
    if state is None:
        state = _gui_detect_state()
    platform = state.get('platform', sys.platform)
    qt_ok = bool(state['qt'])
    if platform.startswith('linux'):
        gtk_ok, _ = state['gtk']
        backend_ok = gtk_ok or qt_ok
    else:
        native_ok, _ = state.get('native', (False, None))
        backend_ok = native_ok or qt_ok
    return bool(state['webview']) and backend_ok and bool(state['display'])


def _running_inside_syswin():
    """Guard against re-exec loops: already using the window venv?"""
    return os.path.basename(os.path.normpath(sys.prefix)) == _SYSWIN_DIR_NAME


def _maybe_auto_setup_window():
    """Create/reuse the syswin venv and re-exec in it when a window is
    wanted but this Python cannot provide one (G6).

    Called only for 'all'/'client' modes, before the server starts. The
    happy path never returns: os.execv replaces this process with the
    same PID (the instance lock stays valid — never two live servers).
    Returns False when there is nothing to do or anything fails; the
    caller then continues with the browser fallback (fail-open).
    """
    if os.environ.get('POSZIONA_NO_AUTO_WINDOW_SETUP'):
        return False
    if os.environ.get('POSZIONA_AUTO_WINDOW_SETUP_TRIED'):
        return False
    if getattr(sys, 'frozen', False):
        return False  # embeds its own Python: the recipe is source-only
    if not sys.platform.startswith('linux'):
        return False
    if _running_inside_syswin():
        return False

    state = _gui_detect_state()
    if not state['display']:
        return False          # no graphical session at all
    if _window_possible(state):
        return False          # this Python is already fine

    python3 = shutil.which('python3')
    if not python3:
        return False
    syswin = os.path.join(_APP_ROOT, _SYSWIN_DIR_NAME)
    venv_python = os.path.join(syswin, 'bin', 'python')
    script = os.path.join(_APP_ROOT, 'scripts', 'run_pos.py')
    if not os.path.exists(script):
        return False

    print("  Desktop window support is missing in this Python.",
          flush=True)
    print("  Setting up a one-time window environment (needs internet)...",
          flush=True)
    try:
        if not os.path.exists(venv_python):
            print(f"    creating {_SYSWIN_DIR_NAME}/ ...", flush=True)
            subprocess.run([python3, '-m', 'venv', '--system-site-packages',
                            syswin], check=True, timeout=180)
        probe = subprocess.run(
            [venv_python, '-c', 'import flask, webview'],
            capture_output=True, timeout=60)
        if probe.returncode != 0:
            print("    installing flask + pywebview (one time)...", flush=True)
            subprocess.run([venv_python, '-m', 'pip', 'install', '--quiet',
                            'flask', 'pywebview', 'flask-cors'],
                           check=True, timeout=600)
    except Exception as exc:
        print(f"  Window setup failed ({exc}) — using the browser instead.",
              flush=True)
        return False

    print("  Relaunching with the window environment...", flush=True)
    os.environ['POSZIONA_AUTO_WINDOW_SETUP_TRIED'] = '1'
    os.execv(venv_python, [venv_python, script, *sys.argv[1:]])
    return False  # not reached with a real execv


def _gui_missing_message(exc, server_url):
    """Explain why the pywebview window could not open."""
    # flush=True: frozen binaries are block-buffered on pipes/files —
    # failure messages must not die in the buffer on SIGKILL/timeout.
    print(f"\nWARNING: Desktop window unavailable ({exc}).", flush=True)
    if not sys.platform.startswith('linux'):
        # The GTK/apt/venv recipe below is Linux-only
        print(f"  Open {server_url} in a browser instead.", flush=True)
        print(_native_install_hint(sys.platform), flush=True)
        return
    print("  pywebview needs GTK+WebKit2GTK (or Qt) system libraries,", flush=True)
    print("  which are not installed on this machine.", flush=True)
    print(f"  Open {server_url} in a browser instead.", flush=True)
    print(_gui_install_hint(), flush=True)
    print("  Or run the app window from source (uses the system Python,", flush=True)
    print("  which can see the distro GTK packages — the frozen binary", flush=True)
    print("  cannot). One time setup, then a real window:", flush=True)
    print("    python3 -m venv --system-site-packages syswin", flush=True)
    print("    syswin/bin/pip install flask pywebview flask-cors", flush=True)
    print("    syswin/bin/python scripts/run_pos.py", flush=True)


def _qt_backend_available():
    """True when pywebview's Qt backend has its Python glue installed."""
    import importlib.util
    for name in ('qtpy', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6'):
        try:
            if importlib.util.find_spec(name):
                return True
        except (ImportError, ValueError):
            continue
    return False


def _start_window(view):
    """Run the window event loop, retrying once on the Qt backend (G2).

    Some distros ship a broken GTK/WebKit2GTK but a working Qt (or the
    other way around); pywebview picks its backend at start(). When the
    default attempt fails and Qt is installed, retry once with
    PYWEBVIEW_GUI=qt — otherwise nothing to try. An explicit
    PYWEBVIEW_GUI in the environment is always respected (no retry).

    Returns (ok, last_exception): ok=True means the event loop ran
    (window closed normally), NOT that a specific backend was used.
    """
    original = os.environ.get('PYWEBVIEW_GUI')
    try:
        backends = [original] if original else [None]
        if not original and _qt_backend_available():
            backends.append('qt')
        last_exc = None
        for backend in backends:
            if backend is None:
                os.environ.pop('PYWEBVIEW_GUI', None)
            else:
                os.environ['PYWEBVIEW_GUI'] = backend
            try:
                # debug=False: no inspector. private_mode=False keeps
                # cookies + localStorage across restarts (pywebview's
                # default, True, wipes them on exit): the 24 h login,
                # the active party and the recent-servers list must
                # survive closing the window.
                view.start(debug=False, private_mode=False)
                return True, None
            except Exception as exc:
                last_exc = exc
                if len(backends) > 1:
                    print(f"  Window backend '{backend or 'default'}' failed: "
                          f"{exc}", flush=True)
        return False, last_exc
    finally:
        if original is None:
            os.environ.pop('PYWEBVIEW_GUI', None)
        else:
            os.environ['PYWEBVIEW_GUI'] = original


def _open_browser(server_url):
    """Auto-open the system browser (stdlib only, zero host deps).

    Returns True when a browser was launched. Opt out with
    POSZIONA_NO_BROWSER=1 (headless boxes, kiosk scripts).
    """
    if os.environ.get('POSZIONA_NO_BROWSER'):
        return False
    try:
        import webbrowser
        if webbrowser.open(server_url, new=1):
            print(f"  Opened system browser at {server_url}", flush=True)
            return True
    except Exception:
        pass
    return False


def select_mode():
    """Prompt the user to choose a startup mode interactively."""
    print("\n" + "=" * 40)
    print("  Posziona — Startup Mode")
    print("=" * 40)
    print()
    print("  1. Server + Client  (Flask + pywebview window)")
    print("  2. Server only       (Flask, no window)")
    print("  3. Client only       (pywebview window to running server)")
    print()
    print("  Use the number to select, or pass flags to skip this menu:")
    print("    python scripts/run_pos.py --mode server")
    print("    python scripts/run_pos.py --mode client")
    print("    python scripts/run_pos.py --mode all   (default)")
    print()

    while True:
        raw = _safe_input("Select mode [1-3] (default 1): ")
        if raw is None:
            return 'all'
        choice = raw.strip()
        if choice == '' or choice == '1':
            return 'all'
        elif choice == '2':
            return 'server'
        elif choice == '3':
            return 'client'
        print("  Invalid choice. Please enter 1, 2, or 3.")


def _warn_if_other_server_live():
    """Best-effort split-brain guard: warn when another server is already
    beacons-live on this network. Two servers = sales in two places.

    Warn-only (never refuse): the instance lock already guards one data
    dir; this catches the *other* failure — a second box serving the same
    party. Skipped with POSZIONA_NO_SERVER_CHECK=1 (scripts, tests).
    """
    if os.environ.get('POSZIONA_NO_SERVER_CHECK'):
        return
    from app.utils.discovery import discover
    try:
        found = discover(timeout=1.5)
    except Exception:
        return
    if not found:
        return
    print("", flush=True)
    print("  NOTICE: another POSziona server is already on this network:",
          flush=True)
    for srv in found:
        tag = f"  (v{srv['version']})" if srv.get('version') else ''
        print(f"    - {srv['name']} — {srv['url']}{tag}", flush=True)
    print("  Sales on two servers end up in two different places.", flush=True)
    print("  If that is your main till, stop this one (Ctrl-C) and use it.",
          flush=True)
    print("  Starting anyway in 3 seconds...", flush=True)
    try:
        time.sleep(3)
    except KeyboardInterrupt:
        sys.exit(1)


def run_server_only():
    """Mode 2: Start Flask server only, no pywebview window."""
    _warn_if_other_server_live()
    _install_shutdown_handler()
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    status = _wait_for_server(server_thread)
    if status == 'failed':
        sys.exit(1)
    if status == 'timeout':
        print("ERROR: Server failed to start in time")
        sys.exit(1)

    print("Server ready. Running in server-only mode (no UI window).")
    print(f"Access the POS at http://{HOST}:{PORT}/  in a browser,")
    _print_lan_hint()
    print(f"or start a separate client with:  python scripts/run_pos.py --mode client")
    print("Press Ctrl+C to stop.")

    _serve_forever()


def _print_lan_hint():
    """Show the URL other devices on the same Wi-Fi/hotspot can use."""
    try:
        from app.utils.discovery import get_lan_ip
        lan = get_lan_ip()
    except Exception:
        lan = None
    if lan:
        print(f"Other devices on this network: http://{lan}:{PORT}/")


def _normalize_server_url(user_input, default_port=None):
    """Turn '192.168.1.10', '192.168.1.10:5000' or a full URL into a normalized server URL.

    A bare IP/hostname gets the default POS port appended — without it
    the client would hit port 80 and land on a dead page.

    Returns None for empty/garbage input (arrow-key escapes, pasted
    terminal noise, unparseable URLs) — the manual prompt re-asks instead
    of dying with a traceback. Never raises.
    """
    import re
    from urllib.parse import urlsplit, urlunsplit
    if default_port is None:
        default_port = PORT
    try:
        user_input = re.sub(r'[\x00-\x20\x7f]+', '', (user_input or '').strip())
        if not user_input:
            return None
        if not user_input.startswith('http://') and not user_input.startswith('https://'):
            user_input = f'http://{user_input}'
        parts = urlsplit(user_input)
    except ValueError:
        return None
    host = parts.hostname or ''
    if not host:
        return user_input.rstrip('/') + '/'
    try:
        port = parts.port
    except ValueError:
        port = None  # garbage port text → keep as-is, probe will reject
    if port is None and ':' not in (parts.netloc.rsplit('@', 1)[-1]):
        netloc = f'{host}:{default_port}'
        if parts.username:
            auth = parts.username + (f':{parts.password}' if parts.password else '') + '@'
            netloc = auth + netloc
        parts = parts._replace(netloc=netloc)
    return urlunsplit(parts).rstrip('/') + '/'


def _server_reachable(server_url, timeout=3):
    """TCP-probe the host:port of a server URL (no HTTP needed)."""
    from urllib.parse import urlsplit
    try:
        parts = urlsplit(server_url)
        host = parts.hostname
        port = parts.port or PORT
        if not host:
            return False
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(timeout)
            return sock.connect_ex((host, port)) == 0
        finally:
            sock.close()
    except Exception:
        return False


def _unreachable_hint(server_url):
    """Concrete next steps when a server URL answers nothing."""
    print(f"  Cannot reach {server_url}", flush=True)
    print("  Check that:", flush=True)
    print("  - the server is started (mode 'server' or 'all'),", flush=True)
    print("  - both machines share the same Wi-Fi/LAN,", flush=True)
    print(f"  - no firewall blocks TCP port {PORT} (nor UDP 42137 for auto-discovery).", flush=True)


def _safe_input(prompt):
    """input() that returns None on EOF/Ctrl-C instead of a traceback."""
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        return None


def _discover_or_ask_server():
    """Find a server: LAN beacons first, manual entry as fallback.

    Returns a server URL. Loops until the user gives a reachable address
    (blank re-prompts — it must NOT start a silent local server, which
    would split sales across two databases in multi-machine setups).
    """
    from app.utils.discovery import discover, scan_tcp_servers, tcp_scan_enabled
    print(f"No server detected on {HOST}:{PORT}.")
    print("  Scanning the local network for POSziona servers...")
    found = discover()
    if not found and tcp_scan_enabled():
        # Some Wi-Fi APs isolate clients or drop UDP broadcast: beacons
        # never arrive even when the server is reachable over TCP.
        print("  No beacon answers — probing the network directly (TCP)...")
        found = scan_tcp_servers(PORT)
    if found:
        print("  Found on this network:")
        for i, srv in enumerate(found, 1):
            tag = f"  (v{srv['version']})" if srv.get('version') else ''
            print(f"    {i}. {srv['name']} — {srv['url']}{tag}")
        print("    0. Enter address manually")
        raw = _safe_input("  Select server [1-%d] (default 1): " % len(found))
        if raw is None:
            print("  Aborted. Tip: pass the server directly with "
                  "--server-url http://<ip>:5000/")
            sys.exit(1)
        choice = raw.strip()
        if choice == '':
            return found[0]['url']
        if choice == '0':
            pass  # fall through to manual entry below
        elif choice.isdigit() and 1 <= int(choice) <= len(found):
            return found[int(choice) - 1]['url']
        else:
            print("  Invalid choice, enter the address manually.")
    else:
        print("  No servers found on this network.")
    print("  To connect to a server on another machine, enter its address below.\n")
    while True:
        raw = _safe_input(
            "  Server IP/URL (e.g., 192.168.1.10 or 192.168.1.10:5000): ")
        if raw is None:
            print("  Aborted. Tip: pass the server directly with "
                  "--server-url http://<ip>:5000/")
            sys.exit(1)
        user_input = raw.strip()
        if not user_input:
            # No silent local server here: in a 2-machine setup that would
            # fork sales into a second database (split-brain). 'all' mode
            # starts a local server on purpose.
            print("  Enter a server address (or Ctrl-C to quit).\n")
            continue
        server_url = _normalize_server_url(user_input)
        if server_url is None:
            print(f"  Not a valid address: {user_input!r} — try again.\n")
            continue
        if _server_reachable(server_url):
            return server_url
        _unreachable_hint(server_url)
        print("  Try again.\n")


def run_client_only(server_url=None):
    """Mode 3: Open pywebview window only, connecting to a specified server.

    If server_url is not provided, checks localhost first. If no server
    is detected on localhost, prompts the user to enter a server IP/URL.
    """
    if server_url is None:
        if check_server_ready(HOST, PORT, timeout=3):
            server_url = f'http://{HOST}:{PORT}/'
            print(f"  Using the server on this machine: {server_url}")
            print("  (to pick another, restart with "
                  "--server-url http://<ip>:5000/)")
        else:
            server_url = _discover_or_ask_server()
    else:
        normalized = _normalize_server_url(server_url)
        if normalized is None:
            print(f"  Invalid --server-url {server_url!r}.", flush=True)
            print("  Example: --server-url http://192.168.178.171:5000/")
            sys.exit(1)
        server_url = normalized
        if not _server_reachable(server_url):
            _unreachable_hint(server_url)
            print("  Continuing anyway (explicit --server-url).", flush=True)

    print(f"Opening pywebview window (client-only mode)...")
    print(f"  Connecting to: {server_url}")

    try:
        view = _get_webview()
    except Exception as exc:
        # pywebview itself unavailable (pip package or GUI libs missing).
        # A client window is the whole point of this mode.
        _gui_missing_message(exc, server_url)
        _open_browser(server_url)
        sys.exit(1)

    view.create_window(
        title='Posziona',
        url=server_url,
        width=1200,
        height=800,
        fullscreen=False,
        resizable=True,
    )
    ok, exc = _start_window(view)
    if not ok:
        # No usable GUI backend (missing GTK/Qt system libs, no display...).
        # A client window is the whole point of this mode, so exit with a
        # clear message instead of a traceback.
        _gui_missing_message(exc, server_url)
        _open_browser(server_url)
        sys.exit(1)


def run_server_and_client():
    """Mode 1 (default): Start Flask server, then open pywebview window."""
    _warn_if_other_server_live()
    _install_shutdown_handler()
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    print("Waiting for server to start...")
    status = _wait_for_server(server_thread)
    if status == 'failed':
        sys.exit(1)
    if status == 'timeout':
        print("ERROR: Server failed to start in time")
        sys.exit(1)

    print("Server ready. Launching pywebview window...")

    # Create pywebview window with url= directly
    # pywebview injects a JS bridge that can cause errors in some WebKit versions
    # Use url= directly instead of iframe wrapper.
    # The iframe approach was breaking Flask session cookies because
    # cookies set inside the iframe may not persist in pywebview contexts.
    # Direct URL loading ensures cookies work correctly.
    try:
        view = _get_webview()
    except Exception as exc:
        # pywebview missing entirely: the server is already up — degrade
        # to server-only + browser instead of dying (G1).
        print("  Continuing in server-only mode.", flush=True)
        _gui_missing_message(exc, f'http://{HOST}:{PORT}/')
        _print_lan_hint()
        _open_browser(f'http://{HOST}:{PORT}/')
        print("Press Ctrl+C to stop.")
        _serve_forever()
        return

    view.create_window(
        title='Posziona',
        url=f'http://{HOST}:{PORT}/',
        width=1200,
        height=800,
        fullscreen=False,  # Set to True for production kiosk mode
        resizable=True,
    )

    # Start the pywebview event loop (retries once on Qt if the default
    # backend is broken — G2).
    ok, exc = _start_window(view)
    if not ok:
        # No usable GUI backend (missing GTK/Qt system libs, no display...).
        # The server is already up, so degrade to server-only mode instead
        # of dying with a traceback.
        print("  Continuing in server-only mode.", flush=True)
        _gui_missing_message(exc, f'http://{HOST}:{PORT}/')
        _print_lan_hint()
        _open_browser(f'http://{HOST}:{PORT}/')
        print("Press Ctrl+C to stop.")
        _serve_forever()


def main(mode=None, server_url=None):
    """Launch the POS application.

    Args:
        mode: 'all' (server+client, default), 'server', or 'client'.
               If None: prompt on a terminal, 'all' otherwise.
        server_url: For 'client' mode only, the URL of the POS server.
                     If None, checks localhost; if not found, prompts for IP.
    """
    if mode is None:
        try:
            interactive = sys.stdin.isatty()
        except Exception:
            interactive = False
        mode = select_mode() if interactive else 'all'

    print(f"Mode: {mode}")
    if mode == 'server':
        run_server_only()
    elif mode == 'client':
        _maybe_auto_setup_window()
        run_client_only(server_url=server_url)
    else:  # 'all' or anything else
        _maybe_auto_setup_window()
        run_server_and_client()


def parse_args(argv=None):
    """Parse CLI flags. Returns (mode, server_url).

    Single implementation shared by scripts/run_pos.py (source) and
    scripts/entry_point.py (frozen) — they differ only in path bootstrap.
    """
    import argparse
    parser = argparse.ArgumentParser(
        description='Run Posziona in one of three modes:',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
  all       Start Flask server + open pywebview window (default)
  server    Start Flask server only (no window)
  client    Open pywebview window only (connects to running server)

If --mode is omitted, an interactive prompt is shown.

Options:
  --mode {all|server|client}   Startup mode (default: all)
  --server-url URL             Server URL for client mode
                               (e.g., http://192.168.1.10:5000/)
  --gui-check                  Diagnose whether the desktop window can
                               open on this machine, then exit
""",
    )
    parser.add_argument(
        '--mode', choices=['all', 'server', 'client'],
        help='Startup mode (omit for interactive prompt)'
    )
    parser.add_argument(
        '--server-url',
        help='Server URL for client mode (e.g., http://192.168.1.10:5000/)'
    )
    parser.add_argument(
        '--gui-check', action='store_true',
        help='Diagnose whether the desktop window can open, then exit'
    )
    args = parser.parse_args(argv)
    if args.gui_check:
        # Doctor mode: report and exit (0 = window can open, 1 = browser
        # fallback). Kept inside parse_args so both entry points (source
        # and frozen) share one implementation without changing the
        # (mode, server_url) contract they rely on.
        sys.exit(gui_check())
    return args.mode, args.server_url


if __name__ == '__main__':
    _mode, _server_url = parse_args()
    main(mode=_mode, server_url=_server_url)
