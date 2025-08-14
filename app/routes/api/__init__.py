"""API routes package."""
from flask import Blueprint

api_bp = Blueprint("api", __name__)

# Import API v1 routes
from . import v1

# Import API sub-modules
from .images import images_api_bp

# Register sub-blueprints
api_bp.register_blueprint(images_api_bp, url_prefix="/images")