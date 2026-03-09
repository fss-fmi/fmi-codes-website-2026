"""API routes — rankings, regulations, admin matching, and lookup data"""
from flask import jsonify, request, render_template
from app.routes import api_bp
from app.database import execute_query, execute_insert
from app.services import ranking_service, regulations_service
from app.services import matching_service, mentor_selection_service
from app.utils.auth_decorators import admin_required
import logging

logger = logging.getLogger(__name__)


# ── Lookup-data endpoints (universities & specialties) ─────────────

@api_bp.route('/universities', methods=['GET'])
def get_universities():
    """Return seed universities only (curated list)"""
    from flask import current_app
    try:
        rows = execute_query(
            current_app,
            "SELECT id, name, city, country FROM universities WHERE is_seed = TRUE ORDER BY id",
            fetch_all=True,
        )
        return jsonify({'success': True, 'universities': [dict(r) for r in rows]}), 200
    except Exception as e:
        logger.error(f"Error fetching universities: {e}")
        return jsonify({'success': False, 'error': 'Failed to fetch universities'}), 500


@api_bp.route('/specialties', methods=['GET'])
def get_specialties():
    """Return seed specialties only (curated list)"""
    from flask import current_app
    try:
        rows = execute_query(
            current_app,
            "SELECT id, name FROM specialties WHERE is_seed = TRUE ORDER BY id",
            fetch_all=True,
        )
        return jsonify({'success': True, 'specialties': [dict(r) for r in rows]}), 200
    except Exception as e:
        logger.error(f"Error fetching specialties: {e}")
        return jsonify({'success': False, 'error': 'Failed to fetch specialties'}), 500


@api_bp.route('/universities', methods=['POST'])
def create_university():
    """Create a user-submitted university (is_seed = FALSE). Returns existing ID if name already taken."""
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    city = (data.get('city') or '').strip()
    country = (data.get('country') or '').strip()

    if not name or not city or not country:
        return jsonify({'success': False, 'error': 'Name, city, and country are required'}), 400

    from flask import current_app
    # Check for existing university with the same name
    existing = execute_query(
        current_app,
        "SELECT id FROM universities WHERE name = %s",
        (name,),
        fetch_one=True,
    )
    if existing:
        return jsonify({'success': True, 'id': existing['id'], 'existing': True}), 200

    try:
        uid = execute_insert(
            current_app,
            "INSERT INTO universities (name, city, country, is_seed) VALUES (%s, %s, %s, FALSE) RETURNING id",
            (name, city, country),
        )
        return jsonify({'success': True, 'id': uid}), 201
    except Exception as e:
        logger.error(f"Error creating university: {e}")
        return jsonify({'success': False, 'error': 'Failed to create university'}), 500


@api_bp.route('/specialties', methods=['POST'])
def create_specialty():
    """Create a user-submitted specialty (is_seed = FALSE). Returns existing ID if name already taken."""
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()

    if not name:
        return jsonify({'success': False, 'error': 'Name is required'}), 400

    from flask import current_app
    existing = execute_query(
        current_app,
        "SELECT id FROM specialties WHERE name = %s",
        (name,),
        fetch_one=True,
    )
    if existing:
        return jsonify({'success': True, 'id': existing['id'], 'existing': True}), 200

    try:
        sid = execute_insert(
            current_app,
            "INSERT INTO specialties (name, description, is_seed) VALUES (%s, NULL, FALSE) RETURNING id",
            (name,),
        )
        return jsonify({'success': True, 'id': sid}), 201
    except Exception as e:
        logger.error(f"Error creating specialty: {e}")
        return jsonify({'success': False, 'error': 'Failed to create specialty'}), 500


# ── Rankings & Regulations ─────────────────────────────────────────

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
