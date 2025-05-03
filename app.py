from db import init_db, get_db
from settings import DEFAULT_SETTINGS, load_settings, ensure_default_settings, get_db, ensure_admin_user
from flask import Flask, render_template, request, redirect, url_for, session, flash, current_app, abort, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
from functools import wraps
from jinja2 import TemplateNotFound, TemplateSyntaxError
from contextlib import contextmanager
import sqlite3
import os
from notifications import *

# App setup
app = Flask(__name__)
IS_PROD = os.environ.get('FLASK_ENV') == 'production'

if IS_PROD and not os.environ.get('SECRET_KEY'):
    raise RuntimeError("SECRET_KEY must be set in production")
if app.secret_key == 'dev-secret-key':
    app.logger.warning("Running with default secret key. Not recommended for production.")

app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key')

UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB limit
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf', 'docx', 'txt'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            flash('Admin access required.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def notify_assigned_user(ticket_id, event_type, user_id):
    with get_db() as conn:
        ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if not ticket or not ticket['assigned_to']:
            return

        assigned_user = conn.execute("""
            SELECT id, username, email, pushover_user_key, pushover_api_token, 
                   notify_email, notify_pushover
            FROM users WHERE id = ?
        """, (ticket['assigned_to'],)).fetchone()

        if not assigned_user or user_id == assigned_user['id']:
            return  # Don't notify the person who triggered the action

        subject = ""
        message = ""

        if event_type == "assigned":
            subject = f"Ticket #{ticket_id} Assigned to You"
            message = f"You have been assigned to ticket #{ticket_id}: {ticket['title']}"
        elif event_type == "status":
            subject = f"Ticket #{ticket_id} Status Updated"
            message = f"The status of ticket #{ticket_id} has changed to '{ticket['status']}'"
        elif event_type == "priority":
            subject = f"Ticket #{ticket_id} Priority Updated"
            message = f"The priority of ticket #{ticket_id} has changed to '{ticket['priority']}'"
        elif event_type == "new_comment":
            subject = f"New Comment on Ticket #{ticket_id}"
            message = f"A new comment was added to ticket #{ticket_id}."

        # Send Pushover if enabled
        if assigned_user['notify_pushover'] == 1 and assigned_user['pushover_user_key'] and assigned_user['pushover_api_token']:
            send_pushover_notification(
                assigned_user['pushover_user_key'],
                assigned_user['pushover_api_token'],
                title=subject,
                message=message
            )

        # Send Email if enabled
        if assigned_user['notify_email'] == 1 and assigned_user['email']:
            send_email_notification(
                assigned_user['email'],
                subject=subject,
                body=message
            )


@app.errorhandler(TemplateNotFound)
def handle_template_not_found(e):
    return render_template("error.html", error="Template not found", details=str(e)), 500

@app.errorhandler(TemplateSyntaxError)
def handle_template_syntax_error(e):
    current_app.logger.error(f"Template syntax error: {e}")
    msg = "There is a syntax issue in one of the templates."
    return render_template("error.html", error=msg), 500

@app.errorhandler(404)
def not_found_error(e):
    current_app.logger.warning(f"404 Error: {e}")
    return render_template("error.html", error="Page not found (404)"), 404

@app.errorhandler(500)
def internal_error(e):
    current_app.logger.error(f"500 Error: {e}")
    if current_app.debug:
        return render_template("error.html", error="Internal Server Error (500)", details=str(e)), 500
    else:
        return render_template("error.html", error="Something went wrong on our end."), 500
    

