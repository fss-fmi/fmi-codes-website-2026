"""Static page routes"""
from flask import render_template, session, send_from_directory
from pathlib import Path
from app.routes import pages_bp


@pages_bp.route('/')
def home():
    """Serve the home page"""
    team_name = session.get('team_name', '')
    return render_template('home.html', logged_in_team=team_name)


@pages_bp.route('/ranking')
def ranking_page():
    """Serve the ranking page"""
    team_name = session.get('team_name', '')
    return render_template('rankings/ranking.html', logged_in_team=team_name)


@pages_bp.route('/teamRanking')
def team_ranking_page():
    """Serve the team ranking page"""
    team_name = session.get('team_name', '')
    return render_template('rankings/teamRanking.html', logged_in_team=team_name)


@pages_bp.route('/regulations')
def regulations_page():
    """Serve the regulations page"""
    team_name = session.get('team_name', '')
    return render_template('regulations.html', logged_in_team=team_name)


@pages_bp.route('/teamRegulations')
def team_regulations_page_alt():
    """Serve the team regulations page (alternate)"""
    team_name = session.get('team_name', '')
    return render_template('teams/teamRegulations.html', logged_in_team=team_name)


@pages_bp.route('/schedule')
def schedule():
    """Serve the schedule page"""
    team_name = session.get('team_name', '')
    return render_template('schedule.html', logged_in_team=team_name)


@pages_bp.route('/navbar.html')
def navbar_fragment():
    """Serve reusable navbar fragment"""
    return render_template('navbar.html')


# Serve static data files (JSON)
@pages_bp.route('/mentors.json')
def mentors_data_file():
    """Serve mentors data JSON file"""
    root = Path(__file__).parent.parent.parent
    return send_from_directory(root, 'mentors.json')


@pages_bp.route('/rankings.json')
def rankings_data_file():
    """Serve rankings data JSON file"""
    root = Path(__file__).parent.parent.parent
    return send_from_directory(root, 'rankings.json')


@pages_bp.route('/regulations.json')
def regulations_data_file():
    """Serve regulations data JSON file"""
    root = Path(__file__).parent.parent.parent
    return send_from_directory(root, 'regulations.json')
