#!/usr/bin/env python3
"""WSGI entry point for gunicorn."""
import os
from pathlib import Path
from app import create_app
from app.services import mentor_service

app = create_app(os.environ.get('FLASK_ENV', 'production'))

# Seed mentors on startup (idempotent)
seeds_path = Path(__file__).parent / 'database' / 'seeds' / 'mentors.json'
if seeds_path.exists():
    with app.app_context():
        mentor_service.load_mentors_from_file(seeds_path)
