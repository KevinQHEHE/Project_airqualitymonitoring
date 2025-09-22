"""Admin API blueprint for user management operations."""
from flask import Blueprint, request, jsonify, current_app
import logging
from datetime import datetime, timezone
import csv
import io
from flask import make_response
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from bson import ObjectId
from pymongo.errors import PyMongoError

from backend.app.repositories import users_repo
from backend.app import db as db_module

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__)


def _require_admin():
    """Helper to check if current user has admin role."""
    claims = get_jwt() or {}
    user_role = claims.get('role', 'user')
    if user_role != 'admin':
        return jsonify({"error": "Admin access required"}), 403
    return None


def _serialize_user_admin(user_doc):
    """Serialize user document for admin interface."""
    if not user_doc:
        return None
    
    return {
        "id": str(user_doc.get('_id', '')),
        "fullname": user_doc.get('fullname', ''),
        "email": user_doc.get('email', ''),
        "username": user_doc.get('username', ''),
        "role": user_doc.get('role', 'user'),
        "is_active": user_doc.get('isActive', True),
        "email_verified": user_doc.get('emailVerified', False),
        "created_at": user_doc.get('createdAt', '').isoformat() if isinstance(user_doc.get('createdAt'), datetime) else user_doc.get('createdAt', ''),
        "last_login": user_doc.get('lastLogin', '').isoformat() if isinstance(user_doc.get('lastLogin'), datetime) else user_doc.get('lastLogin', ''),
    }


