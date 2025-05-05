from app import app, get_db, settings
from datetime import datetime
from flask import request, jsonify
from flask_jwt_extended import JWTManager, jwt_required, create_access_token, get_jwt_identity
from werkzeug.security import check_password_hash

# Initialize the JWT manager
app.config['JWT_SECRET_KEY'] = 'your_jwt_secret_key'  # TODO: change for production
jwt = JWTManager(app)

# --- API Routes ---

# Login
@app.route('/api/login', methods=['POST'])
def api_login():
    username = request.json.get('username')
    password = request.json.get('password')

    with get_db() as conn:
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

    if user and check_password_hash(user['password'], password):
        access_token = create_access_token(identity=user['id'])
        return {'access_token': access_token}, 200
    else:
        return {'msg': 'Invalid credentials'}, 401

# Get all tickets
@app.route('/api/tickets', methods=['GET'])
def api_get_tickets():
    show_closed = request.args.get('show_closed', 'false').lower() == 'true'
    sort_by = request.args.get('sort_by', 'created_at')
    page = request.args.get('page', 1, type=int)
    per_page = 15

    query = '''
        SELECT tickets.*, queues.name AS queue
        FROM tickets
        LEFT JOIN queues ON tickets.queue_id = queues.id
        WHERE LOWER(tickets.status) != "closed"
        ORDER BY tickets.created_at DESC
        LIMIT ? OFFSET ?
    '''
    with get_db() as conn:
        tickets = conn.execute(query, (per_page, (page - 1) * per_page)).fetchall()

    return {'tickets': [dict(ticket) for ticket in tickets]}, 200

# Get a single ticket
@app.route('/api/tickets/<int:ticket_id>', methods=['GET'])
@jwt_required()
def api_get_ticket(ticket_id):
    with get_db() as conn:
        ticket = conn.execute('SELECT * FROM tickets WHERE id = ?', (ticket_id,)).fetchone()

    if ticket is None:
        return {'msg': 'Ticket not found'}, 404

    return {'ticket': dict(ticket)}, 200

# Create ticket
@app.route('/api/tickets', methods=['POST'])
@jwt_required()
def api_create_ticket():
    data = request.json
    created_at = datetime.now().isoformat()

    with get_db() as conn:
        conn.execute('''
            INSERT INTO tickets (title, description, status, priority, deadline, created_at, queue_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['title'], data['description'], data['status'],
            data['priority'], data['deadline'], created_at, data['queue_id']
        ))
        conn.commit()

    return {'msg': 'Ticket created successfully'}, 201

@app.route('/api/webhook/create-ticket', methods=['POST'])
def create_ticket_from_webhook():
    """Create a ticket from Uptime Kuma webhook"""
    # Ensure that the request is in JSON format
    if not request.is_json:
        return jsonify({"msg": "Invalid content type, expected JSON"}), 400

    # Get the JSON data sent by Uptime Kuma
    data = request.get_json()

    # Extract necessary fields from the webhook data
    monitor_name = data.get("monitor_name")
    status = data.get("status")  # e.g., 'down' or 'up'
    message = data.get("message")  # Alert message, why the monitor is down or up
    timestamp = data.get("timestamp")  # Timestamp of the alert

    # Set default values or handle missing data (for instance, "up" as default status)
    created_at = datetime.now().isoformat()
    ticket_title = f"Uptime Kuma Alert - {monitor_name} is {status}"
    ticket_description = f"Status: {status}\nMessage: {message}\nTimestamp: {timestamp}"

    # Example: Set priority to "high" if the status is "down"
    priority = "high" if status == "down" else "low"

    # Assuming you have a default queue_id, or you can dynamically assign it
    queue_id = 1  # Adjust this according to your logic or config

    # Insert the new ticket into the database using your existing logic
    try:
        with get_db() as conn:
            conn.execute(''' 
                INSERT INTO tickets (title, description, status, priority, deadline, created_at, queue_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                ticket_title, ticket_description, "open",  # Default status is 'open'
                priority, None, created_at, queue_id
            ))
            conn.commit()

        # Return a success response
        return jsonify({'msg': 'Ticket created successfully'}), 201

    except Exception as e:
        return jsonify({"msg": "Failed to create ticket", "error": str(e)}), 500


# Update ticket
@app.route('/api/tickets/<int:ticket_id>', methods=['PUT'])
@jwt_required()
def api_update_ticket(ticket_id):
    data = request.json

    with get_db() as conn:
        conn.execute('UPDATE tickets SET status=? WHERE id=?', (data['status'], ticket_id))
        conn.commit()

    return {'msg': 'Ticket updated successfully'}, 200

# Add comment to ticket
@app.route('/api/tickets/<int:ticket_id>/comment', methods=['POST'])
@jwt_required()
def api_add_comment(ticket_id):
    data = request.json
    created_at = datetime.now().isoformat()

    with get_db() as conn:
        conn.execute('INSERT INTO comments (ticket_id, content, created_at) VALUES (?, ?, ?)',
                     (ticket_id, data['content'], created_at))
        conn.commit()

    return {'msg': 'Comment added successfully'}, 201

# Get queues
@app.route('/api/queues', methods=['GET'])
@jwt_required()
def api_get_queues():
    with get_db() as conn:
        queues = conn.execute('SELECT * FROM queues').fetchall()

    return {'queues': [dict(queue) for queue in queues]}, 200

# Create queue
@app.route('/api/queues', methods=['POST'])
@jwt_required()
def api_create_queue():
    data = request.json

    with get_db() as conn:
        conn.execute('INSERT INTO queues (name) VALUES (?)', (data['name'],))
        conn.commit()

    return {'msg': 'Queue created successfully'}, 201
