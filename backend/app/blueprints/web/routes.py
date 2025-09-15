from flask import Blueprint, render_template, jsonify, redirect, url_for

web_bp = Blueprint('web', __name__)

@web_bp.route('/')
def dashboard():
    return render_template('dashboard/index.html')

@web_bp.route('/login')
def login_page():
    return render_template('auth/login.html')

@web_bp.route('/register')
def register_page():
    return render_template('auth/register.html')

@web_bp.route('/reports')
def reports_page():
    return render_template('reports/summary.html')

@web_bp.route('/forgot-password')
def forgot_password_page():
    return render_template('auth/forgot.html')

@web_bp.route('/reset-password')
def reset_password_page():
    return render_template('auth/reset.html')

# Short aliases
@web_bp.route('/forgot')
def forgot_alias():
    return redirect(url_for('web.forgot_password_page'), code=302)

@web_bp.route('/reset')
def reset_alias():
    return redirect(url_for('web.reset_password_page'), code=302)
