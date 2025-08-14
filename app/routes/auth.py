"""Authentication routes for Google OAuth."""
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, logout_user, current_user, login_user
from app.extensions import db
from app.models.user import User
from app.services.oauth import GoogleOAuthService

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login")
def login():
    """Login page with Google OAuth."""
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    
    # Check if user wants to start OAuth flow
    if request.args.get('start_oauth'):
        oauth_service = GoogleOAuthService()
        redirect_uri = url_for('auth.oauth_callback', _external=True)
        authorization_url = oauth_service.get_authorization_url(redirect_uri)
        return redirect(authorization_url)
    
    return render_template("auth/login.html", title="Sign In")


@auth_bp.route("/logout")
@login_required
def logout():
    """Logout user and redirect to homepage."""
    logout_user()
    flash("You have been logged out successfully.", "info")
    return redirect(url_for("main.index"))


@auth_bp.route("/profile")
@login_required
def profile():
    """User profile page."""
    return render_template("auth/profile.html", title="Profile")


@auth_bp.route("/callback")
def oauth_callback():
    """OAuth callback handler."""
    # Check for errors from OAuth provider
    error = request.args.get('error')
    if error:
        current_app.logger.warning(f"OAuth error: {error}")
        flash("Authentication failed. Please try again.", "error")
        return redirect(url_for("auth.login"))
    
    # Get authorization code and state
    code = request.args.get('code')
    state = request.args.get('state')
    
    if not code:
        flash("Authorization code not received. Please try again.", "error")
        return redirect(url_for("auth.login"))
    
    # Exchange code for token
    oauth_service = GoogleOAuthService()
    redirect_uri = url_for('auth.oauth_callback', _external=True)
    token_data = oauth_service.exchange_code_for_token(code, redirect_uri, state)
    
    if not token_data:
        flash("Failed to authenticate with Google. Please try again.", "error")
        return redirect(url_for("auth.login"))
    
    # Get user information
    access_token = token_data.get('access_token')
    user_info = oauth_service.get_user_info(access_token)
    
    if not user_info:
        flash("Failed to retrieve user information. Please try again.", "error")
        return redirect(url_for("auth.login"))
    
    # Find or create user
    google_id = user_info.get('id')
    email = user_info.get('email')
    
    user = User.query.filter_by(google_id=google_id).first()
    
    if not user:
        # Check if user exists with same email
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            # Link Google account to existing user
            existing_user.google_id = google_id
            existing_user.full_name = user_info.get('name', '')
            existing_user.display_name = user_info.get('given_name', user_info.get('name', 'User'))
            existing_user.profile_picture_url = user_info.get('picture')
            existing_user.email_verified = user_info.get('email_verified', False)
            user = existing_user
        else:
            # Create new user using the proper OAuth mapping
            # Map Google's user_info format to expected format
            oauth_data = {
                'sub': google_id,
                'email': email,
                'email_verified': user_info.get('email_verified', False),
                'name': user_info.get('name', ''),
                'given_name': user_info.get('given_name', ''),
                'picture': user_info.get('picture')
            }
            user = User.create_from_google_oauth(oauth_data)
    else:
        # Update existing user information
        user.full_name = user_info.get('name', '')
        user.display_name = user_info.get('given_name', user_info.get('name', 'User'))
        user.profile_picture_url = user_info.get('picture')
        user.email_verified = user_info.get('email_verified', False)
        user.last_login_at = db.func.now()
    
    try:
        db.session.commit()
        login_user(user, remember=True)
        
        # Welcome message for new vs returning users
        if hasattr(user, '_sa_instance_state') and user._sa_instance_state.pending:
            flash(f"Welcome to Mapid, {user.display_name}!", "success")
        else:
            flash(f"Welcome back, {user.display_name}!", "success")
        
        # Redirect to next page or home
        next_page = request.args.get('next')
        return redirect(next_page) if next_page else redirect(url_for('main.index'))
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating/updating user: {e}")
        flash("An error occurred during sign-in. Please try again.", "error")
        return redirect(url_for("auth.login"))