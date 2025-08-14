"""PostImage model for storing image metadata and S3 references."""
from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy import (
    Column, String, Text, Integer, Boolean, DateTime, 
    ForeignKey, JSON, Index, Enum
)
from sqlalchemy.orm import relationship
import enum

from app.extensions import db
from app.models.base import BaseModel, SoftDeleteMixin


class ModerationStatus(enum.Enum):
    """Enumeration for image moderation status."""
    PENDING = "pending"
    APPROVED = "approved" 
    FLAGGED = "flagged"
    REJECTED = "rejected"


class PostImage(BaseModel, SoftDeleteMixin):
    """Model for post images with S3 storage and moderation tracking."""
    
    __tablename__ = "post_images"
    
    # Relationships
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Image metadata
    original_filename = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)  # Original file size in bytes
    mime_type = Column(String(50), nullable=False)
    
    # S3 storage information
    s3_bucket = Column(String(100), nullable=False)
    s3_keys = Column(JSON, nullable=False)  # Dict mapping size names to S3 keys
    s3_urls = Column(JSON, nullable=False)  # Dict mapping size names to S3 URLs
    
    # Image processing metadata
    original_dimensions = Column(JSON, nullable=True)  # {"width": 1920, "height": 1080}
    processed_sizes = Column(JSON, nullable=True)  # Available processed sizes
    
    # Content moderation
    moderation_status = Column(
        Enum(ModerationStatus), 
        default=ModerationStatus.PENDING, 
        nullable=False
    )
    moderation_results = Column(JSON, nullable=True)  # Moderation service results
    moderation_timestamp = Column(DateTime, nullable=True)
    
    # Image ordering and status
    display_order = Column(Integer, default=0, nullable=False)  # Order within post
    is_primary = Column(Boolean, default=False, nullable=False)  # Primary post image
    is_public = Column(Boolean, default=True, nullable=False)  # Public visibility
    
    # Upload tracking
    upload_ip = Column(String(45), nullable=True)  # IPv4/IPv6 address
    upload_user_agent = Column(String(500), nullable=True)
    upload_session_id = Column(String(100), nullable=True)
    
    # Relationships
    post = relationship("Post", backref="images")
    user = relationship("User", backref="uploaded_images")
    
    # Indexes for performance
    __table_args__ = (
        Index("idx_post_images_post_id", "post_id"),
        Index("idx_post_images_user_id", "user_id"),
        Index("idx_post_images_moderation", "moderation_status", "created_at"),
        Index("idx_post_images_post_order", "post_id", "display_order"),
        Index("idx_post_images_primary", "post_id", "is_primary"),
    )
    
    def __repr__(self) -> str:
        """String representation of post image."""
        return f"<PostImage {self.original_filename} for Post {self.post_id}>"
    
    @property
    def is_approved(self) -> bool:
        """Check if image is approved for display."""
        return self.moderation_status == ModerationStatus.APPROVED
    
    @property
    def is_pending_moderation(self) -> bool:
        """Check if image is pending moderation."""
        return self.moderation_status == ModerationStatus.PENDING
    
    @property
    def is_flagged(self) -> bool:
        """Check if image is flagged by moderation."""
        return self.moderation_status == ModerationStatus.FLAGGED
    
    @property
    def is_rejected(self) -> bool:
        """Check if image is rejected by moderation."""
        return self.moderation_status == ModerationStatus.REJECTED
    
    def get_url(self, size: str = 'medium') -> Optional[str]:
        """
        Get image URL for specified size.
        
        Args:
            size: Image size ('thumbnail', 'medium', 'full', 'original')
            
        Returns:
            S3 URL for the requested size, or None if not available
        """
        if not self.s3_urls or not isinstance(self.s3_urls, dict):
            return None
        
        return self.s3_urls.get(size)
    
    def get_s3_key(self, size: str = 'medium') -> Optional[str]:
        """
        Get S3 key for specified size.
        
        Args:
            size: Image size ('thumbnail', 'medium', 'full', 'original')
            
        Returns:
            S3 key for the requested size, or None if not available
        """
        if not self.s3_keys or not isinstance(self.s3_keys, dict):
            return None
        
        return self.s3_keys.get(size)
    
    def get_available_sizes(self) -> List[str]:
        """Get list of available image sizes."""
        if not self.s3_urls or not isinstance(self.s3_urls, dict):
            return []
        
        return list(self.s3_urls.keys())
    
    def set_moderation_result(self, moderation_result: Dict[str, Any], 
                            auto_approve: bool = True) -> None:
        """
        Set moderation result and update status.
        
        Args:
            moderation_result: Result from content moderation service
            auto_approve: Whether to auto-approve non-flagged content
        """
        self.moderation_results = moderation_result
        self.moderation_timestamp = datetime.utcnow()
        
        # Update moderation status based on results
        if moderation_result.get('is_flagged', False):
            # Check if should be auto-rejected
            confidence = moderation_result.get('confidence', 0)
            if confidence > 90.0:
                self.moderation_status = ModerationStatus.REJECTED
            else:
                self.moderation_status = ModerationStatus.FLAGGED
        elif auto_approve:
            self.moderation_status = ModerationStatus.APPROVED
        else:
            self.moderation_status = ModerationStatus.PENDING
        
        db.session.commit()
    
    def approve(self) -> None:
        """Manually approve image."""
        self.moderation_status = ModerationStatus.APPROVED
        db.session.commit()
    
    def reject(self) -> None:
        """Manually reject image."""
        self.moderation_status = ModerationStatus.REJECTED
        db.session.commit()
    
    def flag(self) -> None:
        """Flag image for manual review."""
        self.moderation_status = ModerationStatus.FLAGGED
        db.session.commit()
    
    def set_as_primary(self) -> None:
        """Set this image as primary for the post."""
        # Remove primary status from other images in this post
        PostImage.query.filter(
            PostImage.post_id == self.post_id,
            PostImage.id != self.id
        ).update({'is_primary': False})
        
        # Set this image as primary
        self.is_primary = True
        db.session.commit()
    
    def update_display_order(self, new_order: int) -> None:
        """Update display order within the post."""
        self.display_order = new_order
        db.session.commit()
    
    def get_metadata(self) -> Dict[str, Any]:
        """Get complete image metadata."""
        return {
            'id': self.id,
            'post_id': self.post_id,
            'original_filename': self.original_filename,
            'file_size': self.file_size,
            'mime_type': self.mime_type,
            'dimensions': self.original_dimensions,
            'available_sizes': self.get_available_sizes(),
            'is_primary': self.is_primary,
            'display_order': self.display_order,
            'moderation_status': self.moderation_status.value,
            'is_approved': self.is_approved,
            'upload_timestamp': self.created_at.isoformat() if self.created_at else None,
            'urls': self.s3_urls
        }
    
    @classmethod
    def create_from_upload_result(cls, upload_result: Dict[str, Any], 
                                post_id: int, user_id: int,
                                display_order: int = 0,
                                request_info: Optional[Dict[str, Any]] = None) -> "PostImage":
        """
        Create PostImage instance from S3 upload service result.
        
        Args:
            upload_result: Result from S3UploadService.upload_image()
            post_id: Associated post ID
            user_id: Uploading user ID
            display_order: Display order within post
            request_info: Optional request metadata (IP, user agent, etc.)
            
        Returns:
            New PostImage instance
        """
        if not upload_result.get('success'):
            raise ValueError(f"Cannot create PostImage from failed upload: {upload_result.get('error')}")
        
        file_info = upload_result.get('file_info', {})
        moderation_result = upload_result.get('moderation_result', {})
        
        # Extract original dimensions if available
        original_dimensions = None
        if 'dimensions' in file_info and 'original' in file_info['dimensions']:
            original_dimensions = file_info['dimensions']['original']
        
        # Create new instance
        image = cls(
            post_id=post_id,
            user_id=user_id,
            original_filename=file_info.get('original_filename', 'unknown'),
            file_size=file_info.get('file_size', 0),
            mime_type='image/jpeg',  # Default, could be improved
            s3_bucket=upload_result.get('s3_bucket', 'unknown'),
            s3_keys=upload_result.get('s3_keys', {}),
            s3_urls=upload_result.get('urls', {}),
            original_dimensions=original_dimensions,
            processed_sizes=list(upload_result.get('urls', {}).keys()),
            display_order=display_order
        )
        
        # Add request information if provided
        if request_info:
            image.upload_ip = request_info.get('remote_addr')
            image.upload_user_agent = request_info.get('user_agent')
            image.upload_session_id = request_info.get('session_id')
        
        # Set moderation result
        if moderation_result:
            image.set_moderation_result(moderation_result, auto_approve=True)
        
        db.session.add(image)
        db.session.commit()
        
        return image
    
    @classmethod
    def get_by_post(cls, post_id: int, approved_only: bool = True) -> List["PostImage"]:
        """Get all images for a specific post."""
        query = cls.query.filter(
            cls.post_id == post_id,
            cls.is_deleted == False
        )
        
        if approved_only:
            query = query.filter(cls.moderation_status == ModerationStatus.APPROVED)
        
        return query.order_by(cls.display_order, cls.created_at).all()
    
    @classmethod
    def get_primary_image(cls, post_id: int) -> Optional["PostImage"]:
        """Get primary image for a post."""
        return cls.query.filter(
            cls.post_id == post_id,
            cls.is_primary == True,
            cls.moderation_status == ModerationStatus.APPROVED,
            cls.is_deleted == False
        ).first()
    
    @classmethod
    def get_pending_moderation(cls, limit: int = 50) -> List["PostImage"]:
        """Get images pending moderation review."""
        return cls.query.filter(
            cls.moderation_status == ModerationStatus.PENDING,
            cls.is_deleted == False
        ).order_by(cls.created_at.desc()).limit(limit).all()
    
    @classmethod
    def get_flagged_images(cls, limit: int = 50) -> List["PostImage"]:
        """Get flagged images for manual review."""
        return cls.query.filter(
            cls.moderation_status == ModerationStatus.FLAGGED,
            cls.is_deleted == False
        ).order_by(cls.created_at.desc()).limit(limit).all()
    
    @classmethod
    def cleanup_orphaned_images(cls, days_old: int = 7) -> int:
        """Mark orphaned images (no associated post) as deleted."""
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        
        # Find orphaned images
        orphaned_images = cls.query.outerjoin(cls.post).filter(
            cls.post_id.is_(None),
            cls.created_at < cutoff_date,
            cls.is_deleted == False
        ).all()
        
        count = 0
        for image in orphaned_images:
            image.soft_delete()
            count += 1
        
        if count > 0:
            db.session.commit()
        
        return count