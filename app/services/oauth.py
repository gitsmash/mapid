"""Google OAuth service for user authentication."""
import secrets
import requests
from urllib.parse import urlencode, parse_qs, urlparse
from flask import current_app, session, url_for
from typing import Dict, Optional, Any


class GoogleOAuthService:
    """Service for handling Google OAuth authentication."""
    
    def __init__(self):
        self.client_id = current_app.config['GOOGLE_CLIENT_ID']
        self.client_secret = current_app.config['GOOGLE_CLIENT_SECRET']
        self.authorization_base_url = 'https://accounts.google.com/o/oauth2/v2/auth'
        self.token_url = 'https://oauth2.googleapis.com/token'
        self.userinfo_url = 'https://www.googleapis.com/oauth2/v2/userinfo'
        self.scope = ['openid', 'email', 'profile']
    
    def get_authorization_url(self, redirect_uri: str) -> str:
        """Generate authorization URL for OAuth flow."""
        # Generate and store state for CSRF protection
        state = secrets.token_urlsafe(32)
        session['oauth_state'] = state
        
        params = {
            'client_id': self.client_id,
            'redirect_uri': redirect_uri,
            'scope': ' '.join(self.scope),
            'response_type': 'code',
            'state': state,
            'access_type': 'offline',
            'prompt': 'consent'
        }
        
        return f"{self.authorization_base_url}?{urlencode(params)}"
    
    def exchange_code_for_token(self, code: str, redirect_uri: str, state: str) -> Optional[Dict[str, Any]]:
        """Exchange authorization code for access token."""
        # Verify state parameter for CSRF protection
        if state != session.get('oauth_state'):
            current_app.logger.warning("OAuth state mismatch - possible CSRF attack")
            return None
        
        # Clear the state from session
        session.pop('oauth_state', None)
        
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri
        }
        
        try:
            response = requests.post(
                self.token_url,
                data=data,
                headers={'Accept': 'application/json'},
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            current_app.logger.error(f"Error exchanging code for token: {e}")
            return None
    
    def get_user_info(self, access_token: str) -> Optional[Dict[str, Any]]:
        """Get user information from Google using access token."""
        headers = {'Authorization': f'Bearer {access_token}'}
        
        try:
            response = requests.get(
                self.userinfo_url,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            current_app.logger.error(f"Error fetching user info: {e}")
            return None
    
    def revoke_token(self, token: str) -> bool:
        """Revoke the given token."""
        revoke_url = 'https://oauth2.googleapis.com/revoke'
        
        try:
            response = requests.post(
                revoke_url,
                data={'token': token},
                timeout=30
            )
            return response.status_code == 200
        except requests.RequestException as e:
            current_app.logger.error(f"Error revoking token: {e}")
            return False