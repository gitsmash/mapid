"""API v1 routes."""
from flask import jsonify
from .. import api_bp


@api_bp.route("/v1/health")
def api_health():
    """API health check."""
    return jsonify({
        "status": "healthy",
        "version": "v1",
        "message": "Mapid API v1 is running"
    })