from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime
import sqlite3

app = Flask(__name__)
DB_PATH = 'database.db'

def init_db():
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'open',
                priority TEXT DEFAULT 'medium',
                deadline TEXT,
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
        conn.commit()

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn


@app.route('/')
def index():
    show_closed = request.args.get('show_closed', 'false').lower() == 'true'
    sort_by = request.args.get('sort_by', 'created_at')

    valid_sorts = {'created_at', 'priority', 'deadline'}
    if sort_by not in valid_sorts:
        sort_by = 'created_at'  # fallback

    query = '''
        SELECT tickets.*, queues.name AS queue
        FROM tickets
        LEFT JOIN queues ON tickets.queue_id = queues.id
    '''

    if not show_closed:
        query += ' WHERE LOWER(tickets.status) != "closed"'

    if sort_by == 'priority':
        query += '''
            ORDER BY CASE LOWER(priority)
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
                ELSE 4
            END
        '''
    else:
        query += f' ORDER BY {sort_by} DESC'

    tickets = []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query).fetchall()

        for row in rows:
            # Deadline handling
            deadline = row['deadline']
            is_overdue = False
            if deadline:
                try:
                    deadline_dt = datetime.fromisoformat(deadline)
                    is_overdue = datetime.now() > deadline_dt
                except ValueError:
                    pass

            # Creation timestamp formatting
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
        sort_by=sort_by
    )



@app.route("/queues", methods=["GET", "POST"])
def manage_queues():
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()

        if request.method == "POST":
            name = request.form["name"]
            cursor.execute("INSERT INTO queues (name) VALUES (?)", (name,))
            conn.commit()

        cursor.execute("SELECT * FROM queues")
        queues = cursor.fetchall()

    return render_template("queues.html", queues=queues)

@app.route('/ticket/<int:ticket_id>')
def ticket_detail(ticket_id):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row  # ✅ Ensure dictionary-style access
    ticket = conn.execute('SELECT * FROM tickets WHERE id = ?', (ticket_id,)).fetchone()
    comments = conn.execute('SELECT * FROM comments WHERE ticket_id = ?', (ticket_id,)).fetchall()
    conn.close()

    if ticket is None:
        abort(404)

    return render_template('ticket_detail.html', ticket=ticket, comments=comments)

@app.route('/create', methods=['GET', 'POST'])
def create_ticket():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        queues = conn.execute("SELECT id, name FROM queues").fetchall()

        if request.method == 'POST':
            title = request.form['title']
            description = request.form['description']
            status = request.form['status']
            priority = request.form['priority']
            deadline = request.form['deadline']
            queue_id = request.form.get('queue_id')  # optional

            created_at = datetime.now().isoformat()
            conn.execute('''
                INSERT INTO tickets (title, description, status, priority, deadline, created_at, queue_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (title, description, status, priority, deadline, created_at, queue_id))
            conn.commit()
            return redirect(url_for('index'))

    return render_template('create_ticket.html', queues=queues)

@app.route('/ticket/<int:ticket_id>/comment', methods=['POST'])
def add_comment(ticket_id):
    content = request.form['content']
    created_at = datetime.now().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('INSERT INTO comments (ticket_id, content, created_at) VALUES (?, ?, ?)',
                     (ticket_id, content, created_at))
    return redirect(url_for('ticket_detail', ticket_id=ticket_id))

@app.route('/ticket/<int:ticket_id>/status', methods=['POST'])
def update_status(ticket_id):
    status = request.form['status']
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('UPDATE tickets SET status=? WHERE id=?', (status, ticket_id))
    return redirect(url_for('ticket_detail', ticket_id=ticket_id))

if __name__ == '__main__':
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
