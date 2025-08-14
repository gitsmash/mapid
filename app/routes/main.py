"""Main routes for homepage and basic functionality."""
from flask import Blueprint, render_template, current_app

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    """Homepage with map and post feed."""
    return render_template("index.html", title="Home")


@main_bp.route("/about")
def about():
    """About page."""
    return render_template("about.html", title="About")


@main_bp.route("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app": current_app.config["APP_NAME"],
        "version": current_app.config["APP_VERSION"],
    }