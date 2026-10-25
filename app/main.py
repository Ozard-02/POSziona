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
    # Lock acquired: this process owns the data dir. Signal it BEFORE
    # binding the port — the main thread must not mistake another
    # server's open port for ours (ready/lock race).
    _server_serving.set()
    # LAN beacon so clients on the same Wi-Fi can discover this server.
    from app.utils.discovery import start_beacon_loop
    start_beacon_loop(PORT)
    start_backup_scheduler()
    print(f"Starting Flask server on {BIND_HOST}:{PORT}...")
    app.run(host=BIND_HOST, port=PORT, threaded=True, use_reloader=False)


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


def _gui_missing_message(exc, server_url):
    """Explain why the pywebview window could not open."""
    # flush=True: frozen binaries are block-buffered on pipes/files —
    # failure messages must not die in the buffer on SIGKILL/timeout.
    print(f"\nWARNING: Desktop window unavailable ({exc}).", flush=True)
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
    from app.utils.discovery import discover
    print(f"No server detected on {HOST}:{PORT}.")
    print("  Scanning the local network for POSziona servers...")
    found = discover()
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
    try:
        view.start(debug=False, private_mode=True)
    except Exception as exc:
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

    # Start the pywebview event loop
    # debug=False: prevents inspector from opening
    # private_mode=True: preserves cookies/sessions
    try:
        view.start(debug=False, private_mode=True)
    except Exception as exc:
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
        run_client_only(server_url=server_url)
    else:  # 'all' or anything else
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
    args = parser.parse_args(argv)
    return args.mode, args.server_url


if __name__ == '__main__':
    _mode, _server_url = parse_args()
    main(mode=_mode, server_url=_server_url)
