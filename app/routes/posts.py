"""Posts routes for CRUD operations."""
import logging
from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, abort
from flask_login import login_required, current_user
from werkzeug.exceptions import NotFound

from app.models.category import PostCategory
from app.models.post import Post
from app.models.post_image import PostImage
from app.forms.posts import BasePostForm, get_form_for_category
from app.services.post_service import get_post_service, PostCreationError, PostValidationError

logger = logging.getLogger(__name__)

posts_bp = Blueprint("posts", __name__)


@posts_bp.route("/")
def list_posts():
    """List all posts with filtering and pagination."""
    try:
        post_service = get_post_service()
        
        # Get filter parameters
        category_filter = request.args.get('category')
        latitude = request.args.get('lat', type=float)
        longitude = request.args.get('lng', type=float)
        radius = request.args.get('radius', 3218, type=int)  # Default 2 miles in meters
        limit = request.args.get('limit', 20, type=int)
        
        posts = []
        
        # Determine which posts to show
        if latitude and longitude:
            # Location-based search
            posts = post_service.get_posts_nearby(
                latitude=latitude,
                longitude=longitude,
                radius_meters=radius,
                limit=limit,
                category_filter=category_filter,
                user=current_user if current_user.is_authenticated else None
            )
        elif category_filter:
            # Category-based search
            posts = post_service.get_posts_by_category(category_filter, limit=limit)
        else:
            # Recent posts
            posts = post_service.get_recent_posts(limit=limit)
        
        # Get all categories for filter dropdown
        categories = PostCategory.get_all_active()
        
        return render_template(
            "posts/list.html", 
            title="Community Posts",
            posts=posts,
            categories=categories,
            current_category=category_filter,
            current_location={'lat': latitude, 'lng': longitude} if latitude and longitude else None
        )
        
    except Exception as e:
        logger.error(f"Error listing posts: {str(e)}")
        flash("Error loading posts. Please try again.", "error")
        return render_template("posts/list.html", title="Community Posts", posts=[], categories=[])


@posts_bp.route("/create")
@login_required
def create_post():
    """Show post creation form with category selection."""
    categories = PostCategory.get_all_active()
    selected_category = request.args.get('category')
    
    # If category is selected, show the specific form
    if selected_category:
        category = PostCategory.get_by_name(selected_category)
        if category:
            form_class = get_form_for_category(selected_category)
            form = form_class()
            form.category_id.data = category.id
            return render_template("posts/create_form.html", 
                                 title=f"Create {category.display_name}", 
                                 form=form, 
                                 category=category)
    
    # Otherwise show category selection
    return render_template("posts/create_select.html", 
                         title="Create Post", 
                         categories=categories)


@posts_bp.route("/create", methods=["POST"])
@login_required
def create_post_submit():
    """Handle post creation form submission."""
    try:
        # Get category from form data
        category_id = request.form.get('category_id')
        if not category_id:
            flash("Please select a valid category", "error")
            return redirect(url_for('posts.create_post'))
        
        category = PostCategory.query.get_or_404(category_id)
        form_class = get_form_for_category(category.name)
        form = form_class()
        
        if form.validate_on_submit():
            try:
                post_service = get_post_service()
                
                # Prepare form data for service
                form_data = {
                    'title': form.title.data,
                    'description': form.description.data,
                    'category_id': form.category_id.data,
                    'location': form.location.data,
                    'expires_at': form.expires_at.data
                }
                
                # Add category-specific data
                for field_name, field in form._fields.items():
                    if field_name not in ['csrf_token', 'title', 'description', 'category_id', 'location', 'expires_at', 'photos', 'address_display']:
                        form_data[field_name] = field.data
                
                # Get uploaded files
                uploaded_files = []
                if form.photos.data:
                    uploaded_files = [f for f in form.photos.data if f.filename]
                
                # Create post
                post, warnings = post_service.create_post(
                    form_data=form_data,
                    user=current_user,
                    uploaded_files=uploaded_files
                )
                
                # Show success message with any warnings
                success_msg = f"Your {category.display_name.lower()} post has been created successfully!"
                if warnings:
                    success_msg += f" (Warnings: {'; '.join(warnings)})"
                
                flash(success_msg, "success")
                return redirect(url_for('posts.view_post', post_id=post.id))
                
            except PostValidationError as e:
                logger.warning(f"Post validation failed: {str(e)}")
                flash(f"Validation error: {str(e)}", "error")
            except PostCreationError as e:
                logger.warning(f"Post creation failed: {str(e)}")
                flash(f"Post creation failed: {str(e)}", "error")
            except Exception as e:
                logger.error(f"Unexpected error creating post: {str(e)}")
                flash("An unexpected error occurred. Please try again.", "error")
        
        # Form validation failed or error occurred, show form with errors
        return render_template("posts/create_form.html",
                             title=f"Create {category.display_name}",
                             form=form,
                             category=category)
        
    except Exception as e:
        logger.error(f"Error in create_post_submit: {str(e)}")
        flash("An error occurred. Please try again.", "error")
        return redirect(url_for('posts.create_post'))


