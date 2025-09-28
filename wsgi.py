"""WSGI entrypoint for development and production (project root).

This file creates the Flask application by calling create_app() from
the `backend.app` package. Placing the entrypoint at the repository root
makes it straightforward to reference as `wsgi:app` from Gunicorn or other
WSGI servers.

Usage examples:
  - Development: python -m flask --app wsgi:app run --debug
  - Gunicorn:   gunicorn wsgi:app -w 4 -b 0.0.0.0:8000
"""
from dotenv import load_dotenv
from backend.app import create_app

# Load environment variables from .env (if present)
load_dotenv()

# Create the Flask application
app = create_app()

if __name__ == '__main__':
    # Run development server when executed directly
    app.run(debug=True)
