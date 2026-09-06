# LEHT

LEHT is a Flask-based appointment booking web application for a hair salon. It provides booking, technician management, services, and admin interfaces.

## Quick start

- Create a virtual environment: `python -m venv venv`
- Activate it: `venv\Scripts\activate` (Windows) or `source venv/bin/activate` (macOS/Linux)
- Install dependencies: `pip install -r requirements.txt`
- Initialize the database (if needed): `python init_db.py`
- Run the app: `python app.py` or `flask run`

## Repo
This repository is intended to be private. It contains the full app code, static assets, templates, and configuration.

## Files of interest
- `app.py` — Flask application entry
- `requirements.txt` — Python dependencies
- `init_db.py`, `db.py` — database initialization and helpers
- `templates/` and `static/` — frontend assets and templates

## Notes
- Add a `.env` file for secrets (do not commit it).
- Ignore uploads and virtual environments in `.gitignore`.
