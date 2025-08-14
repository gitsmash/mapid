"""Location services for geocoding and location validation."""
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from flask import current_app
from geopy import distance
from geopy.exc import GeocoderQuotaExceeded, GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Nominatim
from geopy.location import Location as GeopyLocation
from shapely.geometry import Point

logger = logging.getLogger(__name__)


@dataclass
class LocationResult:
    """Structured location result."""
    latitude: float
    longitude: float
    address: str
    formatted_address: str
    confidence: float = 1.0
    place_type: Optional[str] = None
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None


@dataclass
class ValidationResult:
    """Location validation result."""
    is_valid: bool
    error_message: Optional[str] = None
    warnings: List[str] = None
    suggested_coordinates: Optional[Tuple[float, float]] = None


class LocationService:
    """Service for location operations including geocoding and validation."""

    def __init__(self):
        """Initialize location service with geocoder."""
        self.geocoder = Nominatim(
            user_agent=current_app.config.get('GEOCODER_USER_AGENT', 'mapid-app/1.0'),
            timeout=current_app.config.get('GEOCODING_TIMEOUT_SECONDS', 10),
        )
        self.max_radius_miles = current_app.config.get('MAX_NEIGHBORHOOD_RADIUS_MILES', 2.0)
        self.privacy_fuzz_meters = current_app.config.get('LOCATION_PRIVACY_FUZZ_METERS', 100)
        self.max_retries = current_app.config.get('GEOCODING_MAX_RETRIES', 3)
        self.timeout_seconds = current_app.config.get('GEOCODING_TIMEOUT_SECONDS', 10)

    def geocode_address(self, address: str) -> Optional[LocationResult]:
        """
        Geocode an address to coordinates with retry logic.
        
        Args:
            address: Address string to geocode
            
        Returns:
            LocationResult if successful, None if failed
        """
        if not address or not address.strip():
            return None

        try:
            logger.info(f"Geocoding address: {address[:50]}...")

            # Try geocoding with retry logic
            location = self._geocode_with_retry(address.strip())

            if not location:
                logger.warning(f"No results found for address: {address}")
                return None

            # Extract location components
            result = self._parse_location_result(location, address)

            logger.info(f"Geocoded '{address}' to ({result.latitude}, {result.longitude})")
            return result

        except Exception as e:
            logger.error(f"Error geocoding address '{address}': {str(e)}")
            return None

    def reverse_geocode(self, latitude: float, longitude: float) -> Optional[LocationResult]:
        """
        Reverse geocode coordinates to address.
        
        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            
        Returns:
            LocationResult if successful, None if failed
        """
        try:
            # Validate coordinates
            if not self._validate_coordinates(latitude, longitude):
                return None

            logger.info(f"Reverse geocoding coordinates: ({latitude}, {longitude})")

            # Try reverse geocoding with retry logic
            location = self._reverse_geocode_with_retry(latitude, longitude)

            if not location:
                logger.warning(f"No address found for coordinates: ({latitude}, {longitude})")
                return None

            # Parse the result
            result = self._parse_location_result(location, location.address)

            logger.info(f"Reverse geocoded ({latitude}, {longitude}) to '{result.address}'")
            return result

        except Exception as e:
            logger.error(f"Error reverse geocoding coordinates ({latitude}, {longitude}): {str(e)}")
            return None

    def validate_location(
        self,
        latitude: float,
        longitude: float,
        reference_point: Optional[Tuple[float, float]] = None,
    ) -> ValidationResult:
        """
        Validate location coordinates against business rules.
        
        Args:
            latitude: Latitude to validate
            longitude: Longitude to validate
            reference_point: Optional reference point for distance validation
            
        Returns:
            ValidationResult with validation status and details
        """
        warnings = []

        # Basic coordinate validation
        if not self._validate_coordinates(latitude, longitude):
            return ValidationResult(
                is_valid=False,
                error_message="Invalid coordinates: latitude must be between -90 and 90, longitude between -180 and 180",
            )

        # Check if coordinates are in a reasonable location (not in ocean, etc.)
        location_check = self._check_location_reasonableness(latitude, longitude)
        if not location_check["is_reasonable"]:
            warnings.append(location_check["warning"])

        # Distance validation if reference point provided
        if reference_point:
            distance_km = self.calculate_distance(
                latitude, longitude,
                reference_point[0], reference_point[1],
            )
            distance_miles = distance_km * 0.621371

            if distance_miles > self.max_radius_miles:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Location is too far ({distance_miles:.1f} miles). Maximum allowed distance is {self.max_radius_miles} miles.",
                    suggested_coordinates=self._suggest_closer_location(latitude, longitude, reference_point),
                )

        return ValidationResult(is_valid=True, warnings=warnings)

    def apply_privacy_fuzz(self, latitude: float, longitude: float) -> Tuple[float, float]:
        """
        Apply privacy fuzzing to coordinates.
        
        Args:
            latitude: Original latitude
            longitude: Original longitude
            
        Returns:
            Tuple of fuzzed (latitude, longitude)
        """
        if self.privacy_fuzz_meters <= 0:
            return latitude, longitude

        try:
            # Create a point and add random offset (point saved for potential future use)
            # original_point = Point(longitude, latitude)

            # Calculate degree offset based on meters
            # Rough approximation: 1 degree ≈ 111,320 meters
            degree_offset = self.privacy_fuzz_meters / 111320

            # Add small random offset (simplified - should use proper random distribution)
            import random
            lat_offset = random.uniform(-degree_offset, degree_offset)
            lng_offset = random.uniform(-degree_offset, degree_offset)

            fuzzed_lat = latitude + lat_offset
            fuzzed_lng = longitude + lng_offset

            # Ensure we stay within valid bounds
            fuzzed_lat = max(-90, min(90, fuzzed_lat))
            fuzzed_lng = max(-180, min(180, fuzzed_lng))

            logger.debug(f"Applied privacy fuzz: ({latitude}, {longitude}) -> ({fuzzed_lat}, {fuzzed_lng})")

            return fuzzed_lat, fuzzed_lng

        except Exception as e:
            logger.error(f"Error applying privacy fuzz: {str(e)}")
            return latitude, longitude

    def calculate_distance(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """
        Calculate distance between two points in kilometers.
        
        Args:
            lat1, lng1: First point coordinates
            lat2, lng2: Second point coordinates
            
        Returns:
            Distance in kilometers
        """
        try:
            point1 = (lat1, lng1)
            point2 = (lat2, lng2)
            return distance.distance(point1, point2).kilometers
        except Exception as e:
            logger.error(f"Error calculating distance: {str(e)}")
            return float('inf')

    def find_nearby_places(
        self,
        latitude: float,
        longitude: float,
        place_type: str = "amenity",
        radius_meters: int = 1000,
    ) -> List[Dict]:
        """
        Find nearby places of interest using Overpass API.
        
        Args:
            latitude: Center latitude
            longitude: Center longitude
            place_type: Type of place to search for
            radius_meters: Search radius in meters
            
        Returns:
            List of nearby places
        """
        try:
            # This is a simplified implementation
            # In production, you might want to use a proper places API
            logger.info(f"Finding nearby {place_type} within {radius_meters}m of ({latitude}, {longitude})")

            # For now, return empty list - can be extended with actual API calls
            return []

        except Exception as e:
            logger.error(f"Error finding nearby places: {str(e)}")
            return []

    def _geocode_with_retry(self, address: str, max_retries: int = None) -> Optional[GeopyLocation]:
        """Geocode with exponential backoff retry."""
        if max_retries is None:
            max_retries = self.max_retries

        for attempt in range(max_retries):
            try:
                location = self.geocoder.geocode(
                    address,
                    exactly_one=True,
                    timeout=self.timeout_seconds,
                )
                return location

            except GeocoderTimedOut:
                if attempt < max_retries - 1:
                    wait_time = min(2 ** attempt, 10)  # Cap at 10 seconds
                    logger.warning(f"Geocoding timeout for '{address[:30]}...', retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Geocoding failed after {max_retries} retries due to timeout for address: '{address[:50]}...'")
                    return None

            except GeocoderQuotaExceeded:
                logger.error("Geocoding quota exceeded - consider upgrading service or implementing caching")
                return None

            except GeocoderServiceError as e:
                logger.error(f"Geocoding service error for '{address[:30]}...': {str(e)}")
                if attempt < max_retries - 1 and "temporarily unavailable" in str(e).lower():
                    wait_time = min(2 ** attempt, 10)
                    logger.info(f"Service temporarily unavailable, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                return None

            except Exception as e:
                logger.error(f"Unexpected error in geocoding for '{address[:30]}...': {str(e)}")
                return None

        return None

    def _reverse_geocode_with_retry(self, lat: float, lng: float, max_retries: int = None) -> Optional[GeopyLocation]:
        """Reverse geocode with exponential backoff retry."""
        if max_retries is None:
            max_retries = self.max_retries

        for attempt in range(max_retries):
            try:
                location = self.geocoder.reverse(
                    (lat, lng),
                    exactly_one=True,
                    timeout=self.timeout_seconds,
                )
                return location

            except GeocoderTimedOut:
                if attempt < max_retries - 1:
                    wait_time = min(2 ** attempt, 10)  # Cap at 10 seconds
                    logger.warning(f"Reverse geocoding timeout for ({lat:.4f}, {lng:.4f}), retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Reverse geocoding failed after {max_retries} retries due to timeout for coordinates: ({lat:.4f}, {lng:.4f})")
                    return None

            except GeocoderQuotaExceeded:
                logger.error("Reverse geocoding quota exceeded - consider upgrading service or implementing caching")
                return None

            except GeocoderServiceError as e:
                logger.error(f"Reverse geocoding service error for ({lat:.4f}, {lng:.4f}): {str(e)}")
                if attempt < max_retries - 1 and "temporarily unavailable" in str(e).lower():
                    wait_time = min(2 ** attempt, 10)
                    logger.info(f"Service temporarily unavailable, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                return None

            except Exception as e:
                logger.error(f"Unexpected error in reverse geocoding for ({lat:.4f}, {lng:.4f}): {str(e)}")
                return None

        return None

    def _parse_location_result(self, location: GeopyLocation, original_query: str) -> LocationResult:
        """Parse geocoder result into LocationResult."""
        # Extract raw data
        raw_data = location.raw if hasattr(location, 'raw') else {}

        # Parse address components (unused for now, but available for future use)
        # address_parts = raw_data.get('display_name', str(location.address)).split(', ')

        return LocationResult(
            latitude=float(location.latitude),
            longitude=float(location.longitude),
            address=str(location.address),
            formatted_address=self._format_address(raw_data),
            confidence=self._calculate_confidence(raw_data),
            place_type=raw_data.get('type'),
            neighborhood=self._extract_neighborhood(raw_data),
            city=self._extract_city(raw_data),
            state=self._extract_state(raw_data),
            country=raw_data.get('country', raw_data.get('country_code')),
            postal_code=raw_data.get('postcode'),
        )

    def _format_address(self, raw_data: Dict) -> str:
        """Format address for display."""
        # Extract key components for a clean address
        components = []

        # House number and street
        if raw_data.get('house_number') and raw_data.get('road'):
            components.append(f"{raw_data['house_number']} {raw_data['road']}")
        elif raw_data.get('road'):
            components.append(raw_data['road'])

        # City
        city = self._extract_city(raw_data)
        if city:
            components.append(city)

        # State
        state = self._extract_state(raw_data)
        if state:
            components.append(state)

        return ', '.join(components) if components else raw_data.get('display_name', '')

    def _extract_neighborhood(self, raw_data: Dict) -> Optional[str]:
        """Extract neighborhood from raw geocoding data."""
        for key in ['neighbourhood', 'suburb', 'district', 'quarter']:
            if raw_data.get(key):
                return raw_data[key]
        return None

    def _extract_city(self, raw_data: Dict) -> Optional[str]:
        """Extract city from raw geocoding data."""
        for key in ['city', 'town', 'village', 'municipality']:
            if raw_data.get(key):
                return raw_data[key]
        return None

    def _extract_state(self, raw_data: Dict) -> Optional[str]:
        """Extract state/province from raw geocoding data."""
        for key in ['state', 'province', 'region']:
            if raw_data.get(key):
                return raw_data[key]
        return None

    def _calculate_confidence(self, raw_data: Dict) -> float:
        """Calculate confidence score based on geocoding result."""
        # Simplified confidence calculation
        importance = raw_data.get('importance', 0.5)
        place_rank = raw_data.get('place_rank', 30)

        # Higher importance and lower place_rank = higher confidence
        confidence = importance * (1 - (place_rank / 50))
        return max(0.1, min(1.0, confidence))

    def _validate_coordinates(self, latitude: float, longitude: float) -> bool:
        """Validate coordinate bounds."""
        return -90 <= latitude <= 90 and -180 <= longitude <= 180

    def _check_location_reasonableness(self, latitude: float, longitude: float) -> Dict:
        """Check if coordinates are in a reasonable location."""
        # Simplified check - can be enhanced with actual land/water detection

        # Check for common "invalid" coordinates
        if latitude == 0 and longitude == 0:
            return {
                "is_reasonable": False,
                "warning": "Coordinates appear to be the null island (0,0)",
            }

        # Check for extreme coordinates that might be in ocean
        # This is a very basic check - should be enhanced with actual land detection
        if abs(latitude) > 85:  # Very close to poles
            return {
                "is_reasonable": False,
                "warning": "Location is very close to polar regions",
            }

        return {"is_reasonable": True}

    def _suggest_closer_location(
        self,
        latitude: float,
        longitude: float,
        reference_point: Tuple[float, float],
    ) -> Optional[Tuple[float, float]]:
        """Suggest a closer location within the allowed radius."""
        # Calculate direction from reference to target
        ref_lat, ref_lng = reference_point

        # Calculate bearing and limit distance
        try:
            # Simple approach: move point towards reference but keep within max distance
            target_distance_km = self.max_radius_miles * 1.60934  # Convert to km

            # Calculate current distance
            current_distance_km = self.calculate_distance(latitude, longitude, ref_lat, ref_lng)

            if current_distance_km <= target_distance_km:
                return None  # Already within range

            # Calculate ratio to scale down
            ratio = target_distance_km / current_distance_km

            # Interpolate between reference and target
            suggested_lat = ref_lat + (latitude - ref_lat) * ratio
            suggested_lng = ref_lng + (longitude - ref_lng) * ratio

            return suggested_lat, suggested_lng

        except Exception as e:
            logger.error(f"Error suggesting closer location: {str(e)}")
            return None


# Global service instance
_location_service = None


def get_location_service() -> LocationService:
    """Get location service instance."""
    global _location_service
    if _location_service is None:
        _location_service = LocationService()
    return _location_service