@app.route("/")
@login_required
def index():
    assigned_only = request.args.get('assigned_only', 'false').lower() == 'true'
    show_closed = request.args.get('show_closed', 'false').lower() == 'true'
    sort_by = request.args.get('sort_by', 'created_at')
    page = request.args.get('page', 1, type=int)
    per_page = 15

    sort_columns = {
        'created_at': 'tickets.created_at DESC',
        'deadline': 'tickets.deadline DESC',
        'priority': '''CASE LOWER(tickets.priority)
                        WHEN 'high' THEN 1
                        WHEN 'medium' THEN 2
                        WHEN 'low' THEN 3
                        ELSE 4
                      END''',
        'queue': 'queues.name ASC',
        'assigned_to': 'users.username ASC'
    }
    order_by_clause = sort_columns.get(sort_by, 'tickets.created_at DESC')

    base_query = '''
        FROM tickets
        LEFT JOIN queues ON tickets.queue_id = queues.id
        LEFT JOIN users ON tickets.assigned_to = users.id
    '''

    where_clauses = []
    params = []

    if not show_closed:
        where_clauses.append('LOWER(tickets.status) != "closed"')

    if assigned_only:
        where_clauses.append('tickets.assigned_to = ?')
        params.append(session.get('user_id'))

    where_clause = ''
    if where_clauses:
        where_clause = 'WHERE ' + ' AND '.join(where_clauses)

    count_query = f'SELECT COUNT(*) {base_query} {where_clause}'

    with get_db() as conn:
        total = conn.execute(count_query, params).fetchone()[0]

    total_pages = (total + per_page - 1) // per_page
    offset = (page - 1) * per_page

    query = f'''
        SELECT 
            tickets.*, 
            queues.name AS queue,
            users.username AS assigned_to_username
        {base_query}
        {where_clause}
        ORDER BY {order_by_clause}
        LIMIT ? OFFSET ?
    '''

    tickets = []
    with get_db() as conn:
        rows = conn.execute(query, (*params, per_page, offset)).fetchall()
        for row in rows:
            deadline = row['deadline']
            is_overdue = False
            if deadline:
                try:
                    deadline_dt = datetime.fromisoformat(deadline)
                    is_overdue = datetime.now() > deadline_dt
                except ValueError:
                    pass

            try:
                created_at_dt = datetime.fromisoformat(row['created_at'])
                created_at_formatted = created_at_dt.strftime('%Y:%m:%d %H:%M:%S')
            except Exception:
                created_at_formatted = "Unknown"

            tickets.append({
                'id': row['id'],
                'title': row['title'],
                'description': row['description'],
                'status': row['status'],
                'priority': row['priority'],
                'deadline': deadline,
                'created_at': row['created_at'],
                'created_at_formatted': created_at_formatted,
                'is_overdue': is_overdue,
                'queue': row['queue'],
                'assigned_to': row['assigned_to_username'] or "Unassigned"
            })

    return render_template(
        'index.html',
        tickets=tickets,
        show_closed=show_closed,
        assigned_only=assigned_only,
        sort_by=sort_by,
        page=page,
        total_pages=total_pages
    )

@app.route('/register', methods=['GET', 'POST'])
def register():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key = 'allow_registration'")
        setting = cur.fetchone()

        if not setting or setting['value'] != '1':
            flash('Registration is currently disabled.', 'warning')
            return redirect(url_for('login'))

    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute('SELECT * FROM users WHERE username = ?', (username,))
            if cur.fetchone():
                flash('Username already exists', 'danger')
                return redirect(url_for('register'))

            cur.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
            flash('Registered successfully. Please log in.', 'success')
            return redirect(url_for('login'))

    return render_template('register.html')

@app.route("/users", methods=["GET", "POST"])
@login_required
def manage_users():
    if not session.get("is_admin"):
        return redirect(url_for("index"))

    with get_db() as conn:
        conn.row_factory = sqlite3.Row  # Important! Make rows dict-like
        cursor = conn.cursor()

        # Add user
        if request.method == "POST" and "new_username" in request.form:
            username = request.form["new_username"]
            password = generate_password_hash(request.form["new_password"])
            is_admin = 0
            try:
                cursor.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)", (username, password, is_admin))
                conn.commit()
            except sqlite3.IntegrityError:
                flash("Username already exists.", "danger")

        # Delete user
        if request.method == "POST" and "delete_user" in request.form:
            user_to_delete = request.form["delete_user"]
            cursor.execute("SELECT is_admin FROM users WHERE username = ?", (user_to_delete,))
            user = cursor.fetchone()
            if user and user["is_admin"] == 1:
                flash("Cannot delete admin user.", "danger")
            else:
                cursor.execute("DELETE FROM users WHERE username = ?", (user_to_delete,))
                conn.commit()

        cursor.execute("SELECT id, username, is_admin FROM users")
        users = cursor.fetchall()

    return render_template("users.html", users=users)

