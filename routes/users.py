from flask import Blueprint, request, redirect, url_for, session, render_template, flash, abort, current_app
from werkzeug.security import generate_password_hash
from utils.decorators import login_required, admin_required
from app.db import get_db
import sqlite3

users_bp = Blueprint("users_bp", __name__)

@users_bp.route("/users", methods=["GET", "POST"])
@login_required
@admin_required
def manage_users():
    admin_user_id = session.get('user_id')
    admin_username = session.get('username')
    current_app.logger.info(
        "Admin accessed user management page",
        extra={'admin_user_id': admin_user_id, 'admin_username': admin_username}
    )

    if not session.get("is_admin"):
        # This check is a bit late if we've already logged access, but good for security
        current_app.logger.warning(
            "Non-admin user attempted to access user management page",
            extra={'user_id': admin_user_id, 'username': admin_username}
        )
        return redirect(url_for("tickets_bp.index")) # Assuming tickets_bp.index is the main page

    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Add user
        if request.method == "POST" and "new_username" in request.form: # This condition implies it's the "Add User" form
            new_username = request.form.get("new_username")
            raw_password = request.form.get("new_password")
            is_admin_flag_for_new_user = 0 # New users created here are not admins by default

            errors_add_user = {}
            if not new_username:
                errors_add_user['new_username'] = "Username is required."
            # TODO: Add more username validation (e.g., length, allowed characters)
            
            if not raw_password:
                errors_add_user['new_password'] = "Password is required."
            else:
                # TODO: Add password complexity rules
                # Example:
                # if len(raw_password) < 8:
                #     errors_add_user['new_password_complexity'] = "Password must be at least 8 characters."
                pass

            if errors_add_user:
                for field, msg in errors_add_user.items():
                    flash(msg, "danger")
                # Log validation errors
                current_app.logger.warning(
                    f"Admin user creation failed due to validation errors: {errors_add_user}",
                    extra={'admin_user_id': admin_user_id, 'admin_username': admin_username, 'attempted_username': new_username}
                )
                # Need to fetch users again for the template
                cursor.execute("SELECT id, username, is_admin FROM users")
                users_for_template = cursor.fetchall()
                return render_template("users.html", users=users_for_template, errors_add_user=errors_add_user)

            log_extra_create = {
                'admin_user_id': admin_user_id,
                'admin_username': admin_username,
                'created_username': new_username
            }
            current_app.logger.info("Admin attempting to create new user", extra=log_extra_create)
            
            try:
                # Generate password hash inside try block
                password = generate_password_hash(raw_password) # Use the validated raw_password
                cursor.execute(
                    "INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)",
                    (new_username, password, is_admin_flag_for_new_user)
                )
                conn.commit()
                current_app.logger.info("Admin successfully created new user", extra=log_extra_create)
                flash(f"User {new_username} created successfully.", "success")
            except sqlite3.IntegrityError:
                current_app.logger.warning("Admin failed to create user: Username already exists", extra=log_extra_create)
                flash("Username already exists.", "danger")
            except Exception as e:
                current_app.logger.error(
                    "Admin failed to create user due to an unexpected error",
                    extra=log_extra_create,
                    exc_info=True
                )
                flash("Error creating user.", "danger")


        # Delete user
        if request.method == "POST" and "delete_user" in request.form:
            user_to_delete_username = request.form["delete_user"]
            log_extra_delete = {
                'admin_user_id': admin_user_id,
                'admin_username': admin_username,
                'deleted_username': user_to_delete_username
            }
            current_app.logger.info("Admin attempting to delete user", extra=log_extra_delete)

            cursor.execute("SELECT id, is_admin FROM users WHERE username = ?", (user_to_delete_username,))
            user_record = cursor.fetchone()

            if not user_record:
                current_app.logger.warning("Admin failed to delete user: User not found", extra=log_extra_delete)
                flash("User not found.", "warning")
            elif user_record["is_admin"] == 1:
                current_app.logger.warning("Admin failed to delete user: Cannot delete an admin user", extra=log_extra_delete)
                flash("Cannot delete admin user.", "danger")
            elif user_record["id"] == admin_user_id:
                 current_app.logger.warning("Admin failed to delete user: Admin cannot delete themselves via this form", extra=log_extra_delete)
                 flash("Cannot delete yourself.", "danger")
            else:
                try:
                    cursor.execute("DELETE FROM users WHERE username = ?", (user_to_delete_username,))
                    conn.commit()
                    current_app.logger.info("Admin successfully deleted user", extra=log_extra_delete)
                    flash(f"User {user_to_delete_username} deleted.", "success")
                except Exception as e:
                    current_app.logger.error(
                        "Admin failed to delete user due to an unexpected error",
                        extra=log_extra_delete,
                        exc_info=True
                    )
                    flash("Error deleting user.", "danger")


        cursor.execute("SELECT id, username, is_admin FROM users")
        users = cursor.fetchall()

    return render_template("users.html", users=users)


