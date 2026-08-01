"""
Entry point for Party POS application with pywebview.
Launches the Flask server in a background thread and wraps it
in a native pywebview desktop window.
"""

import os
import sys
import threading
import time
import webview

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.utils.config import HOST, PORT

# Create Flask app
app = create_app()


def start_server():
    """Start Flask server in a background thread."""
    print(f"Starting Flask server on {HOST}:{PORT}...")
    app.run(host=HOST, port=PORT, threaded=True, use_reloader=False)


def check_server_ready(host, port, timeout=5):
    """Check if the Flask server is ready to accept connections."""
    import socket
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


def main():
    """Launch the POS application in a pywebview window."""
    
    # Start Flask server in background thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    
    # Wait for server to be ready
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


if __name__ == '__main__':
    main()