@app.route('/notifications', methods=['GET', 'POST'])
@login_required
def notifications():
    with get_db() as conn:
        user = conn.execute('SELECT email, pushover_user_key, pushover_api_token, notify_email, notify_pushover FROM users WHERE username = ?', (session['username'],)).fetchone()

        if request.method == 'POST':
            email = request.form['email']
            pushover_user_key = request.form['pushover_user_key']
            pushover_api_token = request.form['pushover_api_token']
            notify_email = 1 if 'notify_email' in request.form else 0
            notify_pushover = 1 if 'notify_pushover' in request.form else 0

            conn.execute('''
                UPDATE users 
                SET email = ?, pushover_user_key = ?, pushover_api_token = ?, 
                    notify_email = ?, notify_pushover = ?
                WHERE username = ?
            ''', (email, pushover_user_key, pushover_api_token, notify_email, notify_pushover, session['username']))
            conn.commit()

            # Optional: send test notification if pushover enabled
            if notify_pushover and pushover_user_key and pushover_api_token:
                threading.Thread(
                    target=send_pushover_notification,
                    args=(pushover_user_key, pushover_api_token, "Pushover Test", "Your Pushover settings have been saved."),
                    daemon=True
                ).start()

            flash('Notification settings updated successfully.', 'success')
            return redirect(url_for('notifications'))

    return render_template('notifications.html', user=user)


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if not session.get('is_admin'):
        return redirect(url_for('index'))

    with get_db() as conn:
        cur = conn.cursor()

        if request.method == 'POST':
            allow_registration = 1 if 'allow_registration' in request.form else 0
            enable_api = 1 if 'enable_api' in request.form else 0
            smtp_server = request.form.get('smtp_server', '')
            smtp_port = request.form.get('smtp_port', '25')
            smtp_from_email = request.form.get('smtp_from_email', '')
            smtp_username = request.form.get('smtp_username', '')
            smtp_password = request.form.get('smtp_password', '')
            smtp_use_tls = 1 if 'smtp_use_tls' in request.form else 0

            cur.execute("UPDATE settings SET value = ? WHERE key = 'allow_registration'", (allow_registration,))
            cur.execute("UPDATE settings SET value = ? WHERE key = 'enable_api'", (enable_api,))
            cur.execute("UPDATE settings SET value = ? WHERE key = 'smtp_server'", (smtp_server,))
            cur.execute("UPDATE settings SET value = ? WHERE key = 'smtp_port'", (smtp_port,))
            cur.execute("UPDATE settings SET value = ? WHERE key = 'smtp_from_email'", (smtp_from_email,))
            cur.execute("UPDATE settings SET value = ? WHERE key = 'smtp_username'", (smtp_username,))
            cur.execute("UPDATE settings SET value = ? WHERE key = 'smtp_password'", (smtp_password,))
            cur.execute("UPDATE settings SET value = ? WHERE key = 'smtp_use_tls'", (smtp_use_tls,))
            conn.commit()
            flash('Settings updated.', 'success')

        # Rename settings_data to settings
        settings = {}
        for row in cur.execute("SELECT key, value FROM settings").fetchall():
            settings[row['key']] = row['value']

    return render_template('settings.html', settings=settings)




