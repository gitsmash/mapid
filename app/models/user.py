"""User model for authentication and user management."""
from datetime import datetime
from typing import Optional
from flask_login import UserMixin
from sqlalchemy import Column, String, Boolean, Float, Integer, DateTime, Text
from geoalchemy2 import Geometry
from app.extensions import db
from app.models.base import BaseModel, SoftDeleteMixin


class User(BaseModel, SoftDeleteMixin, UserMixin):
    """User model for Google OAuth authenticated users."""
    
    __tablename__ = "users"
    
    # OAuth fields
    google_id = Column(String(100), unique=True, nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    email_verified = Column(Boolean, default=False, nullable=False)
    
    # Profile fields
    full_name = Column(String(100), nullable=False)
    display_name = Column(String(50), nullable=False)  # How they appear to others
    profile_picture_url = Column(String(255), nullable=True)
    bio = Column(Text, nullable=True)
    
    # Location fields - using PostGIS geometry
    location = Column(Geometry("POINT", srid=4326), nullable=True)  # Exact location (private)
    neighborhood = Column(String(100), nullable=True)  # General area name
    city = Column(String(50), nullable=True)
    state = Column(String(50), nullable=True)
    country = Column(String(50), nullable=True)
    location_verified = Column(Boolean, default=False, nullable=False)
    location_updated_at = Column(DateTime, nullable=True)
    
    # Community reputation
    reputation_score = Column(Float, default=0.0, nullable=False)
    total_likes_received = Column(Integer, default=0, nullable=False)
    total_posts_created = Column(Integer, default=0, nullable=False)
    total_comments_made = Column(Integer, default=0, nullable=False)
    total_help_provided = Column(Integer, default=0, nullable=False)
    
    # Privacy settings
    show_neighborhood = Column(Boolean, default=True, nullable=False)
    show_activity_stats = Column(Boolean, default=True, nullable=False)
    show_exact_location = Column(Boolean, default=False, nullable=False)  # For trusted users only
    
    # Account status
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    last_login_at = Column(DateTime, nullable=True)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self) -> str:
        """String representation of user."""
        return f"<User {self.display_name} ({self.email})>"
    
    @property
    def is_authenticated(self) -> bool:
        """Check if user is authenticated (for Flask-Login)."""
        return True
    
    @property
    def is_anonymous(self) -> bool:
        """Check if user is anonymous (for Flask-Login)."""
        return False
    
    def get_id(self) -> str:
        """Get user ID as string (for Flask-Login)."""
        return str(self.id)
    
    def update_last_seen(self) -> None:
        """Update user's last seen timestamp."""
        self.last_seen_at = datetime.utcnow()
        db.session.commit()
    
    def update_location(self, latitude: float, longitude: float, 
                       neighborhood: Optional[str] = None,
                       city: Optional[str] = None,
                       state: Optional[str] = None,
                       country: Optional[str] = None) -> None:
        """Update user's location information."""
        from geoalchemy2.elements import WKTElement
        
        # Create point geometry from coordinates
        point = WKTElement(f"POINT({longitude} {latitude})", srid=4326)
        self.location = point
        
        # Update location metadata
        if neighborhood:
            self.neighborhood = neighborhood
        if city:
            self.city = city
        if state:
            self.state = state
        if country:
            self.country = country
            
        self.location_updated_at = datetime.utcnow()
        self.location_verified = True
        db.session.commit()
    
    def get_coordinates(self) -> Optional[tuple[float, float]]:
        """Get user coordinates as (latitude, longitude) tuple."""
        if not self.location:
            return None
        
        from geoalchemy2.shape import to_shape
        point = to_shape(self.location)
        return (point.y, point.x)  # (latitude, longitude)
    
    def calculate_distance_to(self, other_location: "Geometry") -> Optional[float]:
        """Calculate distance to another location in meters."""
        if not self.location:
            return None
        
        # Use PostGIS ST_Distance function for accurate distance
        from sqlalchemy import func
        distance = db.session.query(
            func.ST_Distance(self.location, other_location)
        ).scalar()
        
        # Convert from degrees to meters (approximate)
        # For more accurate distance, use ST_Distance_Sphere
        return distance * 111320 if distance else None  # ~111.32 km per degree
    
    def increment_reputation(self, points: float) -> None:
        """Increment user's reputation score."""
        self.reputation_score += points
        db.session.commit()
    
    def increment_post_count(self) -> None:
        """Increment user's post count."""
        self.total_posts_created += 1
        db.session.commit()
    
    def increment_comment_count(self) -> None:
        """Increment user's comment count."""
        self.total_comments_made += 1
        db.session.commit()
    
    def increment_likes_received(self) -> None:
        """Increment user's likes received count."""
        self.total_likes_received += 1
        db.session.commit()
    
    def increment_help_provided(self) -> None:
        """Increment user's help provided count."""
        self.total_help_provided += 1
        db.session.commit()
    
    @classmethod
    def find_by_google_id(cls, google_id: str) -> Optional["User"]:
        """Find user by Google ID."""
        return cls.query.filter_by(google_id=google_id, is_deleted=False).first()
    
    @classmethod
    def find_by_email(cls, email: str) -> Optional["User"]:
        """Find user by email address."""
        return cls.query.filter_by(email=email, is_deleted=False).first()
    
    @classmethod
    def create_from_google_oauth(cls, google_user_info: dict) -> "User":
        """Create new user from Google OAuth user info."""
        user = cls(
            google_id=google_user_info["sub"],
            email=google_user_info["email"],
            email_verified=google_user_info.get("email_verified", False),
            full_name=google_user_info.get("name", ""),
            display_name=google_user_info.get("given_name", google_user_info.get("name", "User")),
            profile_picture_url=google_user_info.get("picture"),
        )
        return user.save()