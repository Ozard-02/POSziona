# Party POS System

A lightweight, offline Point of Sale application for parties/events.

## Quick Start

```bash
# Setup (one-time)
cd party-pos
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

## Structure

See `STRUCTURE.md` for full project layout.

## License

MIT — see [LICENSE](LICENSE).
