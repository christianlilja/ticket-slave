from flask import Blueprint, request, redirect, url_for, session, render_template, flash, abort, current_app
from werkzeug.security import generate_password_hash
from utils.decorators import login_required, admin_required
from app.db import db_manager # Use the db_manager instance
import sqlite3 # For IntegrityError, if not handled by db_manager
import re # For email validation in edit_user

# Route definitions for user management
users_bp = Blueprint("users_bp", __name__)

@users_bp.route("/users", methods=["GET", "POST"])
@login_required
@admin_required
def manage_users():
    admin_user_id = session.get('user_id')
    admin_username = session.get('username')
    log_base_extra = {'admin_user_id': admin_user_id, 'admin_username': admin_username}

    if not session.get("is_admin"): # Redundant due to @admin_required but good for defense in depth
        current_app.logger.warning("Non-admin attempted user management access (decorator should prevent).", extra=log_base_extra)
        return redirect(url_for("main_bp.index")) # Redirect to main index

    if request.method == "POST":
        form_action = request.form.get("form_action") # Hidden field to distinguish forms

        if form_action == "add_user":
            new_username = request.form.get("new_username")
            raw_password = request.form.get("new_password")
            # New users created via this admin form are not admins by default.
            # Admin status can be changed via edit_user if needed, or a separate mechanism.
            is_admin_flag_for_new_user = 0
            log_add_extra = {**log_base_extra, 'attempted_username': new_username}

            errors_add_user = {}
            if not new_username: errors_add_user['new_username'] = "Username is required."
            if not raw_password: errors_add_user['new_password'] = "Password is required."
            # Add more validation as needed (length, complexity)

            if errors_add_user:
                for msg in errors_add_user.values(): flash(msg, "danger")
                current_app.logger.warning(f"Admin user creation validation errors: {errors_add_user}", extra=log_add_extra)
            else:
                try:
                    password_hash = generate_password_hash(raw_password)
                    db_manager.insert(
                        "INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)",
                        (new_username, password_hash, is_admin_flag_for_new_user)
                    )
                    current_app.logger.info("Admin created new user.", extra={**log_add_extra, 'created_username': new_username})
                    flash(f"User {new_username} created successfully.", "success")
                except sqlite3.IntegrityError: # Assuming db_manager might re-raise this
                    current_app.logger.warning("Admin user creation failed: Username exists.", extra=log_add_extra)
                    flash("Username already exists.", "danger")
                except Exception as e:
                    current_app.logger.error("Admin user creation failed (unexpected).", extra=log_add_extra, exc_info=True)
                    flash("Error creating user.", "danger")
            # Redirect to GET to avoid form re-submission issues and show updated list
            return redirect(url_for('users_bp.manage_users'))


        elif form_action == "delete_user":
            user_to_delete_username = request.form.get("delete_user_username") # Changed from delete_user to avoid conflict
            log_delete_extra = {**log_base_extra, 'deleted_username_attempt': user_to_delete_username}
            current_app.logger.info("Admin attempting to delete user", extra=log_delete_extra)

            user_record = db_manager.fetchone("SELECT id, is_admin FROM users WHERE username = ?", (user_to_delete_username,))

            if not user_record:
                flash("User not found.", "warning")
                current_app.logger.warning("Admin delete user: Not found.", extra=log_delete_extra)
            elif user_record["is_admin"] == 1: # Check as integer
                flash("Cannot delete an admin user.", "danger")
                current_app.logger.warning("Admin delete user: Is admin.", extra=log_delete_extra)
            elif user_record["id"] == admin_user_id:
                flash("Cannot delete yourself.", "danger")
                current_app.logger.warning("Admin delete user: Attempt to self-delete.", extra=log_delete_extra)
            else:
                try:
                    db_manager.delete("DELETE FROM users WHERE username = ?", (user_to_delete_username,))
                    current_app.logger.info("Admin deleted user.", extra={**log_delete_extra, 'deleted_username_confirmed': user_to_delete_username})
                    flash(f"User {user_to_delete_username} deleted.", "success")
                except Exception as e:
                    current_app.logger.error("Admin delete user failed (unexpected).", extra=log_delete_extra, exc_info=True)
                    flash("Error deleting user.", "danger")
            return redirect(url_for('users_bp.manage_users'))

    # For GET request or if POST didn't redirect (e.g. initial load)
    try:
        users = db_manager.fetchall("SELECT id, username, is_admin FROM users")
        if request.method == "GET": # Log only on initial page load
             current_app.logger.info("Admin accessed user management page", extra=log_base_extra)
    except Exception as e:
        current_app.logger.error("Failed to fetch users for management page.", extra=log_base_extra, exc_info=True)
        flash("Error loading user data.", "danger")
        users = []
    return render_template("users.html", users=users)


