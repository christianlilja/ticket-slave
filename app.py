from flask import Flask, render_template, request, redirect, url_for, session, flash, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps
from jinja2 import TemplateNotFound, TemplateSyntaxError
from contextlib import contextmanager
import sqlite3

app = Flask(__name__)
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
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'open',
                priority TEXT DEFAULT 'medium',
                deadline TEXT,
                created_at TEXT,
                queue_id INTEGER,
                FOREIGN KEY (queue_id) REFERENCES queues(id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS queues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
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
                ticket_id INTEGER,
                content TEXT NOT NULL,
                created_at TEXT,
                FOREIGN KEY (ticket_id) REFERENCES tickets(id)
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
    msg = "There’s a syntax issue in one of the templates."
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

app.secret_key = 'change-me-top-secret'

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
            conn.execute('''
                INSERT INTO tickets (title, description, status, priority, deadline, created_at, queue_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (title, description, status, priority, deadline, created_at, queue_id))
            conn.commit()
            return redirect(url_for('index'))

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
