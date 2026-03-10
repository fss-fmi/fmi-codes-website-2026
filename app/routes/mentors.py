"""Mentor management routes — JWT-protected"""
import base64
from io import BytesIO
from flask import jsonify, request, send_file, render_template, g, current_app
from app.routes import mentors_bp
from app.services import mentor_service, mentor_selection_service
from app.database import execute_query
from app.utils.auth_decorators import (
    token_required, participant_required, captain_required, mentor_required,
)


@mentors_bp.route('/mentors', methods=['GET'])
def mentors_page():
    """Serve the public mentors listing page (or stay-tuned placeholder)"""
    if current_app.config.get('MENTORS_STAY_TUNED'):
        return render_template('mentors/mentorsStayTuned.html')
    return render_template('mentors/mentors.html')


@mentors_bp.route('/chooseMentor', methods=['GET'])
def choose_mentor_page():
    """Serve the captain's mentor preference page"""
    return render_template('mentors/chooseMentor.html')


@mentors_bp.route('/selectedMentors', methods=['GET'])
def selected_mentors_page():
    """Serve the selected mentors page"""
    return render_template('mentors/selectedMentors.html')


@mentors_bp.route('/mentorDashboard', methods=['GET'])
def mentor_dashboard_page():
    """Serve the mentor dashboard / team preference page"""
    return render_template('mentors/mentorDashboard.html')


# ── Public mentor API ──────────────────────────────────────────────

@mentors_bp.route('/api/mentors', methods=['GET'])
def get_mentors():
    """Get all registered mentors (public)"""
    try:
        mentors = mentor_service.get_all_mentors()
        return jsonify({'success': True, 'mentors': [dict(m) for m in mentors]}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@mentors_bp.route('/api/mentors/<int:mentor_id>/picture', methods=['GET'])
def get_mentor_picture(mentor_id):
    """Get mentor picture by ID"""
    try:
        picture_data, filename = mentor_service.get_mentor_picture(mentor_id)
        if not picture_data:
            return jsonify({'success': False, 'error': 'Picture not found'}), 404
        return send_file(
            BytesIO(picture_data),
            mimetype='image/png',
            as_attachment=False,
            download_name=filename or 'mentor_picture.png'
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Team mentor preferences (captain) ─────────────────────────────

@mentors_bp.route('/api/teams/<int:team_id>/available-mentors', methods=['GET'])
@captain_required
def get_available_mentors(team_id):
    """List all active mentors for captain to rank"""
    if g.current_user.get('team_id') != team_id:
        return jsonify({'success': False, 'error': 'Not your team'}), 403
    mentors = mentor_selection_service.get_available_mentors_for_ranking(team_id)
    return jsonify({'success': True, 'mentors': [dict(m) for m in mentors]}), 200


@mentors_bp.route('/api/teams/<int:team_id>/mentor-preferences', methods=['POST'])
@captain_required
def set_team_preferences(team_id):
    """Captain sets ranked mentor preferences for the team"""
    if g.current_user.get('team_id') != team_id:
        return jsonify({'success': False, 'error': 'Not your team'}), 403

    data = request.get_json(silent=True) or {}
    preferences = data.get('preferences', [])

    success, message = mentor_selection_service.set_team_mentor_preferences(team_id, preferences)
    if success:
        return jsonify({'success': True, 'message': message}), 200
    return jsonify({'success': False, 'error': message}), 400


@mentors_bp.route('/api/teams/<int:team_id>/mentor-preferences', methods=['GET'])
@captain_required
def get_team_preferences(team_id):
    """Get team's current mentor preferences"""
    if g.current_user.get('team_id') != team_id:
        return jsonify({'success': False, 'error': 'Not your team'}), 403

    prefs = mentor_selection_service.get_team_mentor_preferences(team_id)
    return jsonify({'success': True, 'preferences': [dict(p) for p in prefs]}), 200


# ── Mentor team preferences (mentor) ──────────────────────────────

@mentors_bp.route('/api/mentors/available-teams', methods=['GET'])
@mentor_required
def get_available_teams():
    """List all active teams for mentor to rank"""
    teams = mentor_selection_service.get_active_teams_for_ranking()
    return jsonify({'success': True, 'teams': [dict(t) for t in teams]}), 200


@mentors_bp.route('/api/mentors/team-preferences', methods=['POST'])
@mentor_required
def set_mentor_preferences():
    """Mentor sets ranked team preferences"""
    data = request.get_json(silent=True) or {}
    preferences = data.get('preferences', [])

    success, message = mentor_selection_service.set_mentor_team_preferences(
        g.current_user['user_id'], preferences
    )
    if success:
        return jsonify({'success': True, 'message': message}), 200
    return jsonify({'success': False, 'error': message}), 400


@mentors_bp.route('/api/mentors/team-preferences', methods=['GET'])
@mentor_required
def get_mentor_preferences():
    """Get mentor's current team preferences"""
    prefs = mentor_selection_service.get_mentor_team_preferences(g.current_user['user_id'])
    return jsonify({'success': True, 'preferences': [dict(p) for p in prefs]}), 200
