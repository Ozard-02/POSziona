"""
Entry point for Party POS application with pywebview.
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
    print(f"Starting Flask server on {HOST}:{PORT}...")
    app.run(host=HOST, port=PORT, threaded=True, use_reloader=False)


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


def select_mode():
    """Prompt the user to choose a startup mode interactively."""
    print("\n" + "=" * 40)
    print("  Party POS — Startup Mode")
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
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    if not check_server_ready(HOST, PORT, timeout=10):
        print("ERROR: Server failed to start in time")
        sys.exit(1)

    print("Server ready. Running in server-only mode (no UI window).")
    print(f"Access the POS at http://{HOST}:{PORT}/  in a browser,")
    print(f"or start a separate client with:  python scripts/run_pos.py --mode client")
    print("Press Ctrl+C to stop.")

    try:
        # Keep the main thread alive while the server runs in the daemon thread
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down server...")


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
        title='Party POS',
        url=server_url,
        width=1200,
        height=800,
        fullscreen=False,
        resizable=True,
    )
    webview.start(debug=False, private_mode=True)


def run_server_and_client():
    """Mode 1 (default): Start Flask server, then open pywebview window."""
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    print("Waiting for server to start...")
    if not check_server_ready(HOST, PORT, timeout=10):
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
        title='Party POS',
        url=f'http://{HOST}:{PORT}/',
        width=1200,
        height=800,
        fullscreen=False,  # Set to True for production kiosk mode
        resizable=True,
    )

    # Start the pywebview event loop
    # debug=False: prevents inspector from opening
    # private_mode=True: preserves cookies/sessions
    webview.start(debug=False, private_mode=True)


def main(mode=None, server_url=None):
    """Launch the POS application.

    Args:
        mode: 'all' (server+client, default), 'server', or 'client'.
               If None, prompts interactively (unless --mode flag was passed).
        server_url: For 'client' mode only, the URL of the POS server.
                     If None, checks localhost; if not found, prompts for IP.
    """
    if mode is None:
        mode = select_mode()

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
