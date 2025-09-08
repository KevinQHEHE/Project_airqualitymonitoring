"""WSGI entrypoint for development and production."""
import os
from backend.app import create_app

# Create the Flask application
app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
