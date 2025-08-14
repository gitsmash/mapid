"""Application configuration."""
import os
from typing import Type
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Base configuration class."""

    # Flask core configuration
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-secret-key-change-in-production"
    
    # Database configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or \
        "postgresql://mapid_user:mapid_password@localhost:5432/mapid_dev"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }
    
    # Application configuration
    APP_NAME = os.environ.get("APP_NAME", "Mapid")
    APP_VERSION = os.environ.get("APP_VERSION", "0.1.0")
    APP_URL = os.environ.get("APP_URL", "http://localhost:8000")
    # Calculate max content length based on image configuration 
    # Allow for multiple images + form data + buffer
    _max_image_bytes = int(os.environ.get("MAX_IMAGE_SIZE_MB", "10")) * 1024 * 1024
    _max_images = int(os.environ.get("MAX_IMAGES_PER_POST", "5"))
    _form_buffer = 2 * 1024 * 1024  # 2MB buffer for form data
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", str(_max_image_bytes * _max_images + _form_buffer)))
    
    # Google OAuth configuration
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
    GOOGLE_DISCOVERY_URL = os.environ.get(
        "GOOGLE_DISCOVERY_URL",
        "https://accounts.google.com/.well-known/openid_configuration"
    )
    
    # AWS S3 configuration
    AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
    AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")
    S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME", "mapid-uploads")
    S3_BUCKET_URL = os.environ.get("S3_BUCKET_URL")
    
    # Image upload configuration
    MAX_IMAGE_SIZE_MB = int(os.environ.get("MAX_IMAGE_SIZE_MB", "10"))  # 10MB per image
    MAX_IMAGES_PER_POST = int(os.environ.get("MAX_IMAGES_PER_POST", "5"))  # 5 images max
    ALLOWED_IMAGE_EXTENSIONS = os.environ.get(
        "ALLOWED_IMAGE_EXTENSIONS", 
        "jpg,jpeg,png,gif,webp"
    ).split(",")
    
    # Image processing configuration
    IMAGE_THUMBNAIL_SIZE = tuple(map(int, os.environ.get("IMAGE_THUMBNAIL_SIZE", "150,150").split(",")))
    IMAGE_MEDIUM_SIZE = tuple(map(int, os.environ.get("IMAGE_MEDIUM_SIZE", "500,500").split(",")))
    IMAGE_FULL_SIZE = tuple(map(int, os.environ.get("IMAGE_FULL_SIZE", "1200,1200").split(",")))
    IMAGE_QUALITY = int(os.environ.get("IMAGE_QUALITY", "85"))  # JPEG/WebP quality
    
    # Image storage and organization
    S3_IMAGES_PREFIX = os.environ.get("S3_IMAGES_PREFIX", "posts")
    IMAGE_CDN_DOMAIN = os.environ.get("IMAGE_CDN_DOMAIN")  # Optional CloudFront domain
    STRIP_EXIF_DATA = os.environ.get("STRIP_EXIF_DATA", "true").lower() == "true"
    
    # Redis configuration
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    
    # Geospatial configuration
    DEFAULT_SRID = int(os.environ.get("DEFAULT_SRID", "4326"))  # WGS84
    NEIGHBORHOOD_RADIUS_METERS = int(os.environ.get("NEIGHBORHOOD_RADIUS_METERS", "3218"))  # 2 miles
    MAX_POSTS_PER_USER_PER_DAY = int(os.environ.get("MAX_POSTS_PER_USER_PER_DAY", "10"))
    
    # Location services configuration
    GEOCODER_USER_AGENT = os.environ.get("GEOCODER_USER_AGENT", "mapid-app/1.0")
    MAX_NEIGHBORHOOD_RADIUS_MILES = float(os.environ.get("MAX_NEIGHBORHOOD_RADIUS_MILES", "2.0"))
    LOCATION_PRIVACY_FUZZ_METERS = int(os.environ.get("LOCATION_PRIVACY_FUZZ_METERS", "100"))
    GEOCODING_TIMEOUT_SECONDS = int(os.environ.get("GEOCODING_TIMEOUT_SECONDS", "10"))
    GEOCODING_MAX_RETRIES = int(os.environ.get("GEOCODING_MAX_RETRIES", "3"))
    
    # Post retention periods (in days) - configurable per category
    POST_RETENTION_DAYS = {
        "garage_sale": int(os.environ.get("RETENTION_GARAGE_SALE", "3")),  # 3 days
        "restaurant": int(os.environ.get("RETENTION_RESTAURANT", "1")),    # 1 day
        "help_needed": int(os.environ.get("RETENTION_HELP_NEEDED", "14")), # 2 weeks
        "for_sale": int(os.environ.get("RETENTION_FOR_SALE", "30")),       # 1 month
        "shop_sale": int(os.environ.get("RETENTION_SHOP_SALE", "7")),      # 1 week
        "borrow": int(os.environ.get("RETENTION_BORROW", "60")),           # 2 months
        "community_event": int(os.environ.get("RETENTION_COMMUNITY_EVENT", "7")),  # 1 week
        "lost_found": int(os.environ.get("RETENTION_LOST_FOUND", "30")),   # 1 month
    }
    
    # Content moderation configuration
    PROFANITY_FILTER_ENABLED = os.environ.get("PROFANITY_FILTER_ENABLED", "true").lower() == "true"
    IMAGE_MODERATION_ENABLED = os.environ.get("IMAGE_MODERATION_ENABLED", "true").lower() == "true"
    PROFANITY_ACTION = os.environ.get("PROFANITY_ACTION", "flag")  # flag, block, or replace
    
    # Content moderation services (AWS Rekognition for images, profanity-check for text)
    AWS_REKOGNITION_ENABLED = os.environ.get("AWS_REKOGNITION_ENABLED", "true").lower() == "true"
    MODERATION_CONFIDENCE_THRESHOLD = float(os.environ.get("MODERATION_CONFIDENCE_THRESHOLD", "70.0"))
    
    # Pagination
    POSTS_PER_PAGE = int(os.environ.get("POSTS_PER_PAGE", "20"))
    COMMENTS_PER_PAGE = int(os.environ.get("COMMENTS_PER_PAGE", "50"))
    
    # Rate limiting
    RATELIMIT_STORAGE_URL = os.environ.get("RATELIMIT_STORAGE_URL", "redis://localhost:6379/1")
    RATELIMIT_DEFAULT = os.environ.get("RATELIMIT_DEFAULT", "1000 per hour")
    
    # WTF Forms
    WTF_CSRF_ENABLED = os.environ.get("WTF_CSRF_ENABLED", "true").lower() == "true"
    WTF_CSRF_TIME_LIMIT = 3600  # 1 hour
    
    # Email configuration (optional)
    MAIL_SERVER = os.environ.get("MAIL_SERVER")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    
    # Logging
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    LOG_FILE = os.environ.get("LOG_FILE", "logs/mapid.log")


class DevelopmentConfig(Config):
    """Development configuration."""
    
    DEBUG = True
    SQLALCHEMY_ECHO = os.environ.get("SQLALCHEMY_ECHO", "false").lower() == "true"
    EXPLAIN_TEMPLATE_LOADING = os.environ.get("EXPLAIN_TEMPLATE_LOADING", "false").lower() == "true"


class ProductionConfig(Config):
    """Production configuration."""
    
    DEBUG = False
    # Override any development settings for production
    SQLALCHEMY_ECHO = False
    EXPLAIN_TEMPLATE_LOADING = False


class TestingConfig(Config):
    """Testing configuration."""
    
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL_TEST") or \
        "postgresql://mapid_user:mapid_password@localhost:5432/mapid_test"
    WTF_CSRF_ENABLED = False  # Disable CSRF for easier testing
    SECRET_KEY = "test-secret-key"


# Configuration dictionary
config: dict[str, Type[Config]] = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}