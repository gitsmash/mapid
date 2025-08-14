"""Post creation and management forms."""
from datetime import datetime, timedelta
from typing import Optional
from flask import current_app
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileSize
from wtforms import (
    StringField, TextAreaField, FloatField, DecimalField, 
    SelectField, DateTimeField, IntegerField, BooleanField,
    MultipleFileField, HiddenField
)
from wtforms.validators import (
    DataRequired, Length, Optional as OptionalValidator, 
    NumberRange, ValidationError
)
from wtforms.widgets import TextArea
from app.models.category import PostCategory


class LocationField(HiddenField):
    """Custom field for storing coordinates and address information."""
    
    def __init__(self, label=None, validators=None, **kwargs):
        """Initialize LocationField with default validation."""
        super().__init__(label, validators, **kwargs)
        self.location_data = None
    
    def process_formdata(self, valuelist):
        """Process coordinate data from form."""
        if valuelist:
            try:
                value = valuelist[0]
                
                # Handle JSON format: {"lat": 40.7128, "lng": -74.0060, "address": "..."}
                if value.startswith('{'):
                    import json
                    data = json.loads(value)
                    if 'lat' in data and 'lng' in data:
                        lat, lng = float(data['lat']), float(data['lng'])
                        if -90 <= lat <= 90 and -180 <= lng <= 180:
                            self.data = data
                            self.location_data = data
                        else:
                            raise ValueError("Coordinates out of valid range")
                    else:
                        raise ValueError("Missing lat/lng in JSON data")
                
                # Handle simple "latitude,longitude" format (legacy)
                elif ',' in value:
                    coords = value.split(',')
                    if len(coords) == 2:
                        lat, lng = float(coords[0]), float(coords[1])
                        if -90 <= lat <= 90 and -180 <= lng <= 180:
                            self.data = {'lat': lat, 'lng': lng}
                            self.location_data = self.data
                        else:
                            raise ValueError("Coordinates out of valid range")
                    else:
                        raise ValueError("Invalid coordinate format")
                
                else:
                    raise ValueError("Unrecognized location format")
                    
            except (ValueError, IndexError, json.JSONDecodeError) as e:
                self.data = None
                self.location_data = None
        else:
            self.data = None
            self.location_data = None
    
    def get_coordinates(self):
        """Get coordinates as tuple (lat, lng)."""
        if self.location_data and 'lat' in self.location_data and 'lng' in self.location_data:
            return (float(self.location_data['lat']), float(self.location_data['lng']))
        return None
    
    def get_address(self):
        """Get formatted address string."""
        if self.location_data and 'address' in self.location_data:
            return str(self.location_data['address'])
        return None
    
    def get_neighborhood(self):
        """Get neighborhood name."""
        if self.location_data and 'neighborhood' in self.location_data:
            return str(self.location_data['neighborhood'])
        return None
    
    def set_location_data(self, latitude, longitude, address=None, **kwargs):
        """Set location data programmatically."""
        location_data = {
            'lat': float(latitude),
            'lng': float(longitude)
        }
        
        if address:
            location_data['address'] = str(address)
        
        # Add any additional data
        for key, value in kwargs.items():
            if value is not None:
                location_data[key] = value
        
        self.data = location_data
        self.location_data = location_data
        
        return location_data


