import os
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from datetime import timedelta
from app.db import get_db
from app.notifications_core import notify_assigned_user # Changed from send_apprise_notification
from utils.context_runner import run_in_app_context


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
    # It's good practice to compare tokens in a way that prevents timing attacks,
    # though for typical webhook secrets, direct comparison is common.
    # For higher security, consider using `hmac.compare_digest`.
    if not token or token != os.getenv('WEBHOOK_SECRET'): # Ensure WEBHOOK_SECRET is set
        current_app.logger.warning("Webhook unauthorized: Missing or incorrect token.")
        return jsonify({'msg': 'Unauthorized'}), 401

    data = request.json
    if not data:
        current_app.logger.warning("Webhook bad request: No JSON payload.")
        return jsonify({'error': 'Request body must be JSON'}), 400

    title = data.get('title')
    description = data.get('description')
    queue_id = data.get('queue_id')
    # Optional fields with defaults
    status = data.get('status', 'open')
    priority = data.get('priority', 'medium')
    assigned_to_user_id = data.get('assigned_to') # Optional: ID of the user to assign

    if not title or not description or queue_id is None: # Check queue_id for None explicitly if 0 is invalid
        current_app.logger.warning(
            "Webhook bad request: Missing title, description, or queue_id.",
            extra={'received_data': data}
        )
        return jsonify({'error': 'Missing title, description, or queue_id'}), 400

    conn = get_db()
    try:
        cursor = conn.cursor()
        # Assuming 'created_by' is nullable or you have a default (e.g., a generic API user ID)
        # For now, created_by is not set by the webhook, relying on DB default or nullable.
        cursor.execute('''
            INSERT INTO tickets (title, description, status, priority, queue_id, assigned_to)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (title, description, status, priority, queue_id, assigned_to_user_id))
        ticket_id = cursor.lastrowid
        conn.commit()

        log_extra_webhook = {
            'ticket_id': ticket_id,
            'webhook_payload': data,
            'assigned_to_user_id': assigned_to_user_id
        }
        current_app.logger.info("Ticket created via webhook", extra=log_extra_webhook)

        if ticket_id and assigned_to_user_id:
            current_app.logger.info(
                f"Webhook: Queuing 'assigned' notification for new ticket {ticket_id} to user {assigned_to_user_id}",
                extra=log_extra_webhook
            )
            # Pass None for triggering_user_id as it's a webhook, not a session user action
            run_in_app_context(
                current_app._get_current_object(),
                notify_assigned_user,
                ticket_id,
                'assigned', # Event type for new assignment
                None
            )
        elif ticket_id:
            current_app.logger.info(
                f"Webhook: Ticket {ticket_id} created. No user assigned, so no 'assigned' notification sent.",
                extra=log_extra_webhook
            )

        return jsonify({'msg': 'Ticket created', 'ticket_id': ticket_id}), 201

    except Exception as e:
        conn.rollback() # Important to rollback on error
        current_app.logger.error(
            f"Webhook ticket creation failed: {e}",
            exc_info=True, # Includes stack trace
            extra={'webhook_payload': data}
        )
        # Avoid exposing raw error details like str(e) to the client in production
        return jsonify({'error': 'Failed to create ticket due to an internal error'}), 500
