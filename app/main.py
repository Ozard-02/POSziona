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
import webview

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.utils.config import HOST, PORT

webview.settings['ALLOW_DOWNLOADS'] = True

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
    start_backup_scheduler()
    print(f"Starting Flask server on {HOST}:{PORT}...")
    app.run(host=HOST, port=PORT, threaded=True, use_reloader=False)


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


def _gui_missing_message(exc, server_url):
    """Explain why the pywebview window could not open."""
    # flush=True: frozen binaries are block-buffered on pipes/files —
    # failure messages must not die in the buffer on SIGKILL/timeout.
    print(f"\nWARNING: Desktop window unavailable ({exc}).", flush=True)
    print("  pywebview needs GTK+WebKit2GTK (or Qt) system libraries,", flush=True)
    print("  which are not installed on this machine.", flush=True)
    print(f"  Open {server_url} in a browser instead.", flush=True)


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
        choice = input("Select mode [1-3] (default 1): ").strip()
        if choice == '' or choice == '1':
            return 'all'
        elif choice == '2':
            return 'server'
        elif choice == '3':
            return 'client'
        print("  Invalid choice. Please enter 1, 2, or 3.")


def run_server_only():
    """Mode 2: Start Flask server only, no pywebview window."""
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
    print(f"or start a separate client with:  python scripts/run_pos.py --mode client")
    print("Press Ctrl+C to stop.")

    _serve_forever()


def run_client_only(server_url=None):
    """Mode 3: Open pywebview window only, connecting to a specified server.

    If server_url is not provided, checks localhost first. If no server
    is detected on localhost, prompts the user to enter a server IP/URL.
    """
    if server_url is None:
        if check_server_ready(HOST, PORT, timeout=3):
            server_url = f'http://{HOST}:{PORT}/'
        else:
            print(f"No server detected on {HOST}:{PORT}.")
            print("  To connect to a server on another machine, enter its address below.")
            print("  Leave blank to start a local server instead (hybrid mode).\n")
            user_input = input("  Server IP/URL (e.g., 192.168.1.10:5000 or http://192.168.1.10:5000/): ").strip()
            if user_input:
                # Normalize user input into a full URL
                if not user_input.startswith('http://') and not user_input.startswith('https://'):
                    user_input = f'http://{user_input}'
                server_url = user_input.rstrip('/') + '/'
            else:
                print("  Starting a local server as fallback (hybrid mode).")
                server_thread = threading.Thread(target=start_server, daemon=True)
                server_thread.start()
                if not check_server_ready(HOST, PORT, timeout=10):
                    print("ERROR: Server failed to start in time")
                    sys.exit(1)
                server_url = f'http://{HOST}:{PORT}/'

    print(f"Opening pywebview window (client-only mode)...")
    print(f"  Connecting to: {server_url}")

    window = webview.create_window(
        title='Posziona',
        url=server_url,
        width=1200,
        height=800,
        fullscreen=False,
        resizable=True,
    )
    try:
        webview.start(debug=False, private_mode=True)
    except Exception as exc:
        # No usable GUI backend (missing GTK/Qt system libs, no display...).
        # A client window is the whole point of this mode, so exit with a
        # clear message instead of a traceback.
        _gui_missing_message(exc, server_url)
        sys.exit(1)


def run_server_and_client():
    """Mode 1 (default): Start Flask server, then open pywebview window."""
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
    window = webview.create_window(
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
        webview.start(debug=False, private_mode=True)
    except Exception as exc:
        # No usable GUI backend (missing GTK/Qt system libs, no display...).
        # The server is already up, so degrade to server-only mode instead
        # of dying with a traceback.
        print("  Continuing in server-only mode.", flush=True)
        _gui_missing_message(exc, f'http://{HOST}:{PORT}/')
        print("Press Ctrl+C to stop.")
        _serve_forever()


def main(mode=None, server_url=None):
    """Launch the POS application.

    Args:
        mode: 'all' (server+client, default), 'server', or 'client'.
               If None, defaults to 'all' (server + client).
        server_url: For 'client' mode only, the URL of the POS server.
                     If None, checks localhost; if not found, prompts for IP.
    """
    if mode is None:
        mode = 'all'

    print(f"Mode: {mode}")
    if mode == 'server':
        run_server_only()
    elif mode == 'client':
        run_client_only(server_url=server_url)
    else:  # 'all' or anything else
        run_server_and_client()


if __name__ == '__main__':
    mode = None
    server_url = None
    args = sys.argv[1:]
    if '--mode' in args:
        idx = args.index('--mode')
        if idx + 1 < len(args):
            mode = args[idx + 1]
            if mode not in ('all', 'server', 'client'):
                print(f"Unknown mode '{mode}'. Use: all, server, or client.")
                sys.exit(1)
    if '--server-url' in args:
        idx = args.index('--server-url')
        if idx + 1 < len(args):
            server_url = args[idx + 1]
    elif '--help' in args or '-h' in args:
        print(__doc__)
        print("\nOptions:")
        print("  --mode {all|server|client}  Startup mode (default: all)")
        print("  --server-url URL            Server URL for client mode (e.g., http://192.168.1.10:5000/)")
        sys.exit(0)

    main(mode=mode, server_url=server_url)
