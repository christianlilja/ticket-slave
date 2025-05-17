from flask import Blueprint, request, redirect, url_for, render_template, session, flash, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from app.db import get_db  # Replace with your actual DB import path

auth_bp = Blueprint('auth_bp', __name__)


def is_registration_allowed():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key = 'allow_registration'")
        setting = cur.fetchone()
        return setting and setting['value'] == '1'


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if not is_registration_allowed():
        flash('Registration is currently disabled.', 'warning')
        return redirect(url_for('auth_bp.login'))

    if request.method == 'POST':
        username = request.form.get('username')
        raw_password = request.form.get('password')

        if not username or not raw_password:
            flash('Username and password are required.', 'danger')
            return redirect(url_for('auth_bp.register'))

        # TODO: Add username validation (e.g., length, allowed characters)
        # TODO: Add password complexity rules (e.g., minimum length, character types)
        # Example:
        # if len(raw_password) < 8:
        #     flash('Password must be at least 8 characters long.', 'danger')
        #     return redirect(url_for('auth_bp.register'))

        password = generate_password_hash(raw_password)

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute('SELECT * FROM users WHERE username = ?', (username,))
            if cur.fetchone():
                flash('Username already exists', 'danger')
                return redirect(url_for('auth_bp.register'))

            cur.execute(
                'INSERT INTO users (username, password) VALUES (?, ?)',
                (username, password)
            )
            conn.commit()
            flash('Registered successfully. Please log in.', 'success')
            return redirect(url_for('auth_bp.login'))

    return render_template('register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    allow_registration = is_registration_allowed()

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            flash('Username and password are required.', 'danger')
            return render_template('login.html', allow_registration=allow_registration)

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute('SELECT * FROM users WHERE username = ?', (username,))
            user = cur.fetchone()

            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['is_admin'] = int(user['is_admin']) == 1
                session['theme'] = user['theme'] if user['theme'] is not None else 'default'
                
                current_app.logger.info(
                    "User logged in successfully",
                    extra={
                        'user_id': user['id'],
                        'username': user['username']
                    }
                )
                flash("Logged in successfully.", "success")
                return redirect(url_for('main_bp.index'))
            else:
                current_app.logger.warning(
                    "Failed login attempt",
                    extra={'username_attempt': username}
                )
                flash('Invalid credentials.', 'danger')

    return render_template('login.html', allow_registration=allow_registration)


@auth_bp.route('/logout')
def logout():
    user_id = session.get('user_id')
    username = session.get('username')
    session.clear()
    current_app.logger.info(
        "User logged out",
        extra={
            'user_id': user_id,
            'username': username
        }
    )
    flash("Logged out successfully.", "info")
    return redirect(url_for('auth_bp.login'))
