# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Mapid is a location-based community platform where users can send geospatial messages about local events and opportunities. The platform supports various message types including garage sales, restaurant specials, help requests, items for sale, shop events, and borrowing requests. All messages are geospatially tagged and have retention periods based on their type.

## Technology Stack

### Core Technologies
- **Python** - Primary programming language (3.11+)
- **uv** - Ultra-fast Python package installer and resolver
- **pyproject.toml** - Modern Python project configuration
- **Docker** - Containerization of our application for deployment to production

### Backend Framework
- **Flask** - Lightweight and flexible web framework for Python
- **Flask-SQLAlchemy** - SQLAlchemy integration for Flask
- **Flask-Login** - User session management for Flask
- **Flask-WTF** - Form handling and CSRF protection
- **Flask-Migrate** - Database migration handling
- **Flask-CORS** - Cross-Origin Resource Sharing support

### Database & Geospatial
- **PostgreSQL** - Primary database with ACID compliance
- **PostGIS** - Geospatial extension for PostgreSQL
- **GeoAlchemy2** - Geospatial ORM extensions for SQLAlchemy
- **Alembic** - Database migration tool

### Authentication & Security
- **Google OAuth 2.0** - Primary authentication method via Authlib
- **Authlib** - OAuth 2.0 and OpenID Connect library
- **Flask-Login** - Session management
- **CSRF Protection** - Built into Flask-WTF

### Cloud Services
- **AWS S3** - Image storage and static asset hosting
- **AWS Rekognition** - Content moderation for images
- **Boto3** - AWS SDK for Python

### Frontend Technologies
- **HTML5/CSS3** - Standard web technologies
- **Tailwind CSS** - Utility-first CSS framework
- **JavaScript (ES6+)** - Client-side interactivity
- **Leaflet.js** - Interactive maps
- **OpenStreetMap** - Map tile provider

### Content Processing
- **Pillow (PIL)** - Image processing and manipulation
- **better-profanity** - Text content moderation
- **WTForms** - Form validation and rendering

### Development Tools
- **Sentry** - Error tracking and performance monitoring
- **Python-dotenv** - Environment variable management
- **Requests** - HTTP library for API calls

## Architecture Overview

### Application Structure
```
mapid/
├── app/                    # Main application package
│   ├── __init__.py        # Application factory
│   ├── config.py          # Configuration management
│   ├── extensions.py      # Flask extension initialization
│   ├── models/            # Database models
│   │   ├── base.py       # Base model classes
│   │   ├── user.py       # User model
│   │   ├── post.py       # Post model
│   │   ├── category.py   # Post category model
│   │   └── post_image.py # Image model
│   ├── routes/            # URL routes and views
│   │   ├── main.py       # Main pages
│   │   ├── auth.py       # Authentication
│   │   ├── posts.py      # Post management
│   │   ├── maps.py       # Map interface
│   │   └── api/          # API endpoints
│   ├── services/          # Business logic services
│   │   ├── oauth.py      # OAuth handling
│   │   ├── location.py   # Geospatial services
│   │   ├── s3_upload.py  # Image upload service
│   │   ├── moderation.py # Content moderation
│   │   └── post_service.py # Post business logic
│   ├── forms/             # WTForms form definitions
│   ├── templates/         # Jinja2 HTML templates
│   ├── static/            # Static assets (CSS, JS, images)
│   └── cli/               # CLI commands
├── migrations/            # Database migrations
├── tests/                 # Test suite
├── docs/                  # Documentation
├── app.py                 # Application entry point
├── pyproject.toml         # Project configuration
└── uv.lock               # Dependency lock file
```

### Key Design Patterns

1. **Application Factory Pattern** - Flask app created via factory function
2. **Blueprint Architecture** - Modular route organization
3. **Service Layer** - Business logic separated from routes
4. **Repository Pattern** - Database access abstraction
5. **Configuration Classes** - Environment-specific settings

## Database Schema

### Core Models

#### User Model
- OAuth-based authentication (Google)
- Location preferences and privacy settings
- Reputation system
- Soft deletion support

#### Post Model
- GeoDjango-style location fields using PostGIS
- Category-specific JSON data storage
- Expiration and lifecycle management
- Image relationships

#### PostCategory Model
- Predefined post types with specific behaviors
- Retention periods and photo limits
- Color coding and emoji representation

#### PostImage Model
- S3 storage integration
- Multiple image sizes (thumbnail, medium, full)
- Content moderation status
- EXIF data stripping

### Geospatial Features
- PostGIS geometry columns for precise location storage
- Distance-based queries and indexing
- Address geocoding and reverse geocoding
- Location privacy with coordinate fuzzing

## Development Guidelines

### Code Style
- Follow PEP 8 for Python code
- Use type hints where appropriate
- Comprehensive docstrings for public methods
- Meaningful variable and function names

### Testing
- Unit tests for models and services
- Integration tests for routes
- Test database with PostGIS support
- Mock external services (AWS, OAuth)

### Security Considerations
- Input validation on all user data
- SQL injection prevention via ORM
- XSS protection through template escaping
- CSRF tokens on all forms
- Rate limiting on API endpoints
- Content moderation for text and images

