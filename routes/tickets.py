"""
Ticket management routes.

This module defines the Flask Blueprint for all ticket-related operations,
including creating, viewing, updating tickets, adding comments, managing
assignments, and handling attachments.
"""
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash,
    session, abort, send_from_directory, current_app
)
from datetime import datetime
from werkzeug.utils import secure_filename # For securely handling filenames.
from utils.decorators import login_required, handle_view_exceptions # Custom decorators.
from utils.session_helpers import get_current_session_info # Helper for session data.
from utils.db_utils import get_ticket_or_404 # Helper to fetch a ticket or raise 404.
from utils.validation import validate_user_assignment_input # Validation for user assignment.
from app.db import db_manager # Global database manager instance.
from app.notifications_core import notify_assigned_user # Core notification logic.
from utils.files import allowed_file # Helper to check for allowed file extensions.
from utils.context_runner import run_in_app_context # Runs a function within app context (for notifications).
import os
import sqlite3 # For specific IntegrityError if needed, though db_manager might abstract.

# Define the Blueprint for ticket routes.
tickets_bp = Blueprint('tickets_bp', __name__)

@tickets_bp.route('/ticket/<int:ticket_id>')
@login_required # Ensures only logged-in users can access this route.
@handle_view_exceptions(flash_error_message="Error loading ticket details.", redirect_endpoint='main_bp.index')
# ^ Decorator for centralized try-except handling in view functions.
def ticket_detail(ticket_id):
    """
    Displays the detailed view of a specific ticket, including its comments and attachments.
    """
    session_info = get_current_session_info() # Get current user's session details for logging.
    log_extra = {**session_info['base_log_extra'], 'ticket_id': ticket_id}
    current_app.logger.info("User viewing ticket details page.", extra=log_extra)

    # Fetch the ticket details; get_ticket_or_404 handles non-existent tickets.
    ticket = get_ticket_or_404(ticket_id, db_manager, log_extra=log_extra)

    # Fetch comments associated with the ticket, ordered by creation time.
    comments = db_manager.fetchall('''
        SELECT comments.*, users.username AS commenter_username
        FROM comments
        LEFT JOIN users ON comments.user_id = users.id
        WHERE ticket_id = ?
        ORDER BY created_at ASC
    ''', (ticket_id,))

    # Fetch all users for populating dropdowns (e.g., assign user).
    users = db_manager.fetchall('SELECT id, username FROM users ORDER BY username ASC')
    # Fetch attachments for this ticket.
    raw_attachments = db_manager.fetchall('SELECT * FROM attachments WHERE ticket_id = ? ORDER BY uploaded_at DESC', (ticket_id,))

    # Process attachments to include file size.
    attachments = []
    for file_attach_row in raw_attachments:
        file_dict = dict(file_attach_row) # Convert sqlite3.Row to dict for easier manipulation.
        try:
            # Get file size from the filesystem.
            file_size_bytes = os.path.getsize(file_dict['filepath'])
            file_dict['size_kb'] = round(file_size_bytes / 1024, 1) # Convert to KB.
        except OSError as e: # More specific exception for file system errors.
            attachment_log_extra = {**log_extra, 'attachment_id': file_dict['id'], 'filename': file_dict['original_filename'], 'error': str(e)}
            current_app.logger.warning(f"Could not get size for attachment ID {file_dict['id']}.", extra=attachment_log_extra)
            file_dict['size_kb'] = "N/A" # Indicate size is unavailable.
        attachments.append(file_dict)

    return render_template('ticket_detail.html', ticket=ticket, comments=comments, users=users, attachments=attachments)