class BasePostForm(FlaskForm):
    """Base form for all post types with common fields."""
    
    title = StringField(
        'Title',
        validators=[
            DataRequired(message="Please provide a title for your post"),
            Length(min=3, max=200, message="Title must be between 3 and 200 characters")
        ],
        render_kw={"placeholder": "Enter a descriptive title..."}
    )
    
    description = TextAreaField(
        'Description',
        validators=[
            DataRequired(message="Please provide a description"),
            Length(min=10, max=2000, message="Description must be between 10 and 2000 characters")
        ],
        render_kw={"placeholder": "Describe your post in detail...", "rows": 4}
    )
    
    category_id = SelectField(
        'Category',
        coerce=int,
        validators=[DataRequired(message="Please select a category")]
    )
    
    location = LocationField(
        'Location',
        validators=[DataRequired(message="Please select a location on the map")]
    )
    
    address_display = StringField(
        'Address',
        validators=[OptionalValidator(), Length(max=255)],
        render_kw={"readonly": True, "placeholder": "Address will be filled automatically"}
    )
    
    photos = MultipleFileField(
        'Photos',
        validators=[
            FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'webp'], 'Only image files are allowed'),
            FileSize(max_size=10 * 1024 * 1024, message="Each file must be less than 10MB")
        ]
    )
    
    expires_at = DateTimeField(
        'Expires',
        validators=[OptionalValidator()],
        format='%Y-%m-%d %H:%M'
    )
    
    def __init__(self, *args, **kwargs):
        """Initialize form with category choices."""
        super().__init__(*args, **kwargs)
        
        # Populate category choices
        categories = PostCategory.get_all_active()
        self.category_id.choices = [
            (cat.id, f"{cat.emoji} {cat.display_name}") 
            for cat in categories
        ]
        
        # Set default expiration if not provided
        if not self.expires_at.data and self.category_id.data:
            category = PostCategory.query.get(self.category_id.data)
            if category:
                self.expires_at.data = datetime.utcnow() + timedelta(days=category.default_expiration_days)
    
    def validate_location(self, field):
        """Validate location coordinates using location service."""
        if not field.data or not isinstance(field.data, dict):
            raise ValidationError("Please select a valid location on the map")
        
        lat, lng = field.data.get('lat'), field.data.get('lng')
        if not lat or not lng:
            raise ValidationError("Invalid location coordinates")
        
        # Basic coordinate validation
        if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
            raise ValidationError("Coordinates are outside valid range")
        
        # Use location service for advanced validation
        try:
            from app.services.location import get_location_service
            location_service = get_location_service()
            
            # Validate location against business rules
            validation_result = location_service.validate_location(lat, lng)
            
            if not validation_result.is_valid:
                if "distance" in validation_result.error_message.lower():
                    raise ValidationError(f"Location is too far from allowed area. {validation_result.error_message}")
                else:
                    raise ValidationError(validation_result.error_message)
            
            # Log warnings but don't fail validation
            if validation_result.warnings:
                import logging
                logger = logging.getLogger(__name__)
                for warning in validation_result.warnings:
                    logger.warning(f"Location validation warning: {warning}")
        
        except ImportError:
            # Fallback to basic validation if service is not available
            pass
        except Exception as e:
            # Log error but don't fail validation - fallback to basic checks
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error in location validation: {str(e)}")
            pass
    
    def validate_photos(self, field):
        """Validate photo count based on category limits."""
        if not field.data:
            return
            
        category = None
        if self.category_id.data:
            category = PostCategory.query.get(self.category_id.data)
        
        max_photos = category.max_photos if category else 5
        
        # Count actual uploaded files
        photo_count = len([f for f in field.data if f.filename])
        
        if photo_count > max_photos:
            raise ValidationError(f"This post type allows maximum {max_photos} photos")


class GarageSaleForm(BasePostForm):
    """Form for garage sale posts."""
    
    start_time = DateTimeField(
        'Sale Start Time',
        validators=[DataRequired(message="Please specify when the sale starts")],
        format='%Y-%m-%d %H:%M',
        render_kw={"placeholder": "When does the sale start?"}
    )
    
    end_time = DateTimeField(
        'Sale End Time',
        validators=[DataRequired(message="Please specify when the sale ends")],
        format='%Y-%m-%d %H:%M',
        render_kw={"placeholder": "When does the sale end?"}
    )
    
    item_categories = StringField(
        'Item Categories',
        validators=[OptionalValidator(), Length(max=500)],
        render_kw={"placeholder": "e.g., Furniture, Clothing, Electronics, Books"}
    )
    
    parking_info = TextAreaField(
        'Parking & Access Info',
        validators=[OptionalValidator(), Length(max=300)],
        render_kw={"placeholder": "Any special parking or access instructions", "rows": 2}
    )
    
    accepts_early_birds = BooleanField(
        'Accept Early Birds',
        default=False
    )
    
    def validate_end_time(self, field):
        """Ensure end time is after start time."""
        if self.start_time.data and field.data:
            if field.data <= self.start_time.data:
                raise ValidationError("End time must be after start time")


