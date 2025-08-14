# Image Upload Implementation

## Overview

The Mapid application implements a comprehensive image upload system that integrates with AWS S3 for storage, includes automatic image processing (resizing, optimization), content moderation via AWS Rekognition, and provides a seamless user experience for post creation.

## Architecture

### Components

1. **Frontend Image Upload Interface** (`app/templates/posts/create_form.html`)
2. **Backend API Endpoints** (`app/routes/api/images.py`)
3. **S3 Upload Service** (`app/services/s3_upload.py`)
4. **Content Moderation Service** (`app/services/moderation.py`)
5. **Database Models** (`app/models/post_image.py`)

### Flow

```
User selects images → Frontend validation → API upload → S3 processing → Content moderation → Database storage → Post association
```

## Frontend Implementation

### File Selection and Preview

The image upload interface provides:
- Drag-and-drop functionality
- Multiple file selection
- Live preview with thumbnails
- Progress indicators
- Error handling and validation

### JavaScript Features

```javascript
// Key features implemented:
- File type validation (JPEG, PNG, GIF, WebP)
- File size limits (10MB per file)
- Preview generation with File API
- Drag-and-drop upload zones
- Progress tracking during uploads
- Error message display
- Image reordering functionality
```

## Backend API

### Endpoints

#### `POST /api/images/upload`
Handles individual image uploads with validation and processing.

**Request Format:**
```
Content-Type: multipart/form-data
Body: image file + metadata
```

**Response Format:**
```json
{
  "success": true,
  "image": {
    "id": 123,
    "filename": "processed_image.jpg",
    "url": "https://s3.../thumbnail.jpg",
    "size": 1024768,
    "width": 800,
    "height": 600,
    "moderation_status": "approved"
  }
}
```

#### `DELETE /api/images/{id}`
Removes an uploaded image from both S3 and database.

#### `POST /api/images/{id}/set-primary`
Sets an image as the primary image for its associated post.

#### `POST /api/images/reorder`
Updates the display order of images for a post.

### Validation

The API performs comprehensive validation:

```python
# File validation checks:
- Allowed file extensions (.jpg, .jpeg, .png, .gif, .webp)
- File size limits (10MB max)
- Image format verification
- MIME type validation
- Post ownership verification
- Category-specific photo limits
```

## S3 Integration

### S3UploadService Features

The `S3UploadService` class provides:

1. **Multi-size Image Processing**
   - Thumbnail (150x150px)
   - Medium (800x600px) 
   - Full size (max 1920x1080px)
   - WebP conversion for optimization

2. **Image Optimization**
   - EXIF data stripping for privacy
   - Quality optimization
   - Progressive JPEG encoding
   - Format conversion when beneficial

3. **Security Features**
   - Secure filename generation (UUID-based)
   - Content-type validation
   - Path traversal prevention
   - Access control via S3 policies

### S3 Configuration

```python
# Required S3 setup:
S3_BUCKET_NAME = "your-mapid-images"
S3_REGION = "us-west-2"
S3_ACCESS_KEY_ID = "..."
S3_SECRET_ACCESS_KEY = "..."

# Bucket structure:
/images/
  /thumbnails/
  /medium/
  /full/
```

### Upload Process

```python
def upload_image(self, file_storage, category=None):
    # 1. Validate file
    validation_result = self._validate_image_file(file_storage)
    
    # 2. Process image (resize, optimize)
    processed_images = self._process_image_sizes(file_storage)
    
    # 3. Upload to S3
    s3_keys = self._upload_to_s3(processed_images)
    
    # 4. Content moderation
    moderation_result = self._moderate_content(s3_keys['full'])
    
    # 5. Return metadata
    return {
        'keys': s3_keys,
        'moderation': moderation_result,
        'metadata': image_metadata
    }
```

## Content Moderation

### AWS Rekognition Integration

The system uses AWS Rekognition to automatically detect inappropriate content:

```python
# Moderation checks:
- Explicit content detection
- Suggestive content detection  
- Violence detection
- Graphic content detection
- Drugs and alcohol detection
- Hate symbols detection
```

### Moderation Workflow

1. **Upload → Immediate Processing**: Images are sent to Rekognition immediately after S3 upload
2. **Confidence Scoring**: Rekognition returns confidence scores for various content types
3. **Threshold-based Decisions**: Configurable thresholds determine auto-approval/rejection
4. **Manual Review Queue**: Borderline content is flagged for human review
5. **Status Updates**: Image moderation status is updated in real-time

### Moderation Statuses

```python
class ModerationStatus(enum.Enum):
    PENDING = "pending"      # Awaiting moderation
    APPROVED = "approved"    # Safe for display
    FLAGGED = "flagged"      # Requires manual review
    REJECTED = "rejected"    # Inappropriate content
```

## Database Schema

### PostImage Model