@tickets_bp.route('/ticket/<int:ticket_id>/assign', methods=['POST'])
@login_required
@handle_view_exceptions(flash_error_message="An error occurred while updating assignment.", redirect_endpoint='tickets_bp.ticket_detail')
def update_assigned_to(ticket_id):
    """
    Handles updating the user assigned to a specific ticket.
    """
    session_info = get_current_session_info()
    log_extra_base = {**session_info['base_log_extra'], 'ticket_id': ticket_id}
    
    new_assigned_user_id_str = request.form.get('assigned_to') # User ID from the form.

    # Validate the input for the new assigned user.
    # This helper function checks if the ID is valid, if the user exists, or if it's an "unassign" action.
    validated_assigned_user_id, redirect_response = validate_user_assignment_input(
        new_assigned_user_id_str,
        db_manager,
        ticket_id_for_redirect=ticket_id, # For redirecting back to the ticket detail page on error.
        log_extra_base=log_extra_base
    )

    # If validation returns a redirect response (e.g., on invalid input), perform the redirect.
    if redirect_response:
        return redirect_response
    
    log_extra_update = {**log_extra_base, 'new_assigned_user_id': validated_assigned_user_id}
    current_app.logger.info("User attempting to update ticket assignment.", extra=log_extra_update)

    # Update the ticket's 'assigned_to' field in the database.
    db_manager.execute_query('UPDATE tickets SET assigned_to = ? WHERE id = ?', (validated_assigned_user_id, ticket_id))
    
    # If a user was assigned (not unassigned), trigger a notification.
    if validated_assigned_user_id:
        current_app.logger.info("Ticket assignment updated. Queuing notification for assigned user.", extra=log_extra_update)
        # `run_in_app_context` is used because notifications might involve operations
        # that require the application context (e.g., sending emails, accessing config).
        # The actor is the currently logged-in user who performed the assignment.
        run_in_app_context(current_app._get_current_object(), notify_assigned_user, ticket_id, 'assigned', session_info['user_id'])
    else:
        current_app.logger.info("Ticket was unassigned.", extra=log_extra_update)
    
    flash('Ticket assignment updated successfully!', 'success')
    return redirect(url_for('tickets_bp.ticket_detail', ticket_id=ticket_id))


