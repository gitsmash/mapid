"""S3 upload service with image processing and content moderation."""
import os
import uuid
import logging
from io import BytesIO
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta

import boto3
from botocore.exceptions import ClientError, BotoCoreError
from PIL import Image, ImageOps
from PIL.ExifTags import TAGS
from werkzeug.datastructures import FileStorage
from flask import current_app

from app.services.moderation import ContentModerationService

logger = logging.getLogger(__name__)


class S3UploadError(Exception):
    """Custom exception for S3 upload errors."""
    pass


class ImageProcessingError(Exception):
    """Custom exception for image processing errors."""
    pass


class S3UploadService:
    """Service for handling secure S3 uploads with image processing."""
    
    # Supported image formats
    SUPPORTED_FORMATS = {'JPEG', 'PNG', 'GIF', 'WEBP'}
    SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    
    # Image size configurations
    SIZE_CONFIGS = {
        'thumbnail': (150, 150),
        'medium': (500, 500),
        'full': (1200, 1200)
    }
    
    def __init__(self):
        """Initialize S3 upload service."""
        self.s3_client = None
        self.bucket_name = current_app.config.get('S3_BUCKET_NAME')
        self.aws_region = current_app.config.get('AWS_REGION', 'us-west-2')
        self.max_file_size = current_app.config.get('MAX_CONTENT_LENGTH', 16777216)  # 16MB
        self.moderation_service = ContentModerationService()
        
        # Initialize S3 client
        self._initialize_s3_client()
        
        # Validate configuration
        self._validate_configuration()
    
    def _initialize_s3_client(self) -> None:
        """Initialize boto3 S3 client with proper credentials."""
        try:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=current_app.config.get('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=current_app.config.get('AWS_SECRET_ACCESS_KEY'),
                region_name=self.aws_region
            )
            logger.info("S3 client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {e}")
            raise S3UploadError(f"S3 client initialization failed: {e}")
    
    def _validate_configuration(self) -> None:
        """Validate required configuration values."""
        required_configs = [
            'S3_BUCKET_NAME',
            'AWS_ACCESS_KEY_ID', 
            'AWS_SECRET_ACCESS_KEY'
        ]
        
        missing_configs = []
        for config in required_configs:
            if not current_app.config.get(config):
                missing_configs.append(config)
        
        if missing_configs:
            raise S3UploadError(f"Missing required S3 configuration: {missing_configs}")
        
        if not self.bucket_name:
            raise S3UploadError("S3_BUCKET_NAME not configured")
    
    def _generate_unique_filename(self, original_filename: str, prefix: str = '') -> str:
        """Generate unique filename with collision prevention."""
        # Extract file extension
        _, ext = os.path.splitext(original_filename.lower())
        
        # Generate unique identifier
        unique_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        
        # Construct unique filename
        if prefix:
            filename = f"{prefix}/{timestamp}_{unique_id}{ext}"
        else:
            filename = f"{timestamp}_{unique_id}{ext}"
        
        return filename
    
    def _validate_image_file(self, file: FileStorage) -> None:
        """Validate image file format, size, and integrity."""
        # Check file extension
        if not file.filename:
            raise ImageProcessingError("No filename provided")
        
        _, ext = os.path.splitext(file.filename.lower())
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise ImageProcessingError(
                f"Unsupported file format. Supported: {', '.join(self.SUPPORTED_EXTENSIONS)}"
            )
        
        # Check file size
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > self.max_file_size:
            max_mb = self.max_file_size / (1024 * 1024)
            current_mb = file_size / (1024 * 1024)
            raise ImageProcessingError(
                f"File too large: {current_mb:.1f}MB. Maximum: {max_mb:.1f}MB"
            )
        
        # Check if file is empty
        if file_size == 0:
            raise ImageProcessingError("Empty file provided")
        
        # Validate image integrity by trying to open it
        try:
            file_content = file.read()
            file.seek(0)
            
            with Image.open(BytesIO(file_content)) as img:
                img.verify()  # Verify image integrity
                
        except Exception as e:
            raise ImageProcessingError(f"Invalid image file: {e}")
    
    def _strip_exif_data(self, image: Image.Image) -> Image.Image:
        """Strip EXIF data from image for privacy protection."""
        try:
            # Create new image without EXIF data
            data = list(image.getdata())
            image_without_exif = Image.new(image.mode, image.size)
            image_without_exif.putdata(data)
            return image_without_exif
        except Exception as e:
            logger.warning(f"Failed to strip EXIF data: {e}")
            return image
    
    def _optimize_image(self, image: Image.Image, size: Tuple[int, int], 
                       quality: int = 85) -> Image.Image:
        """Resize and optimize image maintaining aspect ratio."""
        try:
            # Convert to RGB if necessary (for JPEG compatibility)
            if image.mode in ('RGBA', 'LA', 'P'):
                # Create white background for transparency
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                image = background
            elif image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Apply orientation from EXIF data
            image = ImageOps.exif_transpose(image)
            
            # Resize maintaining aspect ratio
            image.thumbnail(size, Image.Resampling.LANCZOS)
            
            return image
        except Exception as e:
            logger.error(f"Failed to optimize image: {e}")
            raise ImageProcessingError(f"Image optimization failed: {e}")
    
    def _process_image_sizes(self, file_content: bytes, 
                           original_filename: str) -> Dict[str, bytes]:
        """Process image into multiple sizes (thumbnail, medium, full)."""
        processed_images = {}
        
        try:
            with Image.open(BytesIO(file_content)) as original_image:
                # Strip EXIF data for privacy
                clean_image = self._strip_exif_data(original_image)
                
                # Process each size configuration
                for size_name, dimensions in self.SIZE_CONFIGS.items():
                    # Create a copy for processing
                    image_copy = clean_image.copy()
                    
                    # Optimize for this size
                    optimized_image = self._optimize_image(image_copy, dimensions)
                    
                    # Save to bytes
                    output = BytesIO()
                    
                    # Use WebP for better compression, fallback to JPEG
                    try:
                        optimized_image.save(output, format='WEBP', quality=85, optimize=True)
                        output.seek(0)
                    except Exception:
                        output = BytesIO()
                        optimized_image.save(output, format='JPEG', quality=85, optimize=True)
                        output.seek(0)
                    
                    processed_images[size_name] = output.getvalue()
                    
        except Exception as e:
            logger.error(f"Failed to process image sizes: {e}")
            raise ImageProcessingError(f"Image processing failed: {e}")
        
        return processed_images
    
    def _upload_to_s3(self, file_content: bytes, s3_key: str, 
                     content_type: str = 'image/jpeg') -> str:
        """Upload file content to S3 and return public URL."""
        try:
            # Upload file to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=file_content,
                ContentType=content_type,
                CacheControl='public, max-age=31536000',  # 1 year cache
                Metadata={
                    'uploaded_at': datetime.utcnow().isoformat(),
                    'service': 'mapid-upload'
                }
            )
            
            # Generate public URL
            s3_url = f"https://{self.bucket_name}.s3.{self.aws_region}.amazonaws.com/{s3_key}"
            
            logger.info(f"Successfully uploaded to S3: {s3_key}")
            return s3_url
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"S3 upload failed ({error_code}): {e}")
            raise S3UploadError(f"S3 upload failed: {error_code}")
        except Exception as e:
            logger.error(f"Unexpected S3 upload error: {e}")
            raise S3UploadError(f"Upload failed: {e}")
    
    def _delete_from_s3(self, s3_key: str) -> bool:
        """Delete file from S3."""
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            logger.info(f"Successfully deleted from S3: {s3_key}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete from S3 ({s3_key}): {e}")
            return False
    
    def upload_image(self, file: FileStorage, user_id: int, 
                    post_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Upload and process image with content moderation.
        
        Args:
            file: Uploaded file from form
            user_id: ID of user uploading the image
            post_id: Optional post ID for organization
            
        Returns:
            Dict containing upload results and S3 URLs for different sizes
        """
        try:
            # Validate image file
            self._validate_image_file(file)
            
            # Read file content
            file_content = file.read()
            file.seek(0)
            
            # Content moderation check
            moderation_result = self.moderation_service.moderate_image(file_content)
            
            # Check if content should be auto-rejected
            if self.moderation_service.should_auto_reject({'image_moderation': [moderation_result]}):
                logger.warning(f"Image upload rejected by moderation - User: {user_id}")
                return {
                    'success': False,
                    'error': 'Content moderation failed',
                    'moderation_result': moderation_result,
                    'reason': 'inappropriate_content'
                }
            
            # Generate base filename
            prefix = f"posts/{user_id}"
            if post_id:
                prefix = f"posts/{user_id}/post_{post_id}"
            
            base_filename = self._generate_unique_filename(file.filename, prefix)
            base_name, ext = os.path.splitext(base_filename)
            
            # Process image into multiple sizes
            processed_images = self._process_image_sizes(file_content, file.filename)
            
            # Upload all sizes to S3
            s3_urls = {}
            s3_keys = {}
            uploaded_files = []
            
            try:
                for size_name, image_content in processed_images.items():
                    s3_key = f"{base_name}_{size_name}.webp"  # Use WebP extension
                    s3_url = self._upload_to_s3(image_content, s3_key, 'image/webp')
                    
                    s3_urls[size_name] = s3_url
                    s3_keys[size_name] = s3_key
                    uploaded_files.append(s3_key)
                
                # Upload original as well (for backup/future processing)
                original_key = f"{base_name}_original{ext}"
                original_url = self._upload_to_s3(file_content, original_key)
                s3_urls['original'] = original_url
                s3_keys['original'] = original_key
                uploaded_files.append(original_key)
                
                # Return success result
                result = {
                    'success': True,
                    'urls': s3_urls,
                    's3_keys': s3_keys,
                    'moderation_result': moderation_result,
                    'file_info': {
                        'original_filename': file.filename,
                        'file_size': len(file_content),
                        'dimensions': {
                            size_name: self.SIZE_CONFIGS[size_name] 
                            for size_name in processed_images.keys()
                        }
                    },
                    'upload_timestamp': datetime.utcnow().isoformat()
                }
                
                logger.info(f"Image upload successful - User: {user_id}, Files: {len(uploaded_files)}")
                return result
                
            except Exception as e:
                # Cleanup uploaded files on error
                logger.error(f"Upload failed, cleaning up {len(uploaded_files)} files")
                for s3_key in uploaded_files:
                    self._delete_from_s3(s3_key)
                raise e
                
        except (ImageProcessingError, S3UploadError) as e:
            logger.error(f"Image upload failed - User: {user_id}, Error: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_type': e.__class__.__name__
            }
        except Exception as e:
            logger.error(f"Unexpected image upload error - User: {user_id}: {e}")
            return {
                'success': False,
                'error': 'Upload failed due to server error',
                'error_type': 'UnexpectedError'
            }
    
    def delete_image(self, s3_keys: Dict[str, str]) -> Dict[str, bool]:
        """
        Delete image files from S3.
        
        Args:
            s3_keys: Dictionary mapping size names to S3 keys
            
        Returns:
            Dictionary mapping size names to deletion success status
        """
        deletion_results = {}
        
        for size_name, s3_key in s3_keys.items():
            if s3_key:
                deletion_results[size_name] = self._delete_from_s3(s3_key)
            else:
                deletion_results[size_name] = False
        
        success_count = sum(1 for success in deletion_results.values() if success)
        total_count = len(deletion_results)
        
        logger.info(f"Image deletion completed: {success_count}/{total_count} files deleted")
        return deletion_results
    
    def get_upload_progress_url(self, upload_id: str) -> Optional[str]:
        """Generate pre-signed URL for tracking upload progress (future enhancement)."""
        # This would be implemented for client-side progress tracking
        # For now, return None as we're doing server-side uploads
        return None
    
    def validate_s3_configuration(self) -> Dict[str, Any]:
        """Validate S3 configuration and connectivity."""
        try:
            # Test bucket access
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            
            # Test permissions by listing objects (limit 1)
            self.s3_client.list_objects_v2(Bucket=self.bucket_name, MaxKeys=1)
            
            return {
                'success': True,
                'bucket_name': self.bucket_name,
                'region': self.aws_region,
                'status': 'connected'
            }
        except ClientError as e:
            error_code = e.response['Error']['Code']
            return {
                'success': False,
                'error': f"S3 access error: {error_code}",
                'bucket_name': self.bucket_name,
                'region': self.aws_region,
                'status': 'error'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f"Configuration validation failed: {e}",
                'status': 'error'
            }


# Utility function for easy service access
def get_s3_upload_service() -> S3UploadService:
    """Get configured S3 upload service instance."""
    return S3UploadService()