#!/usr/bin/env python3
"""Application entry point and server runner"""

import os
from pathlib import Path

from dotenv import load_dotenv


def main():
    """Create and run the Flask application"""
    # Load environment before importing modules that read config at import time.
    load_dotenv()

    from app import create_app
    from app.services import mentor_service

    # Get environment
    env = os.environ.get("FLASK_ENV", "development")

    # Create app
    app = create_app(env)

    # Seed all lookup/data tables from JSON seed files if available (idempotent)
    seeds_dir = Path(__file__).parent / "database" / "seeds"
    with app.app_context():
        seeded = mentor_service.load_universities_from_file(seeds_dir / "universities.json")
        if seeded:
            print(f"[OK] Seeded {seeded} university(s) from universities.json")
        seeded = mentor_service.load_specialties_from_file(seeds_dir / "specialties.json")
        if seeded:
            print(f"[OK] Seeded {seeded} specialty(s) from specialties.json")
        seeded = mentor_service.load_mentors_from_file(seeds_dir / "mentors.json")
        if seeded:
            print(f"[OK] Seeded {seeded} mentor(s) from mentors.json")

    # Print startup info
    print(f"\n[OK] Database: {app.config.get('DATABASE_URL', 'configured')}")
    print("[OK] Starting server at http://localhost:5001")
    print("[OK] Press Ctrl+C to stop the server\n")

    # Run the app
    # Bind to loopback only in development — never expose Werkzeug debugger
    # to the network.  Set FLASK_HOST=0.0.0.0 only when proxied by an ingress.
    app.run(
        host=os.environ.get("FLASK_HOST", "127.0.0.1"),
        port=int(os.environ.get("FLASK_PORT", 5001)),
        debug=env == "development",
    )


if __name__ == "__main__":
    main()
