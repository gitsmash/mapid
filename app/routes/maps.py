"""Maps routes for geospatial functionality."""
import logging
from typing import Dict, Any, Optional, List
from flask import Blueprint, render_template, jsonify, request, current_app
from flask_login import login_required, current_user
from werkzeug.exceptions import BadRequest
from app.services.location import get_location_service, ValidationResult, LocationResult

logger = logging.getLogger(__name__)
maps_bp = Blueprint("maps", __name__)


@maps_bp.route("/")
def map_view():
    """Main map interface."""
    return render_template("maps/map_view.html", title="Map")


@maps_bp.route("/api/posts")
def api_posts_nearby():
    """
    API endpoint for posts visible in the current map viewport.
    
    Query parameters:
    - north, south, east, west: Bounding box coordinates 
    - category: Optional category filter
    - limit: Maximum number of posts (default: 50)
    
    Returns:
    {
        "success": true,
        "posts": [...],
        "total_count": 25
    }
    """
    try:
        # Extract bounding box parameters
        north = request.args.get('north', type=float)
        south = request.args.get('south', type=float)
        east = request.args.get('east', type=float)
        west = request.args.get('west', type=float)
        
        # Validate required parameters
        if None in (north, south, east, west):
            return jsonify({
                "success": False,
                "error": "Bounding box coordinates (north, south, east, west) are required"
            }), 400
            
        # Validate coordinate ranges
        if not (-90 <= south <= north <= 90):
            return jsonify({
                "success": False,
                "error": "Invalid latitude values"
            }), 400
            
        if not (-180 <= west <= 180 and -180 <= east <= 180):
            return jsonify({
                "success": False,
                "error": "Invalid longitude values"
            }), 400
        
        # Optional parameters
        category_filter = request.args.get('category', '').strip()
        limit = min(int(request.args.get('limit', 50)), 100)  # Max 100 posts
        
        # Get posts within bounding box using optimized PostGIS query
        from app.models.post import Post
        posts = Post.find_in_bounding_box(
            north=north, 
            south=south, 
            east=east, 
            west=west,
            category_name=category_filter if category_filter else None,
            limit=limit
        )
        
        # Convert posts to JSON format for map markers
        posts_data = []
        for post in posts:
            try:
                coords = post.get_coordinates()
                if not coords:
                    continue
                    
                # Calculate distance if user is logged in and has location
                distance_text = None
                if current_user.is_authenticated and current_user.location:
                    distance_meters = post.calculate_distance_to_user(current_user)
                    if distance_meters is not None:
                        if distance_meters < 1609:  # Less than 1 mile
                            distance_text = "< 1 mile"
                        else:
                            miles = distance_meters * 0.000621371
                            distance_text = f"{miles:.1f} miles"
                
                post_data = {
                    "id": post.id,
                    "title": post.title,
                    "description": post.description[:200] + ("..." if len(post.description) > 200 else ""),
                    "latitude": coords[0],
                    "longitude": coords[1], 
                    "category": post.category.name,
                    "emoji": post.category.emoji,
                    "color": post.category.color_hex,
                    "address": post.address,
                    "neighborhood": post.neighborhood,
                    "city": post.city,
                    "created_at": post.created_at.isoformat() if post.created_at else None,
                    "expires_at": post.expires_at.isoformat() if post.expires_at else None,
                    "view_count": post.view_count,
                    "like_count": post.like_count,
                    "distance": distance_text,
                    "user_display_name": post.user.display_name if post.user else "Anonymous"
                }
                
                # Add category-specific data
                if post.category_data:
                    # Include relevant category data for display
                    if post.category.name == 'for_sale' and post.category_data.get('price'):
                        post_data['price'] = post.category_data['price']
                    elif post.category.name == 'restaurant' and post.category_data.get('special_item'):
                        post_data['special_item'] = post.category_data['special_item']
                    elif post.category.name == 'garage_sale' and post.category_data.get('start_time'):
                        post_data['start_time'] = post.category_data['start_time']
                    elif post.category.name == 'help_needed' and post.category_data.get('urgency_level'):
                        post_data['urgency_level'] = post.category_data['urgency_level']
                
                posts_data.append(post_data)
                
            except Exception as e:
                logger.warning(f"Error serializing post {post.id}: {str(e)}")
                continue
        
        # Log request for monitoring
        logger.info(f"Map API: Returned {len(posts_data)} posts in bounding box "
                   f"({north}, {south}, {east}, {west}) with category filter '{category_filter}'")
        
        response = jsonify({
            "success": True,
            "posts": posts_data,
            "total_count": len(posts_data)
        })
        
        # Add caching headers for performance (cache for 30 seconds)
        response.headers['Cache-Control'] = 'public, max-age=30'
        response.headers['ETag'] = f'posts-{len(posts_data)}-{hash(str(sorted([p["id"] for p in posts_data])))}'
        
        return response
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": "Invalid numeric parameters"
        }), 400
    except Exception as e:
        logger.error(f"Error in map posts API: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Internal server error"
        }), 500


