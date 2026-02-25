#!/usr/bin/env python3
"""Script to view all registered mentors from the database"""
import sqlite3
from pathlib import Path
import base64

DB_PATH = Path(__file__).parent / "teams.db"

def view_all_mentors():
    """Display all mentors"""
    if not DB_PATH.exists():
        print("❌ Database not found. Please run the application first.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM mentors ORDER BY created_at DESC')
    mentors = cursor.fetchall()

    if not mentors:
        print("📋 No mentors registered yet.\n")
        conn.close()
        return

    print("\n" + "="*80)
    print("REGISTERED MENTORS".center(80))
    print("="*80 + "\n")

    for mentor in mentors:
        print(f"ID: {mentor['id']}")
        print(f"Name: {mentor['name']} {mentor['surname']}")
        print(f"Workplace: {mentor['workplace']}")
        print(f"Picture: {mentor['picture_filename']}")
        print(f"Registered: {mentor['created_at']}")
        print("-" * 80)

    print("="*80 + "\n")
    conn.close()

if __name__ == '__main__':
    view_all_mentors()
