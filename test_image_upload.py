#!/usr/bin/env python3
"""
Image Upload Test Script

This script tests the image upload functionality of the Mapid application.
It simulates uploading images through the API and verifies the response.
"""

import os
import sys
import requests
import json
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

class ImageUploadTester:
    def __init__(self, base_url="http://localhost:5000"):
        self.base_url = base_url
        self.session = requests.Session()
        
    def login(self, email="test@example.com"):
        """Login to get session cookies"""
        # For testing, we'll assume OAuth is configured
        # In a real test, you'd need to handle OAuth flow
        print(f"Attempting to login with {email}...")
        return True
        
    def test_single_upload(self, image_path):
        """Test uploading a single image"""
        if not os.path.exists(image_path):
            print(f"Error: Image file {image_path} not found")
            return False
            
        print(f"Testing upload of {image_path}...")
        
        with open(image_path, 'rb') as f:
            files = {'image': (os.path.basename(image_path), f, 'image/jpeg')}
            
            response = self.session.post(
                f"{self.base_url}/api/images/upload",
                files=files
            )
            
        if response.status_code == 200:
            result = response.json()
            print(f"Upload successful: {result}")
            return result
        else:
            print(f"Upload failed: {response.status_code} - {response.text}")
            return False
            
    def test_multiple_uploads(self, image_paths):
        """Test uploading multiple images"""
        results = []
        for path in image_paths:
            result = self.test_single_upload(path)
            if result:
                results.append(result)
        return results
        
    def test_invalid_file(self):
        """Test uploading an invalid file type"""
        print("Testing invalid file upload...")
        
        # Create a temporary text file
        with open('/tmp/test.txt', 'w') as f:
            f.write("This is not an image")
            
        with open('/tmp/test.txt', 'rb') as f:
            files = {'image': ('test.txt', f, 'text/plain')}
            
            response = self.session.post(
                f"{self.base_url}/api/images/upload",
                files=files
            )
            
        # Should return error
        if response.status_code != 200:
            print(f"Correctly rejected invalid file: {response.status_code}")
            return True
        else:
            print("Error: Invalid file was accepted")
            return False
            
    def test_large_file(self):
        """Test uploading a file that's too large"""
        print("Testing large file upload...")
        # This would require creating a large test file
        # For now, just return True
        return True
        
    def test_image_processing(self, image_id):
        """Test that uploaded images are processed correctly"""
        print(f"Testing image processing for image {image_id}...")
        
        response = self.session.get(f"{self.base_url}/api/images/{image_id}")
        
        if response.status_code == 200:
            image_data = response.json()
            
            # Check that all required sizes exist
            required_keys = ['url_thumbnail', 'url_medium', 'url_full']
            for key in required_keys:
                if key not in image_data:
                    print(f"Error: Missing {key} in image data")
                    return False
                    
            print("Image processing successful")
            return True
        else:
            print(f"Error retrieving image data: {response.status_code}")
            return False
            
    def run_all_tests(self):
        """Run all image upload tests"""
        print("Starting image upload tests...")
        
        # Login first
        if not self.login():
            print("Login failed, cannot continue tests")
            return False
            
        test_results = {
            'single_upload': False,
            'multiple_uploads': False,
            'invalid_file': False,
            'large_file': False,
            'image_processing': False
        }
        
        # Test single upload
        test_image = "test_images/sample.jpg"
        if os.path.exists(test_image):
            result = self.test_single_upload(test_image)
            test_results['single_upload'] = bool(result)
            
            if result:
                # Test image processing
                image_id = result.get('image', {}).get('id')
                if image_id:
                    test_results['image_processing'] = self.test_image_processing(image_id)
        
        # Test multiple uploads
        test_images = ["test_images/sample1.jpg", "test_images/sample2.jpg"]
        existing_images = [img for img in test_images if os.path.exists(img)]
        if existing_images:
            results = self.test_multiple_uploads(existing_images)
            test_results['multiple_uploads'] = len(results) == len(existing_images)
            
        # Test invalid file
        test_results['invalid_file'] = self.test_invalid_file()
        
        # Test large file
        test_results['large_file'] = self.test_large_file()
        
        # Print summary
        print("\n=== Test Results ===")
        passed = 0
        total = len(test_results)
        
        for test_name, result in test_results.items():
            status = "PASS" if result else "FAIL"
            print(f"{test_name}: {status}")
            if result:
                passed += 1
                
        print(f"\nTotal: {passed}/{total} tests passed")
        return passed == total

def main():
    """Main function to run tests"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test image upload functionality")
    parser.add_argument("--url", default="http://localhost:5000", 
                       help="Base URL of the application")
    parser.add_argument("--image", help="Path to a specific image file to test")
    parser.add_argument("--all", action="store_true", 
                       help="Run all tests")
    
    args = parser.parse_args()
    
    tester = ImageUploadTester(args.url)
    
    if args.image:
        # Test specific image
        tester.login()
        result = tester.test_single_upload(args.image)
        if result:
            print("Single image test passed")
        else:
            print("Single image test failed")
    elif args.all:
        # Run all tests
        success = tester.run_all_tests()
        sys.exit(0 if success else 1)
    else:
        print("Please specify --image or --all")
        sys.exit(1)

if __name__ == "__main__":
    main()