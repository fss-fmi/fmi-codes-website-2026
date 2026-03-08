"""API routes — rankings, regulations, and admin matching"""
from flask import jsonify, render_template
from app.routes import api_bp
from app.services import ranking_service, regulations_service
from app.services import matching_service, mentor_selection_service
from app.utils.auth_decorators import admin_required


@api_bp.route('/ranking', methods=['GET'])
def get_ranking():
    """Get rankings sorted by points"""
    try:
        rankings = ranking_service.get_rankings()
        return jsonify({'success': True, 'rankings': rankings}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/regulations', methods=['GET'])
def get_regulations():
    """Get regulations"""
    try:
        regulations = regulations_service.get_regulations()
        return jsonify({'success': True, 'regulations': regulations}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Admin matching endpoints ───────────────────────────────────────

@api_bp.route('/admin/preference-status', methods=['GET'])
@admin_required
def preference_status():
    """Get which teams/mentors have submitted preferences"""
    status = mentor_selection_service.get_preference_submission_status()
    return jsonify({'success': True, **status}), 200


@api_bp.route('/admin/run-matching', methods=['POST'])
@admin_required
def run_matching():
    """Trigger Gale-Shapley matching algorithm"""
    success, message, assignments = matching_service.run_gale_shapley()
    if not success:
        return jsonify({'success': False, 'error': message}), 400

    try:
        matching_service.save_matching_results(assignments)
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to save results: {e}'}), 500

    # Format results for response
    results = {}
    for team_id, mentor_id in assignments:
        results.setdefault(team_id, []).append(mentor_id)

    return jsonify({
        'success': True,
        'message': message,
        'assignment_count': len(assignments),
        'assignments': results,
    }), 200


@api_bp.route('/admin/matching-results', methods=['GET'])
@admin_required
def get_matching_results():
    """Get current matching results"""
    results = matching_service.get_matching_results()
    return jsonify({'success': True, 'results': [dict(r) for r in results]}), 200