@tickets_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_ticket():
    """
    Handles the creation of a new ticket.
    GET: Displays the form to create a new ticket.
    POST: Processes the submitted form data to create the ticket.
    """
    session_info = get_current_session_info()
    log_extra_base = session_info['base_log_extra']
    current_user_id = session_info['user_id'] # User creating the ticket.

    if request.method == 'GET':
        current_app.logger.info("User accessed the create new ticket page.", extra=log_extra_base)

    # Fetch data needed for the form (queues, users for assignment).
    try:
        queues = db_manager.fetchall("SELECT id, name FROM queues ORDER BY name ASC")
        users = db_manager.fetchall("SELECT id, username FROM users ORDER BY username ASC")
    except Exception as e:
        current_app.logger.error(f"Error fetching queues/users for create ticket page: {e}", extra=log_extra_base, exc_info=True)
        flash("Error loading page data. Please try again or contact support.", "danger")
        queues, users = [], [] # Ensure lists are passed to template even on error.

    if request.method == 'POST':
        # Retrieve form data.
        title = request.form.get('title')
        description = request.form.get('description')
        priority = request.form.get('priority')
        deadline_str = request.form.get('deadline') # Deadline as string from form.
        queue_id_str = request.form.get('queue_id')
        assigned_to_user_id_str = request.form.get('assigned_to') or None # Can be empty if not assigned.
        
        created_at_iso = datetime.now().isoformat() # Timestamp for creation.
        initial_status = 'open' # Default status for new tickets.

        log_extra_create = {
            **log_extra_base, 'ticket_title': title, 'priority': priority,
            'queue_id_str': queue_id_str, 'assigned_to_user_id_str': assigned_to_user_id_str
        }
        current_app.logger.info("User submitted new ticket creation form.", extra=log_extra_create)

        # --- Validate form inputs ---
        errors = {}
        if not title: errors['title'] = "Title is a required field."
        if not description: errors['description'] = "Description is a required field."
        if priority not in ['low', 'medium', 'high']: errors['priority'] = "Invalid priority selected."

        validated_deadline_iso = None
        if deadline_str: # If a deadline was provided.
            try:
                # Parse and reformat to ensure consistent ISO format.
                validated_deadline_iso = datetime.fromisoformat(deadline_str).isoformat()
            except ValueError:
                errors['deadline'] = "Invalid deadline format. Please use YYYY-MM-DDTHH:MM."
        
        queue_id_to_save = None
        default_queue_id_from_config = current_app.config.get('DEFAULT_QUEUE_ID') # Check for a system-wide default.

        if queue_id_str: # If a queue was selected.
            try:
                val_queue_id = int(queue_id_str)
                # Verify the selected queue exists in the database.
                if not db_manager.fetchone("SELECT 1 FROM queues WHERE id = ?", (val_queue_id,)):
                    errors['queue_id'] = "The selected queue does not exist."
                else:
                    queue_id_to_save = val_queue_id
            except ValueError:
                errors['queue_id'] = "Invalid queue ID format."
        
        # If no valid queue was selected and there's no error yet for queue_id.
        if not errors.get('queue_id') and queue_id_to_save is None:
            if default_queue_id_from_config is not None:
                queue_id_to_save = default_queue_id_from_config # Use system default.
                current_app.logger.info(f"No queue selected, using system default queue ID: {default_queue_id_from_config}", extra=log_extra_create)
            else:
                errors['queue_id'] = "Queue selection is required, and no system default is configured."
                current_app.logger.error("Ticket creation failed: Queue not selected and no default queue configured.", extra=log_extra_create)
        
        assigned_to_user_id_to_save = None
        if assigned_to_user_id_str: # If a user was selected for assignment.
            try:
                val_assigned_user_id = int(assigned_to_user_id_str)
                # Verify the selected user exists.
                if not db_manager.fetchone("SELECT 1 FROM users WHERE id = ?", (val_assigned_user_id,)):
                    errors['assigned_to'] = "The user selected for assignment does not exist."
                else:
                    assigned_to_user_id_to_save = val_assigned_user_id
            except ValueError:
                errors['assigned_to'] = "Invalid user ID format for assignment."

        # If there are any validation errors, re-render the form with errors and submitted values.
        if errors:
            for field, msg in errors.items(): flash(msg, "danger")
            current_app.logger.warning(f"Ticket creation validation failed: {errors}", extra=log_extra_create)
            return render_template('create_ticket.html', queues=queues, users=users, title=title,
                                   description=description, priority=priority, deadline=deadline_str,
                                   queue_id=queue_id_str, assigned_to=assigned_to_user_id_str, errors=errors)

        # --- If validation passes, proceed to create the ticket and handle attachment ---
        try:
            # Insert the new ticket into the database.
            new_ticket_id = db_manager.insert('''
                INSERT INTO tickets (title, description, status, priority, deadline, created_at, queue_id, assigned_to, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (title, description, initial_status, priority, validated_deadline_iso, created_at_iso, 
                 queue_id_to_save, assigned_to_user_id_to_save, current_user_id)
            )
            log_extra_create['created_ticket_id'] = new_ticket_id # Add new ticket ID to logs.

            # Handle file attachment if one was provided.
            file_attachment = request.files.get('file') # Get file from the form.
            if file_attachment and file_attachment.filename: # Check if a file was actually uploaded.
                if allowed_file(file_attachment.filename): # Check if file extension is allowed.
                    original_filename = secure_filename(file_attachment.filename) # Sanitize filename.
                    # Create a unique stored filename to prevent conflicts and add context.
                    timestamped_filename = f"{new_ticket_id}_{int(datetime.now().timestamp())}_{original_filename}"
                    save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], timestamped_filename)
                    file_attachment.save(save_path) # Save the file to the upload folder.
                    
                    # Record the attachment in the database.
                    db_manager.insert('''
                        INSERT INTO attachments (ticket_id, original_filename, stored_filename, filepath, uploaded_at, user_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (new_ticket_id, original_filename, timestamped_filename, save_path, datetime.now().isoformat(), current_user_id))
                    current_app.logger.info(f"File '{original_filename}' attached to new ticket ID {new_ticket_id}.", extra={**log_extra_create, 'filename': original_filename})
                else:
                    # File was provided but its type is not allowed.
                    current_app.logger.warning(f"Invalid file type for attachment: '{file_attachment.filename}' for new ticket.", extra=log_extra_create)
                    flash(f"Invalid file type ('{file_attachment.filename.split('.')[-1]}'). Ticket created without this attachment.", "warning")

            current_app.logger.info(f"New ticket (ID: {new_ticket_id}) created successfully by user ID {current_user_id}.", extra=log_extra_create)
            
            # If the ticket was assigned upon creation, notify the assigned user.
            if assigned_to_user_id_to_save:
                 current_app.logger.info(f"Queuing assignment notification for ticket ID {new_ticket_id}.", extra=log_extra_create)
                 run_in_app_context(current_app._get_current_object(), notify_assigned_user, new_ticket_id, 'assigned_on_creation', current_user_id)
            
            flash('Ticket created successfully!', 'success')
            return redirect(url_for('tickets_bp.ticket_detail', ticket_id=new_ticket_id)) # Redirect to the new ticket's detail page.
        
        except Exception as e:
            # Catch-all for errors during DB insertion or file saving.
            current_app.logger.error("Error during ticket database insertion or attachment saving.", extra=log_extra_create, exc_info=True)
            flash('An unexpected error occurred while creating the ticket. Please try again.', 'danger')
            # Re-render form with submitted values to allow user to correct and resubmit.
            return render_template('create_ticket.html', queues=queues, users=users, title=title,
                                   description=description, priority=priority, deadline=deadline_str,
                                   queue_id=queue_id_str, assigned_to=assigned_to_user_id_str)

    # For GET requests, render the empty creation form.
    return render_template('create_ticket.html', queues=queues, users=users)


@tickets_bp.route('/ticket/<int:ticket_id>/comment', methods=['POST'])
@login_required
@handle_view_exceptions(flash_error_message="An error occurred while adding the comment.", redirect_endpoint='tickets_bp.ticket_detail')
def add_comment(ticket_id):
    """
    Handles adding a new comment to a specific ticket.
    """
    session_info = get_current_session_info()
    log_extra = {**session_info['base_log_extra'], 'ticket_id': ticket_id}
    current_user_id = session_info['user_id'] # User adding the comment.

    content = request.form.get('content') # Comment text from the form.
    created_at_iso = datetime.now().isoformat() # Timestamp for the comment.

    if not content or not content.strip(): # Ensure comment is not empty or just whitespace.
        current_app.logger.warning("Add comment attempt failed: Content was empty.", extra=log_extra)
        flash('Comment content cannot be empty.', 'danger')
    else:
        # Insert the new comment into the database.
        db_manager.insert('INSERT INTO comments (ticket_id, content, user_id, created_at) VALUES (?, ?, ?, ?)',
                          (ticket_id, content.strip(), current_user_id, created_at_iso))
        current_app.logger.info(f"Comment added to ticket ID {ticket_id} by user ID {current_user_id}. Queuing notification.", extra=log_extra)
        # Notify relevant users about the new comment.
        run_in_app_context(current_app._get_current_object(), notify_assigned_user, ticket_id, 'new_comment', current_user_id)
        flash('Comment added successfully!', 'success')
    
    return redirect(url_for('tickets_bp.ticket_detail', ticket_id=ticket_id))


@tickets_bp.route('/ticket/<int:ticket_id>/status', methods=['POST'])
@login_required
@handle_view_exceptions(flash_error_message="An error occurred while updating status.", redirect_endpoint='tickets_bp.ticket_detail')
def update_status(ticket_id):
    """
    Handles updating the status of a specific ticket.
    """
    session_info = get_current_session_info()
    log_extra_base = session_info['base_log_extra']
    current_user_id = session_info['user_id'] # User performing the update.

    new_status = request.form.get('status') # New status from the form.
    log_extra = {**log_extra_base, 'ticket_id': ticket_id, 'new_status': new_status}
    
    # Define allowed status values to prevent arbitrary input.
    # These should ideally match the CHECK constraint in the database schema.
    allowed_statuses = ['open', 'in progress', 'closed', 'pending', 'resolved'] # Added more common statuses
    if not new_status or new_status.lower() not in allowed_statuses:
        msg = 'New status cannot be empty.' if not new_status else f"Invalid status provided. Must be one of: {', '.join(allowed_statuses)}."
        current_app.logger.warning(f"Update status attempt failed for ticket ID {ticket_id}: {msg}", extra=log_extra)
        flash(msg, 'danger')
    else:
        # Update the ticket status in the database.
        db_manager.execute_query('UPDATE tickets SET status = ? WHERE id = ?', (new_status.lower(), ticket_id))
        current_app.logger.info(f"Ticket ID {ticket_id} status updated to '{new_status}' by user ID {current_user_id}. Queuing notification.", extra=log_extra)
        # Notify relevant users about the status change.
        run_in_app_context(current_app._get_current_object(), notify_assigned_user, ticket_id, 'status_update', current_user_id)
        flash('Ticket status updated successfully!', 'success')
        
    return redirect(url_for('tickets_bp.ticket_detail', ticket_id=ticket_id))


@tickets_bp.route('/ticket/<int:ticket_id>/priority', methods=['POST'])
@login_required
@handle_view_exceptions(flash_error_message="An error occurred while updating priority.", redirect_endpoint='tickets_bp.ticket_detail')
def update_priority(ticket_id):
    """
    Handles updating the priority of a specific ticket.
    """
    session_info = get_current_session_info()
    log_extra_base = session_info['base_log_extra']
    current_user_id = session_info['user_id'] # User performing the update.

    new_priority = request.form.get('priority') # New priority from the form.
    log_extra = {**log_extra_base, 'ticket_id': ticket_id, 'new_priority': new_priority}

    # Define allowed priority values.
    allowed_priorities = ['low', 'medium', 'high']
    if not new_priority or new_priority.lower() not in allowed_priorities:
        msg = 'New priority cannot be empty.' if not new_priority else f"Invalid priority provided. Must be one of: {', '.join(allowed_priorities)}."
        current_app.logger.warning(f"Update priority attempt failed for ticket ID {ticket_id}: {msg}", extra=log_extra)
        flash(msg, 'danger')
    else:
        # Update the ticket priority in the database.
        db_manager.execute_query('UPDATE tickets SET priority = ? WHERE id = ?', (new_priority.lower(), ticket_id))
        current_app.logger.info(f"Ticket ID {ticket_id} priority updated to '{new_priority}' by user ID {current_user_id}. Queuing notification.", extra=log_extra)
        # Notify relevant users about the priority change.
        run_in_app_context(current_app._get_current_object(), notify_assigned_user, ticket_id, 'priority_update', current_user_id)
        flash('Ticket priority updated successfully!', 'success')
        
    return redirect(url_for('tickets_bp.ticket_detail', ticket_id=ticket_id))


@tickets_bp.route('/uploads/<path:filename>')
@login_required # Ensure only logged-in users can attempt to download.
@handle_view_exceptions(flash_error_message="Error downloading attachment.", redirect_endpoint='main_bp.index')
def download_attachment(filename):
    """
    Handles downloading of a ticket attachment.
    The `filename` parameter is expected to be the `stored_filename` from the attachments table.
    """
    session_info = get_current_session_info()
    # Attempt to extract ticket_id from filename for logging, assuming a pattern like "ticketid_timestamp_original.ext".
    ticket_id_from_filename = filename.split('_')[0] if '_' in filename and filename.split('_')[0].isdigit() else None
    
    log_extra = {
        **session_info['base_log_extra'],
        'requested_filename': filename, # This is the stored_filename.
        'ticket_id_inferred_from_filename': ticket_id_from_filename
    }
    current_app.logger.info("User attempting to download attachment.", extra=log_extra)

    # Security check: Verify the requested filename (stored_filename) exists in the attachments table.
    # This prevents users from attempting to guess file paths or access unauthorized files,
    # even if `send_from_directory` is generally safe with an absolute UPLOAD_FOLDER.
    attachment_record = db_manager.fetchone("SELECT ticket_id, original_filename FROM attachments WHERE stored_filename = ?", (filename,))
    
    if not attachment_record:
        current_app.logger.warning(f"Download attempt for non-existent or unauthorized attachment record: '{filename}'.", extra=log_extra)
        # The @handle_view_exceptions decorator will catch this abort and redirect.
        # A more specific "Attachment not found" page could be implemented if desired.
        abort(404, description="Attachment not found or you do not have permission to access it.")
    
    # Optional further security: Check if the logged-in user has permission to view the ticket
    # associated with `attachment_record['ticket_id']`. This is important in multi-tenant systems
    # or systems with complex ticket visibility rules. For this example, we assume basic access control.
    # Example: if not user_has_permission_for_ticket(session_info['user_id'], attachment_record['ticket_id']):
    #     abort(403)

    # Serve the file from the configured UPLOAD_FOLDER.
    # `as_attachment=True` prompts the browser to download the file.
    # `download_name` can be used to set the filename suggested to the user, defaulting to `original_filename`.
    try:
        response = send_from_directory(
            current_app.config['UPLOAD_FOLDER'], 
            filename, # This is the `stored_filename`.
            as_attachment=True,
            download_name=attachment_record['original_filename'] # Suggest the original filename to the user.
        )
        current_app.logger.info(f"Attachment download initiated for '{filename}' (original: '{attachment_record['original_filename']}').", extra=log_extra)
        return response
    except FileNotFoundError:
        current_app.logger.error(f"Attachment file not found on server: '{filename}' in UPLOAD_FOLDER. Path: {os.path.join(current_app.config['UPLOAD_FOLDER'], filename)}", extra=log_extra)
        # This will be caught by @handle_view_exceptions, which redirects.
        # Alternatively, flash a message and redirect manually if more control is needed.
        abort(404, description="The requested attachment file could not be found on the server.")
    # Other exceptions (e.g., permission errors on the file system) will also be caught by @handle_view_exceptions.
