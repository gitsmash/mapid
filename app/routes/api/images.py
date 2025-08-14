"""API endpoints for image upload and management."""
import logging
from typing import Dict, Any, List, Optional
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import RequestEntityTooLarge, BadRequest

from app.services.s3_upload import get_s3_upload_service, S3UploadError, ImageProcessingError
from app.models.post_image import PostImage, ModerationStatus
from app.models.post import Post
from app.models.category import PostCategory
from app.extensions import db

logger = logging.getLogger(__name__)
images_api_bp = Blueprint("images_api", __name__)


def get_request_info() -> Dict[str, Any]:
    """Extract request information for tracking."""
    return {
        'remote_addr': request.environ.get('REMOTE_ADDR'),
        'user_agent': request.headers.get('User-Agent', ''),
        'session_id': request.cookies.get('session', '')
    }


def validate_image_upload_request() -> Dict[str, Any]:
    """Validate image upload request and return validation results."""
    if not current_user.is_authenticated:
        return {'error': 'Authentication required', 'status': 401}
    
    # Check if files are present
    if 'images' not in request.files:
        return {'error': 'No images provided', 'status': 400}
    
    files = request.files.getlist('images')
    if not files or all(f.filename == '' for f in files):
        return {'error': 'No valid images selected', 'status': 400}
    
    # Check file count limits
    max_images = current_app.config.get('MAX_IMAGES_PER_POST', 5)
    if len(files) > max_images:
        return {
            'error': f'Too many images. Maximum {max_images} images per upload',
            'status': 400
        }
    
    # Validate each file
    max_size = current_app.config.get('MAX_IMAGE_SIZE_MB', 10) * 1024 * 1024
    allowed_extensions = current_app.config.get('ALLOWED_IMAGE_EXTENSIONS', ['jpg', 'jpeg', 'png', 'gif', 'webp'])
    
    for i, file in enumerate(files):
        if not file or not file.filename:
            return {'error': f'Invalid file at position {i}', 'status': 400}
        
        # Check file extension
        ext = file.filename.lower().split('.')[-1] if '.' in file.filename else ''
        if ext not in allowed_extensions:
            return {
                'error': f'Unsupported file format: .{ext}. Allowed: {", ".join(allowed_extensions)}',
                'status': 400
            }
        
        # Check file size
        file.seek(0, 2)  # Seek to end
        size = file.tell()
        file.seek(0)  # Reset to beginning
        
        if size > max_size:
            max_mb = max_size / (1024 * 1024)
            current_mb = size / (1024 * 1024)
            return {
                'error': f'File "{file.filename}" too large: {current_mb:.1f}MB. Maximum: {max_mb}MB',
                'status': 400
            }
    
    return {'success': True}


