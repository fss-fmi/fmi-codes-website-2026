#!/usr/bin/env python3
"""WSGI entry point for gunicorn."""
import os
from pathlib import Path
from app import create_app
from app.services import mentor_service

app = create_app(os.environ.get('FLASK_ENV', 'production'))

# Seed all lookup/data tables on startup (idempotent)
seeds_dir = Path(__file__).parent / 'database' / 'seeds'
with app.app_context():
    mentor_service.load_universities_from_file(seeds_dir / 'universities.json')
    mentor_service.load_specialties_from_file(seeds_dir / 'specialties.json')
    mentor_service.load_mentors_from_file(seeds_dir / 'mentors.json')
