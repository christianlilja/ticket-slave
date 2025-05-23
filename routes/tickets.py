from flask import (
    Blueprint, render_template, request, redirect, url_for, flash,
    session, abort, send_from_directory, current_app
)
from datetime import datetime
from werkzeug.utils import secure_filename
from utils.decorators import login_required, handle_view_exceptions
from utils.session_helpers import get_current_session_info
from utils.db_utils import get_ticket_or_404
from utils.validation import validate_user_assignment_input
from app.db import db_manager # Use the db_manager instance
from app.notifications_core import notify_assigned_user
from utils.files import allowed_file
from utils.context_runner import run_in_app_context
import os
import sqlite3 # For specific IntegrityError if needed, though db_manager might abstract

tickets_bp = Blueprint('tickets_bp', __name__)

@tickets_bp.route('/ticket/<int:ticket_id>')
@login_required
@handle_view_exceptions(flash_error_message="Error loading ticket details.", redirect_endpoint='main_bp.index')
def ticket_detail(ticket_id):
    session_info = get_current_session_info()
    log_extra = {**session_info['base_log_extra'], 'ticket_id': ticket_id}
    current_app.logger.info("User viewing ticket details", extra=log_extra)

    ticket = get_ticket_or_404(ticket_id, db_manager, log_extra=log_extra)

    comments = db_manager.fetchall('''
        SELECT comments.*, users.username
        FROM comments
        LEFT JOIN users ON comments.user_id = users.id
        WHERE ticket_id = ?
        ORDER BY created_at ASC
    ''', (ticket_id,))

    users = db_manager.fetchall('SELECT id, username FROM users')
    raw_attachments = db_manager.fetchall('SELECT * FROM attachments WHERE ticket_id = ?', (ticket_id,))
    
    attachments = []
    for file_attach in raw_attachments:
        file_dict = dict(file_attach) # Convert sqlite3.Row to dict if necessary
        try:
            file_size = os.path.getsize(file_attach['filepath'])
            file_dict['size_kb'] = round(file_size / 1024, 1)
        except Exception as e:
            log_msg = f"Could not get size for attachment {file_attach['original_filename']}"
            # Use a more specific log_extra for this particular warning
            attachment_log_extra = {**log_extra, 'attachment_id': file_attach['id'], 'error': str(e)}
            current_app.logger.warning(log_msg, extra=attachment_log_extra)
            file_dict['size_kb'] = None
        attachments.append(file_dict)

    return render_template('ticket_detail.html', ticket=ticket, comments=comments, users=users, attachments=attachments)

@tickets_bp.route('/ticket/<int:ticket_id>/assign', methods=['POST'])
@login_required
@handle_view_exceptions(flash_error_message="An error occurred while updating assignment.", redirect_endpoint='tickets_bp.ticket_detail')
def update_assigned_to(ticket_id):
    session_info = get_current_session_info()
    log_extra_base = {**session_info['base_log_extra'], 'ticket_id': ticket_id}
    
    new_assigned_user_id_str = request.form.get('assigned_to')

    # The validate_user_assignment_input function needs to be imported
    # from utils.validation import validate_user_assignment_input
    # This import should be added at the top of the file.
    
    validated_assigned_user_id, redirect_response = validate_user_assignment_input(
        new_assigned_user_id_str,
        db_manager,
        ticket_id_for_redirect=ticket_id,
        log_extra_base=log_extra_base
    )

    if redirect_response:
        return redirect_response
    
    log_extra_update = {**log_extra_base, 'new_assigned_user_id': validated_assigned_user_id}
    current_app.logger.info("User attempting to update ticket assignment", extra=log_extra_update)

    db_manager.execute_query('UPDATE tickets SET assigned_to = ? WHERE id = ?', (validated_assigned_user_id, ticket_id))
    
    if validated_assigned_user_id:
        current_app.logger.info("Ticket assignment updated, queuing notification", extra=log_extra_update)
        # Ensure session_info['user_id'] is used for the actor of the notification
        run_in_app_context(current_app._get_current_object(), notify_assigned_user, ticket_id, 'assigned', session_info['user_id'])
    else:
        current_app.logger.info("Ticket unassigned", extra=log_extra_update)
    flash('Assigned user updated successfully!', 'success')
    
    return redirect(url_for('tickets_bp.ticket_detail', ticket_id=ticket_id))