@app.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    with get_db() as conn:
        user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()

        if not user:
            abort(404)

        if request.method == 'POST':
            email = request.form['email']
            pushover_user_key = request.form['pushover_user_key']
            pushover_api_token = request.form['pushover_api_token']
            new_password = request.form.get('new_password')

            # Always update email and pushover fields
            conn.execute(
                'UPDATE users SET email = ?, pushover_user_key = ?, pushover_api_token = ? WHERE id = ?', 
                (email, pushover_user_key, pushover_api_token, user_id)
            )

            # Only update password if a new password was entered
            if new_password:
                hashed_password = generate_password_hash(new_password)
                conn.execute('UPDATE users SET password = ? WHERE id = ?', (hashed_password, user_id))

            conn.commit()
            flash('User updated successfully.', 'success')
            return redirect(url_for('manage_users'))

    return render_template('edit_user.html', user=user)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user_id = session.get('user_id')

    with get_db() as conn:
        user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()

        if not user:
            abort(404)

        if request.method == 'POST':
            email = request.form['email']
            pushover_user_key = request.form['pushover_user_key']
            pushover_api_token = request.form['pushover_api_token']
            notify_email = 1 if 'notify_email' in request.form else 0
            notify_pushover = 1 if 'notify_pushover' in request.form else 0
            new_password = request.form.get('new_password')

            conn.execute(
                '''UPDATE users
                   SET email = ?, pushover_user_key = ?, pushover_api_token = ?,
                       notify_email = ?, notify_pushover = ?
                   WHERE id = ?''',
                (email, pushover_user_key, pushover_api_token,
                 notify_email, notify_pushover, user_id)
            )

            if new_password:
                hashed_password = generate_password_hash(new_password)
                conn.execute('UPDATE users SET password = ? WHERE id = ?', (hashed_password, user_id))

            conn.commit()

            # Handle "Test Notification"
            if 'test_notification' in request.form:
                if notify_pushover and pushover_user_key and pushover_api_token:
                    threading.Thread(
                        target=send_pushover_notification,
                        args=(pushover_user_key, pushover_api_token, "Test", "This is a test Pushover notification"),
                        daemon=True
                    ).start()
                if notify_email and email:
                    threading.Thread(
                        target=send_email_notification,
                        args=(email, "Test", "This is a test email notification"),
                        daemon=True
                    ).start()
                flash('Test notification sent.', 'info')
            else:
                flash('Profile updated successfully.', 'success')

            return redirect(url_for('profile'))

    return render_template('profile.html', user=user)

@app.route('/login', methods=['GET', 'POST'])
def login():
    allow_registration = True

    with get_db() as conn:
        cur = conn.cursor()

        # Check setting BEFORE anything else
        cur.execute("SELECT value FROM settings WHERE key = 'allow_registration'")
        setting = cur.fetchone()
        if setting and setting['value'] == '0':
            allow_registration = False

        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']

            cur.execute('SELECT * FROM users WHERE username = ?', (username,))
            user = cur.fetchone()

            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['is_admin'] = bool(user['is_admin'])
                return redirect(url_for('index'))
            else:
                flash('Invalid credentials.', 'danger')

    return render_template('login.html', allow_registration=allow_registration)


@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for('login'))

@app.route("/queues", methods=["GET", "POST"])
@login_required
def manage_queues():
    with get_db() as conn:
        cursor = conn.cursor()
        if request.method == "POST":
            name = request.form["name"]
            cursor.execute("INSERT INTO queues (name) VALUES (?)", (name,))
            conn.commit()
        cursor.execute("SELECT * FROM queues")
        queues = cursor.fetchall()
    return render_template("queues.html", queues=queues)

@app.route('/ticket/<int:ticket_id>')
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

        # Add file size in KB to each attachment
        attachments = []
        for file in raw_attachments:
            file_dict = dict(file)
            try:
                file_size = os.path.getsize(file['filepath'])
                file_dict['size_kb'] = round(file_size / 1024, 1)
            except Exception:
                file_dict['size_kb'] = None  # If file missing
            attachments.append(file_dict)

    return render_template(
        'ticket_detail.html',
        ticket=ticket,
        comments=comments,
        users=users,
        attachments=attachments
    )

@app.route('/ticket/<int:ticket_id>/assign', methods=['POST'])
@login_required
def update_assigned_to(ticket_id):
    assigned_to = request.form['assigned_to'] or None
    with get_db() as conn:
        conn.execute('UPDATE tickets SET assigned_to = ? WHERE id = ?', (assigned_to, ticket_id))
    if assigned_to:
        threading.Thread(target=notify_assigned_user, args=(ticket_id, 'assigned'), daemon=True).start()
    flash('Assigned user updated successfully!', 'success')
    return redirect(url_for('ticket_detail', ticket_id=ticket_id))


