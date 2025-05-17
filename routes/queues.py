from flask import Blueprint, render_template, request, session, current_app, flash # Added session, current_app, flash
from utils.decorators import login_required, admin_required # Assuming admin_required for queue management
from app.db import get_db
import sqlite3 # For IntegrityError

queues_bp = Blueprint('queues_bp', __name__)

@queues_bp.route("/queues", methods=["GET", "POST"])
@login_required
@admin_required # It's good practice to make queue management admin-only
def manage_queues():
    user_id = session.get('user_id')
    username = session.get('username')
    log_extra_base = {'user_id': user_id, 'username': username, 'action_area': 'queue_management'}

    if request.method == "GET":
        current_app.logger.info(
            "Admin accessed queue management page",
            extra=log_extra_base
        )

    with get_db() as conn:
        cursor = conn.cursor()
        if request.method == "POST":
            queue_name = request.form.get("name")
            log_extra_create = {**log_extra_base, 'queue_name_attempt': queue_name}
            current_app.logger.info("Admin attempting to create new queue", extra=log_extra_create)

            if not queue_name:  # Basic validation
                current_app.logger.warning("Queue creation failed: Name not provided", extra=log_extra_create)
                flash("Queue name cannot be empty.", "danger")
            else:
                try:
                    cursor.execute("INSERT INTO queues (name) VALUES (?)", (queue_name,))
                    conn.commit()
                    new_queue_id = cursor.lastrowid # Get the ID of the newly inserted queue
                    log_extra_create['created_queue_id'] = new_queue_id
                    current_app.logger.info("New queue created successfully", extra=log_extra_create)
                    flash(f"Queue '{queue_name}' created successfully.", "success")
                except sqlite3.IntegrityError: # Assuming queue names should be unique
                    current_app.logger.warning(
                        "Queue creation failed: Queue name likely already exists",
                        extra=log_extra_create
                    )
                    flash(f"Queue name '{queue_name}' already exists.", "danger")
                except Exception as e:
                    current_app.logger.error(
                        "Error creating queue",
                        extra=log_extra_create,
                        exc_info=True
                    )
                    flash("An error occurred while creating the queue.", "danger")
        
        # Always fetch queues for display, regardless of POST outcome
        cursor.execute("SELECT * FROM queues ORDER BY name ASC") # Added ORDER BY
        queues = cursor.fetchall()
        
    return render_template("queues.html", queues=queues)
