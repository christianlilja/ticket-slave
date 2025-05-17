from flask import (
    Blueprint, render_template, request, redirect, url_for, flash,
    session, abort, send_from_directory, current_app
)
from datetime import datetime
from werkzeug.utils import secure_filename
from utils.decorators import login_required
from app.db import get_db
from app.notifications_core import notify_assigned_user
from utils.files import allowed_file
from utils.context_runner import run_in_app_context
import os

tickets_bp = Blueprint('tickets_bp', __name__)

@tickets_bp.route('/ticket/<int:ticket_id>')
@login_required
def ticket_detail(ticket_id):
    user_id = session.get('user_id')
    username = session.get('username')
    log_extra = {'user_id': user_id, 'username': username, 'ticket_id': ticket_id}
    
    current_app.logger.info("User viewing ticket details", extra=log_extra)

    with get_db() as conn:
        ticket = conn.execute('SELECT * FROM tickets WHERE id = ?', (ticket_id,)).fetchone()
        if ticket is None:
            current_app.logger.warning("User attempted to view non-existent ticket", extra=log_extra)
            abort(404)

        comments = conn.execute('''
            SELECT comments.*, users.username
            FROM comments
            LEFT JOIN users ON comments.user_id = users.id
            WHERE ticket_id = ?
            ORDER BY created_at ASC
        ''', (ticket_id,)).fetchall()

        users = conn.execute('SELECT id, username FROM users').fetchall()

        raw_attachments = conn.execute(
            'SELECT * FROM attachments WHERE ticket_id = ?', (ticket_id,)
        ).fetchall()

        attachments = []
        for file_attach in raw_attachments: # Renamed to avoid conflict with 'file' from request.files
            file_dict = dict(file_attach)
            try:
                file_size = os.path.getsize(file_attach['filepath'])
                file_dict['size_kb'] = round(file_size / 1024, 1)
            except Exception as e:
                current_app.logger.warning(
                    f"Could not get size for attachment {file_attach['original_filename']}",
                    extra={**log_extra, 'attachment_id': file_attach['id'], 'filepath': file_attach['filepath'], 'error': str(e)}
                )
                file_dict['size_kb'] = None
            attachments.append(file_dict)

    return render_template(
        'ticket_detail.html',
        ticket=ticket,
        comments=comments,
        users=users,
        attachments=attachments
    )

@tickets_bp.route('/ticket/<int:ticket_id>/assign', methods=['POST'])
@login_required
def update_assigned_to(ticket_id):
    user_id = session.get('user_id')
    username = session.get('username')
    new_assigned_user_id_str = request.form.get('assigned_to')
    validated_assigned_user_id = None

    if new_assigned_user_id_str and new_assigned_user_id_str.strip(): # Check if not empty string and not just whitespace
        try:
            val_user_id = int(new_assigned_user_id_str)
            with get_db() as conn_check: # Use a different name for the connection variable if inside another 'with get_db()'
                user_exists = conn_check.execute("SELECT 1 FROM users WHERE id = ?", (val_user_id,)).fetchone()
                if not user_exists:
                    flash('Selected user for assignment does not exist.', 'danger')
                    current_app.logger.warning(f"Update assignment failed: User ID {val_user_id} does not exist.", extra={'user_id': user_id, 'username': username, 'ticket_id': ticket_id})
                    return redirect(url_for('tickets_bp.ticket_detail', ticket_id=ticket_id))
            validated_assigned_user_id = val_user_id
        except ValueError:
            flash('Invalid user ID for assignment.', 'danger')
            current_app.logger.warning(f"Update assignment failed: Invalid user ID '{new_assigned_user_id_str}'.", extra={'user_id': user_id, 'username': username, 'ticket_id': ticket_id})
            return redirect(url_for('tickets_bp.ticket_detail', ticket_id=ticket_id))
    # If new_assigned_user_id_str is empty or None, validated_assigned_user_id remains None, which is fine for unassigning.

    log_extra = {
        'user_id': user_id,
        'username': username,
        'ticket_id': ticket_id,
        'new_assigned_user_id': validated_assigned_user_id # Corrected variable name
    }
    current_app.logger.info("User attempting to update ticket assignment", extra=log_extra)

    try:
        with get_db() as conn:
            # Optionally, get old assigned user for logging comparison
            # old_assignment = conn.execute('SELECT assigned_to FROM tickets WHERE id = ?', (ticket_id,)).fetchone()
            # log_extra['old_assigned_user_id'] = old_assignment['assigned_to'] if old_assignment else None
            
            conn.execute('UPDATE tickets SET assigned_to = ? WHERE id = ?', (validated_assigned_user_id, ticket_id))
            conn.commit() # Make sure to commit

        if validated_assigned_user_id: # Check the validated ID
            # Consider logging before potentially long-running notification
            current_app.logger.info("Ticket assignment updated, queuing notification", extra=log_extra)
            run_in_app_context(current_app._get_current_object(), notify_assigned_user, ticket_id, 'assigned', user_id)
        else:
            current_app.logger.info("Ticket unassigned", extra=log_extra)
            
        flash('Assigned user updated successfully!', 'success')
    except Exception as e:
        current_app.logger.error(
            "Error updating ticket assignment",
            extra=log_extra,
            exc_info=True
        )
        flash('An error occurred while updating assignment.', 'danger')
    return redirect(url_for('tickets_bp.ticket_detail', ticket_id=ticket_id))

