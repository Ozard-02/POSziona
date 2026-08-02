"""
Standalone entry point for PyInstaller builds of Party POS.

This script handles both development mode (running from source)
and frozen mode (running as a PyInstaller bundle / AppImage / .exe).

In frozen mode, it adds the bundled resources to sys.path and adjusts
the template/static paths so Flask can find them.
"""
import os
import sys
import argparse

# --- Handle frozen (PyInstaller) bundles ---
if getattr(sys, 'frozen', False):
    # Running as a bundled executable
    _bundle_dir = os.path.dirname(sys.executable)
    # In one-file mode, sys._MEIPASS points to the temp extraction dir
    if hasattr(sys, '_MEIPASS'):  # type: ignore[attr-defined]
        _bundle_dir = sys._MEIPASS  # type: ignore[attr-defined]
    sys.path.insert(0, _bundle_dir)
    # Resources (templates, static) are extracted to the same dir
    os.environ.setdefault('PARTY_POS_DATA_DIR', _bundle_dir)
else:
    # Running from source — add project root to path
    _bundle_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, _bundle_dir)

from app.main import main

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Run Party POS in one of three modes:',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
  all       Start Flask server + open pywebview window (default)
  server    Start Flask server only (no window)
  client    Open pywebview window only (connects to running server)

If --mode is omitted, an interactive prompt is shown.""",
    )
    parser.add_argument(
        '--mode', choices=['all', 'server', 'client'],
        help='Startup mode (omit for interactive prompt)'
    )
    parser.add_argument(
        '--server-url',
        help='Server URL for client mode (e.g., http://192.168.1.10:5000/)'
    )
    args = parser.parse_args()
    main(mode=args.mode, server_url=args.server_url)