### Performance
- Database query optimization
- Geospatial indexing for location queries
- Image optimization and CDN usage
- Caching for frequently accessed data

## Environment Setup

### Required Environment Variables
```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost/mapid

# Flask Configuration
SECRET_KEY=your-secret-key-here
FLASK_ENV=development  # or production

# Google OAuth
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

# AWS Services
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
AWS_DEFAULT_REGION=us-west-2
S3_BUCKET_NAME=your-s3-bucket

# Optional Services
SENTRY_DSN=your-sentry-dsn  # Error tracking
REDIS_URL=redis://localhost:6379  # Caching
```

### Development Setup
1. Install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. Create virtual environment: `uv venv`
3. Activate environment: `source .venv/bin/activate`
4. Install dependencies: `uv sync`
5. Set up PostgreSQL with PostGIS
6. Copy `.env.example` to `.env` and configure
7. Run migrations: `flask db upgrade`
8. Start development server: `python app.py`

## API Design

### RESTful Endpoints
- `/api/posts` - Post CRUD operations
- `/api/images` - Image upload and management
- `/api/maps` - Geospatial queries
- `/api/auth` - Authentication endpoints

### Response Format
```json
{
  "success": true,
  "data": {...},
  "message": "Optional message",
  "errors": []  // Only on failure
}
```

### Error Handling
- Consistent error response format
- Appropriate HTTP status codes
- Detailed error messages for development
- Generic messages for production

## Deployment

### Production Requirements
- PostgreSQL 14+ with PostGIS 3+
- Python 3.11+
- Redis for caching (optional)
- AWS S3 bucket for images
- SSL certificate

### Environment-Specific Configurations
- Development: SQLite with SpatiaLite (for quick setup)
- Staging: PostgreSQL with PostGIS
- Production: PostgreSQL with PostGIS + Redis

### Container Deployment
- Docker support for consistent environments
- Multi-stage builds for optimization
- Health check endpoints
- Graceful shutdown handling

## Monitoring & Observability

### Logging
- Structured logging with JSON format
- Different log levels per environment
- Request/response logging
- Error tracking with Sentry

### Metrics
- Application performance monitoring
- Database query performance
- S3 upload success rates
- User engagement metrics

### Health Checks
- Database connectivity
- S3 service availability
- OAuth service status
- Memory and CPU usage

## Common Tasks

### Adding New Post Categories
1. Update `PostCategory.create_default_categories()`
2. Create new form class in `forms/posts.py`
3. Update `get_form_for_category()` mapping
4. Add category-specific template sections
5. Run migration to add new category

### Database Migrations
```bash
# Create migration
flask db migrate -m "Description of changes"

# Review generated migration
# Edit migration file if needed

# Apply migration
flask db upgrade
```

### Adding New API Endpoints
1. Create route in appropriate blueprint
2. Add input validation
3. Implement business logic in service layer
4. Add proper error handling
5. Write tests
6. Update API documentation

### Image Processing
- All images automatically resized to multiple sizes
- EXIF data stripped for privacy
- Content moderation via AWS Rekognition
- Asynchronous processing for large images

## Troubleshooting

### Common Issues
1. **PostGIS Extension Missing**: Install PostGIS extension in PostgreSQL
2. **OAuth Redirect Issues**: Check OAuth app configuration
3. **S3 Upload Failures**: Verify AWS credentials and bucket permissions
4. **Map Loading Issues**: Check Leaflet.js and OpenStreetMap connectivity
5. **Migration Conflicts**: Resolve conflicts manually or reset migration

### Debug Mode
- Set `FLASK_ENV=development` for detailed error pages
- Use Flask-DebugToolbar for SQL query analysis
- Enable verbose logging for troubleshooting

### Performance Issues
- Use `EXPLAIN ANALYZE` for slow database queries
- Monitor S3 upload times and sizes
- Check Redis cache hit rates
- Profile Python code with cProfile

## Security Best Practices

### Authentication
- OAuth 2.0 with Google (no password storage)
- Session management with secure cookies
- CSRF protection on all forms
- Rate limiting on authentication endpoints

### Data Protection
- Input sanitization and validation
- SQL injection prevention via ORM
- XSS protection through template escaping
- Location data privacy controls

### Content Moderation
- Automated text filtering for profanity
- Image content scanning with AWS Rekognition
- User reporting and admin review systems
- Automated post expiration

### Infrastructure Security
- HTTPS enforcement in production
- Secure environment variable management
- Regular dependency updates
- AWS IAM least-privilege access

## Contributing

### Code Review Process
1. Create feature branch from main
2. Implement changes with tests
3. Run test suite and linting
4. Create pull request with description
5. Code review and feedback
6. Merge after approval

### Testing Requirements
- Unit tests for new functionality
- Integration tests for API endpoints
- Manual testing of UI changes
- Performance testing for database queries

### Documentation Updates
- Update this file for architectural changes
- Add docstrings for new public methods
- Update API documentation
- Create user documentation for new features

This documentation should be updated as the project evolves. Last updated: August 2024.