@tickets_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_ticket():
    user_id = session.get('user_id')
    username = session.get('username')
    
    if request.method == 'GET':
        current_app.logger.info(
            "User accessed create ticket page",
            extra={'user_id': user_id, 'username': username}
        )

    with get_db() as conn:
        queues = conn.execute("SELECT id, name FROM queues").fetchall()
        users = conn.execute("SELECT id, username FROM users").fetchall()

        if request.method == 'POST':
            title = request.form.get('title')
            description = request.form.get('description')
            priority = request.form.get('priority')
            deadline = request.form.get('deadline') # Consider validating date format
            queue_id = request.form.get('queue_id')
            assigned_to_user_id = request.form.get('assigned_to') or None # Renamed for clarity
            created_at = datetime.now().isoformat()
            status = 'open' # Default status

            log_extra_create = {
                'user_id': user_id,
                'username': username,
                'ticket_title': title, # Log title for easier identification
                'priority': priority,
                'queue_id': queue_id,
                'assigned_to_user_id': assigned_to_user_id
            }
            current_app.logger.info("User attempting to create new ticket", extra=log_extra_create)

            errors = {}
            if not title:
                errors['title'] = "Title is required."
            if not description:
                errors['description'] = "Description is required."

            allowed_priorities = ['low', 'medium', 'high']
            if priority not in allowed_priorities:
                errors['priority'] = f"Invalid priority. Must be one of: {', '.join(allowed_priorities)}."

            validated_deadline = None
            if deadline:
                try:
                    validated_deadline = datetime.fromisoformat(deadline).isoformat() # Store consistently
                except ValueError:
                    errors['deadline'] = "Invalid deadline format. Please use YYYY-MM-DDTHH:MM."
            
            validated_queue_id = None
            if queue_id:
                try:
                    val_queue_id = int(queue_id)
                    # Check if queue exists
                    queue_exists = conn.execute("SELECT 1 FROM queues WHERE id = ?", (val_queue_id,)).fetchone()
                    if not queue_exists:
                        errors['queue_id'] = "Selected queue does not exist."
                    else:
                        validated_queue_id = val_queue_id
                except ValueError:
                    errors['queue_id'] = "Invalid queue ID."
            
            validated_assigned_to_user_id = None
            if assigned_to_user_id: # assigned_to_user_id is already None if not provided or empty string
                try:
                    val_assigned_user_id = int(assigned_to_user_id)
                    # Check if user exists
                    user_exists = conn.execute("SELECT 1 FROM users WHERE id = ?", (val_assigned_user_id,)).fetchone()
                    if not user_exists:
                        errors['assigned_to'] = "Selected user to assign does not exist."
                    else:
                        validated_assigned_to_user_id = val_assigned_user_id
                except ValueError:
                    errors['assigned_to'] = "Invalid user ID for assignment."

            if errors:
                for field, msg in errors.items():
                    flash(msg, "danger")
                current_app.logger.warning(f"Ticket creation failed due to validation errors: {errors}", extra=log_extra_create)
                return render_template('create_ticket.html', queues=queues, users=users,
                                       title=title, description=description, priority=priority,
                                       deadline=deadline, queue_id=queue_id, assigned_to=assigned_to_user_id,
                                       errors=errors) # Pass errors to template

            # Use validated values from here on
            deadline_to_save = validated_deadline # This is already an ISO string or None
            queue_id_to_save = validated_queue_id
            assigned_to_user_id_to_save = validated_assigned_to_user_id


            try:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO tickets (title, description, status, priority, deadline, created_at, queue_id, assigned_to, created_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', # Added created_by
                    (title, description, status, priority, deadline_to_save, created_at, queue_id_to_save, assigned_to_user_id_to_save, user_id))
                ticket_id = cursor.lastrowid
                log_extra_create['created_ticket_id'] = ticket_id

                file_attachment = request.files.get('file') # Renamed for clarity
                if file_attachment and file_attachment.filename:
                    if allowed_file(file_attachment.filename):
                        original_filename = secure_filename(file_attachment.filename)
                        # Using ticket_id in filename is good
                        timestamped_filename = f"{ticket_id}_{datetime.now().timestamp()}_{original_filename}"
                        save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], timestamped_filename)
                        file_attachment.save(save_path)

                        cursor.execute('''
                            INSERT INTO attachments (ticket_id, original_filename, stored_filename, filepath, uploaded_at, user_id)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (ticket_id, original_filename, timestamped_filename, save_path, datetime.now().isoformat(), user_id))
                        current_app.logger.info(
                            "File attached to new ticket",
                            extra={**log_extra_create, 'filename': original_filename, 'stored_filename': timestamped_filename}
                        )
                    else:
                        current_app.logger.warning(
                            "Invalid file type for attachment during ticket creation",
                            extra={**log_extra_create, 'filename': file_attachment.filename}
                        )
                        flash("Invalid file type. File not uploaded, but ticket created (if other fields were valid).", "warning")
                        # Decide if ticket creation should proceed or fail if attachment fails

                conn.commit()
                current_app.logger.info("New ticket created successfully", extra=log_extra_create)

                if assigned_to_user_id:
                     current_app.logger.info("Queuing assignment notification for new ticket", extra=log_extra_create)
                     run_in_app_context(current_app._get_current_object(), notify_assigned_user, ticket_id, 'assigned', user_id)

                flash('Ticket created successfully!', 'success')
                return redirect(url_for('main_bp.index')) # Or to the new ticket's detail page
            except Exception as e:
                # The existing logger.error is fine, but let's add more context
                current_app.logger.error(
                    "Error creating ticket",
                    extra=log_extra_create,
                    exc_info=True # This will add stack trace
                )
                flash('An error occurred while creating the ticket.', 'danger')
                # Fall through to render template with original values
                return render_template('create_ticket.html', queues=queues, users=users,
                                   title=title, description=description, priority=priority,
                                   deadline=deadline, queue_id=queue_id, assigned_to=assigned_to_user_id)


    return render_template('create_ticket.html', queues=queues, users=users)

@tickets_bp.route('/ticket/<int:ticket_id>/comment', methods=['POST'])
@login_required
def add_comment(ticket_id):
    content = request.form.get('content') # Use .get for safety
    user_id = session.get('user_id')
    username = session.get('username')
    created_at = datetime.now().isoformat()

    log_extra = {
        'user_id': user_id,
        'username': username,
        'ticket_id': ticket_id
    }
    current_app.logger.info("User attempting to add comment to ticket", extra=log_extra)

    if not content:
        current_app.logger.warning("Add comment failed: Content was empty", extra=log_extra)
        flash('Comment cannot be empty.', 'danger')
        return redirect(url_for('tickets_bp.ticket_detail', ticket_id=ticket_id))
    
    try:
        with get_db() as conn:
            conn.execute('INSERT INTO comments (ticket_id, content, user_id, created_at) VALUES (?, ?, ?, ?)', (ticket_id, content, user_id, created_at))
            conn.commit() # Make sure to commit
        
        current_app.logger.info("Comment added successfully, queuing notification", extra=log_extra)
        run_in_app_context(current_app._get_current_object(), notify_assigned_user, ticket_id, 'new_comment', user_id)
        flash('Comment added successfully!', 'success')
    except Exception as e:
        current_app.logger.error(
            "Error adding comment to ticket",
            extra=log_extra,
            exc_info=True
        )
        flash('An error occurred while adding the comment.', 'danger')
    return redirect(url_for('tickets_bp.ticket_detail', ticket_id=ticket_id))

@tickets_bp.route('/ticket/<int:ticket_id>/status', methods=['POST'])
@login_required
def update_status(ticket_id):
    new_status = request.form.get('status') # Use .get for safety
    user_id = session.get('user_id')
    username = session.get('username')

    log_extra = {
        'user_id': user_id,
        'username': username,
        'ticket_id': ticket_id,
        'new_status': new_status
    }
    current_app.logger.info("User attempting to update ticket status", extra=log_extra)

    allowed_statuses = ['open', 'in progress', 'pending', 'resolved', 'closed'] # Define your allowed statuses
    if not new_status:
        current_app.logger.warning("Update status failed: New status not provided", extra=log_extra)
        flash('New status cannot be empty.', 'danger')
        return redirect(url_for('tickets_bp.ticket_detail', ticket_id=ticket_id))
    if new_status not in allowed_statuses:
        current_app.logger.warning(f"Update status failed: Invalid status '{new_status}'", extra=log_extra)
        flash(f"Invalid status. Must be one of: {', '.join(allowed_statuses)}.", 'danger')
        return redirect(url_for('tickets_bp.ticket_detail', ticket_id=ticket_id))

    try:
        with get_db() as conn:
            # Optionally, log old status
            # old_status_row = conn.execute('SELECT status FROM tickets WHERE id = ?', (ticket_id,)).fetchone()
            # log_extra['old_status'] = old_status_row['status'] if old_status_row else 'N/A'
            conn.execute('UPDATE tickets SET status = ? WHERE id = ?', (new_status, ticket_id))
            conn.commit() # Make sure to commit

        current_app.logger.info("Ticket status updated successfully, queuing notification", extra=log_extra)
        run_in_app_context(current_app._get_current_object(), notify_assigned_user, ticket_id, 'status', user_id)
        flash('Status updated successfully!', 'success')
    except Exception as e:
        current_app.logger.error(
            "Error updating ticket status",
            extra=log_extra,
            exc_info=True
        )
        flash('An error occurred while updating status.', 'danger')
    return redirect(url_for('tickets_bp.ticket_detail', ticket_id=ticket_id))

@tickets_bp.route('/ticket/<int:ticket_id>/priority', methods=['POST'])
@login_required
def update_priority(ticket_id):
    new_priority = request.form.get('priority') # Use .get for safety
    user_id = session.get('user_id')
    username = session.get('username')

    log_extra = {
        'user_id': user_id,
        'username': username,
        'ticket_id': ticket_id,
        'new_priority': new_priority
    }
    current_app.logger.info("User attempting to update ticket priority", extra=log_extra)

    allowed_priorities = ['low', 'medium', 'high']
    if not new_priority:
        current_app.logger.warning("Update priority failed: New priority not provided", extra=log_extra)
        flash('New priority cannot be empty.', 'danger')
        return redirect(url_for('tickets_bp.ticket_detail', ticket_id=ticket_id))
    if new_priority not in allowed_priorities:
        current_app.logger.warning(f"Update priority failed: Invalid priority '{new_priority}'", extra=log_extra)
        flash(f"Invalid priority. Must be one of: {', '.join(allowed_priorities)}.", 'danger')
        return redirect(url_for('tickets_bp.ticket_detail', ticket_id=ticket_id))

    try:
        with get_db() as conn:
            # Optionally, log old priority
            # old_priority_row = conn.execute('SELECT priority FROM tickets WHERE id = ?', (ticket_id,)).fetchone()
            # log_extra['old_priority'] = old_priority_row['priority'] if old_priority_row else 'N/A'
            conn.execute('UPDATE tickets SET priority = ? WHERE id = ?', (new_priority, ticket_id))
            conn.commit() # Make sure to commit

        current_app.logger.info("Ticket priority updated successfully, queuing notification", extra=log_extra)
        run_in_app_context(current_app._get_current_object(), notify_assigned_user, ticket_id, 'priority', user_id)
        flash('Priority updated successfully!', 'success')
    except Exception as e:
        current_app.logger.error(
            "Error updating ticket priority",
            extra=log_extra,
            exc_info=True
        )
        flash('An error occurred while updating priority.', 'danger')
    return redirect(url_for('tickets_bp.ticket_detail', ticket_id=ticket_id))

@tickets_bp.route('/uploads/<path:filename>')
@login_required
def download_attachment(filename):
    user_id = session.get('user_id')
    username = session.get('username')
    # Try to extract ticket_id from filename if it follows "ticketid_timestamp_original.ext"
    ticket_id_from_filename = None
    try:
        if '_' in filename:
            ticket_id_from_filename = int(filename.split('_')[0])
    except ValueError:
        pass # Not a critical error if parsing fails, just won't be in log

    log_extra = {
        'user_id': user_id,
        'username': username,
        'filename': filename,
        'ticket_id_from_filename': ticket_id_from_filename # May be None
    }
    current_app.logger.info("User attempting to download attachment", extra=log_extra)
    
    # Security: Ensure the filename is safe and doesn't allow directory traversal beyond UPLOAD_FOLDER
    # secure_filename() is usually for upload, but checking for '..' or '/' might be good here too.
    # However, send_from_directory itself should be relatively safe if UPLOAD_FOLDER is well-defined.

    try:
        response = send_from_directory(current_app.config['UPLOAD_FOLDER'], filename, as_attachment=True)
        current_app.logger.info("Attachment download initiated successfully", extra=log_extra)
        return response
    except FileNotFoundError:
        current_app.logger.error("Attachment download failed: File not found on server", extra=log_extra)
        abort(404) # Or flash a message and redirect
    except Exception as e:
        current_app.logger.error(
            "Attachment download failed due to an unexpected error",
            extra=log_extra,
            exc_info=True
        )
        abort(500) # Or flash a message
