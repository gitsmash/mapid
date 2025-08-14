# Mapid - Neighborhood Community Platform

## Product Overview

**Mapid** is a location-based community platform that helps neighbors connect, share, and build stronger local communities through an interactive map interface.

## Core Features

### 1. Interactive Community Map
- Real-time map showing local community posts
- Marker clustering for dense areas
- Category-based filtering and visual coding
- Mobile-responsive design

### 2. Post Categories
- **Garage Sales** 🏠: Neighborhood sales and estate sales
- **Restaurant Specials** 🍽️: Daily deals and special offers
- **Help Needed** ❓: Community assistance requests
- **For Sale** 💰: Individual items for sale
- **Shop Sales** 🛍️: Business promotions and events
- **Borrow** 📚: Tool and item sharing
- **Community Events** 🎉: Local gatherings and activities
- **Lost & Found** 🔍: Missing items and pets

### 3. User Authentication
- Google OAuth integration
- User profiles with reputation system
- Privacy controls for location sharing

### 4. Geospatial Features
- PostGIS-powered location storage
- Distance-based search and filtering
- Address geocoding and reverse geocoding
- Location privacy with fuzzing options

### 5. Content Management
- Rich post creation with category-specific fields
- Multiple image upload with S3 storage
- Content moderation (text and image)
- Post expiration and lifecycle management

## Technical Stack

- **Backend**: Python Flask with SQLAlchemy
- **Database**: PostgreSQL with PostGIS extension
- **Frontend**: HTML/CSS with Tailwind, JavaScript
- **Maps**: Leaflet.js with OpenStreetMap
- **Authentication**: Google OAuth 2.0
- **Storage**: AWS S3 for images
- **Moderation**: AWS Rekognition + profanity filtering

## Target Users

- **Neighbors**: People wanting to connect with their local community
- **Local Businesses**: Small businesses promoting deals and events
- **Community Organizers**: People organizing local events and activities
- **Families**: Parents looking for local resources and connections

## Value Proposition

1. **Hyperlocal Focus**: Unlike social media, focuses specifically on neighborhood-level interactions
2. **Location-Centric**: Map-first interface makes geographic relevance clear
3. **Category Diversity**: Supports various types of community interactions
4. **Privacy-Aware**: Configurable location sharing and privacy controls
5. **Mobile-First**: Designed for on-the-go community engagement

## Success Metrics

- Active monthly users in target neighborhoods
- Number of posts created per user
- Successful connections (measured by responses/interactions)
- Geographic coverage and density of posts
- User retention and engagement rates

## Development Status

**Current Phase**: MVP Development
- ✅ Core backend infrastructure
- ✅ Database schema with PostGIS
- ✅ User authentication system
- ✅ Post creation and management
- ✅ Interactive map interface
- ✅ Image upload and processing
- 🔄 Content moderation
- 🔄 Mobile optimization
- ⏳ Beta testing preparation

## Next Steps

1. Complete MVP features and testing
2. Deploy to staging environment
3. Recruit beta testers from target neighborhoods
4. Iterate based on user feedback
5. Plan public launch strategy