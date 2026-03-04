"""Team management routes"""
from flask import jsonify, request, render_template, session
from app.routes import teams_bp
from app.services import teams_service


@teams_bp.route('/team', methods=['GET'])
def team_page():
    """Serve the team page for logged-in users"""
    team_name = session.get('team_name', '')
    return render_template('teams/team.html', logged_in_team=team_name)


@teams_bp.route('/teamMentors', methods=['GET'])
def team_mentors_page():
    """Serve the team mentors page"""
    team_name = session.get('team_name', '')
    return render_template('teams/teamMentors.html', logged_in_team=team_name)


@teams_bp.route('/teamSchedule', methods=['GET'])
def team_schedule_page():
    """Serve the team schedule page"""
    team_name = session.get('team_name', '')
    return render_template('teams/teamSchedule.html', logged_in_team=team_name)


@teams_bp.route('/teamRegulations', methods=['GET'])
def team_regulations_page():
    """Serve the team regulations page"""
    team_name = session.get('team_name', '')
    return render_template('teams/teamRegulations.html', logged_in_team=team_name)


@teams_bp.route('/api/register', methods=['POST'])
def register_team():
    """Handle team registration"""
    try:
        data = request.json
        team_name = data.get('teamName', '').strip()
        password = data.get('password', '').strip()
        participants = data.get('participants', [])

        success, message, team_id = teams_service.register_team(team_name, password, participants)

        if success:
            return jsonify({'success': True, 'message': message}), 201
        else:
            return jsonify({'success': False, 'error': message}), 400

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@teams_bp.route('/api/teams', methods=['GET'])
def get_teams():
    """Get all registered teams"""
    teams = teams_service.get_all_teams()
    return jsonify({'success': True, 'teams': teams}), 200


@teams_bp.route('/api/teams/<team_name>', methods=['GET'])
def get_team(team_name):
    """Get a specific team by name"""
    team = teams_service.get_team_by_name(team_name)
    if team:
        return jsonify({'success': True, 'team': team}), 200
    else:
        return jsonify({'success': False, 'error': 'Team not found'}), 404


@teams_bp.route('/api/teams/<team_name>', methods=['DELETE'])
def delete_team(team_name):
    """Delete a team and its participants"""
    try:
        success, message = teams_service.delete_team(team_name)
        if success:
            return jsonify({'success': True, 'message': message}), 200
        else:
            return jsonify({'success': False, 'error': message}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