@admin_bp.route('/users', methods=['GET'])
@jwt_required()
def get_users():
    """Get paginated list of users with search and filters."""
    # Check admin access
    admin_check = _require_admin()
    if admin_check:
        return admin_check
    
    try:
        # Get query parameters
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 25))
        search = request.args.get('search', '').strip()
        status = request.args.get('status', '')
        date_from = request.args.get('date_from', '')
        date_to = request.args.get('date_to', '')
        
        # Build MongoDB filter
        filter_query = {}
        
        # Search by name or email
        if search:
            filter_query['$or'] = [
                {'fullname': {'$regex': search, '$options': 'i'}},
                {'email': {'$regex': search, '$options': 'i'}},
                {'username': {'$regex': search, '$options': 'i'}}
            ]
        
        # Filter by status
        if status == 'active':
            filter_query['isActive'] = True
        elif status == 'inactive':
            filter_query['isActive'] = False
        
        # Date range filter
        if date_from or date_to:
            date_filter = {}
            if date_from:
                date_filter['$gte'] = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
            if date_to:
                date_filter['$lte'] = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
            filter_query['createdAt'] = date_filter
        
        # Get users collection
        db = db_module.get_database()
        users_collection = db.users
        
        # Get total count
        total = users_collection.count_documents(filter_query)
        
        # Calculate pagination
        total_pages = (total + per_page - 1) // per_page
        skip = (page - 1) * per_page
        
        # Get users with pagination
        cursor = users_collection.find(filter_query).sort('createdAt', -1).skip(skip).limit(per_page)
        users = [_serialize_user_admin(user) for user in cursor]
        
        return jsonify({
            "success": True,
            "users": users,
            "total": total,
            "pages": total_pages,
            "current_page": page,
            "per_page": per_page
        }), 200
        
    except Exception as e:
        logger.error(f"Get users error: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@admin_bp.route('/users/<user_id>', methods=['GET'])
@jwt_required()
def get_user_detail(user_id):
    """Get detailed user information including locations and alerts."""
    # Check admin access
    admin_check = _require_admin()
    if admin_check:
        return admin_check
    
    try:
        # Get user by ID
        user = users_repo.find_by_id(ObjectId(user_id))
        if not user:
            return jsonify({"success": False, "error": "User not found"}), 404
        
        # Get user's favorite locations (mock data for now)
        favorite_locations = [
            {
                "name": "Hà Nội",
                "address": "Hà Nội, Việt Nam",
                "created_at": "2024-01-15T10:30:00Z"
            },
            {
                "name": "TP. Hồ Chí Minh",
                "address": "TP. Hồ Chí Minh, Việt Nam", 
                "created_at": "2024-02-20T14:45:00Z"
            }
        ]
        
        # Get user's alert settings (mock data for now)
        alert_settings = [
            {
                "location_name": "Hà Nội",
                "alert_type": "AQI Cao",
                "threshold": "101 (Không tốt cho sức khỏe)",
                "frequency": "Ngay lập tức",
                "is_active": True
            },
            {
                "location_name": "TP. Hồ Chí Minh",
                "alert_type": "PM2.5 Cao", 
                "threshold": "35.4 μg/m³",
                "frequency": "Hàng ngày",
                "is_active": False
            }
        ]
        
        user_data = _serialize_user_admin(user)
        user_data['favorite_locations'] = favorite_locations
        user_data['alert_settings'] = alert_settings
        
        return jsonify({
            "success": True,
            "user": user_data
        }), 200
        
    except Exception as e:
        logger.error(f"Get user detail error: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@admin_bp.route('/users/<user_id>/status', methods=['PUT'])
@jwt_required()
def update_user_status(user_id):
    """Update user active status."""
    # Check admin access
    admin_check = _require_admin()
    if admin_check:
        return admin_check
    
    try:
        data = request.get_json(silent=True) or {}
        is_active = data.get('is_active')
        
        if is_active is None:
            return jsonify({"success": False, "error": "is_active field required"}), 400
        
        # Update user status
        result = users_repo.update_user_status(ObjectId(user_id), is_active)
        
        if result:
            return jsonify({"success": True, "message": "User status updated"}), 200
        else:
            return jsonify({"success": False, "error": "User not found"}), 404
            
    except Exception as e:
        logger.error(f"Update user status error: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@admin_bp.route('/users/<user_id>/role', methods=['PUT'])
@jwt_required()
def update_user_role(user_id):
    """Update user role."""
    # Check admin access
    admin_check = _require_admin()
    if admin_check:
        return admin_check
    
    try:
        data = request.get_json(silent=True) or {}
        new_role = data.get('role')
        
        if new_role not in ['user', 'admin']:
            return jsonify({"success": False, "error": "Invalid role"}), 400
        
        # Update user role
        result = users_repo.update_user_role(ObjectId(user_id), new_role)
        
        if result:
            return jsonify({"success": True, "message": "User role updated"}), 200
        else:
            return jsonify({"success": False, "error": "User not found"}), 404
            
    except Exception as e:
        logger.error(f"Update user role error: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@admin_bp.route('/users/bulk-action', methods=['POST'])
@jwt_required()
def bulk_user_action():
    """Perform bulk actions on multiple users."""
    # Check admin access
    admin_check = _require_admin()
    if admin_check:
        return admin_check
    
    try:
        data = request.get_json(silent=True) or {}
        action = data.get('action')
        user_ids = data.get('user_ids', [])
        
        if not action or not user_ids:
            return jsonify({"success": False, "error": "Action and user_ids required"}), 400
        
        if action not in ['activate', 'deactivate']:
            return jsonify({"success": False, "error": "Invalid action"}), 400
        
        # Convert string IDs to ObjectIds
        object_ids = [ObjectId(uid) for uid in user_ids]
        
        # Perform bulk action
        if action == 'activate':
            result = users_repo.bulk_update_status(object_ids, True)
        else:
            result = users_repo.bulk_update_status(object_ids, False)
        
        return jsonify({
            "success": True,
            "message": f"Bulk {action} completed",
            "affected_count": result
        }), 200
        
    except Exception as e:
        logger.error(f"Bulk user action error: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@admin_bp.route('/users/export', methods=['GET'])
@jwt_required()
def export_users():
    """Export users to CSV."""
    # Check admin access
    admin_check = _require_admin()
    if admin_check:
        return admin_check
    
    try:
        # Get query parameters (same as get_users)
        search = request.args.get('search', '').strip()
        status = request.args.get('status', '')
        date_from = request.args.get('date_from', '')
        date_to = request.args.get('date_to', '')
        selected_ids = request.args.get('selected_ids', '')
        
        # Build filter query
        filter_query = {}
        
        # If specific users selected, export only those
        if selected_ids:
            user_ids = [ObjectId(uid.strip()) for uid in selected_ids.split(',') if uid.strip()]
            filter_query['_id'] = {'$in': user_ids}
        else:
            # Apply same filters as get_users
            if search:
                filter_query['$or'] = [
                    {'fullname': {'$regex': search, '$options': 'i'}},
                    {'email': {'$regex': search, '$options': 'i'}},
                    {'username': {'$regex': search, '$options': 'i'}}
                ]
            
            if status == 'active':
                filter_query['isActive'] = True
            elif status == 'inactive':
                filter_query['isActive'] = False
            
            if date_from or date_to:
                date_filter = {}
                if date_from:
                    date_filter['$gte'] = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
                if date_to:
                    date_filter['$lte'] = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
                filter_query['createdAt'] = date_filter
        
        # Get users
        db = db_module.get_database()
        users_collection = db.users
        cursor = users_collection.find(filter_query).sort('createdAt', -1)
        
        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'ID', 'Họ tên', 'Email', 'Tên đăng nhập', 'Vai trò', 
            'Trạng thái', 'Email xác thực', 'Ngày tạo', 'Đăng nhập cuối'
        ])
        
        # Write user data
        for user in cursor:
            writer.writerow([
                str(user.get('_id', '')),
                user.get('fullname', ''),
                user.get('email', ''),
                user.get('username', ''),
                user.get('role', 'user'),
                'Hoạt động' if user.get('isActive', True) else 'Không hoạt động',
                'Đã xác thực' if user.get('emailVerified', False) else 'Chưa xác thực',
                user.get('createdAt', '').isoformat() if isinstance(user.get('createdAt'), datetime) else user.get('createdAt', ''),
                user.get('lastLogin', '').isoformat() if isinstance(user.get('lastLogin'), datetime) else user.get('lastLogin', '')
            ])
        
        # Create response
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        response.headers['Content-Disposition'] = f'attachment; filename=users_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        
        return response
        
    except Exception as e:
        logger.error(f"Export users error: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500