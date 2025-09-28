from flask import Blueprint, render_template, jsonify, redirect, url_for, request

web_bp = Blueprint('web', __name__)

@web_bp.route('/')
def dashboard():
    return render_template('dashboard/index.html')

@web_bp.route('/admin')
def admin_dashboard():
    """Admin dashboard for user management."""
    return render_template('admin/user_management.html')

@web_bp.route('/login')
def login_page():
    return render_template('auth/login.html')

@web_bp.route('/register')
def register_page():
    return render_template('auth/register.html')


@web_bp.route('/terms')
def terms_page():
    """Render the Terms of Service page."""
    return render_template('auth/terms_of_service.html')

@web_bp.route('/reports')
def reports_page():
    return render_template('reports/summary.html')

@web_bp.route('/forgot-password')
def forgot_password_page():
    return render_template('auth/forgot.html')

@web_bp.route('/reset-password')
def reset_password_page():
    return render_template('auth/reset.html')


@web_bp.route('/verify-code')
def verify_code_page():
    # optional email query param for context
    from flask import request
    email = request.args.get('email', '')
    return render_template('auth/verifycode.html', email=email)



# Short aliases
@web_bp.route('/forgot')
def forgot_alias():
    return redirect(url_for('web.forgot_password_page'), code=302)

@web_bp.route('/reset')
def reset_alias():
    return redirect(url_for('web.reset_password_page'), code=302)

@web_bp.route('/clear-auth')
def clear_auth():
    return render_template('clear_auth.html')


@web_bp.route('/debug/headers', methods=['GET', 'POST'])
def debug_headers():
    """Temporary debug endpoint: returns incoming request headers as JSON.

    Use this locally to confirm whether the Authorization header (or others)
    are reaching the Flask app. Do NOT enable or expose this in production.
    """
    try:
        hdrs = {k: v for k, v in request.headers.items()}
        return jsonify({"headers": hdrs}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Station Subscriptions page (UI)
@web_bp.route('/subscriptions.html')
@web_bp.route('/subscriptions')
def subscriptions_page():
    """Render the Station Subscriptions management UI.

    Both `/subscriptions` and `/subscriptions.html` are supported because
    the frontend links sometimes point to the `.html` path.
    """
    return render_template('dashboard/subscriptions.html')


@web_bp.route('/admin/users/<user_id>/edit')
def admin_edit_user(user_id: str):
    """Render the admin edit user page. Frontend will fetch user details via API."""
    return render_template('admin/edit_user.html', user_id=user_id)


@web_bp.route('/admin/users/add')
def admin_add_user():
    """Render the admin add user page."""
    return render_template('admin/add_user.html')
