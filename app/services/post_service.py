"""Post service for managing post CRUD operations and business logic."""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from flask import current_app, request
from flask_login import current_user
from geoalchemy2.elements import WKTElement
from sqlalchemy import func, and_, or_

from app.extensions import db
from app.models.post import Post
from app.models.category import PostCategory
from app.models.post_image import PostImage, ModerationStatus
from app.models.user import User
from app.services.location import get_location_service, LocationResult
from app.services.s3_upload import get_s3_upload_service
from app.services.moderation import ContentModerationService

logger = logging.getLogger(__name__)


class PostCreationError(Exception):
    """Custom exception for post creation errors."""
    pass


class PostValidationError(Exception):
    """Custom exception for post validation errors."""
    pass


class PostService:
    """Service for post CRUD operations and business logic."""
    
    def __init__(self):
        """Initialize post service with required dependencies."""
        self.location_service = get_location_service()
        self.s3_service = get_s3_upload_service()
        self.moderation_service = ContentModerationService()
    
    def create_post(self, form_data: Dict[str, Any], user: User, 
                    uploaded_files: List = None) -> Tuple[Post, List[str]]:
        """
        Create a new post with full validation and moderation.
        
        Args:
            form_data: Validated form data from post creation form
            user: User creating the post
            uploaded_files: List of uploaded image files
            
        Returns:
            Tuple of (created_post, list_of_warnings)
            
        Raises:
            PostCreationError: If post creation fails
            PostValidationError: If validation fails
        """
        warnings = []
        
        try:
            # Extract and validate location
            location_data = form_data.get('location')
            if not location_data or not isinstance(location_data, dict):
                raise PostValidationError("Invalid location data")
            
            lat, lng = location_data.get('lat'), location_data.get('lng')
            if not lat or not lng:
                raise PostValidationError("Missing coordinates")
            
            # Validate location against business rules
            validation_result = self.location_service.validate_location(
                lat, lng, reference_point=user.get_coordinates() if user.location else None
            )
            
            if not validation_result.is_valid:
                raise PostValidationError(f"Location validation failed: {validation_result.error_message}")
            
            if validation_result.warnings:
                warnings.extend(validation_result.warnings)
            
            # Get category
            category_id = form_data.get('category_id')
            category = PostCategory.query.get(category_id)
            if not category:
                raise PostValidationError("Invalid category")
            
            # Content moderation for text
            title = form_data.get('title', '').strip()
            description = form_data.get('description', '').strip()
            
            # Process images first for moderation
            image_bytes_list = []
            if uploaded_files:
                for file in uploaded_files:
                    if file and file.filename:
                        file.seek(0)
                        image_bytes_list.append(file.read())
                        file.seek(0)  # Reset for later processing
            
            # Comprehensive content moderation
            moderation_result = self.moderation_service.moderate_post_content(
                title=title,
                description=description,
                image_files=image_bytes_list
            )
            
            # Check if content should be auto-rejected
            if self.moderation_service.should_auto_reject(moderation_result):
                flagged_reasons = ', '.join(moderation_result.get('flagged_reasons', []))
                raise PostCreationError(f"Content moderation failed: {flagged_reasons}")
            
            # Apply privacy fuzzing to coordinates
            fuzzed_lat, fuzzed_lng = self.location_service.apply_privacy_fuzz(lat, lng)
            
            # Create geospatial point (store exact coordinates for queries, display fuzzy ones)
            exact_point = WKTElement(f"POINT({lng} {lat})", srid=4326)
            
            # Reverse geocode for address information
            address_info = self.location_service.reverse_geocode(fuzzed_lat, fuzzed_lng)
            
            # Create post instance
            post = Post(
                user_id=user.id,
                category_id=category.id,
                title=title,
                description=description,
                location=exact_point,
                address=address_info.formatted_address if address_info else location_data.get('address'),
                neighborhood=address_info.neighborhood if address_info else location_data.get('neighborhood'),
                city=address_info.city if address_info else location_data.get('city'),
                state=address_info.state if address_info else location_data.get('state'),
                is_active=True
            )
            
            # Set category-specific data
            category_data = self._extract_category_data(form_data, category.name)
            if category_data:
                post.category_data = category_data
            
            # Set expiration date
            expiration_date = form_data.get('expires_at')
            if expiration_date and isinstance(expiration_date, datetime):
                post.expires_at = expiration_date
            else:
                post.expires_at = datetime.utcnow() + timedelta(days=category.default_expiration_days)
            
            # Save post to database first to get ID
            db.session.add(post)
            db.session.flush()  # Get post ID without committing
            
            # Process and upload images
            uploaded_images = []
            if uploaded_files:
                for i, file in enumerate(uploaded_files):
                    if file and file.filename:
                        try:
                            # Upload to S3 with moderation
                            upload_result = self.s3_service.upload_image(
                                file=file,
                                user_id=user.id,
                                post_id=post.id
                            )
                            
                            if upload_result.get('success'):
                                # Create PostImage record
                                request_info = {
                                    'remote_addr': request.remote_addr if request else None,
                                    'user_agent': request.user_agent.string if request and request.user_agent else None
                                }
                                
                                post_image = PostImage.create_from_upload_result(
                                    upload_result=upload_result,
                                    post_id=post.id,
                                    user_id=user.id,
                                    display_order=i,
                                    request_info=request_info
                                )
                                
                                uploaded_images.append(post_image)
                                
                                # Set first approved image as primary
                                if i == 0 and post_image.is_approved:
                                    post_image.set_as_primary()
                                    
                            else:
                                error_msg = upload_result.get('error', 'Unknown error')
                                logger.warning(f"Image upload failed for post {post.id}: {error_msg}")
                                warnings.append(f"Image {i+1} upload failed: {error_msg}")
                                
                        except Exception as e:
                            logger.error(f"Error processing image {i} for post {post.id}: {str(e)}")
                            warnings.append(f"Error processing image {i+1}: {str(e)}")
            
            # Commit transaction
            db.session.commit()
            
            logger.info(f"Post created successfully - ID: {post.id}, User: {user.id}, Images: {len(uploaded_images)}")
            
            return post, warnings
            
        except PostValidationError as e:
            db.session.rollback()
            logger.error(f"Post validation failed: {str(e)}")
            raise e
        except PostCreationError as e:
            db.session.rollback()
            logger.error(f"Post creation failed: {str(e)}")
            raise e
        except Exception as e:
            db.session.rollback()
            logger.error(f"Unexpected error creating post: {str(e)}")
            raise PostCreationError(f"Post creation failed: {str(e)}")
    
    def update_post(self, post_id: int, form_data: Dict[str, Any], 
                    user: User) -> Tuple[Post, List[str]]:
        """
        Update an existing post.
        
        Args:
            post_id: ID of post to update
            form_data: Updated form data
            user: User making the update
            
        Returns:
            Tuple of (updated_post, list_of_warnings)
            
        Raises:
            PostValidationError: If validation fails
            PermissionError: If user doesn't have permission to update
        """
        warnings = []
        
        try:
            # Get existing post
            post = Post.query.get(post_id)
            if not post:
                raise PostValidationError("Post not found")
            
            # Check permissions
            if post.user_id != user.id and not user.is_admin:
                raise PermissionError("Not authorized to update this post")
            
            # Check if post is expired
            if post.is_expired:
                raise PostValidationError("Cannot update expired post")
            
            # Content moderation for updated text
            title = form_data.get('title', '').strip()
            description = form_data.get('description', '').strip()
            
            moderation_result = self.moderation_service.moderate_text(f"{title} {description}")
            
            if self.moderation_service.should_auto_reject({'text_moderation': moderation_result}):
                raise PostCreationError("Updated content failed moderation")
            
            # Update basic fields
            post.title = title
            post.description = description
            
            # Update category-specific data if provided
            if 'category_data' in form_data:
                category_data = self._extract_category_data(form_data, post.category.name)
                if category_data:
                    post.category_data = category_data
            
            # Update expiration if provided
            if 'expires_at' in form_data and form_data['expires_at']:
                post.expires_at = form_data['expires_at']
            
            # Update location if provided
            if 'location' in form_data:
                location_data = form_data['location']
                if isinstance(location_data, dict) and 'lat' in location_data and 'lng' in location_data:
                    lat, lng = location_data['lat'], location_data['lng']
                    
                    # Validate new location
                    validation_result = self.location_service.validate_location(lat, lng)
                    if not validation_result.is_valid:
                        raise PostValidationError(f"Location validation failed: {validation_result.error_message}")
                    
                    # Update location
                    exact_point = WKTElement(f"POINT({lng} {lat})", srid=4326)
                    post.location = exact_point
                    
                    # Update address information
                    address_info = self.location_service.reverse_geocode(lat, lng)
                    if address_info:
                        post.address = address_info.formatted_address
                        post.neighborhood = address_info.neighborhood
                        post.city = address_info.city
                        post.state = address_info.state
            
            # Update timestamp
            post.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            logger.info(f"Post updated successfully - ID: {post.id}, User: {user.id}")
            
            return post, warnings
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating post {post_id}: {str(e)}")
            raise e
    
    def delete_post(self, post_id: int, user: User, hard_delete: bool = False) -> bool:
        """
        Delete or soft-delete a post.
        
        Args:
            post_id: ID of post to delete
            user: User requesting deletion
            hard_delete: Whether to permanently delete (admin only)
            
        Returns:
            True if successful
            
        Raises:
            PermissionError: If user doesn't have permission to delete
        """
        try:
            # Get post
            post = Post.query.get(post_id)
            if not post:
                return False
            
            # Check permissions
            if post.user_id != user.id and not user.is_admin:
                raise PermissionError("Not authorized to delete this post")
            
            if hard_delete and not user.is_admin:
                raise PermissionError("Hard delete requires admin privileges")
            
            if hard_delete:
                # Delete associated images from S3
                images = PostImage.get_by_post(post_id, approved_only=False)
                for image in images:
                    if image.s3_keys:
                        self.s3_service.delete_image(image.s3_keys)
                
                # Hard delete post and related records
                PostImage.query.filter(PostImage.post_id == post_id).delete()
                db.session.delete(post)
            else:
                # Soft delete
                post.soft_delete()
                
                # Mark associated images as deleted
                images = PostImage.get_by_post(post_id, approved_only=False)
                for image in images:
                    image.soft_delete()
            
            db.session.commit()
            
            logger.info(f"Post {'hard' if hard_delete else 'soft'} deleted - ID: {post_id}, User: {user.id}")
            
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting post {post_id}: {str(e)}")
            raise e
    
    def get_post_by_id(self, post_id: int, user: Optional[User] = None) -> Optional[Post]:
        """
        Get a post by ID with appropriate permissions.
        
        Args:
            post_id: Post ID to retrieve
            user: Current user (for permission checks)
            
        Returns:
            Post instance or None if not found/not authorized
        """
        try:
            post = Post.query.get(post_id)
            if not post or post.is_deleted:
                return None
            
            # Check if post is active or user owns it
            if not post.is_active and (not user or post.user_id != user.id):
                return None
            
            # Increment view count if not owner
            if user and post.user_id != user.id:
                post.increment_view_count()
            
            return post
            
        except Exception as e:
            logger.error(f"Error retrieving post {post_id}: {str(e)}")
            return None
    
    def get_posts_nearby(self, latitude: float, longitude: float, 
                        radius_meters: int = 3218, limit: int = 20,
                        category_filter: Optional[str] = None,
                        user: Optional[User] = None) -> List[Post]:
        """
        Get posts near a location with filtering options.
        
        Args:
            latitude: Center latitude
            longitude: Center longitude
            radius_meters: Search radius in meters (default: 2 miles)
            limit: Maximum number of posts to return
            category_filter: Optional category name filter
            user: Current user for personalized results
            
        Returns:
            List of nearby posts sorted by distance
        """
        try:
            center_point = WKTElement(f"POINT({longitude} {latitude})", srid=4326)
            
            query = Post.query.filter(
                Post.is_active == True,
                Post.is_deleted == False,
                func.ST_Distance_Sphere(Post.location, center_point) <= radius_meters
            )
            
            # Apply category filter
            if category_filter:
                category = PostCategory.get_by_name(category_filter)
                if category:
                    query = query.filter(Post.category_id == category.id)
            
            # Order by distance
            query = query.order_by(
                func.ST_Distance_Sphere(Post.location, center_point)
            ).limit(limit)
            
            posts = query.all()
            
            logger.info(f"Found {len(posts)} posts within {radius_meters}m of ({latitude}, {longitude})")
            
            return posts
            
        except Exception as e:
            logger.error(f"Error finding nearby posts: {str(e)}")
            return []
    
    def get_posts_by_category(self, category_name: str, limit: int = 20) -> List[Post]:
        """Get recent posts by category."""
        try:
            return Post.find_by_category(category_name, limit=limit)
        except Exception as e:
            logger.error(f"Error getting posts by category {category_name}: {str(e)}")
            return []
    
    def get_recent_posts(self, limit: int = 20) -> List[Post]:
        """Get recent active posts."""
        try:
            return Post.find_recent(limit=limit)
        except Exception as e:
            logger.error(f"Error getting recent posts: {str(e)}")
            return []
    
    def get_user_posts(self, user_id: int, include_inactive: bool = False, 
                      limit: int = 50) -> List[Post]:
        """Get posts created by a specific user."""
        try:
            query = Post.query.filter(
                Post.user_id == user_id,
                Post.is_deleted == False
            )
            
            if not include_inactive:
                query = query.filter(Post.is_active == True)
            
            return query.order_by(Post.created_at.desc()).limit(limit).all()
            
        except Exception as e:
            logger.error(f"Error getting user posts for user {user_id}: {str(e)}")
            return []
    
    def cleanup_expired_posts(self) -> int:
        """Mark expired posts as inactive."""
        try:
            return Post.cleanup_expired_posts()
        except Exception as e:
            logger.error(f"Error cleaning up expired posts: {str(e)}")
            return 0
    
    def _extract_category_data(self, form_data: Dict[str, Any], category_name: str) -> Dict[str, Any]:
        """
        Extract category-specific data from form data.
        
        Args:
            form_data: Raw form data
            category_name: Name of the category
            
        Returns:
            Dict of category-specific data
        """
        category_data = {}
        
        # Category-specific field mappings
        field_mappings = {
            'garage_sale': ['start_time', 'end_time', 'item_categories', 'parking_info', 'accepts_early_birds'],
            'restaurant': ['business_name', 'special_item', 'price', 'available_from', 'available_until', 'dietary_options'],
            'help_needed': ['task_type', 'urgency_level', 'estimated_duration', 'needed_by', 'compensation_offered', 'requirements'],
            'for_sale': ['item_name', 'price', 'condition', 'category_type', 'brand_model', 'pickup_delivery', 'negotiable', 'accepts_trades', 'trade_preferences'],
            'shop_sale': ['business_name', 'sale_type', 'discount_details', 'sale_start', 'sale_end', 'store_hours', 'featured_items', 'special_features'],
            'borrow': ['item_needed', 'item_category', 'duration_needed', 'needed_by', 'return_by', 'care_agreement', 'return_favor', 'pickup_return_method']
        }
        
        # Extract relevant fields for this category
        fields = field_mappings.get(category_name, [])
        for field in fields:
            if field in form_data and form_data[field] is not None:
                value = form_data[field]
                
                # Convert datetime objects to ISO strings for JSON storage
                if isinstance(value, datetime):
                    value = value.isoformat()
                
                category_data[field] = value
        
        return category_data


# Global service instance
_post_service = None


def get_post_service() -> PostService:
    """Get post service instance."""
    global _post_service
    if _post_service is None:
        _post_service = PostService()
    return _post_service