@app.route('/create', methods=['GET', 'POST'])
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
            status = 'open'  # Always open when created

            if not title or not description:
                flash("Both title and description are required.", "danger")
                return redirect(url_for("create_ticket"))

            try:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO tickets (title, description, status, priority, deadline, created_at, queue_id, assigned_to)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                    (title, description, status, priority, deadline, created_at, queue_id, assigned_to))
                ticket_id = cursor.lastrowid

                # 📎 Handle file upload
                file = request.files.get('file')
                if file and file.filename:
                    if allowed_file(file.filename):
                        original_filename = secure_filename(file.filename)
                        timestamped_filename = f"{ticket_id}_{datetime.now().timestamp()}_{original_filename}"
                        save_path = os.path.join(app.config['UPLOAD_FOLDER'], timestamped_filename)
                        file.save(save_path)

                        cursor.execute('''
                            INSERT INTO attachments (ticket_id, original_filename, stored_filename, filepath, uploaded_at)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (ticket_id, original_filename, timestamped_filename, save_path, datetime.now().isoformat()))
                    else:
                        flash("Invalid file type. Upload aborted.", "warning")

                conn.commit()

                # Notify assigned user (optional)
                if assigned_to:
                    threading.Thread(
                        target=notify_assigned_user,
                        args=(ticket_id, 'assigned', session.get('user_id')),
                        daemon=True
                    ).start()

                flash('Ticket created successfully!', 'success')
                return redirect(url_for('index'))
            except Exception as e:
                current_app.logger.error(f"Error creating ticket: {e}")
                flash('An error occurred while creating the ticket. Please try again.', 'danger')
                return render_template('create_ticket.html', queues=queues, users=users)

    return render_template('create_ticket.html', queues=queues, users=users)

@app.route('/uploads/<path:filename>')
@login_required
def download_attachment(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

@app.route('/ticket/<int:ticket_id>/priority', methods=['POST'])
@login_required
def update_priority(ticket_id):
    new_priority = request.form['priority']
    user_id = session.get('user_id')
    with get_db() as conn:
        conn.execute('UPDATE tickets SET priority = ? WHERE id = ?', (new_priority, ticket_id))
    threading.Thread(
        target=notify_assigned_user, 
        args=(ticket_id, 'priority', user_id), 
        daemon=True
    ).start()
    flash('Priority updated successfully!', 'success')
    return redirect(url_for('ticket_detail', ticket_id=ticket_id))


@app.route('/ticket/<int:ticket_id>/comment', methods=['POST'])
@login_required
def add_comment(ticket_id):
    content = request.form['content']
    user_id = session.get('user_id')
    created_at = datetime.now().isoformat()
    if not content:
        flash('Comment cannot be empty.', 'danger')
        return redirect(url_for('ticket_detail', ticket_id=ticket_id))
    with get_db() as conn:
        conn.execute('INSERT INTO comments (ticket_id, content, user_id, created_at) VALUES (?, ?, ?, ?)', (ticket_id, content, user_id, created_at))
    threading.Thread(target=notify_assigned_user,args=(ticket_id, 'new_comment', user_id), daemon=True).start()
    flash('Comment added successfully!', 'success')
    return redirect(url_for('ticket_detail', ticket_id=ticket_id))


@app.route('/ticket/<int:ticket_id>/status', methods=['POST'])
@login_required
def update_status(ticket_id):
    new_status = request.form['status']
    user_id = session.get('user_id')
    with get_db() as conn:
        conn.execute('UPDATE tickets SET status = ? WHERE id = ?', (new_status, ticket_id))
    threading.Thread(
        target=notify_assigned_user, 
        args=(ticket_id, 'status', user_id), 
        daemon=True
    ).start()
    flash('Status updated successfully!', 'success')
    return redirect(url_for('ticket_detail', ticket_id=ticket_id))


if __name__ == '__main__':
    init_db()
    ensure_default_settings()
    # Load settings globally
    settings = load_settings()
    # Conditionally load API if enabled
    ensure_admin_user()
    if settings.get('enable_api') == '1':
        import api


    app.run(host="0.0.0.0", port=5000, debug=True)

if not app.debug:
    import logging
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler('error.log', maxBytes=10240, backupCount=5)
    file_handler.setLevel(logging.ERROR)
    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]')
    file_handler.setFormatter(formatter)
    app.logger.addHandler(file_handler)
