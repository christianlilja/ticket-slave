"""
Ticket queue management routes for administrators.

This module defines the Flask Blueprint for administrator-only routes
related to managing ticket queues, including listing existing queues
and creating new ones.
"""
from flask import Blueprint, render_template, request, session, current_app, flash, redirect, url_for
from utils.decorators import login_required, admin_required # Ensure only logged-in admins can access.
from utils.session_helpers import get_current_session_info # Helper for session data.
from app.db import db_manager # Global database manager instance.
import sqlite3 # Imported specifically for catching sqlite3.IntegrityError.

# Define the Blueprint for queue management routes.
queues_bp = Blueprint('queues_bp', __name__)

@queues_bp.route("/queues", methods=["GET", "POST"])
@login_required # User must be logged in.
@admin_required # User must be an administrator.
def manage_queues():
    """
    Handles listing existing ticket queues and creating new ones.
    This page is accessible only to administrators.

    GET: Displays the list of current queues and a form to add a new queue.
    POST: Processes the form submission for creating a new queue.
    """
    session_info = get_current_session_info()
    # Base logging information for actions performed by the current admin.
    log_extra_base = {
        **session_info['base_log_extra'], # Includes admin_user_id and admin_username.
        'action_area': 'queue_management'
    }

    if request.method == "POST":
        # --- Handle New Queue Creation Form Submission ---
        queue_name = request.form.get("name") # Name for the new queue from the form.
        
        log_extra_create = {**log_extra_base, 'attempted_queue_name': queue_name}
        current_app.logger.info("Admin attempting to create a new ticket queue.", extra=log_extra_create)

        # Validate that a queue name was provided.
        if not queue_name or not queue_name.strip():
            current_app.logger.warning("Queue creation failed: Name was not provided or was empty.", extra=log_extra_create)
            flash("Queue name cannot be empty.", "danger")
        else:
            try:
                # Attempt to insert the new queue into the database.
                # The 'name' column in the 'queues' table has a UNIQUE constraint.
                new_queue_id = db_manager.insert("INSERT INTO queues (name) VALUES (?)", (queue_name.strip(),))
                log_extra_create['created_queue_id'] = new_queue_id # Add new ID to logs.
                current_app.logger.info(f"New queue '{queue_name.strip()}' (ID: {new_queue_id}) created successfully.", extra=log_extra_create)
                flash(f"Queue '{queue_name.strip()}' created successfully.", "success")
            except sqlite3.IntegrityError:
                # This error occurs if the queue name already exists due to the UNIQUE constraint.
                current_app.logger.warning(
                    f"Queue creation failed for '{queue_name.strip()}': Queue name likely already exists (IntegrityError).",
                    extra=log_extra_create
                )
                flash(f"A queue with the name '{queue_name.strip()}' already exists. Please choose a different name.", "danger")
            except Exception as e:
                # Catch any other unexpected errors during database insertion.
                current_app.logger.error(
                    f"An unexpected error occurred while creating queue '{queue_name.strip()}': {e}",
                    extra=log_extra_create,
                    exc_info=True # Include stack trace in the log.
                )
                flash("An unexpected error occurred while creating the queue. Please try again.", "danger")
        # Redirect to GET after POST to prevent form re-submission on refresh and to show the updated list.
        return redirect(url_for('queues_bp.manage_queues'))
    
    # --- For GET requests: Fetch and display existing queues ---
    # This part is outside the POST block, so it runs for GET requests and after a POST redirect.
    try:
        # Fetch all queues from the database, ordered by name for consistent display.
        queues_list = db_manager.fetchall("SELECT id, name FROM queues ORDER BY name ASC")
        if request.method == "GET": # Log only on initial page load (GET request).
             current_app.logger.info("Admin accessed the queue management page.", extra=log_extra_base)
    except Exception as e:
        current_app.logger.error("An error occurred while fetching queues for display.", extra=log_extra_base, exc_info=True)
        flash("An error occurred while fetching the list of queues. Please try again.", "danger")
        queues_list = [] # Ensure queues_list is an empty list on error to prevent template errors.
        
    return render_template("queues.html", queues=queues_list)

# TODO: Consider adding routes for editing and deleting queues if that functionality is required.
# Example for deleting a queue (would need a form or link in queues.html):
# @queues_bp.route("/queues/<int:queue_id>/delete", methods=["POST"])
# @login_required
# @admin_required
# def delete_queue(queue_id):
#     # Check if queue is default or has tickets before deleting.
#     # db_manager.delete("DELETE FROM queues WHERE id = ?", (queue_id,))
#     # flash("Queue deleted.", "success")
#     # return redirect(url_for('queues_bp.manage_queues'))