@maps_bp.route("/api/posts/count")
def api_posts_count():
    """
    Get post count within a bounding box for performance.
    
    Query parameters:
    - north, south, east, west: Bounding box coordinates
    - category: Optional category filter
    
    Returns:
    {
        "success": true,
        "count": 42
    }
    """
    try:
        # Extract bounding box parameters
        north = request.args.get('north', type=float)
        south = request.args.get('south', type=float)
        east = request.args.get('east', type=float)
        west = request.args.get('west', type=float)
        
        # Validate required parameters
        if None in (north, south, east, west):
            return jsonify({
                "success": False,
                "error": "Bounding box coordinates (north, south, east, west) are required"
            }), 400
        
        # Validate coordinate ranges  
        if not (-90 <= south <= north <= 90):
            return jsonify({
                "success": False,
                "error": "Invalid latitude values"
            }), 400
            
        if not (-180 <= west <= 180 and -180 <= east <= 180):
            return jsonify({
                "success": False,
                "error": "Invalid longitude values"
            }), 400
        
        # Optional parameters
        category_filter = request.args.get('category', '').strip()
        
        # Get post count
        from app.models.post import Post
        from app.models.category import PostCategory
        from geoalchemy2.elements import WKTElement
        from sqlalchemy import func
        
        # Create bounding box polygon
        bbox_wkt = f"POLYGON(({west} {south}, {east} {south}, {east} {north}, {west} {north}, {west} {south}))"
        bbox_polygon = WKTElement(bbox_wkt, srid=4326)
        
        query = Post.query.filter(
            Post.is_active == True,
            Post.is_deleted == False,
            func.ST_Within(Post.location, bbox_polygon)
        )
        
        # Apply category filter if provided
        if category_filter:
            query = query.join(PostCategory).filter(
                PostCategory.name == category_filter,
                PostCategory.is_active == True
            )
        
        count = query.count()
        
        return jsonify({
            "success": True,
            "count": count
        })
        
    except ValueError:
        return jsonify({
            "success": False,
            "error": "Invalid numeric parameters"
        }), 400
    except Exception as e:
        logger.error(f"Error in post count API: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Internal server error"
        }), 500


@maps_bp.route("/location-picker")
@login_required
def location_picker():
    """Location picker interface for creating posts."""
    return render_template("maps/location_picker.html", title="Choose Location")


