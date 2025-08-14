"""Flask application factory."""
import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask
from app.config import config
from app.extensions import db, migrate, login_manager, csrf, cors


def create_app(config_name: str | None = None) -> Flask:
    """Create and configure Flask application.
    
    Args:
        config_name: Configuration name (development, production, testing)
        
    Returns:
        Configured Flask application instance
    """
    # Create Flask app instance
    app = Flask(__name__)
    
    # Load configuration
    config_name = config_name or os.getenv("FLASK_ENV", "default")
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    cors.init_app(app)
    
    # Create logs directory if it doesn't exist
    if not os.path.exists("logs"):
        os.mkdir("logs")
    
    # Configure logging
    if not app.debug and not app.testing:
        file_handler = RotatingFileHandler(
            app.config["LOG_FILE"],
            maxBytes=10240000,  # 10MB
            backupCount=10
        )
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]"
        ))
        file_handler.setLevel(getattr(logging, app.config["LOG_LEVEL"]))
        app.logger.addHandler(file_handler)
        app.logger.setLevel(getattr(logging, app.config["LOG_LEVEL"]))
        app.logger.info("Mapid application startup")
    
    # Register blueprints
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.posts import posts_bp
    from app.routes.maps import maps_bp
    from app.routes.api import api_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(posts_bp, url_prefix="/posts")
    app.register_blueprint(maps_bp, url_prefix="/maps")
    app.register_blueprint(api_bp, url_prefix="/api")
    
    # Register CLI commands
    from app.cli import db as db_cli
    app.register_blueprint(db_cli.bp)
    
    # Context processors for templates
    @app.context_processor
    def inject_config():
        """Inject configuration variables into templates."""
        return {
            "APP_NAME": app.config["APP_NAME"],
            "APP_VERSION": app.config["APP_VERSION"],
        }
    
    @app.context_processor
    def inject_template_utils():
        """Inject utility functions into templates."""
        from datetime import datetime
        from markupsafe import Markup
        import re
        
        def moment_from_now(dt):
            """Get human-readable time from datetime."""
            if not dt:
                return "Unknown"
            
            now = datetime.utcnow()
            diff = now - dt
            
            if diff.days > 0:
                if diff.days == 1:
                    return "1 day ago"
                elif diff.days < 7:
                    return f"{diff.days} days ago"
                elif diff.days < 30:
                    weeks = diff.days // 7
                    return f"{weeks} week{'s' if weeks > 1 else ''} ago"
                elif diff.days < 365:
                    months = diff.days // 30
                    return f"{months} month{'s' if months > 1 else ''} ago"
                else:
                    years = diff.days // 365
                    return f"{years} year{'s' if years > 1 else ''} ago"
            
            seconds = diff.seconds
            if seconds < 60:
                return "Just now"
            elif seconds < 3600:
                minutes = seconds // 60
                return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
            else:
                hours = seconds // 3600
                return f"{hours} hour{'s' if hours > 1 else ''} ago"
        
        def moment_format(dt, format_str='MMM D, YYYY'):
            """Format datetime with basic formatting."""
            if not dt:
                return "Unknown"
            
            # Simple format mapping
            format_map = {
                'MMM': dt.strftime('%b'),
                'D': str(dt.day),
                'YYYY': str(dt.year),
                'h': str(dt.hour % 12 or 12),
                'mm': dt.strftime('%M'),
                'A': dt.strftime('%p')
            }
            
            result = format_str
            for key, value in format_map.items():
                result = result.replace(key, value)
            
            return result
        
        def nl2br(value):
            """Convert newlines to HTML breaks."""
            if not value:
                return value
            return Markup(re.sub(r'\n', '<br>', str(value)))
        
        # Create moment object with methods
        class MomentHelper:
            @staticmethod
            def fromNow():
                return moment_from_now
            
            @staticmethod  
            def format(format_str='MMM D, YYYY'):
                return lambda dt: moment_format(dt, format_str)
        
        def moment(dt):
            """Create moment-like object for datetime."""
            class MomentInstance:
                def __init__(self, datetime_obj):
                    self.dt = datetime_obj
                
                def fromNow(self):
                    return moment_from_now(self.dt)
                
                def format(self, format_str='MMM D, YYYY'):
                    return moment_format(self.dt, format_str)
            
            return MomentInstance(dt)
        
        return {
            "moment": moment,
            "nl2br": nl2br,
        }
    
    return app