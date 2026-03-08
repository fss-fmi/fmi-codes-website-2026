"""Authentication routes — JWT-based individual auth for participants, mentors, and admin"""
from flask import jsonify, request, render_template, current_app
from app.routes import auth_bp
from app.services.auth_service import hash_password, verify_password, generate_token
from app.database import execute_query, execute_insert
from app.utils.auth_decorators import token_required
from flask import g
import logging

logger = logging.getLogger(__name__)


@auth_bp.route('/login', methods=['GET'])
def login_page():
    """Serve the login page"""
    return render_template('auth/login.html')


@auth_bp.route('/registration', methods=['GET'])
def registration_page():
    """Serve the participant registration form"""
    return render_template('auth/registration.html')


@auth_bp.route('/api/auth/register', methods=['POST'])
def register_participant():
    """Register a new participant and return JWT."""
    data = request.get_json(silent=True) or {}
    required = ['first_name', 'last_name', 'email', 'password', 'phone_number',
                'faculty_number', 'course', 'specialty_id', 'university_id']
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({'success': False, 'error': f'Missing fields: {", ".join(missing)}'}), 400

    email = data['email'].strip().lower()
    existing = execute_query(current_app, "SELECT id FROM participants WHERE email = %s", (email,), fetch_one=True)
    if existing:
        return jsonify({'success': False, 'error': 'Email already registered'}), 409

    fac = data['faculty_number'].strip()
    existing_fac = execute_query(current_app, "SELECT id FROM participants WHERE faculty_number = %s", (fac,), fetch_one=True)
    if existing_fac:
        return jsonify({'success': False, 'error': 'Faculty number already registered'}), 409

    course = int(data['course'])
    if not 1 <= course <= 4:
        return jsonify({'success': False, 'error': 'Course must be between 1 and 4'}), 400

    pw_hash = hash_password(data['password'])

    query = """
        INSERT INTO participants
            (first_name, last_name, email, phone_number, faculty_number,
             course, specialty_id, university_id, password_hash, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'active')
        RETURNING id
    """
    try:
        pid = execute_insert(current_app, query, (
            data['first_name'].strip(), data['last_name'].strip(), email,
            data['phone_number'].strip(), fac, course,
            int(data['specialty_id']), int(data['university_id']), pw_hash
        ))
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return jsonify({'success': False, 'error': 'Registration failed'}), 500

    token = generate_token(pid, 'participant')
    return jsonify({'success': True, 'token': token, 'user_id': pid, 'role': 'participant'}), 201


@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    """Login for participants, mentors, or admin. Returns JWT."""
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password', '')
    role = (data.get('role') or 'participant').strip().lower()

    if not email or not password:
        return jsonify({'success': False, 'error': 'Email and password are required'}), 400

    # Admin login
    if role == 'admin':
        admin_email = current_app.config.get('ADMIN_EMAIL', '')
        admin_password = current_app.config.get('ADMIN_PASSWORD', '')
        if email == admin_email and password == admin_password:
            token = generate_token(0, 'admin')
            return jsonify({'success': True, 'token': token, 'user_id': 0, 'role': 'admin'}), 200
        return jsonify({'success': False, 'error': 'Invalid admin credentials'}), 401

    if role == 'participant':
        user = execute_query(
            current_app,
            "SELECT id, password_hash FROM participants WHERE email = %s AND status = 'active'",
            (email,), fetch_one=True
        )
    elif role == 'mentor':
        user = execute_query(
            current_app,
            "SELECT id, password_hash FROM mentors WHERE email = %s AND status = 'active'",
            (email,), fetch_one=True
        )
    else:
        return jsonify({'success': False, 'error': 'Invalid role'}), 400

    if not user or not user.get('password_hash'):
        return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

    if not verify_password(password, user['password_hash']):
        return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

    token = generate_token(user['id'], role)
    return jsonify({'success': True, 'token': token, 'user_id': user['id'], 'role': role}), 200


@auth_bp.route('/api/auth/me', methods=['GET'])
@token_required
def get_me():
    """Return current user profile from JWT."""
    user = g.current_user
    if user['role'] == 'admin':
        return jsonify({'success': True, 'user': {'role': 'admin'}}), 200

    if user['role'] == 'participant':
        profile = execute_query(
            current_app,
            """SELECT p.id, p.first_name, p.last_name, p.email, p.phone_number,
                      p.faculty_number, p.course, p.is_captain, p.team_id, p.status,
                      s.name as specialty, u.name as university, t.team_name, t.join_code
               FROM participants p
               LEFT JOIN specialties s ON p.specialty_id = s.id
               LEFT JOIN universities u ON p.university_id = u.id
               LEFT JOIN teams t ON p.team_id = t.id
               WHERE p.id = %s""",
            (user['user_id'],), fetch_one=True
        )
    else:
        profile = execute_query(
            current_app,
            """SELECT id, first_name, last_name, email, phone_number,
                      company_name, bio, status
               FROM mentors WHERE id = %s""",
            (user['user_id'],), fetch_one=True
        )

    if not profile:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    profile_dict = dict(profile)
    profile_dict['role'] = user['role']
    return jsonify({'success': True, 'user': profile_dict}), 200


@auth_bp.route('/api/auth/change-password', methods=['PATCH'])
@token_required
def change_password():
    """Change the current user's password. Requires current password verification."""
    user = g.current_user
    if user['role'] == 'admin':
        return jsonify({'success': False, 'error': 'Admin password cannot be changed here'}), 403

    data = request.get_json(silent=True) or {}
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')

    if not current_password or not new_password:
        return jsonify({'success': False, 'error': 'Current password and new password are required'}), 400

    if len(new_password) < 6:
        return jsonify({'success': False, 'error': 'New password must be at least 6 characters'}), 400

    table = 'participants' if user['role'] == 'participant' else 'mentors'
    row = execute_query(
        current_app,
        f"SELECT password_hash FROM {table} WHERE id = %s",
        (user['user_id'],), fetch_one=True
    )

    if not row or not verify_password(current_password, row['password_hash']):
        return jsonify({'success': False, 'error': 'Current password is incorrect'}), 401

    new_hash = hash_password(new_password)
    execute_query(
        current_app,
        f"UPDATE {table} SET password_hash = %s WHERE id = %s",
        (new_hash, user['user_id'])
    )

    return jsonify({'success': True, 'message': 'Password changed successfully'}), 200
