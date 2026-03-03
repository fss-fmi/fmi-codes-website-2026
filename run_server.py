#!/usr/bin/env python3
"""Application entry point and server runner"""
import os
from pathlib import Path
from app import create_app
from app.database import init_database
from app.services import mentor_service


def main():
    """Create and run the Flask application"""
    # Get environment
    env = os.environ.get('FLASK_ENV', 'development')
    
    # Create app
    app = create_app(env)
    
    # Load mentor data from JSON seed file if available
    seeds_path = Path(__file__).parent / 'database' / 'seeds' / 'mentors.json'
    if seeds_path.exists():
        with app.app_context():
            seeded = mentor_service.load_mentors_from_file(seeds_path)
            if seeded:
                print(f"✓ Seeded {seeded} mentor(s) from mentors.json")
    
    # Print startup info
    db_path = app.config['DATABASE_PATH']
    print(f"\n✓ Database: {db_path}")
    print(f"✓ Starting server at http://localhost:5000")
    print(f"✓ Press Ctrl+C to stop the server\n")
    
    # Run the app
    app.run(
        host=os.environ.get('FLASK_HOST', '0.0.0.0'),
        port=int(os.environ.get('FLASK_PORT', 5000)),
        debug=env == 'development'
    )


if __name__ == '__main__':
    main()