@maps_bp.route("/api/geocode", methods=["POST"])
@login_required
def api_geocode():
    """
    Geocode an address to coordinates.
    
    Expected JSON payload:
    {
        "address": "123 Main St, City, State"
    }
    
    Returns:
    {
        "success": true,
        "data": {
            "latitude": 40.7128,
            "longitude": -74.0060,
            "address": "formatted address",
            "confidence": 0.95
        }
    }
    """
    try:
        data = request.get_json()
        
        if not data or not data.get('address'):
            return jsonify({
                "success": False,
                "error": "Address is required"
            }), 400
        
        address = data['address'].strip()
        if len(address) < 3:
            return jsonify({
                "success": False,
                "error": "Address must be at least 3 characters long"
            }), 400
        
        # Get location service and geocode
        location_service = get_location_service()
        result = location_service.geocode_address(address)
        
        if not result:
            return jsonify({
                "success": False,
                "error": "Could not find location for the provided address"
            }), 404
        
        # Validate the result
        validation = location_service.validate_location(result.latitude, result.longitude)
        
        if not validation.is_valid:
            return jsonify({
                "success": False,
                "error": validation.error_message,
                "suggested_coordinates": validation.suggested_coordinates
            }), 400
        
        # Return successful result
        response_data = {
            "latitude": result.latitude,
            "longitude": result.longitude,
            "address": result.address,
            "formatted_address": result.formatted_address,
            "confidence": result.confidence,
            "warnings": validation.warnings or []
        }
        
        # Add neighborhood info if available
        if result.neighborhood:
            response_data["neighborhood"] = result.neighborhood
        if result.city:
            response_data["city"] = result.city
        
        logger.info(f"Geocoded address for user {current_user.id}: '{address}' -> ({result.latitude}, {result.longitude})")
        
        return jsonify({
            "success": True,
            "data": response_data
        })
        
    except BadRequest:
        return jsonify({
            "success": False,
            "error": "Invalid JSON payload"
        }), 400
    except Exception as e:
        logger.error(f"Error in geocode API: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Internal server error"
        }), 500


@maps_bp.route("/api/reverse-geocode", methods=["POST"])
@login_required
def api_reverse_geocode():
    """
    Reverse geocode coordinates to address.
    
    Expected JSON payload:
    {
        "latitude": 40.7128,
        "longitude": -74.0060
    }
    
    Returns:
    {
        "success": true,
        "data": {
            "address": "formatted address",
            "neighborhood": "Downtown",
            "city": "New York"
        }
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "error": "JSON payload is required"
            }), 400
        
        # Extract and validate coordinates
        try:
            latitude = float(data.get('latitude', 0))
            longitude = float(data.get('longitude', 0))
        except (ValueError, TypeError):
            return jsonify({
                "success": False,
                "error": "Invalid latitude or longitude values"
            }), 400
        
        # Basic coordinate validation
        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            return jsonify({
                "success": False,
                "error": "Coordinates are outside valid range"
            }), 400
        
        # Get location service and reverse geocode
        location_service = get_location_service()
        result = location_service.reverse_geocode(latitude, longitude)
        
        if not result:
            return jsonify({
                "success": False,
                "error": "Could not find address for the provided coordinates"
            }), 404
        
        # Validate the location
        validation = location_service.validate_location(latitude, longitude)
        
        response_data = {
            "address": result.address,
            "formatted_address": result.formatted_address,
            "confidence": result.confidence,
            "warnings": validation.warnings or []
        }
        
        # Add optional components
        if result.neighborhood:
            response_data["neighborhood"] = result.neighborhood
        if result.city:
            response_data["city"] = result.city
        if result.state:
            response_data["state"] = result.state
        if result.postal_code:
            response_data["postal_code"] = result.postal_code
        
        logger.info(f"Reverse geocoded for user {current_user.id}: ({latitude}, {longitude}) -> '{result.address}'")
        
        return jsonify({
            "success": True,
            "data": response_data
        })
        
    except BadRequest:
        return jsonify({
            "success": False,
            "error": "Invalid JSON payload"
        }), 400
    except Exception as e:
        logger.error(f"Error in reverse geocode API: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Internal server error"
        }), 500


@maps_bp.route("/api/validate-location", methods=["POST"])
@login_required
def api_validate_location():
    """
    Validate location coordinates against business rules.
    
    Expected JSON payload:
    {
        "latitude": 40.7128,
        "longitude": -74.0060,
        "reference_latitude": 40.7000,  // optional
        "reference_longitude": -74.0000  // optional
    }
    
    Returns:
    {
        "success": true,
        "data": {
            "is_valid": true,
            "warnings": [],
            "distance_miles": 1.2  // if reference point provided
        }
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "error": "JSON payload is required"
            }), 400
        
        # Extract and validate coordinates
        try:
            latitude = float(data.get('latitude', 0))
            longitude = float(data.get('longitude', 0))
        except (ValueError, TypeError):
            return jsonify({
                "success": False,
                "error": "Invalid latitude or longitude values"
            }), 400
        
        # Extract reference point if provided
        reference_point = None
        if data.get('reference_latitude') is not None and data.get('reference_longitude') is not None:
            try:
                ref_lat = float(data['reference_latitude'])
                ref_lng = float(data['reference_longitude'])
                reference_point = (ref_lat, ref_lng)
            except (ValueError, TypeError):
                return jsonify({
                    "success": False,
                    "error": "Invalid reference coordinates"
                }), 400
        
        # Validate location
        location_service = get_location_service()
        validation = location_service.validate_location(latitude, longitude, reference_point)
        
        response_data = {
            "is_valid": validation.is_valid,
            "warnings": validation.warnings or []
        }
        
        if not validation.is_valid:
            response_data["error_message"] = validation.error_message
            if validation.suggested_coordinates:
                response_data["suggested_coordinates"] = {
                    "latitude": validation.suggested_coordinates[0],
                    "longitude": validation.suggested_coordinates[1]
                }
        
        # Calculate distance if reference point provided
        if reference_point and validation.is_valid:
            distance_km = location_service.calculate_distance(
                latitude, longitude, reference_point[0], reference_point[1]
            )
            response_data["distance_miles"] = distance_km * 0.621371
            response_data["distance_km"] = distance_km
        
        return jsonify({
            "success": True,
            "data": response_data
        })
        
    except BadRequest:
        return jsonify({
            "success": False,
            "error": "Invalid JSON payload"
        }), 400
    except Exception as e:
        logger.error(f"Error in validate location API: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Internal server error"
        }), 500


