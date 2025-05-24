"""
User management routes for administrators.

This module defines the Flask Blueprint for administrator-only routes
related to managing application users, including listing, adding,
editing, and deleting users.
"""
from flask import Blueprint, request, redirect, url_for, session, render_template, flash, abort, current_app
from werkzeug.security import generate_password_hash # For hashing new passwords.
from utils.decorators import login_required, admin_required # Ensure only logged-in admins can access.
from utils.session_helpers import get_current_session_info # Helper for session data.
from utils.db_utils import get_user_or_404 # Helper to fetch a user or raise 404.
from app.db import db_manager # Global database manager instance.
import sqlite3 # For catching sqlite3.IntegrityError specifically.
import re # For regular expression matching, e.g., email validation.

# Define the Blueprint for user management routes.
users_bp = Blueprint("users_bp", __name__)

@users_bp.route("/users", methods=["GET", "POST"])
@login_required # User must be logged in.
@admin_required # User must be an administrator.
def manage_users():
    """
    Handles listing, adding, and deleting users.
    This page is accessible only to administrators.

    GET: Displays the list of users and forms for adding/deleting users.
    POST: Processes form submissions for adding a new user or deleting an existing user.
    """
    session_info = get_current_session_info()
    # Base logging information for actions performed by the current admin.
    log_base_extra = {
        'admin_user_id': session_info['user_id'],
        'admin_username': session_info['username']
    }
    current_admin_user_id = session_info['user_id'] # ID of the admin performing the action.

    # Defensive check, though @admin_required should handle this.
    if not session_info.get("is_admin"): # Check if 'is_admin' is True in session_info.
        current_app.logger.warning(
            "Non-admin user attempted to access user management page (decorator should have prevented).",
            extra=log_base_extra
        )
        flash("You do not have permission to access this page.", "danger")
        return redirect(url_for("main_bp.index"))

    if request.method == "POST":
        # A hidden field 'form_action' distinguishes between 'add_user' and 'delete_user' forms on the same page.
        form_action = request.form.get("form_action")

        if form_action == "add_user":
            # --- Handle Add User Form Submission ---
            new_username = request.form.get("new_username")
            raw_password = request.form.get("new_password")
            # New users created via this admin form are not admins by default.
            # Admin status can be changed via the edit_user page.
            is_admin_flag_for_new_user = 0 # 0 for False, 1 for True.
            
            log_add_extra = {**log_base_extra, 'attempted_new_username': new_username}
            current_app.logger.info("Admin attempting to add a new user.", extra=log_add_extra)

            errors_add_user = {}
            if not new_username: errors_add_user['new_username'] = "Username is a required field."
            if not raw_password: errors_add_user['new_password'] = "Password is a required field."
            # TODO: Add more robust validation for username (length, allowed characters)
            # TODO: Add password complexity rules (minimum length, character types)

            if errors_add_user:
                for msg in errors_add_user.values(): flash(msg, "danger")
                current_app.logger.warning(f"Admin user creation form validation errors: {errors_add_user}", extra=log_add_extra)
            else:
                try:
                    password_hash = generate_password_hash(raw_password) # Securely hash the password.
                    db_manager.insert(
                        "INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)",
                        (new_username, password_hash, is_admin_flag_for_new_user)
                    )
                    current_app.logger.info(f"Admin successfully created new user: '{new_username}'.", extra=log_add_extra)
                    flash(f"User '{new_username}' created successfully.", "success")
                except sqlite3.IntegrityError: # Username likely already exists.
                    current_app.logger.warning(f"Admin user creation failed for '{new_username}': Username already exists (IntegrityError).", extra=log_add_extra)
                    flash("Username already exists. Please choose a different one.", "danger")
                except Exception as e:
                    current_app.logger.error(f"Admin user creation failed for '{new_username}' due to an unexpected error: {e}", extra=log_add_extra, exc_info=True)
                    flash("An unexpected error occurred while creating the user.", "danger")
            # Redirect to GET to refresh the user list and avoid form re-submission issues.
            return redirect(url_for('users_bp.manage_users'))

        elif form_action == "delete_user":
            # --- Handle Delete User Form Submission ---
            username_to_delete = request.form.get("delete_user_username")
            log_delete_extra = {**log_base_extra, 'attempted_delete_username': username_to_delete}
            current_app.logger.info(f"Admin attempting to delete user: '{username_to_delete}'.", extra=log_delete_extra)

            user_record_to_delete = db_manager.fetchone("SELECT id, is_admin FROM users WHERE username = ?", (username_to_delete,))

            if not user_record_to_delete:
                flash(f"User '{username_to_delete}' not found.", "warning")
                current_app.logger.warning(f"Admin delete user: User '{username_to_delete}' not found.", extra=log_delete_extra)
            elif user_record_to_delete["is_admin"] == 1: # Check if the user to be deleted is an admin.
                flash("Cannot delete an administrator user. Demote them first if necessary.", "danger")
                current_app.logger.warning(f"Admin delete user: Attempt to delete admin user '{username_to_delete}'.", extra=log_delete_extra)
            elif user_record_to_delete["id"] == current_admin_user_id: # Prevent self-deletion.
                flash("You cannot delete your own account.", "danger")
                current_app.logger.warning("Admin delete user: Attempt to self-delete.", extra=log_delete_extra)
            else:
                try:
                    # TODO: Consider what happens to tickets/comments created by or assigned to this user.
                    #       Database schema uses ON DELETE SET NULL for foreign keys, which is a good default.
                    db_manager.delete("DELETE FROM users WHERE username = ?", (username_to_delete,))
                    current_app.logger.info(f"Admin successfully deleted user: '{username_to_delete}'.", extra=log_delete_extra)
                    flash(f"User '{username_to_delete}' deleted successfully.", "success")
                except Exception as e:
                    current_app.logger.error(f"Admin delete user failed for '{username_to_delete}' due to an unexpected error: {e}", extra=log_delete_extra, exc_info=True)
                    flash("An unexpected error occurred while deleting the user.", "danger")
            return redirect(url_for('users_bp.manage_users'))

    # For GET requests, or if POST didn't explicitly redirect (should not happen with current logic).
    try:
        # Fetch all users to display in the management list.
        users_list = db_manager.fetchall("SELECT id, username, email, is_admin FROM users ORDER BY username ASC")
        if request.method == "GET": # Log only on initial page load.
             current_app.logger.info("Admin accessed the user management page.", extra=log_base_extra)
    except Exception as e:
        current_app.logger.error("Failed to fetch users for the user management page.", extra=log_base_extra, exc_info=True)
        flash("Error loading user data. Please try again.", "danger")
        users_list = [] # Ensure users_list is an empty list on error for template compatibility.
    
    return render_template("users.html", users=users_list)


