from flask import Blueprint, request, redirect, url_for, session, render_template, flash, abort
from werkzeug.security import generate_password_hash
from utils.decorators import login_required, admin_required
from db import get_db
import sqlite3

users_bp = Blueprint("users_bp", __name__)

@users_bp.route("/users", methods=["GET", "POST"])
@login_required
@admin_required
def manage_users():
    if not session.get("is_admin"):
        return redirect(url_for("tickets_bp.index"))

    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Add user
        if request.method == "POST" and "new_username" in request.form:
            username = request.form["new_username"]
            password = generate_password_hash(request.form["new_password"])
            is_admin = 0
            try:
                cursor.execute(
                    "INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)",
                    (username, password, is_admin)
                )
                conn.commit()
            except sqlite3.IntegrityError:
                flash("Username already exists.", "danger")

        # Delete user
        if request.method == "POST" and "delete_user" in request.form:
            user_to_delete = request.form["delete_user"]
            cursor.execute("SELECT is_admin FROM users WHERE username = ?", (user_to_delete,))
            user = cursor.fetchone()
            if user and user["is_admin"] == 1:
                flash("Cannot delete admin user.", "danger")
            else:
                cursor.execute("DELETE FROM users WHERE username = ?", (user_to_delete,))
                conn.commit()

        cursor.execute("SELECT id, username, is_admin FROM users")
        users = cursor.fetchall()

    return render_template("users.html", users=users)


@users_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    with get_db() as conn:
        user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()

        if not user:
            abort(404)

        if request.method == 'POST':
            email = request.form['email']
            pushover_user_key = request.form['pushover_user_key']
            pushover_api_token = request.form['pushover_api_token']
            apprise_url = request.form.get('apprise_url', '')
            notify_email = 1 if 'notify_email' in request.form else 0
            notify_pushover = 1 if 'notify_pushover' in request.form else 0
            notify_apprise = 1 if 'notify_apprise' in request.form else 0
            new_password = request.form.get('new_password')

            conn.execute(
                '''UPDATE users 
                   SET email = ?, pushover_user_key = ?, pushover_api_token = ?, 
                       notify_email = ?, notify_pushover = ?, apprise_url = ?, notify_apprise = ?
                   WHERE id = ?''',
                (email, pushover_user_key, pushover_api_token,
                 notify_email, notify_pushover, apprise_url, notify_apprise, user_id)
            )

            if new_password:
                hashed_password = generate_password_hash(new_password)
                conn.execute('UPDATE users SET password = ? WHERE id = ?', (hashed_password, user_id))

            conn.commit()
            flash('User updated successfully.', 'success')
            return redirect(url_for('users_bp.manage_users'))

    return render_template('edit_user.html', user=user)