@maps_bp.route("/api/nearby-places", methods=["POST"])
@login_required
def api_nearby_places():
    """
    Find nearby places of interest.
    
    Expected JSON payload:
    {
        "latitude": 40.7128,
        "longitude": -74.0060,
        "place_type": "amenity",  // optional
        "radius_meters": 1000     // optional
    }
    
    Returns:
    {
        "success": true,
        "data": {
            "places": [...]
        }
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "error": "JSON payload is required"
            }), 400
        
        # Extract and validate coordinates
        try:
            latitude = float(data.get('latitude', 0))
            longitude = float(data.get('longitude', 0))
        except (ValueError, TypeError):
            return jsonify({
                "success": False,
                "error": "Invalid latitude or longitude values"
            }), 400
        
        # Basic coordinate validation
        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            return jsonify({
                "success": False,
                "error": "Coordinates are outside valid range"
            }), 400
        
        # Extract optional parameters
        place_type = data.get('place_type', 'amenity')
        radius_meters = min(int(data.get('radius_meters', 1000)), 5000)  # Max 5km
        
        # Find nearby places
        location_service = get_location_service()
        places = location_service.find_nearby_places(
            latitude, longitude, place_type, radius_meters
        )
        
        return jsonify({
            "success": True,
            "data": {
                "places": places,
                "total_count": len(places)
            }
        })
        
    except BadRequest:
        return jsonify({
            "success": False,
            "error": "Invalid JSON payload"
        }), 400
    except Exception as e:
        logger.error(f"Error in nearby places API: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Internal server error"
        }), 500


@maps_bp.errorhandler(404)
def api_not_found(e):
    """Handle API 404 errors."""
    return jsonify({
        "success": False,
        "error": "Endpoint not found"
    }), 404


@maps_bp.errorhandler(405)
def api_method_not_allowed(e):
    """Handle API method not allowed errors."""
    return jsonify({
        "success": False,
        "error": "Method not allowed"
    }), 405