@users_bp.route('/users/<int:user_id_to_edit>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id_to_edit):
    """
    Handles editing details of a specific user.
    Accessible only to administrators.

    Args:
        user_id_to_edit (int): The ID of the user to be edited.
    """
    session_info = get_current_session_info()
    log_base_extra = {
        'admin_user_id': session_info['user_id'],
        'admin_username': session_info['username'],
        'target_user_id': user_id_to_edit
    }
    
    # Fetch the user to be edited; get_user_or_404 handles non-existent users.
    user_to_edit = get_user_or_404(user_id_to_edit, db_manager, log_extra=log_base_extra)
    # `user_to_edit` is a dictionary-like object (sqlite3.Row).

    if request.method == 'POST':
        current_app.logger.info(f"Admin attempting to update details for user ID {user_id_to_edit} ('{user_to_edit['username']}').", extra=log_base_extra)
        
        # Retrieve updated data from the form, falling back to existing values if not provided.
        email = request.form.get('email', user_to_edit['email'])
        pushover_user_key = request.form.get('pushover_user_key', user_to_edit['pushover_user_key'])
        pushover_api_token = request.form.get('pushover_api_token', user_to_edit['pushover_api_token'])
        apprise_url = request.form.get('apprise_url', user_to_edit['apprise_url'])
        # Checkboxes: value is present if checked, absent if not.
        notify_email = 1 if 'notify_email' in request.form else 0
        notify_pushover = 1 if 'notify_pushover' in request.form else 0
        notify_apprise = 1 if 'notify_apprise' in request.form else 0
        new_password = request.form.get('new_password') # Optional: only update if provided.
        is_admin_form = 1 if 'is_admin' in request.form else 0 # Admin status from form.

        edit_errors = {}
        # Validate email format if it's being changed and is not empty.
        if email and email != user_to_edit['email'] and not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
            edit_errors['email'] = "Invalid email address format."
        
        # TODO: Add password complexity validation if new_password is set.
        # if new_password and len(new_password) < 8: edit_errors['new_password'] = "New password must be at least 8 characters."

        # Prevent admin from demoting themselves if they are the only admin left.
        if user_to_edit['is_admin'] == 1 and is_admin_form == 0 and user_to_edit['id'] == session_info['user_id']:
            admin_count = db_manager.fetchone("SELECT COUNT(*) AS count FROM users WHERE is_admin = 1")
            if admin_count and admin_count['count'] <= 1:
                edit_errors['is_admin'] = "Cannot remove admin status from the only remaining administrator."
                current_app.logger.warning("Admin attempted to demote the last admin (self).", extra=log_base_extra)


        if edit_errors:
            for msg in edit_errors.values(): flash(msg, 'danger')
            current_app.logger.warning(f"Admin edit user (ID: {user_id_to_edit}) form validation errors: {edit_errors}", extra=log_base_extra)
            # Re-render the edit form with current (pre-POST) user data and errors.
            return render_template('edit_user.html', user=user_to_edit, errors=edit_errors)

        try:
            # Update user's general information.
            db_manager.execute_query(
                '''UPDATE users SET email = ?, pushover_user_key = ?, pushover_api_token = ?,
                   notify_email = ?, notify_pushover = ?, apprise_url = ?, notify_apprise = ?, is_admin = ?
                   WHERE id = ?''',
                (email, pushover_user_key, pushover_api_token, notify_email, notify_pushover,
                 apprise_url, notify_apprise, is_admin_form, user_id_to_edit)
            )

            # If a new password was provided, hash and update it.
            if new_password:
                hashed_password = generate_password_hash(new_password)
                db_manager.execute_query('UPDATE users SET password = ? WHERE id = ?', (hashed_password, user_id_to_edit))
                current_app.logger.info(f"Admin updated password for user ID {user_id_to_edit}.", extra=log_base_extra)

            current_app.logger.info(f"Admin successfully updated details for user ID {user_id_to_edit} ('{user_to_edit['username']}').", extra=log_base_extra)
            flash(f"User '{user_to_edit['username']}' updated successfully.", 'success')
            return redirect(url_for('users_bp.manage_users')) # Redirect back to the user list.
        except Exception as e:
            current_app.logger.error(f"Admin edit user (ID: {user_id_to_edit}) failed due to an unexpected error: {e}", extra=log_base_extra, exc_info=True)
            flash("An unexpected error occurred while updating the user.", "danger")
            # Re-render with current user data if update fails, allowing user to see what was submitted.
            # For a better UX, one might pass the submitted form values back instead of re-fetching `user_to_edit`.
            return render_template('edit_user.html', user=user_to_edit)

    # For GET requests, display the edit user form populated with the user's current data.
    current_app.logger.info(f"Admin accessed edit page for user ID {user_id_to_edit} ('{user_to_edit['username']}').", extra=log_base_extra)
    return render_template('edit_user.html', user=user_to_edit)