@posts_bp.route("/api/category/<category_name>/fields")
def get_category_form_fields(category_name):
    """API endpoint to get form fields for a specific category."""
    category = PostCategory.get_by_name(category_name)
    if not category:
        return jsonify({"error": "Category not found"}), 404
    
    form_class = get_form_for_category(category_name)
    form = form_class()
    
    # Return field metadata for dynamic form building
    fields = {}
    for field_name, field in form._fields.items():
        if field_name in ['csrf_token', 'category_id']:
            continue
            
        field_info = {
            "type": field.__class__.__name__,
            "label": field.label.text,
            "required": any(v.__class__.__name__ == 'DataRequired' for v in field.validators),
            "validators": [v.__class__.__name__ for v in field.validators],
        }
        
        # Add choices for SelectField
        if hasattr(field, 'choices'):
            field_info["choices"] = field.choices
            
        # Add render_kw attributes
        if hasattr(field, 'render_kw') and field.render_kw:
            field_info["render_kw"] = field.render_kw
            
        fields[field_name] = field_info
    
    return jsonify({
        "category": {
            "name": category.name,
            "display_name": category.display_name,
            "emoji": category.emoji,
            "color_hex": category.color_hex,
            "max_photos": category.max_photos,
            "requires_time": category.requires_time,
            "requires_price": category.requires_price
        },
        "fields": fields
    })


@posts_bp.route("/<int:post_id>")
def view_post(post_id):
    """View individual post with all details."""
    try:
        post_service = get_post_service()
        
        # Get post with permission checks
        post = post_service.get_post_by_id(
            post_id, 
            user=current_user if current_user.is_authenticated else None
        )
        
        if not post:
            flash("Post not found or no longer available.", "error")
            return redirect(url_for('posts.list_posts'))
        
        # Get approved images for this post
        images = PostImage.get_by_post(post_id, approved_only=True)
        
        # Calculate distance from current user if available
        distance = None
        if current_user.is_authenticated and current_user.location:
            distance = post.calculate_distance_to_user(current_user)
        
        # Check if current user owns this post
        is_owner = current_user.is_authenticated and post.user_id == current_user.id
        
        return render_template(
            "posts/detail.html",
            title=post.title,
            post=post,
            images=images,
            distance=distance,
            is_owner=is_owner
        )
        
    except Exception as e:
        logger.error(f"Error viewing post {post_id}: {str(e)}")
        flash("Error loading post. Please try again.", "error")
        return redirect(url_for('posts.list_posts'))


@posts_bp.route("/<int:post_id>/edit")
@login_required
def edit_post(post_id):
    """Show edit form for existing post."""
    try:
        post_service = get_post_service()
        
        # Get post with ownership check
        post = post_service.get_post_by_id(post_id, user=current_user)
        if not post:
            flash("Post not found or not authorized to edit.", "error")
            return redirect(url_for('posts.list_posts'))
        
        # Check ownership
        if post.user_id != current_user.id and not current_user.is_admin:
            flash("You are not authorized to edit this post.", "error")
            return redirect(url_for('posts.view_post', post_id=post_id))
        
        # Check if post is expired
        if post.is_expired:
            flash("Cannot edit expired posts.", "error")
            return redirect(url_for('posts.view_post', post_id=post_id))
        
        # Get appropriate form for category
        form_class = get_form_for_category(post.category.name)
        form = form_class()
        
        # Pre-populate form with existing data
        form.title.data = post.title
        form.description.data = post.description
        form.category_id.data = post.category_id
        form.expires_at.data = post.expires_at
        
        # Set location data
        coordinates = post.get_coordinates()
        if coordinates:
            form.location.set_location_data(
                latitude=coordinates[0],
                longitude=coordinates[1],
                address=post.address,
                neighborhood=post.neighborhood,
                city=post.city,
                state=post.state
            )
        
        # Pre-populate category-specific fields
        if post.category_data:
            for field_name, value in post.category_data.items():
                if hasattr(form, field_name):
                    field = getattr(form, field_name)
                    # Handle datetime fields
                    if hasattr(field, 'data') and isinstance(value, str):
                        try:
                            from datetime import datetime
                            if 'time' in field_name.lower() or 'date' in field_name.lower():
                                value = datetime.fromisoformat(value)
                        except ValueError:
                            pass
                    field.data = value
        
        # Get existing images
        images = PostImage.get_by_post(post_id, approved_only=False)
        
        return render_template(
            "posts/edit.html",
            title=f"Edit {post.category.display_name}",
            form=form,
            post=post,
            images=images
        )
        
    except Exception as e:
        logger.error(f"Error showing edit form for post {post_id}: {str(e)}")
        flash("Error loading edit form. Please try again.", "error")
        return redirect(url_for('posts.view_post', post_id=post_id))


