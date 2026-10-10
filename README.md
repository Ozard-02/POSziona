# Posziona System

A lightweight, offline Point of Sale application for parties/events.

## Quick Start

```bash
# Setup (one-time)
cd posziona
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or venv\Scripts\activate  # Windows
pip install -r requirements.txt

# Run
python scripts/run_pos.py
```

## Tech Stack

- **Backend**: Python + Flask
- **UI**: pywebview (native desktop window wrapping Flask app)
- **Database**: SQLite (one file per party + one shared templates DB)
- **Frontend**: HTML/CSS/JS served by Flask

## Linux notes

- No desktop window opens and no extra packages installed? That's fine:
  `./posziona` falls back to server-only mode and opens your browser at
  `http://127.0.0.1:5000/` automatically (opt out: `POSZIONA_NO_BROWSER=1`).
- For the native window instead, install your distro's GTK+WebKit2GTK
  packages (the app prints the exact command) and run from source.
- Data lives in `~/.posziona/` (`POSZIONA_DATA_DIR` overrides).
- Clients find servers on the same Wi-Fi automatically (UDP beacon,
  opt out: `POSZIONA_NO_BEACON=1`).

## Structure

See `STRUCTURE.md` for full project layout.

## License

MIT — see [LICENSE](LICENSE).
