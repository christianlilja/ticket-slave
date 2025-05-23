from flask import Blueprint, render_template, request, session, current_app, flash
from utils.decorators import login_required, admin_required
from utils.session_helpers import get_current_session_info
from app.db import db_manager # Import the db_manager instance
import sqlite3 # For IntegrityError, though db_manager might abstract this away

queues_bp = Blueprint('queues_bp', __name__)

@queues_bp.route("/queues", methods=["GET", "POST"])
@login_required
@admin_required
def manage_queues():
    session_info = get_current_session_info()
    log_extra_base = {**session_info['base_log_extra'], 'action_area': 'queue_management'}

    if request.method == "POST":
        queue_name = request.form.get("name")
        log_extra_create = {**log_extra_base, 'queue_name_attempt': queue_name}
        current_app.logger.info("Admin attempting to create new queue", extra=log_extra_create)

        if not queue_name:
            current_app.logger.warning("Queue creation failed: Name not provided", extra=log_extra_create)
            flash("Queue name cannot be empty.", "danger")
        else:
            try:
                # Use db_manager for the insert operation
                new_queue_id = db_manager.insert("INSERT INTO queues (name) VALUES (?)", (queue_name,))
                log_extra_create['created_queue_id'] = new_queue_id
                current_app.logger.info("New queue created successfully", extra=log_extra_create)
                flash(f"Queue '{queue_name}' created successfully.", "success")
            except sqlite3.IntegrityError: # Catch specific error if db_manager doesn't abstract it
                current_app.logger.warning(
                    "Queue creation failed: Queue name likely already exists",
                    extra=log_extra_create
                )
                flash(f"Queue name '{queue_name}' already exists.", "danger")
            except Exception as e: # Catch other potential errors from db_manager or elsewhere
                current_app.logger.error(
                    "Error creating queue",
                    extra=log_extra_create,
                    exc_info=True
                )
                flash("An error occurred while creating the queue.", "danger")
    
    # Always fetch queues for display
    # This part is outside the POST block, so it runs for GET requests too.
    try:
        queues = db_manager.fetchall("SELECT * FROM queues ORDER BY name ASC")
        if request.method == "GET": # Log only on initial page load
             current_app.logger.info("Admin accessed queue management page", extra=log_extra_base)
    except Exception as e:
        current_app.logger.error("Error fetching queues for display", extra=log_extra_base, exc_info=True)
        flash("An error occurred while fetching queues.", "danger")
        queues = [] # Ensure queues is an empty list on error to prevent template errors
        
    return render_template("queues.html", queues=queues)