@posts_bp.route("/<int:post_id>/edit", methods=["POST"])
@login_required
def edit_post_submit(post_id):
    """Handle post edit form submission."""
    try:
        post_service = get_post_service()
        
        # Get post with ownership check
        post = post_service.get_post_by_id(post_id, user=current_user)
        if not post:
            flash("Post not found or not authorized to edit.", "error")
            return redirect(url_for('posts.list_posts'))
        
        # Get appropriate form for category
        form_class = get_form_for_category(post.category.name)
        form = form_class()
        
        if form.validate_on_submit():
            try:
                # Prepare form data for service
                form_data = {
                    'title': form.title.data,
                    'description': form.description.data,
                    'location': form.location.data,
                    'expires_at': form.expires_at.data
                }
                
                # Add category-specific data
                for field_name, field in form._fields.items():
                    if field_name not in ['csrf_token', 'title', 'description', 'category_id', 'location', 'expires_at', 'photos', 'address_display']:
                        form_data[field_name] = field.data
                
                # Update post
                updated_post, warnings = post_service.update_post(
                    post_id=post_id,
                    form_data=form_data,
                    user=current_user
                )
                
                # Show success message
                success_msg = f"Your {post.category.display_name.lower()} has been updated successfully!"
                if warnings:
                    success_msg += f" (Warnings: {'; '.join(warnings)})"
                
                flash(success_msg, "success")
                return redirect(url_for('posts.view_post', post_id=post_id))
                
            except PostValidationError as e:
                logger.warning(f"Post update validation failed: {str(e)}")
                flash(f"Validation error: {str(e)}", "error")
            except PermissionError as e:
                logger.warning(f"Post update permission denied: {str(e)}")
                flash("You are not authorized to edit this post.", "error")
                return redirect(url_for('posts.view_post', post_id=post_id))
            except Exception as e:
                logger.error(f"Unexpected error updating post {post_id}: {str(e)}")
                flash("An unexpected error occurred. Please try again.", "error")
        
        # Form validation failed, show form with errors
        images = PostImage.get_by_post(post_id, approved_only=False)
        return render_template(
            "posts/edit.html",
            title=f"Edit {post.category.display_name}",
            form=form,
            post=post,
            images=images
        )
        
    except Exception as e:
        logger.error(f"Error in edit_post_submit for post {post_id}: {str(e)}")
        flash("An error occurred. Please try again.", "error")
        return redirect(url_for('posts.view_post', post_id=post_id))


@posts_bp.route("/<int:post_id>/delete", methods=["POST"])
@login_required
def delete_post(post_id):
    """Delete a post (soft delete)."""
    try:
        post_service = get_post_service()
        
        # Get post
        post = Post.query.get(post_id)
        if not post:
            flash("Post not found.", "error")
            return redirect(url_for('posts.list_posts'))
        
        # Check permissions
        if post.user_id != current_user.id and not current_user.is_admin:
            flash("You are not authorized to delete this post.", "error")
            return redirect(url_for('posts.view_post', post_id=post_id))
        
        # Delete post
        success = post_service.delete_post(
            post_id=post_id,
            user=current_user,
            hard_delete=False
        )
        
        if success:
            flash(f"Your {post.category.display_name.lower()} has been deleted.", "success")
            return redirect(url_for('posts.list_posts'))
        else:
            flash("Failed to delete post. Please try again.", "error")
            return redirect(url_for('posts.view_post', post_id=post_id))
        
    except PermissionError as e:
        logger.warning(f"Post deletion permission denied: {str(e)}")
        flash("You are not authorized to delete this post.", "error")
        return redirect(url_for('posts.view_post', post_id=post_id))
    except Exception as e:
        logger.error(f"Error deleting post {post_id}: {str(e)}")
        flash("An error occurred while deleting the post.", "error")
        return redirect(url_for('posts.view_post', post_id=post_id))


@posts_bp.route("/my-posts")
@login_required
def my_posts():
    """Show current user's posts."""
    try:
        post_service = get_post_service()
        
        # Get user's posts including inactive ones
        posts = post_service.get_user_posts(
            user_id=current_user.id,
            include_inactive=True,
            limit=50
        )
        
        return render_template(
            "posts/my_posts.html",
            title="My Posts",
            posts=posts
        )
        
    except Exception as e:
        logger.error(f"Error loading user posts: {str(e)}")
        flash("Error loading your posts. Please try again.", "error")
        return render_template("posts/my_posts.html", title="My Posts", posts=[])