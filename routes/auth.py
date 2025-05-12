from flask import Blueprint, request, redirect, url_for, render_template, session, flash
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
        username = request.form['username']
        password = generate_password_hash(request.form['password'])

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute('SELECT * FROM users WHERE username = ?', (username,))
            if cur.fetchone():
                flash('Username already exists', 'danger')
                return redirect(url_for('auth.register'))

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
        username = request.form['username']
        password = request.form['password']

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute('SELECT * FROM users WHERE username = ?', (username,))
            user = cur.fetchone()

            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['is_admin'] = int(user['is_admin']) == 1
                session['theme'] = user['theme'] if user['theme'] is not None else 'default'
                flash("Logged in successfully.", "success")
                return redirect(url_for('main_bp.index'))
            else:
                flash('Invalid credentials.', 'danger')

    return render_template('login.html', allow_registration=allow_registration)


@auth_bp.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for('auth_bp.login'))
