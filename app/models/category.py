"""Post category model for organizing different types of posts."""
from typing import Optional
from sqlalchemy import Column, String, Text, Integer, Boolean
from app.models.base import BaseModel


class PostCategory(BaseModel):
    """Model for post categories (Garage Sale, Restaurant, Help Needed, etc.)."""
    
    __tablename__ = "post_categories"
    
    # Category identification
    name = Column(String(50), unique=True, nullable=False)  # e.g., "garage_sale"
    display_name = Column(String(100), nullable=False)  # e.g., "Garage Sale"
    description = Column(Text, nullable=True)
    emoji = Column(String(10), nullable=False)  # Unicode emoji
    color_hex = Column(String(7), nullable=False)  # Hex color code
    
    # Category configuration
    default_expiration_days = Column(Integer, nullable=False)
    max_photos = Column(Integer, default=5, nullable=False)
    requires_time = Column(Boolean, default=False, nullable=False)  # Needs start/end times
    requires_price = Column(Boolean, default=False, nullable=False)  # Needs pricing info
    allows_comments = Column(Boolean, default=True, nullable=False)
    
    # Display order and status
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    def __repr__(self) -> str:
        """String representation of category."""
        return f"<PostCategory {self.display_name}>"
    
    @classmethod
    def get_by_name(cls, name: str) -> Optional["PostCategory"]:
        """Get category by name."""
        return cls.query.filter_by(name=name, is_active=True).first()
    
    @classmethod
    def get_all_active(cls) -> list["PostCategory"]:
        """Get all active categories ordered by sort_order."""
        return cls.query.filter_by(is_active=True).order_by(cls.sort_order).all()
    
    @classmethod
    def create_default_categories(cls) -> list["PostCategory"]:
        """Create default post categories with configurable retention periods."""
        from flask import current_app
        
        # Get retention periods from configuration
        retention_config = current_app.config.get("POST_RETENTION_DAYS", {})
        
        categories = [
            {
                "name": "garage_sale",
                "display_name": "Garage Sale",
                "description": "Sell items from your home - furniture, clothes, books, toys, and household items",
                "emoji": "🏠",
                "color_hex": "#DC2626",  # red-600
                "default_expiration_days": retention_config.get("garage_sale", 3),
                "max_photos": 5,
                "requires_time": True,
                "requires_price": False,
                "sort_order": 1,
            },
            {
                "name": "restaurant",
                "display_name": "Restaurant Special",
                "description": "Share daily specials, menu items, and food deals from local restaurants",
                "emoji": "🍽️",
                "color_hex": "#2563EB",  # blue-600
                "default_expiration_days": retention_config.get("restaurant", 1),
                "max_photos": 3,
                "requires_time": True,
                "requires_price": True,
                "sort_order": 2,
            },
            {
                "name": "help_needed",
                "display_name": "Help Needed",
                "description": "Request assistance from neighbors - moving, repairs, pet sitting, etc.",
                "emoji": "❓",
                "color_hex": "#16A34A",  # green-600
                "default_expiration_days": retention_config.get("help_needed", 14),
                "max_photos": 2,
                "requires_time": True,
                "requires_price": False,
                "sort_order": 3,
            },
            {
                "name": "for_sale",
                "display_name": "For Sale",
                "description": "Sell individual items - electronics, furniture, vehicles, collectibles",
                "emoji": "💰",
                "color_hex": "#EA580C",  # orange-600
                "default_expiration_days": retention_config.get("for_sale", 30),
                "max_photos": 5,
                "requires_time": False,
                "requires_price": True,
                "sort_order": 4,
            },
            {
                "name": "shop_sale",
                "display_name": "Shop Sale",
                "description": "Business promotions, sales events, and special offers from local shops",
                "emoji": "🛍️",
                "color_hex": "#9333EA",  # purple-600
                "default_expiration_days": retention_config.get("shop_sale", 7),
                "max_photos": 4,
                "requires_time": True,
                "requires_price": False,
                "sort_order": 5,
            },
            {
                "name": "borrow",
                "display_name": "Borrow",
                "description": "Borrow tools, equipment, or items from neighbors - lawn mowers, books, etc.",
                "emoji": "📚",
                "color_hex": "#DB2777",  # pink-600
                "default_expiration_days": retention_config.get("borrow", 60),
                "max_photos": 2,
                "requires_time": False,
                "requires_price": False,
                "sort_order": 6,
            },
            # Additional recommended categories
            {
                "name": "community_event",
                "display_name": "Community Event",
                "description": "Neighborhood gatherings, block parties, festivals, and community meetings",
                "emoji": "🎉",
                "color_hex": "#F59E0B",  # amber-500
                "default_expiration_days": retention_config.get("community_event", 7),
                "max_photos": 4,
                "requires_time": True,
                "requires_price": False,
                "sort_order": 7,
            },
            {
                "name": "lost_found",
                "display_name": "Lost & Found",
                "description": "Help reunite lost pets, keys, wallets, and other items with their owners",
                "emoji": "🔍",
                "color_hex": "#06B6D4",  # cyan-500
                "default_expiration_days": retention_config.get("lost_found", 30),
                "max_photos": 3,
                "requires_time": False,
                "requires_price": False,
                "sort_order": 8,
            },
        ]
        
        created_categories = []
        for category_data in categories:
            existing = cls.get_by_name(category_data["name"])
            if not existing:
                category = cls.create(**category_data)
                created_categories.append(category)
            else:
                created_categories.append(existing)
        
        return created_categories