@tickets_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_ticket():
    session_info = get_current_session_info()
    log_extra_base = session_info['base_log_extra']
    user_id = session_info['user_id'] # Needed for created_by and notifications

    if request.method == 'GET':
        current_app.logger.info("User accessed create ticket page", extra=log_extra_base)

    try:
        queues = db_manager.fetchall("SELECT id, name FROM queues")
        users = db_manager.fetchall("SELECT id, username FROM users")
    except Exception as e:
        current_app.logger.error(f"Error fetching queues/users for create ticket page: {e}", extra=log_extra_base, exc_info=True)
        flash("Error loading page data. Please try again.", "danger")
        queues, users = [], [] # Ensure they are lists for the template

    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        priority = request.form.get('priority')
        deadline_str = request.form.get('deadline')
        queue_id_str = request.form.get('queue_id')
        assigned_to_user_id_str = request.form.get('assigned_to') or None
        created_at = datetime.now().isoformat()
        status = 'open'

        log_extra_create = {**log_extra_base, 'ticket_title': title, 'priority': priority,
                            'queue_id_str': queue_id_str, 'assigned_to_user_id_str': assigned_to_user_id_str}
        current_app.logger.info("User attempting to create new ticket", extra=log_extra_create)

        errors = {}
        if not title: errors['title'] = "Title is required."
        if not description: errors['description'] = "Description is required."
        if priority not in ['low', 'medium', 'high']: errors['priority'] = "Invalid priority."

        validated_deadline = None
        if deadline_str:
            try:
                validated_deadline = datetime.fromisoformat(deadline_str).isoformat()
            except ValueError:
                errors['deadline'] = "Invalid deadline format (YYYY-MM-DDTHH:MM)."
        
        queue_id_to_save = None
        default_queue_id_from_config = current_app.config.get('DEFAULT_QUEUE_ID')

        if queue_id_str:
            try:
                val_queue_id = int(queue_id_str)
                if not db_manager.fetchone("SELECT 1 FROM queues WHERE id = ?", (val_queue_id,)):
                    errors['queue_id'] = "Selected queue does not exist."
                else:
                    queue_id_to_save = val_queue_id
            except ValueError:
                errors['queue_id'] = "Invalid queue ID format."
        
        if not errors.get('queue_id') and queue_id_to_save is None: # No valid selection or empty
            if default_queue_id_from_config is not None:
                queue_id_to_save = default_queue_id_from_config
                current_app.logger.info(f"Assigning default queue ID: {default_queue_id_from_config}", extra=log_extra_create)
            else:
                errors['queue_id'] = "Queue is required, and no default is configured."
                current_app.logger.error("Ticket creation: Queue not selected, no default configured.", extra=log_extra_create)
        
        assigned_to_user_id_to_save = None
        if assigned_to_user_id_str:
            try:
                val_assigned_user_id = int(assigned_to_user_id_str)
                if not db_manager.fetchone("SELECT 1 FROM users WHERE id = ?", (val_assigned_user_id,)):
                    errors['assigned_to'] = "Selected user to assign does not exist."
                else:
                    assigned_to_user_id_to_save = val_assigned_user_id
            except ValueError:
                errors['assigned_to'] = "Invalid user ID for assignment."

        if errors:
            for field, msg in errors.items(): flash(msg, "danger")
            current_app.logger.warning(f"Ticket creation validation errors: {errors}", extra=log_extra_create)
            return render_template('create_ticket.html', queues=queues, users=users, title=title,
                                   description=description, priority=priority, deadline=deadline_str,
                                   queue_id=queue_id_str, assigned_to=assigned_to_user_id_str, errors=errors)

        try:
            ticket_id = db_manager.insert('''
                INSERT INTO tickets (title, description, status, priority, deadline, created_at, queue_id, assigned_to, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (title, description, status, priority, validated_deadline, created_at, queue_id_to_save, assigned_to_user_id_to_save, user_id)
            )
            log_extra_create['created_ticket_id'] = ticket_id

            file_attachment = request.files.get('file')
            if file_attachment and file_attachment.filename and allowed_file(file_attachment.filename):
                original_filename = secure_filename(file_attachment.filename)
                timestamped_filename = f"{ticket_id}_{datetime.now().timestamp()}_{original_filename}"
                save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], timestamped_filename)
                file_attachment.save(save_path)
                db_manager.insert('''
                    INSERT INTO attachments (ticket_id, original_filename, stored_filename, filepath, uploaded_at, user_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (ticket_id, original_filename, timestamped_filename, save_path, datetime.now().isoformat(), user_id))
                current_app.logger.info("File attached to new ticket", extra={**log_extra_create, 'filename': original_filename})
            elif file_attachment and file_attachment.filename: # File provided but not allowed
                 current_app.logger.warning("Invalid file type for attachment", extra={**log_extra_create, 'filename': file_attachment.filename})
                 flash("Invalid file type. Ticket created without attachment.", "warning")


            current_app.logger.info("New ticket created successfully", extra=log_extra_create)
            if assigned_to_user_id_to_save:
                 current_app.logger.info("Queuing assignment notification", extra=log_extra_create)
                 run_in_app_context(current_app._get_current_object(), notify_assigned_user, ticket_id, 'assigned', user_id)
            flash('Ticket created successfully!', 'success')
            return redirect(url_for('tickets_bp.ticket_detail', ticket_id=ticket_id)) # Redirect to new ticket
        except Exception as e:
            current_app.logger.error("Error during ticket DB insertion/attachment", extra=log_extra_create, exc_info=True)
            flash('An error occurred while creating the ticket.', 'danger')
            # Render again with submitted values
            return render_template('create_ticket.html', queues=queues, users=users, title=title,
                                   description=description, priority=priority, deadline=deadline_str,
                                   queue_id=queue_id_str, assigned_to=assigned_to_user_id_str)

    return render_template('create_ticket.html', queues=queues, users=users)


@tickets_bp.route('/ticket/<int:ticket_id>/comment', methods=['POST'])
@login_required
@handle_view_exceptions(flash_error_message="An error occurred while adding the comment.", redirect_endpoint='tickets_bp.ticket_detail')
def add_comment(ticket_id):
    session_info = get_current_session_info()
    log_extra = {**session_info['base_log_extra'], 'ticket_id': ticket_id}
    user_id = session_info['user_id']

    content = request.form.get('content')
    created_at = datetime.now().isoformat()

    if not content:
        current_app.logger.warning("Add comment failed: Content empty", extra=log_extra)
        flash('Comment cannot be empty.', 'danger')
    else:
        db_manager.insert('INSERT INTO comments (ticket_id, content, user_id, created_at) VALUES (?, ?, ?, ?)',
                          (ticket_id, content, user_id, created_at))
        current_app.logger.info("Comment added, queuing notification", extra=log_extra)
        run_in_app_context(current_app._get_current_object(), notify_assigned_user, ticket_id, 'new_comment', user_id)
        flash('Comment added successfully!', 'success')
    return redirect(url_for('tickets_bp.ticket_detail', ticket_id=ticket_id))


@tickets_bp.route('/ticket/<int:ticket_id>/status', methods=['POST'])
@login_required
@handle_view_exceptions(flash_error_message="An error occurred while updating status.", redirect_endpoint='tickets_bp.ticket_detail')
def update_status(ticket_id):
    session_info = get_current_session_info()
    log_extra_base = session_info['base_log_extra']
    user_id = session_info['user_id']

    new_status = request.form.get('status')
    log_extra = {**log_extra_base, 'ticket_id': ticket_id, 'new_status': new_status}
    
    allowed_statuses = ['open', 'in progress', 'pending', 'resolved', 'closed']
    if not new_status or new_status not in allowed_statuses:
        msg = 'New status cannot be empty.' if not new_status else f"Invalid status. Must be one of: {', '.join(allowed_statuses)}."
        current_app.logger.warning(f"Update status failed: {msg}", extra=log_extra)
        flash(msg, 'danger')
    else:
        db_manager.execute_query('UPDATE tickets SET status = ? WHERE id = ?', (new_status, ticket_id))
        current_app.logger.info("Ticket status updated, queuing notification", extra=log_extra)
        run_in_app_context(current_app._get_current_object(), notify_assigned_user, ticket_id, 'status', user_id)
        flash('Status updated successfully!', 'success')
    return redirect(url_for('tickets_bp.ticket_detail', ticket_id=ticket_id))


@tickets_bp.route('/ticket/<int:ticket_id>/priority', methods=['POST'])
@login_required
@handle_view_exceptions(flash_error_message="An error occurred while updating priority.", redirect_endpoint='tickets_bp.ticket_detail')
def update_priority(ticket_id):
    session_info = get_current_session_info()
    log_extra_base = session_info['base_log_extra']
    user_id = session_info['user_id']

    new_priority = request.form.get('priority')
    log_extra = {**log_extra_base, 'ticket_id': ticket_id, 'new_priority': new_priority}

    allowed_priorities = ['low', 'medium', 'high']
    if not new_priority or new_priority not in allowed_priorities:
        msg = 'New priority cannot be empty.' if not new_priority else f"Invalid priority. Must be one of: {', '.join(allowed_priorities)}."
        current_app.logger.warning(f"Update priority failed: {msg}", extra=log_extra)
        flash(msg, 'danger')
    else:
        db_manager.execute_query('UPDATE tickets SET priority = ? WHERE id = ?', (new_priority, ticket_id))
        current_app.logger.info("Ticket priority updated, queuing notification", extra=log_extra)
        run_in_app_context(current_app._get_current_object(), notify_assigned_user, ticket_id, 'priority', user_id)
        flash('Priority updated successfully!', 'success')
    return redirect(url_for('tickets_bp.ticket_detail', ticket_id=ticket_id))


@tickets_bp.route('/uploads/<path:filename>')
@login_required
@handle_view_exceptions(flash_error_message="Error downloading attachment.", redirect_endpoint='main_bp.index') # Or a more specific error page
def download_attachment(filename):
    session_info = get_current_session_info()
    ticket_id_from_filename = filename.split('_')[0] if '_' in filename else None
    log_extra = {
        **session_info['base_log_extra'],
        'filename': filename,
        'ticket_id_from_filename': ticket_id_from_filename
    }
    current_app.logger.info("User attempting to download attachment", extra=log_extra)

    # It's good practice to verify the attachment record exists and belongs to an accessible ticket,
    # but send_from_directory with a secure UPLOAD_FOLDER path is the primary defense here.
    # For added security, one might check if `filename` (which is stored_filename) exists in attachments table.
    attachment_record = db_manager.fetchone("SELECT ticket_id FROM attachments WHERE stored_filename = ?", (filename,))
    if not attachment_record:
        current_app.logger.warning("Download attempt for non-existent attachment record", extra=log_extra)
        # The @handle_view_exceptions decorator will catch this abort and redirect.
        # If a specific "not found" page for attachments is desired, this could be handled differently.
        abort(404)
    # Further checks could involve ensuring the user has rights to the ticket_id from attachment_record.

    response = send_from_directory(current_app.config['UPLOAD_FOLDER'], filename, as_attachment=True)
    current_app.logger.info("Attachment download initiated", extra=log_extra)
    return response
    # FileNotFoundError will be caught by @handle_view_exceptions
    # Other exceptions will also be caught by @handle_view_exceptions
