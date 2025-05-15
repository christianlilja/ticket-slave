import os
from flask import Blueprint, request, jsonify
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from datetime import timedelta
from app.db import get_db

api = Blueprint('api', __name__)

# JWT Setup
jwt = JWTManager()
def init_jwt(app):
    app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'your_fallback_secret')
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)
    jwt.init_app(app)

# Helper: Pagination metadata
def get_total_tickets_count(show_closed):
    conn = get_db()
    query = "SELECT COUNT(*) FROM tickets"
    if not show_closed:
        query += " WHERE LOWER(status) != 'closed'"
    return conn.execute(query).fetchone()[0]

@api.route('/api/token', methods=['POST'])
def api_get_token():
    data = request.json
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'msg': 'Missing username or password'}), 400

    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (data['username'],)).fetchone()

    if user and user['password'] == data['password']:  # Use hashed passwords in production
        access_token = create_access_token(identity=user['id'])
        return jsonify(access_token=access_token)
    return jsonify({'msg': 'Bad username or password'}), 401

@api.route('/api/tickets', methods=['GET'])
@jwt_required()
def api_get_tickets():
    user_id = get_jwt_identity()
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))
    show_closed = request.args.get('show_closed', 'false').lower() == 'true'

    conn = get_db()
    query = """
        SELECT tickets.*, users.username as assigned_user 
        FROM tickets 
        LEFT JOIN users ON tickets.assigned_to = users.id
    """
    if not show_closed:
        query += " WHERE LOWER(tickets.status) != 'closed'"
    query += " ORDER BY tickets.id DESC LIMIT ? OFFSET ?"

    tickets = conn.execute(query, (per_page, (page - 1) * per_page)).fetchall()
    total_count = get_total_tickets_count(show_closed)

    return jsonify({
        'tickets': [dict(ticket) for ticket in tickets],
        'page': page,
        'per_page': per_page,
        'total': total_count
    })

@api.route('/api/tickets/<int:ticket_id>', methods=['GET'])
@jwt_required()
def api_get_ticket(ticket_id):
    conn = get_db()
    ticket = conn.execute(
        'SELECT tickets.*, users.username as assigned_user FROM tickets '
        'LEFT JOIN users ON tickets.assigned_to = users.id '
        'WHERE tickets.id = ?', (ticket_id,)
    ).fetchone()

    if ticket is None:
        return jsonify({'msg': 'Ticket not found'}), 404

    return jsonify(dict(ticket))

@api.route('/api/tickets/<int:ticket_id>', methods=['PUT'])
@jwt_required()
def api_update_ticket(ticket_id):
    data = request.json
    conn = get_db()

    ticket = conn.execute('SELECT * FROM tickets WHERE id = ?', (ticket_id,)).fetchone()
    if ticket is None:
        return jsonify({'msg': 'Ticket not found'}), 404

    fields = []
    values = []
    for field in ['title', 'description', 'status', 'priority', 'deadline', 'queue_id', 'assigned_to']:
        if field in data:
            fields.append(f"{field} = ?")
            values.append(data[field])

    if fields:
        values.append(ticket_id)
        query = f"UPDATE tickets SET {', '.join(fields)} WHERE id = ?"
        conn.execute(query, values)
        conn.commit()

    return jsonify({'msg': 'Ticket updated'})

@api.route('/api/webhook/create-ticket', methods=['POST'])
def webhook_create_ticket():
    token = request.headers.get('X-Webhook-Token')
    if token != os.getenv('WEBHOOK_SECRET', 'default_token'):
        return jsonify({'msg': 'Unauthorized'}), 401

    data = request.json
    title = data.get('title', 'No title provided')
    description = data.get('description', 'No description provided')
    queue_id = data.get('queue_id', 1)
    priority = data.get('priority', 'Low')
    status = 'Open'

    conn = get_db()
    conn.execute('''
        INSERT INTO tickets (title, description, status, priority, queue_id)
        VALUES (?, ?, ?, ?, ?)
    ''', (title, description, status, priority, queue_id))
    conn.commit()

    send_notifications(f"New Ticket Created via Webhook:\n{title}\n{description}")

    return jsonify({'msg': 'Ticket created'}), 201