class RestaurantForm(BasePostForm):
    """Form for restaurant special posts."""
    
    business_name = StringField(
        'Business Name',
        validators=[
            DataRequired(message="Please provide the restaurant name"),
            Length(min=2, max=150, message="Business name must be between 2 and 150 characters")
        ],
        render_kw={"placeholder": "Restaurant or business name"}
    )
    
    special_item = StringField(
        'Special Item/Dish',
        validators=[
            DataRequired(message="What's the special item or dish?"),
            Length(min=2, max=200, message="Item name must be between 2 and 200 characters")
        ],
        render_kw={"placeholder": "e.g., Fish & Chips, Happy Hour Special"}
    )
    
    price = DecimalField(
        'Price ($)',
        validators=[
            DataRequired(message="Please specify the price"),
            NumberRange(min=0.01, max=999.99, message="Price must be between $0.01 and $999.99")
        ],
        places=2,
        render_kw={"placeholder": "0.00", "step": "0.01"}
    )
    
    available_from = DateTimeField(
        'Available From',
        validators=[DataRequired(message="When is this special available from?")],
        format='%Y-%m-%d %H:%M'
    )
    
    available_until = DateTimeField(
        'Available Until',
        validators=[DataRequired(message="When does this special end?")],
        format='%Y-%m-%d %H:%M'
    )
    
    dietary_options = StringField(
        'Dietary Options',
        validators=[OptionalValidator(), Length(max=200)],
        render_kw={"placeholder": "e.g., Vegetarian, Vegan, Gluten-Free"}
    )
    
    def validate_available_until(self, field):
        """Ensure available until is after available from."""
        if self.available_from.data and field.data:
            if field.data <= self.available_from.data:
                raise ValidationError("End time must be after start time")


class HelpNeededForm(BasePostForm):
    """Form for help needed posts."""
    
    task_type = SelectField(
        'Type of Help',
        choices=[
            ('moving', '📦 Moving & Transportation'),
            ('repairs', '🔧 Repairs & Maintenance'),
            ('gardening', '🌱 Gardening & Yard Work'),
            ('pet_care', '🐕 Pet Care & Walking'),
            ('childcare', '👶 Childcare & Babysitting'),
            ('cleaning', '🧽 Cleaning & Organization'),
            ('technology', '💻 Technology Support'),
            ('errands', '🛒 Errands & Shopping'),
            ('other', '❓ Other')
        ],
        validators=[DataRequired(message="Please select the type of help needed")]
    )
    
    urgency_level = SelectField(
        'Urgency',
        choices=[
            ('low', '🟢 Low - Flexible timing'),
            ('medium', '🟡 Medium - Within a few days'),
            ('high', '🔴 High - ASAP/Today')
        ],
        validators=[DataRequired(message="Please indicate urgency level")],
        default='medium'
    )
    
    estimated_duration = SelectField(
        'Estimated Duration',
        choices=[
            ('30min', '⏱️ 30 minutes or less'),
            ('1hour', '🕐 About 1 hour'),
            ('2hours', '🕑 2-3 hours'),
            ('halfday', '🕐 Half day (4+ hours)'),
            ('fullday', '📅 Full day'),
            ('multiple', '📅 Multiple days')
        ],
        validators=[OptionalValidator()]
    )
    
    needed_by = DateTimeField(
        'Needed By',
        validators=[OptionalValidator()],
        format='%Y-%m-%d %H:%M',
        render_kw={"placeholder": "When do you need this completed?"}
    )
    
    compensation_offered = StringField(
        'Compensation Offered',
        validators=[OptionalValidator(), Length(max=200)],
        render_kw={"placeholder": "e.g., $20/hour, Free lunch, Return favor"}
    )
    
    requirements = TextAreaField(
        'Special Requirements',
        validators=[OptionalValidator(), Length(max=500)],
        render_kw={"placeholder": "Any special skills, tools, or requirements needed", "rows": 3}
    )