@images_api_bp.route("/upload", methods=["POST"])
@login_required
def upload_images():
    """
    Upload one or more images.
    
    Form data:
        - images: Multiple image files
        - post_id: Optional existing post ID
        - category: Optional category name for new post
        
    Returns:
        JSON response with upload results
    """
    try:
        # Validate request
        validation = validate_image_upload_request()
        if 'error' in validation:
            return jsonify(validation), validation['status']
        
        # Get form data
        post_id = request.form.get('post_id')
        category_name = request.form.get('category')
        files = request.files.getlist('images')
        
        # Validate post ownership or category
        post = None
        if post_id:
            post = Post.query.get(post_id)
            if not post:
                return jsonify({'error': 'Post not found'}), 404
            if post.user_id != current_user.id:
                return jsonify({'error': 'Access denied'}), 403
        elif category_name:
            category = PostCategory.get_by_name(category_name)
            if not category:
                return jsonify({'error': 'Invalid category'}), 400
        else:
            return jsonify({'error': 'Either post_id or category must be provided'}), 400
        
        # Get S3 upload service
        upload_service = get_s3_upload_service()
        
        # Process uploads
        upload_results = []
        created_images = []
        
        for i, file in enumerate(files):
            try:
                # Upload to S3
                result = upload_service.upload_image(
                    file=file,
                    user_id=current_user.id,
                    post_id=int(post_id) if post_id else None
                )
                
                if result['success']:
                    # Create PostImage record if we have a post
                    if post:
                        image = PostImage.create_from_upload_result(
                            upload_result=result,
                            post_id=post.id,
                            user_id=current_user.id,
                            display_order=i,
                            request_info=get_request_info()
                        )
                        created_images.append(image)
                        
                        # Set as primary if first image
                        if i == 0 and not post.images:
                            image.set_as_primary()
                        
                        result['image_id'] = image.id
                        result['metadata'] = image.get_metadata()
                
                upload_results.append({
                    'file_index': i,
                    'filename': file.filename,
                    'success': result['success'],
                    'result': result
                })
                
            except (S3UploadError, ImageProcessingError) as e:
                logger.error(f"Upload failed for {file.filename}: {e}")
                upload_results.append({
                    'file_index': i,
                    'filename': file.filename,
                    'success': False,
                    'error': str(e)
                })
            except Exception as e:
                logger.error(f"Unexpected error uploading {file.filename}: {e}")
                upload_results.append({
                    'file_index': i,
                    'filename': file.filename,
                    'success': False,
                    'error': 'Upload failed due to server error'
                })
        
        # Calculate success metrics
        successful_uploads = [r for r in upload_results if r['success']]
        failed_uploads = [r for r in upload_results if not r['success']]
        
        response = {
            'success': len(successful_uploads) > 0,
            'total_files': len(files),
            'successful_uploads': len(successful_uploads),
            'failed_uploads': len(failed_uploads),
            'results': upload_results,
            'post_id': int(post_id) if post_id else None,
            'images_created': len(created_images)
        }
        
        # Include moderation warnings
        flagged_images = [r for r in upload_results if r.get('result', {}).get('moderation_result', {}).get('is_flagged')]
        if flagged_images:
            response['moderation_warning'] = f"{len(flagged_images)} images flagged for review"
        
        return jsonify(response)
        
    except RequestEntityTooLarge:
        return jsonify({
            'error': 'Request too large. Check image sizes and count.',
            'max_size_mb': current_app.config.get('MAX_IMAGE_SIZE_MB', 10)
        }), 413
    except Exception as e:
        logger.error(f"Image upload API error: {e}")
        return jsonify({
            'error': 'Image upload failed due to server error',
            'success': False
        }), 500


@images_api_bp.route("/post/<int:post_id>/images", methods=["GET"])
def get_post_images(post_id: int):
    """Get all images for a specific post."""
    try:
        # Check if post exists and is accessible
        post = Post.query.get_or_404(post_id)
        
        # Get images (approved only for public access)
        approved_only = True
        if current_user.is_authenticated and current_user.id == post.user_id:
            approved_only = False  # Post owner can see all their images
        
        images = PostImage.get_by_post(post_id, approved_only=approved_only)
        
        return jsonify({
            'post_id': post_id,
            'image_count': len(images),
            'images': [image.get_metadata() for image in images]
        })
        
    except Exception as e:
        logger.error(f"Error fetching post images: {e}")
        return jsonify({'error': 'Failed to fetch images'}), 500


@images_api_bp.route("/image/<int:image_id>", methods=["GET"])
def get_image_details(image_id: int):
    """Get detailed information about a specific image."""
    try:
        image = PostImage.query.get_or_404(image_id)
        
        # Check access permissions
        if not image.is_approved:
            if not current_user.is_authenticated or current_user.id != image.user_id:
                return jsonify({'error': 'Image not found or not accessible'}), 404
        
        return jsonify({
            'image': image.get_metadata(),
            'post_id': image.post_id,
            'user_id': image.user_id
        })
        
    except Exception as e:
        logger.error(f"Error fetching image details: {e}")
        return jsonify({'error': 'Failed to fetch image details'}), 500


