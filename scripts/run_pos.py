"""
Run script for Party POS application.

Startup mode can be selected interactively or via CLI flags:
    python scripts/run_pos.py              # Interactive prompt
    python scripts/run_pos.py --mode all   # Server + client (default)
    python scripts/run_pos.py --mode server  # Server only (no UI window)
    python scripts/run_pos.py --mode client  # Client only (connects to running server)
    python scripts/run_pos.py --mode client --server-url http://192.168.1.10:5000/
    python scripts/run_pos.py --help       # Show help
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import main

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Run Party POS in one of three modes:',
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
    args = parser.parse_args()
    main(mode=args.mode, server_url=args.server_url)
