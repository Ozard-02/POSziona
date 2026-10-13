"""
Standalone entry point for PyInstaller builds of Posziona.

This script handles both development mode (running from source)
and frozen mode (running as a PyInstaller bundle / AppImage / .exe).

In frozen mode, it adds the bundled resources to sys.path and adjusts
the template/static paths so Flask can find them.
"""
import os
import sys

# --- Handle frozen (PyInstaller) bundles ---
if getattr(sys, 'frozen', False):
    # Running as a bundled executable
    _bundle_dir = os.path.dirname(sys.executable)
    # In one-file mode, sys._MEIPASS points to the temp extraction dir
    if hasattr(sys, '_MEIPASS'):  # type: ignore[attr-defined]
        _bundle_dir = sys._MEIPASS  # type: ignore[attr-defined]
    sys.path.insert(0, _bundle_dir)
    # Resources (templates, static) are extracted to the same dir.
    # The app's config.py uses __file__ to resolve paths, which works
    # because sys.path now includes the bundle dir.
else:
    # Running from source — add project root to path
    _bundle_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, _bundle_dir)

from app.main import main, parse_args

if __name__ == '__main__':
    mode, server_url = parse_args()
    main(mode=mode, server_url=server_url)