class ForSaleForm(BasePostForm):
    """Form for for sale posts."""
    
    item_name = StringField(
        'Item Name',
        validators=[
            DataRequired(message="What are you selling?"),
            Length(min=2, max=150, message="Item name must be between 2 and 150 characters")
        ],
        render_kw={"placeholder": "e.g., iPhone 13, Dining Table, Mountain Bike"}
    )
    
    price = DecimalField(
        'Asking Price ($)',
        validators=[
            DataRequired(message="Please specify your asking price"),
            NumberRange(min=0.01, max=99999.99, message="Price must be between $0.01 and $99,999.99")
        ],
        places=2,
        render_kw={"placeholder": "0.00", "step": "0.01"}
    )
    
    condition = SelectField(
        'Condition',
        choices=[
            ('new', '✨ New/Unused'),
            ('excellent', '💎 Excellent - Like new'),
            ('good', '👍 Good - Minor wear'),
            ('fair', '👌 Fair - Some wear'),
            ('poor', '⚠️ Poor - Needs work')
        ],
        validators=[DataRequired(message="Please specify item condition")],
        default='good'
    )
    
    category_type = SelectField(
        'Item Category',
        choices=[
            ('electronics', '📱 Electronics'),
            ('furniture', '🪑 Furniture'),
            ('clothing', '👕 Clothing & Accessories'),
            ('vehicles', '🚗 Vehicles & Parts'),
            ('books', '📚 Books & Media'),
            ('sports', '⚽ Sports & Recreation'),
            ('home', '🏠 Home & Garden'),
            ('tools', '🔧 Tools & Equipment'),
            ('toys', '🧸 Toys & Games'),
            ('other', '📦 Other')
        ],
        validators=[OptionalValidator()]
    )
    
    brand_model = StringField(
        'Brand/Model',
        validators=[OptionalValidator(), Length(max=100)],
        render_kw={"placeholder": "e.g., Apple iPhone 13, IKEA HEMNES"}
    )
    
    pickup_delivery = SelectField(
        'Pickup/Delivery',
        choices=[
            ('pickup', '📍 Pickup only'),
            ('delivery', '🚚 Delivery available'),
            ('both', '📍🚚 Both pickup and delivery'),
            ('shipping', '📦 Can ship')
        ],
        validators=[DataRequired(message="Please specify pickup/delivery options")],
        default='pickup'
    )
    
    negotiable = BooleanField(
        'Price Negotiable',
        default=True
    )
    
    accepts_trades = BooleanField(
        'Accept Trades/Exchanges',
        default=False
    )
    
    trade_preferences = StringField(
        'Trade Preferences',
        validators=[OptionalValidator(), Length(max=200)],
        render_kw={"placeholder": "What would you trade for?"}
    )


class ShopSaleForm(BasePostForm):
    """Form for shop sale posts."""
    
    business_name = StringField(
        'Business Name',
        validators=[
            DataRequired(message="Please provide the business name"),
            Length(min=2, max=150, message="Business name must be between 2 and 150 characters")
        ],
        render_kw={"placeholder": "Your business or store name"}
    )
    
    sale_type = SelectField(
        'Sale Type',
        choices=[
            ('percentage', '📊 Percentage off (e.g., 20% off)'),
            ('clearance', '🏷️ Clearance sale'),
            ('bogo', '🎯 Buy one get one'),
            ('seasonal', '🍂 Seasonal sale'),
            ('grand_opening', '🎉 Grand opening'),
            ('closing', '📢 Closing sale'),
            ('special_event', '🎪 Special event'),
            ('other', '🛍️ Other promotion')
        ],
        validators=[DataRequired(message="Please specify the type of sale")]
    )
    
    discount_details = StringField(
        'Discount Details',
        validators=[
            DataRequired(message="Please describe the discount or promotion"),
            Length(min=5, max=300, message="Discount details must be between 5 and 300 characters")
        ],
        render_kw={"placeholder": "e.g., 25% off all winter clothing, Buy 2 get 1 free"}
    )
    
    sale_start = DateTimeField(
        'Sale Starts',
        validators=[DataRequired(message="When does the sale start?")],
        format='%Y-%m-%d %H:%M'
    )
    
    sale_end = DateTimeField(
        'Sale Ends',
        validators=[DataRequired(message="When does the sale end?")],
        format='%Y-%m-%d %H:%M'
    )
    
    store_hours = StringField(
        'Store Hours During Sale',
        validators=[OptionalValidator(), Length(max=100)],
        render_kw={"placeholder": "e.g., Mon-Fri 9AM-6PM, Sat 9AM-5PM"}
    )
    
    featured_items = TextAreaField(
        'Featured Items',
        validators=[OptionalValidator(), Length(max=500)],
        render_kw={"placeholder": "Highlight specific items or categories on sale", "rows": 3}
    )
    
    special_features = StringField(
        'Special Features',
        validators=[OptionalValidator(), Length(max=200)],
        render_kw={"placeholder": "e.g., Free gift wrapping, Extended returns"}
    )
    
    def validate_sale_end(self, field):
        """Ensure sale end is after sale start."""
        if self.sale_start.data and field.data:
            if field.data <= self.sale_start.data:
                raise ValidationError("Sale end time must be after start time")


