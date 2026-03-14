"""Static page routes"""

from flask import current_app, render_template

from app.routes import pages_bp


@pages_bp.route("/")
def home():
    """Serve the home page"""
    return render_template(
        "home.html",
        discord_url=current_app.config.get("DISCORD_URL", ""),
        instagram_url=current_app.config.get("INSTAGRAM_URL", ""),
        facebook_url=current_app.config.get("FACEBOOK_URL", ""),
        contact_email=current_app.config.get("CONTACT_EMAIL", ""),
        contact_phone=current_app.config.get("CONTACT_PHONE", ""),
    )


@pages_bp.route("/rankings")
def rankings_page():
    """Serve TBD placeholder or live leaderboard depending on RANKINGS_LIVE config"""
    if current_app.config.get("RANKINGS_LIVE"):
        return render_template("rankings/rankingsLive.html")
    return render_template("rankings/rankingsTBD.html")


@pages_bp.route("/rankings/live")
def rankings_live_page():
    """Direct access to the live rankings page (always shows live, ignores toggle)"""
    return render_template("rankings/rankingsLive.html")

@pages_bp.route("/regulations")
def regulations_page():
    """Serve the regulations page"""
    return render_template("regulations.html")


@pages_bp.route("/schedule")
def schedule():
    """Serve the schedule page"""
    return render_template("schedule.html")


@pages_bp.route("/admin/matching")
def admin_matching_page():
    """Serve the admin matching dashboard"""
    return render_template("admin/matching.html")


@pages_bp.route("/profile")
def profile_page():
    """Serve the user profile page"""
    return render_template("auth/profile.html")


@pages_bp.route("/navbar.html")
def navbar_fragment():
    """Serve reusable navbar fragment"""
    return render_template("navbar.html")
