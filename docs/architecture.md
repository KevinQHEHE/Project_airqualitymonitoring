# Architecture Overview

This document provides a high-level overview of the Air Quality Monitoring System architecture.

## System Components

### Application Layer
- Flask web application with REST API endpoints
- Real-time dashboard with charts and maps
- Background task scheduler for data ingestion and alerts

### Data Layer
- MongoDB Atlas for data storage
- Collections for stations, measurements, alerts, and forecasts
- Optimized indexes for query performance

### External Integrations
- OpenAQ API for real-time air quality data
- Email service for alert notifications
- Redis for caching and rate limiting

## Data Flow
1. Scheduled ingestion from OpenAQ API
2. Data validation and AQI calculation
3. Storage in MongoDB with proper indexing
4. Real-time updates via Server-Sent Events
5. Alert processing and notification delivery
