# Flask App Layout

Minimal Flask app scaffold.

Quick start

```bash
# create venv (macOS/Linux)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

App structure

- app/ - application package
  - __init__.py - factory
  - routes.py - blueprints/routes
  - templates/ - Jinja2 templates
  - static/ - static assets (css/js/images)
- run.py - development entrypoint
- requirements.txt
