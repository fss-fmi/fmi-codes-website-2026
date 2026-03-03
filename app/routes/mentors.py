"""Mentor management routes"""
from flask import jsonify, request, send_file, render_template, session
from io import BytesIO
from app.routes import mentors_bp
from app.services import mentor_service, mentor_selection_service


@mentors_bp.route('/mentors', methods=['GET'])
def mentors_page():
    """Serve the mentors page"""
    team_name = session.get('team_name', '')
    return render_template('mentors/mentors.html', logged_in_team=team_name)


@mentors_bp.route('/chooseMentor', methods=['GET'])
def choose_mentor_page():
    """Serve the choose mentor page"""
    team_name = session.get('team_name', '')
    return render_template('mentors/chooseMentor.html', logged_in_team=team_name)


@mentors_bp.route('/selectedMentors', methods=['GET'])
def selected_mentors_page():
    """Serve the selected mentors page for the current team"""
    team_name = session.get('team_name', '')
    return render_template('mentors/selectedMentors.html', logged_in_team=team_name)


@mentors_bp.route('/api/mentors', methods=['POST'])
def register_mentor():
    """Handle mentor registration"""
    try:
        # Check if request has file
        if 'picture' not in request.files and 'pictureData' not in request.form:
            return jsonify({'success': False, 'error': 'Picture is required'}), 400

        name = request.form.get('name', '').strip()
        surname = request.form.get('surname', '').strip()
        workplace = request.form.get('workplace', '').strip()

        picture_data = None
        picture_filename = None

        # Handle file upload
        if 'picture' in request.files:
            file = request.files['picture']
            if file.filename:
                picture_data = file.read()
                picture_filename = file.filename

        success, message, mentor_id = mentor_service.register_mentor(
            name, surname, workplace, picture_data, picture_filename
        )

        if success:
            return jsonify({
                'success': True,
                'message': message,
                'mentor_id': mentor_id
            }), 201
        else:
            return jsonify({'success': False, 'error': message}), 400

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@mentors_bp.route('/api/mentors', methods=['GET'])
def get_mentors():
    """Get all registered mentors"""
    try:
        mentors = mentor_service.get_all_mentors()
        return jsonify({'success': True, 'mentors': mentors}), 200

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


@mentors_bp.route('/api/mentors/<int:mentor_id>', methods=['DELETE'])
def delete_mentor(mentor_id):
    """Delete a mentor"""
    try:
        success, message = mentor_service.delete_mentor(mentor_id)

        if success:
            return jsonify({'success': True, 'message': message}), 200
        else:
            return jsonify({'success': False, 'error': message}), 404

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@mentors_bp.route('/api/mentors/available', methods=['GET'])
def get_available_mentors_for_selection():
    """Return mentors available for selection or the current team's selection"""
    team_id = session.get('team_id')
    if not team_id:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401

    try:
        result = mentor_selection_service.get_available_mentors_for_team(team_id)
        return jsonify({'success': True, **result}), 200

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@mentors_bp.route('/api/chooseMentor', methods=['POST'])
def choose_mentor():
    """Handle mentor selection for a team"""
    try:
        team_id = session.get('team_id')
        if not team_id:
            return jsonify({'success': False, 'error': 'You must be logged in to select mentors'}), 401

        data = request.json
        mentor_ids = data.get('mentorIds', [])

        success, message = mentor_selection_service.select_mentors_for_team(team_id, mentor_ids)

        if success:
            return jsonify({'success': True, 'message': message}), 200
        else:
            return jsonify({'success': False, 'error': message}), 400

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
