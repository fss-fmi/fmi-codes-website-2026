#!/usr/bin/env python3
import sqlite3
import json
import base64
from flask import Flask, render_template_string, request, jsonify, session
from pathlib import Path
from datetime import datetime
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
DB_PATH = Path(__file__).parent / "website.db"
@app.route('/')
def home():
    """Serve the home page"""
    with open(Path(__file__).parent / 'home.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    # Inject session data into page
    team_name = session.get('team_name', '')
    html_content = html_content.replace('</body>', f'<script>window.loggedInTeam = "{team_name}";</script></body>')
    return html_content

@app.route('/chooseMentor')
def choose_mentor_page():
    """Serve the choose mentor page"""
    with open(Path(__file__).parent / 'chooseMentor.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    team_name = session.get('team_name', '')
    html_content = html_content.replace('</body>', f'<script>window.loggedInTeam = "{team_name}";</script></body>')
    return html_content


@app.route('/team')
def team_page():
    """Serve the team page for logged-in users"""
    with open(Path(__file__).parent / 'team.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    team_name = session.get('team_name', '')
    html_content = html_content.replace('</body>', f'<script>window.loggedInTeam = "{team_name}";</script></body>')
    return html_content
@app.route('/teamRegulations')
def team_regulations_page():
    """Serve the team regulations page"""
    with open(Path(__file__).parent / 'teamRegulations.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    team_name = session.get('team_name', '')
    html_content = html_content.replace('</body>', f'<script>window.loggedInTeam = "{team_name}";</script></body>')
    return html_content

@app.route('/teamSchedule')
def team_schedule_page():
    """Serve the team schedule page"""
    with open(Path(__file__).parent / 'teamSchedule.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    team_name = session.get('team_name', '')
    html_content = html_content.replace('</body>', f'<script>window.loggedInTeam = "{team_name}";</script></body>')
    return html_content

@app.route('/teamMentors')
def team_mentors_page():
    """Serve the team mentors page"""
    with open(Path(__file__).parent / 'teamMentors.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    team_name = session.get('team_name', '')
    html_content = html_content.replace('</body>', f'<script>window.loggedInTeam = "{team_name}";</script></body>')
    return html_content

@app.route('/teamRanking')
def team_ranking_page():
    """Serve the team ranking page"""
    with open(Path(__file__).parent / 'teamRanking.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    team_name = session.get('team_name', '')
    html_content = html_content.replace('</body>', f'<script>window.loggedInTeam = "{team_name}";</script></body>')
    return html_content

@app.route('/teamRegistration')
def team_registration_page():
    """Serve the team registration form"""
    with open(Path(__file__).parent / 'teamRegistration.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    team_name = session.get('team_name', '')
    html_content = html_content.replace('</body>', f'<script>window.loggedInTeam = "{team_name}";</script></body>')
    return html_content

@app.route('/selectedMentors')
def selected_mentors_page():
    """Serve the selected mentors page for the current team"""
    with open(Path(__file__).parent / 'selectedMentors.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    team_name = session.get('team_name', '')
    html_content = html_content.replace('</body>', f'<script>window.loggedInTeam = "{team_name}";</script></body>')
    return html_content

def init_database():
    """Initialize the database with teams, participants, and mentors tables"""
    conn = sqlite3.connect(DB_PATH)
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

    # Ensure uniqueness by name, surname, and workplace
    cursor.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mentors_identity
        ON mentors(name, surname, workplace)
    ''')

    conn.commit()
    conn.close()

def get_team_by_name(team_name):
    """Get team details by team name"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM teams WHERE team_name = ?', (team_name,))
    team = cursor.fetchone()

    if team:
        cursor.execute('SELECT * FROM participants WHERE team_id = ?', (team['id'],))
        participants = [dict(row) for row in cursor.fetchall()]
        team_dict = dict(team)
        team_dict['participants'] = participants
    else:
        team_dict = None

    conn.close()
    return team_dict

def get_all_teams():
    """Get all teams with their participants"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM teams ORDER BY created_at DESC')
    teams = [dict(row) for row in cursor.fetchall()]

    for team in teams:
        cursor.execute('SELECT * FROM participants WHERE team_id = ?', (team['id'],))
        team['participants'] = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return teams


def ensure_team_mentors_table(cursor):
    """Ensure team_mentors table exists before mentor operations"""
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


def serialize_mentor_row(row, selection_count=0):
    """Serialize mentor row with optional picture and selection count"""
    data = {
        'id': row['id'],
        'name': row['name'],
        'surname': row['surname'],
        'workplace': row['workplace'],
        'picture_filename': row.get('picture_filename') if isinstance(row, dict) else row['picture_filename'],
        'selection_count': selection_count
    }
    picture_blob = row['picture'] if 'picture' in row.keys() else None
    if picture_blob:
        data['picture_data'] = base64.b64encode(picture_blob).decode('utf-8')
    else:
        data['picture_data'] = None
    return data


def mentor_exists(name: str, surname: str, workplace: str) -> bool:
    """Check if a mentor already exists by identity fields"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT 1 FROM mentors WHERE name = ? AND surname = ? AND workplace = ?',
        (name, surname, workplace)
    )
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def load_mentors_from_file(json_path: Path) -> int:
    """Load mentors from a JSON file into the database if not already present"""
    if not json_path.exists():
        return 0

    with open(json_path, 'r', encoding='utf-8') as f:
        mentors = json.load(f)

    if not isinstance(mentors, list):
        return 0

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    inserted = 0

    for mentor in mentors:
        name = str(mentor.get('name', '')).strip()
        surname = str(mentor.get('surname', '')).strip()
        workplace = str(mentor.get('workplace', '')).strip()
        picture_path = mentor.get('picturePath')

        if not name or not surname or not workplace:
            continue

        if mentor_exists(name, surname, workplace):
            continue

        picture_data = None
        picture_filename = None
        if picture_path:
            resolved_path = (json_path.parent / picture_path).resolve()
            if resolved_path.exists():
                with open(resolved_path, 'rb') as img_file:
                    picture_data = img_file.read()
                picture_filename = resolved_path.name

        try:
            cursor.execute(
                '''INSERT OR IGNORE INTO mentors (name, surname, workplace, picture, picture_filename)
                   VALUES (?, ?, ?, ?, ?)''',
                (name, surname, workplace, picture_data, picture_filename)
            )
            if cursor.rowcount:
                inserted += 1
        except sqlite3.IntegrityError:
            continue

    conn.commit()
    conn.close()
    return inserted

@app.route('/schedule')
def schedule():
    """Serve the schedule page"""
    with open(Path(__file__).parent / 'schedule.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    team_name = session.get('team_name', '')
    html_content = html_content.replace('</body>', f'<script>window.loggedInTeam = "{team_name}";</script></body>')
    return html_content

@app.route('/mentors')
def mentors_page():
    """Serve the mentors page"""
    with open(Path(__file__).parent / 'mentors.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    team_name = session.get('team_name', '')
    html_content = html_content.replace('</body>', f'<script>window.loggedInTeam = "{team_name}";</script></body>')
    return html_content

@app.route('/regulations')
def regulations_page():
    """Serve the regulations page"""
    with open(Path(__file__).parent / 'regulations.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    team_name = session.get('team_name', '')
    html_content = html_content.replace('</body>', f'<script>window.loggedInTeam = "{team_name}";</script></body>')
    return html_content

@app.route('/api/register', methods=['POST'])
def register_team():
    """Handle team registration"""
    try:
        data = request.json
        team_name = data.get('teamName', '').strip()
        password = data.get('password', '').strip()
        participants = data.get('participants', [])

        # Validation
        if not team_name:
            return jsonify({'success': False, 'error': 'Team name is required'}), 400

        if not password:
            return jsonify({'success': False, 'error': 'Password is required'}), 400

        if len(participants) < 3 or len(participants) > 6:
            return jsonify({'success': False, 'error': 'Team must have 3-6 participants'}), 400

        # Check if team already exists
        if get_team_by_name(team_name):
            return jsonify({'success': False, 'error': f'Team name "{team_name}" is already taken. Please choose a different name.'}), 400

        # Insert into database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        try:
            # Insert team
            cursor.execute(
                'INSERT INTO teams (team_name, password, participant_count) VALUES (?, ?, ?)',
                (team_name, password, len(participants))
            )
            team_id = cursor.lastrowid

            # Insert participants
            for participant in participants:
                cursor.execute(
                    '''INSERT INTO participants
                       (team_id, first_name, last_name, faculty_number, discord)
                       VALUES (?, ?, ?, ?, ?)''',
                    (
                        team_id,
                        participant.get('firstName', '').strip(),
                        participant.get('lastName', '').strip(),
                        participant.get('facultyNumber', '').strip(),
                        participant.get('discord', '').strip()
                    )
                )

            conn.commit()

            return jsonify({
                'success': True,
                'message': f'Team "{team_name}" registered successfully with {len(participants)} participants'
            }), 201

        except sqlite3.IntegrityError as e:
            conn.rollback()
            return jsonify({'success': False, 'error': 'Database error: ' + str(e)}), 400
        finally:
            conn.close()

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/teams', methods=['GET'])
def get_teams():
    """Get all registered teams"""
    teams = get_all_teams()
    return jsonify({'success': True, 'teams': teams}), 200

@app.route('/api/teams/<team_name>', methods=['GET'])
def get_team(team_name):
    """Get a specific team by name"""
    team = get_team_by_name(team_name)
    if team:
        return jsonify({'success': True, 'team': team}), 200
    else:
        return jsonify({'success': False, 'error': 'Team not found'}), 404

@app.route('/api/teams/<team_name>', methods=['DELETE'])
def delete_team(team_name):
    """Delete a team and its participants"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Get team
        cursor.execute('SELECT id FROM teams WHERE team_name = ?', (team_name,))
        team = cursor.fetchone()

        if not team:
            return jsonify({'success': False, 'error': 'Team not found'}), 404

        team_id = team[0]

        # Delete participants
        cursor.execute('DELETE FROM participants WHERE team_id = ?', (team_id,))

        # Delete team
        cursor.execute('DELETE FROM teams WHERE id = ?', (team_id,))

        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': f'Team "{team_name}" deleted successfully'}), 200

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Mentor Routes

@app.route('/api/mentors', methods=['POST'])
def register_mentor():
    """Handle mentor registration"""
    try:
        # Check if request has file
        if 'picture' not in request.files and 'pictureData' not in request.form:
            return jsonify({'success': False, 'error': 'Picture is required'}), 400

        name = request.form.get('name', '').strip()
        surname = request.form.get('surname', '').strip()
        workplace = request.form.get('workplace', '').strip()

        # Validation
        if not name or not surname or not workplace:
            return jsonify({'success': False, 'error': 'All fields are required'}), 400

        picture_data = None
        picture_filename = None

        # Handle file upload
        if 'picture' in request.files:
            file = request.files['picture']
            if file.filename:
                picture_data = file.read()
                picture_filename = file.filename

        # Insert into database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        try:
            cursor.execute(
                '''INSERT INTO mentors (name, surname, workplace, picture, picture_filename)
                   VALUES (?, ?, ?, ?, ?)''',
                (name, surname, workplace, picture_data, picture_filename)
            )
            conn.commit()
            mentor_id = cursor.lastrowid

            return jsonify({
                'success': True,
                'message': f'Mentor "{name} {surname}" registered successfully',
                'mentor_id': mentor_id
            }), 201

        except Exception as e:
            conn.rollback()
            return jsonify({'success': False, 'error': str(e)}), 400
        finally:
            conn.close()

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/mentors', methods=['GET'])
def get_mentors():
    """Get all registered mentors"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('SELECT id, name, surname, workplace, picture_filename, created_at FROM mentors ORDER BY created_at DESC')
        mentors = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return jsonify({'success': True, 'mentors': mentors}), 200

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/mentors/<int:mentor_id>/picture', methods=['GET'])
def get_mentor_picture(mentor_id):
    """Get mentor picture by ID"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute('SELECT picture, picture_filename FROM mentors WHERE id = ?', (mentor_id,))
        result = cursor.fetchone()
        conn.close()

        if not result or not result[0]:
            return jsonify({'success': False, 'error': 'Picture not found'}), 404

        picture_data, filename = result
        return picture_data, 200, {'Content-Type': 'image/png', 'Content-Disposition': f'inline; filename={filename}'}

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/mentors/<int:mentor_id>', methods=['DELETE'])
def delete_mentor(mentor_id):
    """Delete a mentor"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute('DELETE FROM mentors WHERE id = ?', (mentor_id,))

        if cursor.rowcount == 0:
            return jsonify({'success': False, 'error': 'Mentor not found'}), 404

        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': 'Mentor deleted successfully'}), 200

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/mentors/available', methods=['GET'])
def get_available_mentors_for_selection():
    """Return mentors available for selection (capacity 3), or the current team's selection if already chosen"""
    team_id = session.get('team_id')
    if not team_id:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    ensure_team_mentors_table(cursor)

    # Current selection for this team
    cursor.execute('''
        SELECT m.*, tm.mentor_id
        FROM mentors m
        JOIN team_mentors tm ON tm.mentor_id = m.id
        WHERE tm.team_id = ?
    ''', (team_id,))
    selected_rows = cursor.fetchall()

    # Selection counts per mentor
    cursor.execute('SELECT mentor_id, COUNT(*) as cnt FROM team_mentors GROUP BY mentor_id')
    counts = {row['mentor_id']: row['cnt'] for row in cursor.fetchall()}

    if selected_rows:
        selected = [serialize_mentor_row(row, counts.get(row['id'], 0)) for row in selected_rows]
        conn.close()
        return jsonify({'success': True, 'selected': selected, 'available': []}), 200

    # If no selection yet, return mentors with capacity < 3
    cursor.execute('SELECT * FROM mentors')
    mentors = []
    for row in cursor.fetchall():
        selection_count = counts.get(row['id'], 0)
        if selection_count < 3:
            mentors.append(serialize_mentor_row(row, selection_count))

    conn.close()
    return jsonify({'success': True, 'selected': [], 'available': mentors}), 200

# Ranking routes

@app.route('/ranking')
def ranking_page():
    """Serve the ranking page"""
    with open(Path(__file__).parent / 'ranking.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    team_name = session.get('team_name', '')
    html_content = html_content.replace('</body>', f'<script>window.loggedInTeam = "{team_name}";</script></body>')
    return html_content

@app.route('/login')
def login_page():
    """Serve the login page"""
    with open(Path(__file__).parent / 'login.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    team_name = session.get('team_name', '')
    html_content = html_content.replace('</body>', f'<script>window.loggedInTeam = "{team_name}";</script></body>')
    return html_content

@app.route('/api/login', methods=['POST'])
def login():
    """Handle team login"""
    try:
        data = request.json
        team_name = data.get('teamName', '').strip()
        password = data.get('password', '').strip()

        if not team_name or not password:
            return jsonify({'success': False, 'error': 'Team name and password are required'}), 400

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM teams WHERE team_name = ? AND password = ?', (team_name, password))
        team = cursor.fetchone()
        conn.close()

        if team:
            session['team_name'] = team_name
            session['team_id'] = team['id']
            return jsonify({'success': True, 'message': 'Login successful', 'teamName': team_name}), 200
        else:
            return jsonify({'success': False, 'error': 'Invalid team name or password'}), 401

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/logout', methods=['POST'])
def logout():
    """Handle team logout"""
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out successfully'}), 200

@app.route('/api/chooseMentor', methods=['POST'])
def choose_mentor():
    """Handle mentor selection for a team"""
    try:
        team_id = session.get('team_id')
        if not team_id:
            return jsonify({'success': False, 'error': 'You must be logged in to select mentors'}), 401

        data = request.json
        mentor_ids = data.get('mentorIds', [])

        if len(mentor_ids) != 3:
            return jsonify({'success': False, 'error': 'You must select exactly 3 mentors'}), 400

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        ensure_team_mentors_table(cursor)

        # Validate mentor existence and capacity (max 3 teams)
        cursor.execute('SELECT mentor_id, COUNT(*) as cnt FROM team_mentors GROUP BY mentor_id')
        counts = {row['mentor_id']: row['cnt'] for row in cursor.fetchall()}

        cursor.execute('SELECT mentor_id FROM team_mentors WHERE team_id = ?', (team_id,))
        existing_selection = {row['mentor_id'] for row in cursor.fetchall()}

        full_mentors = []
        for mentor_id in mentor_ids:
            cursor.execute('SELECT id FROM mentors WHERE id = ?', (mentor_id,))
            if cursor.fetchone() is None:
                conn.close()
                return jsonify({'success': False, 'error': f'Mentor with id {mentor_id} does not exist'}), 404

            current_count = counts.get(mentor_id, 0)
            # Allow keeping already selected mentors even if at capacity
            if mentor_id not in existing_selection and current_count >= 3:
                full_mentors.append(mentor_id)

        if full_mentors:
            conn.close()
            return jsonify({'success': False, 'error': 'One or more mentors are already at capacity (3 teams). Please pick others.'}), 400

        # Replace selection
        cursor.execute('DELETE FROM team_mentors WHERE team_id = ?', (team_id,))
        for mentor_id in mentor_ids:
            cursor.execute('INSERT INTO team_mentors (team_id, mentor_id) VALUES (?, ?)', (team_id, mentor_id))

        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': 'Mentors selected successfully'}), 200

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/session', methods=['GET'])
def get_session():
    """Get current session info"""
    team_name = session.get('team_name')
    if team_name:
        return jsonify({'success': True, 'loggedIn': True, 'teamName': team_name}), 200
    else:
        return jsonify({'success': True, 'loggedIn': False}), 200

@app.route('/api/ranking', methods=['GET'])
def get_ranking():
    """Return rankings from rankings.json sorted by points desc"""
    try:
        path = Path(__file__).parent / 'rankings.json'
        if not path.exists():
            return jsonify({'success': True, 'rankings': []}), 200

        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if not isinstance(data, list):
            data = []

        normalized = []
        for it in data:
            team = str(it.get('team', '')).strip()
            pts = it.get('points', 0)
            img = it.get('image')
            if team:
                try:
                    pts = int(pts)
                except Exception:
                    pts = 0
                normalized.append({'team': team, 'points': pts, 'image': img})

        normalized.sort(key=lambda x: x['points'], reverse=True)

        return jsonify({'success': True, 'rankings': normalized}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
# Regulations API

@app.route('/api/regulations', methods=['GET'])
def get_regulations():
    """Return regulations from regulations.json"""
    try:
        path = Path(__file__).parent / 'regulations.json'
        if not path.exists():
            return jsonify({'success': True, 'regulations': []}), 200

        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if not isinstance(data, list):
            data = []

        # Normalize items to have question/answer keys
        normalized = []
        for it in data:
            q = str(it.get('question', '')).strip()
            a = str(it.get('answer', '')).strip()
            if q or a:
                normalized.append({'question': q, 'answer': a})

        return jsonify({'success': True, 'regulations': normalized}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    init_database()
    seeded = load_mentors_from_file(Path(__file__).parent / 'mentors.json')
    if seeded:
        print(f"✓ Seeded {seeded} mentor(s) from mentors.json")
    print(f"✓ Database initialized at: {DB_PATH}")
    print(f"✓ Starting server at http://localhost:5000")
    app.run(debug=True, port=5000)