@users_bp.route('/users/<int:user_id_to_edit>/edit', methods=['GET', 'POST']) # Renamed user_id to avoid conflict
@login_required
@admin_required
def edit_user(user_id_to_edit):
    admin_user_id = session.get('user_id')
    admin_username = session.get('username')
    log_base_extra = {'admin_user_id': admin_user_id, 'admin_username': admin_username, 'target_user_id': user_id_to_edit}
    
    user = db_manager.fetchone('SELECT * FROM users WHERE id = ?', (user_id_to_edit,))
    if not user:
        current_app.logger.warning("Admin edit user: Target user not found.", extra=log_base_extra)
        abort(404)

    if request.method == 'POST':
        current_app.logger.info("Admin attempting to update user details", extra={**log_base_extra, 'target_username': user['username']})
        
        email = request.form.get('email', user['email'])
        pushover_user_key = request.form.get('pushover_user_key', user['pushover_user_key'])
        pushover_api_token = request.form.get('pushover_api_token', user['pushover_api_token'])
        apprise_url = request.form.get('apprise_url', user['apprise_url'])
        notify_email = 1 if 'notify_email' in request.form else 0
        notify_pushover = 1 if 'notify_pushover' in request.form else 0
        notify_apprise = 1 if 'notify_apprise' in request.form else 0
        new_password = request.form.get('new_password')
        # Admin status change - ensure this is handled carefully
        is_admin_form = 1 if 'is_admin' in request.form else 0


        edit_errors = {}
        if email and email != user['email'] and not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            edit_errors['email'] = "Invalid email format."
        # Add password complexity validation if new_password is set

        if edit_errors:
            for msg in edit_errors.values(): flash(msg, 'danger')
            current_app.logger.warning(f"Admin edit user validation errors: {edit_errors}", extra=log_base_extra)
            return render_template('edit_user.html', user=user, errors=edit_errors) # Re-render with current user data

        try:
            # Update general info
            db_manager.execute_query(
                '''UPDATE users SET email = ?, pushover_user_key = ?, pushover_api_token = ?,
                   notify_email = ?, notify_pushover = ?, apprise_url = ?, notify_apprise = ?, is_admin = ?
                   WHERE id = ?''',
                (email, pushover_user_key, pushover_api_token, notify_email, notify_pushover,
                 apprise_url, notify_apprise, is_admin_form, user_id_to_edit)
            )

            if new_password:
                hashed_password = generate_password_hash(new_password)
                db_manager.execute_query('UPDATE users SET password = ? WHERE id = ?', (hashed_password, user_id_to_edit))

            current_app.logger.info("Admin updated user details.", extra={**log_base_extra, 'target_username': user['username']})
            flash('User updated successfully.', 'success')
            return redirect(url_for('users_bp.manage_users'))
        except Exception as e:
            current_app.logger.error("Admin edit user failed (unexpected).", extra=log_base_extra, exc_info=True)
            flash("Error updating user.", "danger")
            # Re-render with current user data if update fails
            return render_template('edit_user.html', user=user)

    # For GET request
    current_app.logger.info("Admin accessed edit page for user.", extra={**log_base_extra, 'target_username': user['username']})
    return render_template('edit_user.html', user=user)
