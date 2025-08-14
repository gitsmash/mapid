"""Content moderation service for text and image filtering."""
import logging
from typing import Dict, Any, Optional
from flask import current_app
import boto3
from botocore.exceptions import ClientError
from better_profanity import profanity

logger = logging.getLogger(__name__)

class ContentModerationService:
    """Service for content moderation using profanity filtering and AWS Rekognition."""
    
    def __init__(self):
        """Initialize the moderation service."""
        # Initialize better-profanity for more comprehensive filtering
        profanity.load_censor_words()
        
        # AWS Rekognition client for image moderation
        self._rekognition_client = None
        if current_app.config.get('AWS_REKOGNITION_ENABLED'):
            try:
                self._rekognition_client = boto3.client(
                    'rekognition',
                    aws_access_key_id=current_app.config.get('AWS_ACCESS_KEY_ID'),
                    aws_secret_access_key=current_app.config.get('AWS_SECRET_ACCESS_KEY'),
                    region_name=current_app.config.get('AWS_REGION', 'us-west-2')
                )
            except Exception as e:
                logger.warning(f"Failed to initialize AWS Rekognition: {e}")
    
    def moderate_text(self, text: str) -> Dict[str, Any]:
        """
        Moderate text content for profanity and inappropriate content.
        
        Args:
            text: Text content to moderate
            
        Returns:
            Dict containing moderation results
        """
        if not current_app.config.get('PROFANITY_FILTER_ENABLED', True):
            return {
                'is_flagged': False,
                'confidence': 0.0,
                'filtered_text': text,
                'reason': None
            }
        
        try:
            # Use better-profanity for profanity detection and filtering
            contains_profanity = profanity.contains_profanity(text)
            filtered_text = profanity.censor(text) if contains_profanity else text
            
            # Calculate confidence based on severity
            profanity_confidence = 0.85 if contains_profanity else 0.0
            
            # Determine final result
            is_flagged = contains_profanity
            action = current_app.config.get('PROFANITY_ACTION', 'flag')
            
            result = {
                'is_flagged': is_flagged,
                'confidence': profanity_confidence * 100,
                'filtered_text': filtered_text if action == 'replace' else text,
                'reason': 'inappropriate_language' if is_flagged else None,
                'action_taken': action if is_flagged else None
            }
            
            if is_flagged:
                logger.warning(f"Text content flagged for profanity - confidence: {profanity_confidence:.2f}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error during text moderation: {e}")
            return {
                'is_flagged': False,
                'confidence': 0.0,
                'filtered_text': text,
                'reason': 'moderation_error',
                'error': str(e)
            }
    
    def moderate_image(self, image_bytes: bytes) -> Dict[str, Any]:
        """
        Moderate image content using AWS Rekognition.
        
        Args:
            image_bytes: Binary image data
            
        Returns:
            Dict containing moderation results
        """
        if not current_app.config.get('IMAGE_MODERATION_ENABLED', True):
            return {
                'is_flagged': False,
                'confidence': 0.0,
                'labels': [],
                'reason': None
            }
        
        if not self._rekognition_client:
            logger.warning("AWS Rekognition not available - skipping image moderation")
            return {
                'is_flagged': False,
                'confidence': 0.0,
                'labels': [],
                'reason': 'service_unavailable'
            }
        
        try:
            # Call AWS Rekognition DetectModerationLabels
            response = self._rekognition_client.detect_moderation_labels(
                Image={'Bytes': image_bytes},
                MinConfidence=50.0  # Lower threshold for detection, we'll filter by config
            )
            
            moderation_labels = response.get('ModerationLabels', [])
            confidence_threshold = current_app.config.get('MODERATION_CONFIDENCE_THRESHOLD', 70.0)
            
            # Filter labels by confidence threshold
            flagged_labels = [
                label for label in moderation_labels 
                if label['Confidence'] >= confidence_threshold
            ]
            
            is_flagged = len(flagged_labels) > 0
            max_confidence = max([label['Confidence'] for label in flagged_labels], default=0.0)
            
            result = {
                'is_flagged': is_flagged,
                'confidence': max_confidence,
                'labels': [
                    {
                        'name': label['Name'],
                        'confidence': label['Confidence'],
                        'parent_name': label.get('ParentName', '')
                    }
                    for label in flagged_labels
                ],
                'reason': 'inappropriate_content' if is_flagged else None
            }
            
            if is_flagged:
                logger.warning(f"Image content flagged - labels: {[l['Name'] for l in flagged_labels]}")
            
            return result
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"AWS Rekognition error ({error_code}): {e}")
            return {
                'is_flagged': False,
                'confidence': 0.0,
                'labels': [],
                'reason': 'moderation_error',
                'error': f"AWS error: {error_code}"
            }
        except Exception as e:
            logger.error(f"Error during image moderation: {e}")
            return {
                'is_flagged': False,
                'confidence': 0.0,
                'labels': [],
                'reason': 'moderation_error',
                'error': str(e)
            }
    
    def moderate_post_content(self, title: str, description: str, 
                            image_files: Optional[list] = None) -> Dict[str, Any]:
        """
        Moderate complete post content including text and images.
        
        Args:
            title: Post title
            description: Post description
            image_files: List of image file bytes
            
        Returns:
            Dict containing comprehensive moderation results
        """
        results = {
            'is_flagged': False,
            'text_moderation': {},
            'image_moderation': [],
            'flagged_reasons': []
        }
        
        # Moderate text content
        combined_text = f"{title} {description}".strip()
        if combined_text:
            text_result = self.moderate_text(combined_text)
            results['text_moderation'] = text_result
            
            if text_result['is_flagged']:
                results['is_flagged'] = True
                results['flagged_reasons'].append(text_result['reason'])
        
        # Moderate images if provided
        if image_files and current_app.config.get('IMAGE_MODERATION_ENABLED', True):
            for i, image_bytes in enumerate(image_files):
                try:
                    image_result = self.moderate_image(image_bytes)
                    image_result['image_index'] = i
                    results['image_moderation'].append(image_result)
                    
                    if image_result['is_flagged']:
                        results['is_flagged'] = True
                        results['flagged_reasons'].append(f"image_{i}_{image_result['reason']}")
                        
                except Exception as e:
                    logger.error(f"Error moderating image {i}: {e}")
                    results['image_moderation'].append({
                        'image_index': i,
                        'is_flagged': False,
                        'error': str(e)
                    })
        
        # Remove duplicates from flagged reasons
        results['flagged_reasons'] = list(set(results['flagged_reasons']))
        
        return results
    
    def should_auto_reject(self, moderation_results: Dict[str, Any]) -> bool:
        """
        Determine if content should be automatically rejected based on moderation results.
        
        Args:
            moderation_results: Results from moderate_post_content
            
        Returns:
            True if content should be auto-rejected
        """
        if not moderation_results['is_flagged']:
            return False
        
        action = current_app.config.get('PROFANITY_ACTION', 'flag')
        if action == 'block':
            return True
        
        # Auto-reject if high-confidence inappropriate content detected
        text_confidence = moderation_results.get('text_moderation', {}).get('confidence', 0)
        if text_confidence > 90.0:
            return True
        
        # Auto-reject if high-confidence inappropriate images
        for image_result in moderation_results.get('image_moderation', []):
            if image_result.get('confidence', 0) > 90.0:
                return True
        
        return False