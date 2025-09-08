from flask import Blueprint, render_template, jsonify

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
