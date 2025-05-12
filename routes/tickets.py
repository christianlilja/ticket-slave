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
import os
import threading

tickets_bp = Blueprint('tickets_bp', __name__)

@tickets_bp.route('/ticket/<int:ticket_id>')
@login_required
def ticket_detail(ticket_id):
    with get_db() as conn:
        ticket = conn.execute('SELECT * FROM tickets WHERE id = ?', (ticket_id,)).fetchone()
        if ticket is None:
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
        for file in raw_attachments:
            file_dict = dict(file)
            try:
                file_size = os.path.getsize(file['filepath'])
                file_dict['size_kb'] = round(file_size / 1024, 1)
            except Exception:
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
    assigned_to = request.form['assigned_to'] or None
    with get_db() as conn:
        conn.execute('UPDATE tickets SET assigned_to = ? WHERE id = ?', (assigned_to, ticket_id))
    if assigned_to:
        threading.Thread(target=notify_assigned_user, args=(ticket_id, 'assigned', session['user_id']), daemon=True).start()
    flash('Assigned user updated successfully!', 'success')
    return redirect(url_for('tickets_bp.ticket_detail', ticket_id=ticket_id))

@tickets_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_ticket():
    with get_db() as conn:
        queues = conn.execute("SELECT id, name FROM queues").fetchall()
        users = conn.execute("SELECT id, username FROM users").fetchall()

        if request.method == 'POST':
            title = request.form['title']
            description = request.form['description']
            priority = request.form['priority']
            deadline = request.form['deadline']
            queue_id = request.form.get('queue_id')
            assigned_to = request.form.get('assigned_to') or None
            created_at = datetime.now().isoformat()
            status = 'open'

            if not title or not description:
                flash("Both title and description are required.", "danger")
                return redirect(url_for("tickets_bp.create_ticket"))

            try:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO tickets (title, description, status, priority, deadline, created_at, queue_id, assigned_to)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                    (title, description, status, priority, deadline, created_at, queue_id, assigned_to))
                ticket_id = cursor.lastrowid

                file = request.files.get('file')
                if file and file.filename:
                    if allowed_file(file.filename):
                        original_filename = secure_filename(file.filename)
                        timestamped_filename = f"{ticket_id}_{datetime.now().timestamp()}_{original_filename}"
                        save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], timestamped_filename)
                        file.save(save_path)

                        cursor.execute('''
                            INSERT INTO attachments (ticket_id, original_filename, stored_filename, filepath, uploaded_at)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (ticket_id, original_filename, timestamped_filename, save_path, datetime.now().isoformat()))
                    else:
                        flash("Invalid file type. Upload aborted.", "warning")

                conn.commit()

                if assigned_to:
                    threading.Thread(
                        target=notify_assigned_user,
                        args=(ticket_id, 'assigned', session.get('user_id')),
                        daemon=True
                    ).start()

                flash('Ticket created successfully!', 'success')
                return redirect(url_for('main_bp.index'))
            except Exception as e:
                current_app.logger.error(f"Error creating ticket: {e}")
                flash('An error occurred while creating the ticket.', 'danger')
                return render_template('create_ticket.html', queues=queues, users=users)

    return render_template('create_ticket.html', queues=queues, users=users)

@tickets_bp.route('/ticket/<int:ticket_id>/comment', methods=['POST'])
@login_required
def add_comment(ticket_id):
    content = request.form['content']
    user_id = session.get('user_id')
    created_at = datetime.now().isoformat()
    if not content:
        flash('Comment cannot be empty.', 'danger')
        return redirect(url_for('tickets_bp.ticket_detail', ticket_id=ticket_id))
    with get_db() as conn:
        conn.execute('INSERT INTO comments (ticket_id, content, user_id, created_at) VALUES (?, ?, ?, ?)', (ticket_id, content, user_id, created_at))
    threading.Thread(target=notify_assigned_user,args=(ticket_id, 'new_comment', user_id), daemon=True).start()
    flash('Comment added successfully!', 'success')
    return redirect(url_for('tickets_bp.ticket_detail', ticket_id=ticket_id))

@tickets_bp.route('/ticket/<int:ticket_id>/status', methods=['POST'])
@login_required
def update_status(ticket_id):
    new_status = request.form['status']
    user_id = session.get('user_id')
    with get_db() as conn:
        conn.execute('UPDATE tickets SET status = ? WHERE id = ?', (new_status, ticket_id))
    threading.Thread(target=notify_assigned_user, args=(ticket_id, 'status', user_id), daemon=True).start()
    flash('Status updated successfully!', 'success')
    return redirect(url_for('tickets_bp.ticket_detail', ticket_id=ticket_id))

@tickets_bp.route('/ticket/<int:ticket_id>/priority', methods=['POST'])
@login_required
def update_priority(ticket_id):
    new_priority = request.form['priority']
    user_id = session.get('user_id')
    with get_db() as conn:
        conn.execute('UPDATE tickets SET priority = ? WHERE id = ?', (new_priority, ticket_id))
    threading.Thread(target=notify_assigned_user, args=(ticket_id, 'priority', user_id), daemon=True).start()
    flash('Priority updated successfully!', 'success')
    return redirect(url_for('tickets_bp.ticket_detail', ticket_id=ticket_id))

@tickets_bp.route('/uploads/<path:filename>')
@login_required
def download_attachment(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename, as_attachment=True)
