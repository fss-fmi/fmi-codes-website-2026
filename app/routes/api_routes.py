"""API routes"""
from flask import jsonify
from app.routes import api_bp
from app.services import ranking_service, regulations_service


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
