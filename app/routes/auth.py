"""Authentication routes"""
from flask import session, jsonify, request
from app.routes import auth_bp
from app.services import teams_service


@auth_bp.route('/login', methods=['GET'])
def login_page():
    """Serve the login page"""
    from flask import render_template
    return render_template('auth/login.html')


@auth_bp.route('/registration', methods=['GET'])
def registration_page():
    """Serve the team registration form"""
    from flask import render_template
    return render_template('auth/registration.html')


@auth_bp.route('/api/login', methods=['POST'])
def login():
    """Handle team login"""
    try:
        data = request.json
        team_name = data.get('teamName', '').strip()
        password = data.get('password', '').strip()

        if not team_name or not password:
            return jsonify({'success': False, 'error': 'Team name and password are required'}), 400

        success, team_id = teams_service.verify_team_credentials(team_name, password)

        if success:
            session['team_name'] = team_name
            session['team_id'] = team_id
            return jsonify({'success': True, 'message': 'Login successful', 'teamName': team_name}), 200
        else:
            return jsonify({'success': False, 'error': 'Invalid team name or password'}), 401

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@auth_bp.route('/api/logout', methods=['POST'])
def logout():
    """Handle team logout"""
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out successfully'}), 200


@auth_bp.route('/api/session', methods=['GET'])
def get_session():
    """Get current session info"""
    team_name = session.get('team_name')
    if team_name:
        return jsonify({'success': True, 'loggedIn': True, 'teamName': team_name}), 200
    else:
        return jsonify({'success': True, 'loggedIn': False}), 200