class BorrowForm(BasePostForm):
    """Form for borrow requests."""
    
    item_needed = StringField(
        'What do you need to borrow?',
        validators=[
            DataRequired(message="Please specify what you need to borrow"),
            Length(min=2, max=150, message="Item name must be between 2 and 150 characters")
        ],
        render_kw={"placeholder": "e.g., Ladder, Power Drill, Folding Chairs"}
    )
    
    item_category = SelectField(
        'Item Category',
        choices=[
            ('tools', '🔧 Tools & Equipment'),
            ('garden', '🌱 Garden & Yard'),
            ('kitchen', '🍳 Kitchen & Appliances'),
            ('events', '🎪 Event & Party Supplies'),
            ('sports', '⚽ Sports & Recreation'),
            ('books', '📚 Books & Media'),
            ('electronics', '📱 Electronics'),
            ('transport', '🚗 Transportation'),
            ('cleaning', '🧽 Cleaning Supplies'),
            ('other', '📦 Other')
        ],
        validators=[OptionalValidator()]
    )
    
    duration_needed = SelectField(
        'How long do you need it?',
        choices=[
            ('few_hours', '⏰ A few hours'),
            ('1_day', '📅 One day'),
            ('weekend', '📅 Weekend (2-3 days)'),
            ('1_week', '📅 One week'),
            ('2_weeks', '📅 Two weeks'),
            ('1_month', '📅 One month'),
            ('flexible', '🤝 Flexible/Negotiable')
        ],
        validators=[DataRequired(message="Please specify how long you need the item")],
        default='1_day'
    )
    
    needed_by = DateTimeField(
        'Needed By',
        validators=[OptionalValidator()],
        format='%Y-%m-%d',
        render_kw={"placeholder": "When do you need this by?"}
    )
    
    return_by = DateTimeField(
        'Will Return By',
        validators=[OptionalValidator()],
        format='%Y-%m-%d',
        render_kw={"placeholder": "When will you return it?"}
    )
    
    care_agreement = TextAreaField(
        'Care & Responsibility Agreement',
        validators=[OptionalValidator(), Length(max=400)],
        render_kw={"placeholder": "How will you take care of the item? Any insurance/deposit offered?", "rows": 3}
    )
    
    return_favor = StringField(
        'Can Offer in Return',
        validators=[OptionalValidator(), Length(max=200)],
        render_kw={"placeholder": "What can you offer in return? Skills, items, favors?"}
    )
    
    pickup_return_method = SelectField(
        'Pickup/Return Method',
        choices=[
            ('pickup', '🏃 I can pick up and return'),
            ('delivery', '🚚 Need delivery/pickup'),
            ('meet', '🤝 Meet halfway'),
            ('flexible', '💬 Let\'s discuss')
        ],
        validators=[DataRequired(message="How would you like to handle pickup/return?")],
        default='pickup'
    )


def get_form_for_category(category_name: str) -> type[BasePostForm]:
    """Get the appropriate form class for a category."""
    form_mapping = {
        'garage_sale': GarageSaleForm,
        'restaurant': RestaurantForm,
        'help_needed': HelpNeededForm,
        'for_sale': ForSaleForm,
        'shop_sale': ShopSaleForm,
        'borrow': BorrowForm,
        # Default categories to base form
        'community_event': BasePostForm,
        'lost_found': BasePostForm,
    }
    
    return form_mapping.get(category_name, BasePostForm)