@users_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    admin_user_id = session.get('user_id')
    admin_username = session.get('username')
    
    with get_db() as conn:
        conn.row_factory = sqlite3.Row # Ensure row_factory for consistent dict-like access
        user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()

        if not user:
            current_app.logger.warning(
                "Admin attempted to edit non-existent user",
                extra={'admin_user_id': admin_user_id, 'admin_username': admin_username, 'target_user_id': user_id}
            )
            abort(404)

        current_app.logger.info(
            "Admin accessed edit page for user",
            extra={
                'admin_user_id': admin_user_id,
                'admin_username': admin_username,
                'target_user_id': user['id'],
                'target_username': user['username']
            }
        )

        if request.method == 'POST':
            log_extra_update = {
                'admin_user_id': admin_user_id,
                'admin_username': admin_username,
                'target_user_id': user['id'],
                'target_username': user['username']
            }
            current_app.logger.info("Admin attempting to update user details", extra=log_extra_update)

            # Capture original values for comparison if detailed change logging is desired (optional)
            # original_email = user['email']
            
            email = request.form.get('email', user['email']) # Keep original if not provided
            pushover_user_key = request.form.get('pushover_user_key', user['pushover_user_key'])
            pushover_api_token = request.form.get('pushover_api_token', user['pushover_api_token'])
            apprise_url = request.form.get('apprise_url', user['apprise_url'])
            notify_email = 1 if 'notify_email' in request.form else 0
            notify_pushover = 1 if 'notify_pushover' in request.form else 0
            notify_apprise = 1 if 'notify_apprise' in request.form else 0
            new_password = request.form.get('new_password')

            edit_errors = {}
            # Validate email format if provided and changed
            if email and email != user['email']:
                import re
                if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                    edit_errors['email'] = "Invalid email format."
            
            # Validate password complexity if new password is provided
            if new_password:
                # TODO: Add password complexity rules (e.g., minimum length, character types)
                # Example:
                # if len(new_password) < 8:
                #     edit_errors['new_password'] = "Password must be at least 8 characters long."
                pass # Placeholder

            if edit_errors:
                for field, msg in edit_errors.items():
                    flash(msg, 'danger')
                current_app.logger.warning(
                    f"Admin failed to update user due to validation errors: {edit_errors}",
                    extra=log_extra_update
                )
                # user object is already fetched, pass errors to template
                return render_template('edit_user.html', user=user, errors=edit_errors)

            # For logging, summarize changes without sensitive data
            updated_fields_log = {
                'email_changed': email != user['email'],
                'pushover_user_key_changed': pushover_user_key != user['pushover_user_key'],
                # Avoid logging tokens directly, just indicate if changed
                'pushover_api_token_changed': bool(pushover_api_token) and pushover_api_token != user['pushover_api_token'],
                'apprise_url_changed': apprise_url != user['apprise_url'],
                'notify_email': notify_email,
                'notify_pushover': notify_pushover,
                'notify_apprise': notify_apprise,
                'password_changed': bool(new_password)
            }
            log_extra_update['updated_fields_summary'] = updated_fields_log

            try:
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
                current_app.logger.info("Admin successfully updated user details", extra=log_extra_update)
                flash('User updated successfully.', 'success')
                return redirect(url_for('users_bp.manage_users'))
            except Exception as e:
                current_app.logger.error(
                    "Admin failed to update user details due to an unexpected error",
                    extra=log_extra_update,
                    exc_info=True
                )
                flash("Error updating user.", "danger")


    # Fetch user again in case of GET or failed POST to ensure fresh data for template
    user_for_template = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone() if conn else user
    return render_template('edit_user.html', user=user_for_template)
