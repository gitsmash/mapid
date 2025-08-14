"""Application entry point."""
import os
from app import create_app
from app.extensions import db

# Create the Flask application
app = create_app(os.getenv("FLASK_ENV"))

# Create application context for CLI commands
@app.shell_context_processor
def make_shell_context():
    """Make shell context for flask shell command."""
    return {
        "db": db,
    }

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)