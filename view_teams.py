#!/usr/bin/env python3
"""Script to view all registered teams from the database"""
import sqlite3
from pathlib import Path
import json

DB_PATH = Path(__file__).parent / "teams.db"

def view_all_teams():
    """Display all teams and their participants"""
    if not DB_PATH.exists():
        print("❌ Database not found. Please run the application first.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM teams ORDER BY created_at DESC')
    teams = cursor.fetchall()

    if not teams:
        print("📋 No teams registered yet.\n")
        return

    print("\n" + "="*80)
    print("REGISTERED TEAMS".center(80))
    print("="*80 + "\n")

    for team in teams:
        print(f"Team Name: {team['team_name']}")
        print(f"Participants: {team['participant_count']}")
        print(f"Registered: {team['created_at']}")
        print("-" * 80)

        cursor.execute(
            'SELECT * FROM participants WHERE team_id = ? ORDER BY id',
            (team['id'],)
        )
        participants = cursor.fetchall()

        for i, p in enumerate(participants, 1):
            print(f"  {i}. {p['first_name']} {p['last_name']}")
            print(f"     Faculty #: {p['faculty_number']}")
            print(f"     Discord: {p['discord']}")

        print()

    print("="*80 + "\n")
    conn.close()

if __name__ == '__main__':
    view_all_teams()