```python
class PostImage(BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'))
    
    # File metadata
    original_filename = db.Column(db.String(255))
    file_size = db.Column(db.Integer)
    mime_type = db.Column(db.String(100))
    
    # S3 storage
    s3_key_thumbnail = db.Column(db.String(255))
    s3_key_medium = db.Column(db.String(255))
    s3_key_full = db.Column(db.String(255))
    
    # URLs (signed or public)
    url_thumbnail = db.Column(db.String(500))
    url_medium = db.Column(db.String(500))
    url_full = db.Column(db.String(500))
    
    # Image properties
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    
    # Display settings
    is_primary = db.Column(db.Boolean, default=False)
    display_order = db.Column(db.Integer, default=0)
    
    # Moderation
    moderation_status = db.Column(db.Enum(ModerationStatus))
    moderation_details = db.Column(db.JSON)
```

## Error Handling

### Frontend Error Handling

```javascript
// Client-side error scenarios:
- File too large
- Invalid file type
- Network timeouts
- Server errors
- Upload cancellation
```

### Backend Error Handling

```python
# Server-side error scenarios:
- S3 connection failures
- Image processing errors
- Moderation service unavailable
- Database constraint violations
- Invalid image formats
```

### Error Response Format

```json
{
  "success": false,
  "error": {
    "code": "FILE_TOO_LARGE",
    "message": "File size exceeds 10MB limit",
    "details": {
      "max_size": 10485760,
      "actual_size": 15728640
    }
  }
}
```

## Performance Considerations

### Optimization Strategies

1. **Async Processing**: Large images processed in background jobs
2. **CDN Integration**: S3 + CloudFront for global content delivery
3. **Progressive Loading**: Thumbnails load first, full images on demand
4. **Client-side Resizing**: Reduce upload bandwidth with browser-based resizing
5. **Batch Operations**: Multiple images uploaded in parallel

### Monitoring

- Upload success/failure rates
- Average upload times
- S3 storage costs
- Moderation accuracy metrics
- User experience metrics (time to first preview)

## Security

### Security Measures

1. **Authentication**: Only authenticated users can upload images
2. **Authorization**: Users can only modify their own images
3. **File Validation**: Strict validation of file types and content
4. **Filename Security**: No user-controlled filenames in S3
5. **Content Scanning**: All images scanned for malicious content
6. **Rate Limiting**: Upload rate limits to prevent abuse
7. **EXIF Stripping**: Remove potentially sensitive metadata

### Privacy

- EXIF data (including GPS coordinates) stripped from all images
- User can delete images at any time
- Images associated with expired posts are automatically removed
- No facial recognition or personal identification

## Configuration

### Environment Variables

```bash
# AWS Configuration
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_DEFAULT_REGION=us-west-2
S3_BUCKET_NAME=mapid-images-prod

# Upload Settings
MAX_CONTENT_LENGTH=10485760  # 10MB
ALLOWED_IMAGE_EXTENSIONS=jpg,jpeg,png,gif,webp

# Moderation Settings
ENABLE_CONTENT_MODERATION=true
MODERATION_CONFIDENCE_THRESHOLD=80
AUTO_REJECT_THRESHOLD=95
```

### Category-Specific Settings

```python
# Different post categories have different image requirements:
CATEGORY_PHOTO_LIMITS = {
    'garage_sale': 8,      # Multiple items to show
    'restaurant': 3,       # Food photos
    'help_needed': 2,      # Before/after or context
    'for_sale': 5,         # Multiple angles
    'shop_sale': 6,        # Products and storefront
    'borrow': 3,           # Item condition
    'community_event': 4,  # Event photos
    'lost_found': 3        # Clear identification
}
```

## Testing

### Test Coverage

The image upload system includes comprehensive tests:

1. **Unit Tests**: Individual component testing
2. **Integration Tests**: End-to-end upload workflows
3. **Load Tests**: Multiple concurrent uploads
4. **Security Tests**: Malicious file upload attempts
5. **Error Scenario Tests**: Network failures, service outages

### Test Files

- `test_image_upload.py`: Core upload functionality
- `tests/test_services/test_s3_upload.py`: S3 service tests
- `tests/test_routes/test_api/test_images.py`: API endpoint tests
- `tests/integration/test_image_workflow.py`: End-to-end tests

## Deployment

### Production Checklist

- [ ] S3 bucket configured with proper permissions
- [ ] AWS Rekognition service enabled
- [ ] CDN (CloudFront) configured for image delivery
- [ ] Environment variables set correctly
- [ ] Image processing background jobs configured
- [ ] Monitoring and alerting set up
- [ ] Backup strategy for S3 content

### Scaling Considerations

For high-traffic scenarios:
1. **Background Processing**: Move image processing to queue system
2. **Multiple S3 Buckets**: Distribute load across regions
3. **Caching Layer**: Redis for frequently accessed image metadata
4. **Client-side Processing**: Browser-based image optimization
5. **Progressive Web App**: Offline upload capabilities

## Future Enhancements

### Planned Features

1. **AI-Powered Tagging**: Automatic image tagging and categorization
2. **Image Compression**: Advanced compression algorithms
3. **Video Support**: Short video clips for certain post types
4. **Social Features**: Image likes, comments, and sharing
5. **Advanced Moderation**: Custom moderation rules per community
6. **Accessibility**: Alt-text generation for screen readers
7. **Analytics**: Image engagement and performance metrics

This implementation provides a robust, scalable, and secure image upload system that enhances the user experience while maintaining high standards for content quality and safety.