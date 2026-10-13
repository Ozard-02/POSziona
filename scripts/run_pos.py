"""
Run script for Posziona application.

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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import main, parse_args

if __name__ == '__main__':
    mode, server_url = parse_args()
    main(mode=mode, server_url=server_url)
