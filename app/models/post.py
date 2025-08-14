"""Post model for community posts with geospatial data."""
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy import (
    Column, String, Text, Integer, Boolean, Float, DateTime, 
    ForeignKey, JSON, Index
)
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry
from app.extensions import db
from app.models.base import BaseModel, SoftDeleteMixin


class Post(BaseModel, SoftDeleteMixin):
    """Model for community posts with geospatial location."""
    
    __tablename__ = "posts"
    
    # Relationships
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("post_categories.id"), nullable=False)
    
    # Post content
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    
    # Location data - using PostGIS geometry
    location = Column(Geometry("POINT", srid=4326), nullable=False)
    address = Column(String(255), nullable=True)  # Approximate address for display
    neighborhood = Column(String(100), nullable=True)
    city = Column(String(50), nullable=True)
    state = Column(String(50), nullable=True)
    
    # Post metadata
    is_active = Column(Boolean, default=True, nullable=False)
    is_featured = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    
    # Engagement metrics
    view_count = Column(Integer, default=0, nullable=False)
    like_count = Column(Integer, default=0, nullable=False)
    comment_count = Column(Integer, default=0, nullable=False)
    
    # Category-specific data stored as JSON
    category_data = Column(JSON, nullable=True)  # Flexible data for different post types
    
    # Photo storage (S3 URLs)
    photo_urls = Column(JSON, nullable=True)  # List of photo URLs
    
    # Relationships
    user = relationship("User", backref="posts")
    category = relationship("PostCategory", backref="posts")
    
    # Indexes for performance
    __table_args__ = (
        Index("idx_posts_location", "location", postgresql_using="gist"),
        Index("idx_posts_category_created", "category_id", "created_at"),
        Index("idx_posts_user_created", "user_id", "created_at"),
        Index("idx_posts_active_expires", "is_active", "expires_at"),
    )
    
    def __repr__(self) -> str:
        """String representation of post."""
        return f"<Post '{self.title}' by {self.user.display_name if self.user else 'Unknown'}>"
    
    @property
    def is_expired(self) -> bool:
        """Check if post has expired."""
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at
    
    @property
    def days_until_expiration(self) -> Optional[int]:
        """Get days until expiration."""
        if not self.expires_at:
            return None
        delta = self.expires_at - datetime.utcnow()
        return max(0, delta.days)
    
    def get_coordinates(self) -> Optional[tuple[float, float]]:
        """Get post coordinates as (latitude, longitude) tuple."""
        if not self.location:
            return None
        
        from geoalchemy2.shape import to_shape
        point = to_shape(self.location)
        return (point.y, point.x)  # (latitude, longitude)
    
    def calculate_distance_to_user(self, user: "User") -> Optional[float]:
        """Calculate distance to user's location in meters."""
        if not user.location or not self.location:
            return None
        
        from sqlalchemy import func
        distance = db.session.query(
            func.ST_Distance_Sphere(self.location, user.location)
        ).scalar()
        
        return distance
    
    def increment_view_count(self) -> None:
        """Increment post view count."""
        self.view_count += 1
        db.session.commit()
    
    def increment_like_count(self) -> None:
        """Increment post like count."""
        self.like_count += 1
        db.session.commit()
    
    def decrement_like_count(self) -> None:
        """Decrement post like count."""
        self.like_count = max(0, self.like_count - 1)
        db.session.commit()
    
    def increment_comment_count(self) -> None:
        """Increment post comment count."""
        self.comment_count += 1
        db.session.commit()
    
    def set_expiration_date(self, days_from_now: Optional[int] = None) -> None:
        """Set post expiration date."""
        if days_from_now is None:
            days_from_now = self.category.default_expiration_days
        
        self.expires_at = datetime.utcnow() + timedelta(days=days_from_now)
        db.session.commit()
    
    def add_photos(self, photo_urls: List[str]) -> None:
        """Add photo URLs to post."""
        if not self.photo_urls:
            self.photo_urls = []
        
        max_photos = self.category.max_photos
        current_count = len(self.photo_urls)
        available_slots = max_photos - current_count
        
        if available_slots > 0:
            new_photos = photo_urls[:available_slots]
            self.photo_urls.extend(new_photos)
            db.session.commit()
    
    def set_category_data(self, **kwargs) -> None:
        """Set category-specific data."""
        if not self.category_data:
            self.category_data = {}
        
        self.category_data.update(kwargs)
        db.session.commit()
    
    def get_category_data(self, key: str, default=None):
        """Get category-specific data value."""
        if not self.category_data:
            return default
        return self.category_data.get(key, default)
    
    @classmethod
    def find_nearby(cls, latitude: float, longitude: float, 
                   radius_meters: int = 3218, limit: int = 20) -> List["Post"]:
        """Find posts within radius of coordinates."""
        from geoalchemy2.elements import WKTElement
        from sqlalchemy import func
        
        center_point = WKTElement(f"POINT({longitude} {latitude})", srid=4326)
        
        return cls.query.filter(
            cls.is_active == True,
            cls.is_deleted == False,
            func.ST_Distance_Sphere(cls.location, center_point) <= radius_meters
        ).order_by(
            func.ST_Distance_Sphere(cls.location, center_point)
        ).limit(limit).all()
    
    @classmethod
    def find_by_category(cls, category_name: str, limit: int = 20) -> List["Post"]:
        """Find posts by category name."""
        from app.models.category import PostCategory
        
        return cls.query.join(PostCategory).filter(
            PostCategory.name == category_name,
            cls.is_active == True,
            cls.is_deleted == False
        ).order_by(cls.created_at.desc()).limit(limit).all()
    
    @classmethod
    def find_recent(cls, limit: int = 20) -> List["Post"]:
        """Find recent active posts."""
        return cls.query.filter(
            cls.is_active == True,
            cls.is_deleted == False
        ).order_by(cls.created_at.desc()).limit(limit).all()
    
    @classmethod
    def find_in_bounding_box(cls, north: float, south: float, east: float, west: float,
                            category_name: str = None, limit: int = 50) -> List["Post"]:
        """
        Find posts within a geographic bounding box using efficient PostGIS queries.
        
        Args:
            north, south, east, west: Bounding box coordinates
            category_name: Optional category name filter
            limit: Maximum number of posts to return
            
        Returns:
            List of Post objects within the bounding box
        """
        from geoalchemy2.elements import WKTElement
        from sqlalchemy import func
        from app.models.category import PostCategory
        
        # Create bounding box polygon (PostGIS uses longitude, latitude order)
        bbox_wkt = f"POLYGON(({west} {south}, {east} {south}, {east} {north}, {west} {north}, {west} {south}))"
        bbox_polygon = WKTElement(bbox_wkt, srid=4326)
        
        query = cls.query.filter(
            cls.is_active == True,
            cls.is_deleted == False,
            func.ST_Within(cls.location, bbox_polygon)
        )
        
        # Apply category filter if provided
        if category_name:
            query = query.join(PostCategory).filter(
                PostCategory.name == category_name,
                PostCategory.is_active == True
            )
        
        # Order by creation date (newest first) with spatial index optimization
        return query.order_by(cls.created_at.desc()).limit(limit).all()
    
    @classmethod
    def cleanup_expired_posts(cls) -> int:
        """Mark expired posts as inactive and return count."""
        now = datetime.utcnow()
        expired_posts = cls.query.filter(
            cls.expires_at <= now,
            cls.is_active == True,
            cls.is_deleted == False
        ).all()
        
        count = 0
        for post in expired_posts:
            post.is_active = False
            count += 1
        
        if count > 0:
            db.session.commit()
        
        return count