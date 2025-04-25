from flask import Flask, render_template, request, redirect, url_for, session, flash, current_app, abort
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps
from jinja2 import TemplateNotFound, TemplateSyntaxError
from contextlib import contextmanager
from flask_jwt_extended import JWTManager, jwt_required, create_access_token, get_jwt_identity
from api import *
import sqlite3
import os

app = Flask(__name__)
IS_PROD = os.environ.get('FLASK_ENV') == 'production'

if IS_PROD and not os.environ.get('SECRET_KEY'):
    raise RuntimeError("SECRET_KEY must be set in production")

#Set variable in prod: export SECRET_KEY='a-very-strong-and-random-secret-key'
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key')

DB_PATH = 'database.db'

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()

        # Enable foreign key constraints
        cursor.execute("PRAGMA foreign_keys = ON")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS queues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'in progress', 'closed')),
                priority TEXT NOT NULL DEFAULT 'medium' CHECK(priority IN ('low', 'medium', 'high')),
                deadline TEXT,
                created_at TEXT NOT NULL,
                queue_id INTEGER NOT NULL,
                FOREIGN KEY (queue_id) REFERENCES queues(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
            )
        """)

        conn.commit()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

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
    show_closed = request.args.get('show_closed', 'false').lower() == 'true'
    sort_by = request.args.get('sort_by', 'created_at')
    page = request.args.get('page', 1, type=int)
    per_page = 15

    sort_columns = {
        'created_at': 'tickets.created_at DESC',
        'deadline': 'tickets.deadline DESC',
        'priority': '''CASE LOWER(priority)
                        WHEN 'high' THEN 1
                        WHEN 'medium' THEN 2
                        WHEN 'low' THEN 3
                        ELSE 4
                      END'''
    }
    order_by_clause = sort_columns.get(sort_by, 'tickets.created_at DESC')

    base_query = '''
        FROM tickets
        LEFT JOIN queues ON tickets.queue_id = queues.id
    '''
    where_clause = ''
    if not show_closed:
        where_clause = ' WHERE LOWER(tickets.status) != "closed"'

    count_query = f'SELECT COUNT(*) {base_query} {where_clause}'
    with get_db() as conn:
        total = conn.execute(count_query).fetchone()[0]

    total_pages = (total + per_page - 1) // per_page
    offset = (page - 1) * per_page

    query = f'''
        SELECT tickets.*, queues.name AS queue
        {base_query}
        {where_clause}
        ORDER BY {order_by_clause}
        LIMIT ? OFFSET ?
    '''

    tickets = []
    with get_db() as conn:
        rows = conn.execute(query, (per_page, offset)).fetchall()
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
                'queue': row['queue']
            })

    return render_template(
        'index.html',
        tickets=tickets,
        show_closed=show_closed,
        sort_by=sort_by,
        page=page,
        total_pages=total_pages
    )

@app.route('/register', methods=['GET', 'POST'])
def register():
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
            conn.commit()
            flash('Registered successfully. Please log in.', 'success')
            return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/create-admin')
def create_admin():
    username = "admin"
    password = "changeme"  # Change this before deploying!
    hashed_password = generate_password_hash(password)
    is_admin = 1

    conn = sqlite3.connect('database.db')  # Use your actual path
    c = conn.cursor()

    # Check if admin already exists
    c.execute("SELECT * FROM users WHERE username = ?", (username,))
    if c.fetchone():
        conn.close()
        return "Admin user already exists."

    # Create the admin user
    c.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)",
              (username, hashed_password, is_admin))
    conn.commit()
    conn.close()

    # Self-destruct by removing the route function
    del app.view_functions['create_admin']
    return "Admin user created successfully. This route is now disabled."

@app.route("/users", methods=["GET", "POST"])
@login_required
def users():
    if not session.get("is_admin"):
        return redirect(url_for("index"))

    with get_db() as conn:
        cursor = conn.cursor()

        # Add user
        if request.method == "POST" and "new_username" in request.form:
            username = request.form["new_username"]
            password = generate_password_hash(request.form["new_password"])
            # Set is_admin to 0 explicitly, since admin creation is disabled
            is_admin = 0
            try:
                cursor.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)", (username, password, is_admin))
                conn.commit()
            except sqlite3.IntegrityError:
                flash("Username already exists.", "danger")

        # Delete user
        if request.method == "POST" and "delete_user" in request.form:
            user_to_delete = request.form["delete_user"]
            # Prevent deleting the admin user
            cursor.execute("SELECT is_admin FROM users WHERE username = ?", (user_to_delete,))
            user = cursor.fetchone()
            if user and user[0] == 1:
                flash("Cannot delete admin user.", "danger")
            else:
                cursor.execute("DELETE FROM users WHERE username = ?", (user_to_delete,))
                conn.commit()

        cursor.execute("SELECT username, is_admin FROM users")
        users = cursor.fetchall()

    return render_template("users.html", users=users)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        with get_db() as conn:
            user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = user['is_admin']  # or 'is_admin'
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('login.html')

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
        comments = conn.execute('SELECT * FROM comments WHERE ticket_id = ?', (ticket_id,)).fetchall()

    if ticket is None:
        abort(404)

    return render_template('ticket_detail.html', ticket=ticket, comments=comments)

@app.route('/create', methods=['GET', 'POST'])
@login_required
def create_ticket():
    with get_db() as conn:
        queues = conn.execute("SELECT id, name FROM queues").fetchall()

        if request.method == 'POST':
            title = request.form['title']
            description = request.form['description']
            status = request.form['status']
            priority = request.form['priority']
            deadline = request.form['deadline']
            queue_id = request.form.get('queue_id')
            created_at = datetime.now().isoformat()

            try:
                conn.execute('''
                    INSERT INTO tickets (title, description, status, priority, deadline, created_at, queue_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (title, description, status, priority, deadline, created_at, queue_id))
                conn.commit()
                flash('Ticket created successfully!', 'success')
                return redirect(url_for('index'))
            except Exception as e:
                current_app.logger.error(f"Error creating ticket: {e}")
                flash('An error occurred while creating the ticket. Please try again.', 'danger')
                # Re-render the form with user's previously entered data
                return render_template(
                    'create_ticket.html',
                    queues=queues,
                    title=title,
                    description=description,
                    status=status,
                    priority=priority,
                    deadline=deadline,
                    queue_id=queue_id
                )

    return render_template('create_ticket.html', queues=queues)

@app.route('/ticket/<int:ticket_id>/comment', methods=['POST'])
@login_required
def add_comment(ticket_id):
    content = request.form['content']
    created_at = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute('INSERT INTO comments (ticket_id, content, created_at) VALUES (?, ?, ?)',
                     (ticket_id, content, created_at))
    return redirect(url_for('ticket_detail', ticket_id=ticket_id))

@app.route('/ticket/<int:ticket_id>/status', methods=['POST'])
@login_required
def update_status(ticket_id):
    status = request.form['status']
    with get_db() as conn:
        conn.execute('UPDATE tickets SET status=? WHERE id=?', (status, ticket_id))
    return redirect(url_for('ticket_detail', ticket_id=ticket_id))

if __name__ == '__main__':
    init_db()
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
