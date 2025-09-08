# MongoDB Setup Guide

**Project:** Air Quality Monitoring System  
**Database:** MongoDB Atlas  
**Last Updated:** September 8, 2025

---

## 📋 Overview

This guide walks through setting up MongoDB Atlas cluster, creating users with appropriate roles, and establishing backend connectivity for the Air Quality Monitoring System.

## 🚀 Quick Start

### 1. MongoDB Atlas Cluster Setup

1. **Create MongoDB Atlas Account**
   - Visit [MongoDB Atlas](https://cloud.mongodb.com/)
   - Sign up for a free account or log in

2. **Create New Cluster**
   - Click "Create a New Cluster"
   - Choose **M0 Sandbox** (Free Tier) for development
   - Select cloud provider and region closest to your location
   - Name your cluster: `air-quality-cluster`

3. **Configure Network Access**
   - Go to "Network Access" → "Add IP Address"
   - For development: Add `0.0.0.0/0` (allow all IPs)
   - For production: Add specific IP addresses

### 2. Database Users & Roles

The system uses three user roles with minimal necessary permissions:

#### Admin User (`aqm_admin`)
- **Purpose**: Database administration, schema changes, user management
- **Permissions**: `readWrite` + `dbAdmin` on `air_quality_db`
- **Usage**: Initial setup, migrations, troubleshooting

#### Application User (`aqm_app`) 
- **Purpose**: Main application backend operations
- **Permissions**: `readWrite` on `air_quality_db`
- **Usage**: Flask backend, data ingestion, API operations

#### Readonly User (`aqm_readonly`)
- **Purpose**: Analytics, reporting, monitoring
- **Permissions**: `read` on `air_quality_db`
- **Usage**: Business intelligence, external tools

### 3. Create Database Users

#### Option A: MongoDB Atlas UI

1. **Navigate to Database Access**
   - Go to "Database Access" in Atlas dashboard
   - Click "Add New Database User"

2. **Create Admin User**
   ```
   Username: aqm_admin
   Password: [Generate secure password]
   Database User Privileges: 
   - Built-in Role: Database Admin
   - Database: air_quality_db
   ```

3. **Create Application User**
   ```
   Username: aqm_app  
   Password: [Generate secure password]
   Database User Privileges:
   - Built-in Role: Read and write to any database
   - Database: air_quality_db
   ```

4. **Create Readonly User**
   ```
   Username: aqm_readonly
   Password: [Generate secure password] 
   Database User Privileges:
   - Built-in Role: Read any database
   - Database: air_quality_db
   ```

#### Option B: MongoDB Shell Commands

Run these commands in MongoDB shell or Atlas Data Explorer:

```javascript
// Switch to admin database
use admin

// Create admin user
db.createUser({
  user: "aqm_admin",
  pwd: "SECURE_ADMIN_PASSWORD",
  roles: [
    { role: "readWrite", db: "air_quality_db" },
    { role: "dbAdmin", db: "air_quality_db" }
  ]
})

// Create application user  
db.createUser({
  user: "aqm_app",
  pwd: "SECURE_APP_PASSWORD", 
  roles: [
    { role: "readWrite", db: "air_quality_db" }
  ]
})

// Create readonly user
db.createUser({
  user: "aqm_readonly",
  pwd: "SECURE_READONLY_PASSWORD",
  roles: [
    { role: "read", db: "air_quality_db" }
  ]
})
```

### 4. Connection String Format

MongoDB Atlas connection strings follow this pattern:

```
mongodb+srv://<username>:<password>@<cluster-name>.<cluster-id>.mongodb.net/?retryWrites=true&w=majority&appName=<app-name>
```

**Example for application user:**
```
mongodb+srv://aqm_app:YOUR_PASSWORD@air-quality-cluster.abc123.mongodb.net/?retryWrites=true&w=majority&appName=AirQualityMonitoring
```

### 5. Environment Configuration

1. **Copy environment template:**
   ```bash
   cp .env.sample .env
   ```

2. **Update `.env` with your credentials:**
   ```bash
   # Replace with your actual cluster details
   MONGO_URI=mongodb+srv://aqm_app:YOUR_APP_PASSWORD@air-quality-cluster.abc123.mongodb.net/?retryWrites=true&w=majority&appName=AirQualityMonitoring
   MONGO_DB=air_quality_db
   ```

3. **Test the connection:**
   ```bash
   python scripts/test_db_connection.py
   ```

## 🔧 Troubleshooting

### Common Issues

#### Authentication Failed
```
pymongo.errors.OperationFailure: Authentication failed
```
**Solutions:**
- Verify username/password in connection string
- Check user exists in correct database
- Ensure user has proper roles assigned

#### Network Timeout  
```
pymongo.errors.ServerSelectionTimeoutError
```
**Solutions:**
- Check network access whitelist in Atlas
- Verify internet connectivity
- Try connecting from different network

#### Database Access Denied
```
pymongo.errors.OperationFailure: not authorized
```
**Solutions:**
- Verify user roles and permissions
- Check if connecting to correct database
- Ensure user has `readWrite` permission

### Connection Testing

Use the provided test script to verify connectivity:

```bash
# Test basic connection
python scripts/test_db_connection.py

# Test with specific user (update script as needed)
python scripts/test_db_connection.py --user aqm_readonly
```

## 🔐 Security Best Practices

### User Management
- Use strong, unique passwords for each user
- Rotate passwords regularly in production
- Limit user permissions to minimum required
- Monitor user access patterns

### Network Security
- Restrict IP access to known addresses in production
- Use VPC peering for cloud deployments
- Enable MongoDB's built-in SSL/TLS encryption

### Application Security  
- Never commit connection strings to git
- Use environment variables for all secrets
- Implement connection pooling and timeouts
- Log authentication events for monitoring

## 📈 Performance Optimization

### Connection Settings
```python
# Recommended PyMongo settings
mongo_client = MongoClient(
    uri,
    maxPoolSize=50,
    minPoolSize=5,
    maxIdleTimeMS=30000,
    serverSelectionTimeoutMS=5000,
    socketTimeoutMS=20000,
    connectTimeoutMS=10000,
    retryWrites=True
)
```

### Index Strategy
- GeoSpatial indexes for location queries
- Compound indexes for common filter combinations
- TTL indexes for automatic data cleanup
- Text indexes for search functionality

## 🔗 References

- [MongoDB Atlas Documentation](https://docs.atlas.mongodb.com/)
- [PyMongo Documentation](https://pymongo.readthedocs.io/)
- [MongoDB Security Checklist](https://docs.mongodb.com/manual/administration/security-checklist/)
- [Air Quality DB Schema](./db_schema.md)

---

**Note:** Replace all placeholder values (`YOUR_PASSWORD`, `abc123`, etc.) with your actual MongoDB Atlas cluster details.
