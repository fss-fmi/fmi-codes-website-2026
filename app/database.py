"""Database initialization and utilities"""
import sqlite3
from pathlib import Path


def init_database(app):
    """Initialize the database with required tables"""
    db_path = app.config['DATABASE_PATH']
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create teams table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_name TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            participant_count INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create participants table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            faculty_number TEXT NOT NULL,
            discord TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (team_id) REFERENCES teams(id)
        )
    ''')

    # Create mentors table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mentors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            surname TEXT NOT NULL,
            workplace TEXT NOT NULL,
            picture BLOB,
            picture_filename TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create unique index on mentors
    cursor.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mentors_identity
        ON mentors(name, surname, workplace)
    ''')

    # Create team_mentors table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS team_mentors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            mentor_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (team_id) REFERENCES teams(id),
            FOREIGN KEY (mentor_id) REFERENCES mentors(id),
            UNIQUE(team_id, mentor_id)
        )
    ''')

    conn.commit()
    conn.close()


def get_db_connection(app):
    """Get a database connection"""
    conn = sqlite3.connect(str(app.config['DATABASE_PATH']))
    conn.row_factory = sqlite3.Row
    return conn