@images_api_bp.route("/image/<int:image_id>", methods=["DELETE"])
@login_required
def delete_image(image_id: int):
    """Delete a specific image."""
    try:
        image = PostImage.query.get_or_404(image_id)
        
        # Check ownership
        if current_user.id != image.user_id:
            return jsonify({'error': 'Access denied'}), 403
        
        # Delete from S3
        upload_service = get_s3_upload_service()
        deletion_results = upload_service.delete_image(image.s3_keys)
        
        # Soft delete from database
        image.soft_delete()
        
        return jsonify({
            'success': True,
            'image_id': image_id,
            'deletion_results': deletion_results,
            'message': 'Image deleted successfully'
        })
        
    except Exception as e:
        logger.error(f"Error deleting image: {e}")
        return jsonify({'error': 'Failed to delete image'}), 500


@images_api_bp.route("/image/<int:image_id>/primary", methods=["POST"])
@login_required
def set_primary_image(image_id: int):
    """Set an image as primary for its post."""
    try:
        image = PostImage.query.get_or_404(image_id)
        
        # Check ownership
        if current_user.id != image.user_id:
            return jsonify({'error': 'Access denied'}), 403
        
        # Check if image is approved
        if not image.is_approved:
            return jsonify({'error': 'Only approved images can be set as primary'}), 400
        
        # Set as primary
        image.set_as_primary()
        
        return jsonify({
            'success': True,
            'image_id': image_id,
            'message': 'Image set as primary'
        })
        
    except Exception as e:
        logger.error(f"Error setting primary image: {e}")
        return jsonify({'error': 'Failed to set primary image'}), 500


@images_api_bp.route("/image/<int:image_id>/reorder", methods=["POST"])
@login_required
def reorder_image(image_id: int):
    """Update display order of an image within its post."""
    try:
        image = PostImage.query.get_or_404(image_id)
        
        # Check ownership
        if current_user.id != image.user_id:
            return jsonify({'error': 'Access denied'}), 403
        
        # Get new order from request
        data = request.get_json()
        if not data or 'display_order' not in data:
            return jsonify({'error': 'display_order required'}), 400
        
        new_order = int(data['display_order'])
        if new_order < 0:
            return jsonify({'error': 'display_order must be non-negative'}), 400
        
        # Update order
        image.update_display_order(new_order)
        
        return jsonify({
            'success': True,
            'image_id': image_id,
            'new_order': new_order,
            'message': 'Image order updated'
        })
        
    except ValueError:
        return jsonify({'error': 'Invalid display_order value'}), 400
    except Exception as e:
        logger.error(f"Error reordering image: {e}")
        return jsonify({'error': 'Failed to update image order'}), 500


@images_api_bp.route("/moderation/pending", methods=["GET"])
@login_required
def get_pending_moderation():
    """Get images pending moderation (admin/moderator only)."""
    # TODO: Add admin/moderator role check when user roles are implemented
    try:
        limit = int(request.args.get('limit', 50))
        limit = min(limit, 100)  # Cap at 100
        
        images = PostImage.get_pending_moderation(limit=limit)
        
        return jsonify({
            'pending_count': len(images),
            'images': [image.get_metadata() for image in images]
        })
        
    except Exception as e:
        logger.error(f"Error fetching pending moderation: {e}")
        return jsonify({'error': 'Failed to fetch pending images'}), 500


@images_api_bp.route("/s3/config/validate", methods=["GET"])
@login_required  
def validate_s3_config():
    """Validate S3 configuration and connectivity (admin only)."""
    # TODO: Add admin role check when user roles are implemented
    try:
        upload_service = get_s3_upload_service()
        validation_result = upload_service.validate_s3_configuration()
        
        return jsonify(validation_result)
        
    except Exception as e:
        logger.error(f"S3 validation error: {e}")
        return jsonify({
            'success': False,
            'error': 'Configuration validation failed',
            'details': str(e)
        }), 500


# Error handlers for the images API
@images_api_bp.errorhandler(413)
def request_entity_too_large(error):
    """Handle request too large errors."""
    return jsonify({
        'error': 'Request too large',
        'message': 'Image files exceed maximum allowed size',
        'max_size_mb': current_app.config.get('MAX_IMAGE_SIZE_MB', 10)
    }), 413


@images_api_bp.errorhandler(400)
def bad_request(error):
    """Handle bad request errors."""
    return jsonify({
        'error': 'Bad request',
        'message': 'Invalid request format or parameters'
    }), 400