from datetime import datetime
from flask import request, jsonify
from flask_jwt_extended import JWTManager, jwt_required, create_access_token, get_jwt_identity
from werkzeug.security import check_password_hash
from app import app, get_db

# API Stuff

# Initialize the JWT manager
app.config['JWT_SECRET_KEY'] = 'your_jwt_secret_key'  # Change this for production
jwt = JWTManager(app)

# Login route with JWT
@app.route('/api/login', methods=['POST'])
def api_login():
    username = request.json.get('username')
    password = request.json.get('password')

    with get_db() as conn:
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

    if user and check_password_hash(user['password'], password):
        # Create JWT token and return it
        access_token = create_access_token(identity=user['id'])
        return {'access_token': access_token}, 200
    else:
        return {'msg': 'Invalid credentials'}, 401
    
@app.route('/api/tickets', methods=['GET'])

def api_get_tickets():
#    current_user = get_jwt_identity()  # Get user info from JWT
    show_closed = request.args.get('show_closed', 'false').lower() == 'true'
    sort_by = request.args.get('sort_by', 'created_at')
    page = request.args.get('page', 1, type=int)
    per_page = 15

    # Define the query logic for pagination, sorting, etc.
    # For simplicity, we’re not handling `current_user` roles here for now.
    
    # Query for the tickets from the database
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

    # Return the tickets in JSON format
    return {'tickets': [dict(ticket) for ticket in tickets]}, 200

@app.route('/api/tickets/<int:ticket_id>', methods=['GET'])
@jwt_required()
def api_get_ticket(ticket_id):
    with get_db() as conn:
        ticket = conn.execute('SELECT * FROM tickets WHERE id = ?', (ticket_id,)).fetchone()

    if ticket is None:
        return {'msg': 'Ticket not found'}, 404

    return {'ticket': dict(ticket)}, 200

@app.route('/api/tickets', methods=['POST'])
@jwt_required()
def api_create_ticket():
    data = request.json
    title = data['title']
    description = data['description']
    status = data['status']
    priority = data['priority']
    deadline = data['deadline']
    queue_id = data['queue_id']

    created_at = datetime.now().isoformat()

    with get_db() as conn:
        conn.execute('''
            INSERT INTO tickets (title, description, status, priority, deadline, created_at, queue_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (title, description, status, priority, deadline, created_at, queue_id))
        conn.commit()

    return {'msg': 'Ticket created successfully'}, 201

@app.route('/api/tickets/<int:ticket_id>', methods=['PUT'])
@jwt_required()
def api_update_ticket(ticket_id):
    data = request.json
    status = data['status']

    with get_db() as conn:
        conn.execute('UPDATE tickets SET status=? WHERE id=?', (status, ticket_id))
        conn.commit()

    return {'msg': 'Ticket updated successfully'}, 200

@app.route('/api/tickets/<int:ticket_id>/comment', methods=['POST'])
@jwt_required()
def api_add_comment(ticket_id):
    data = request.json
    content = data['content']
    created_at = datetime.now().isoformat()

    with get_db() as conn:
        conn.execute('INSERT INTO comments (ticket_id, content, created_at) VALUES (?, ?, ?)',
                     (ticket_id, content, created_at))
        conn.commit()

    return {'msg': 'Comment added successfully'}, 201

@app.route('/api/queues', methods=['GET'])
@jwt_required()
def api_get_queues():
    with get_db() as conn:
        queues = conn.execute('SELECT * FROM queues').fetchall()

    return {'queues': [dict(queue) for queue in queues]}, 200

@app.route('/api/queues', methods=['POST'])
@jwt_required()
def api_create_queue():
    data = request.json
    name = data['name']

    with get_db() as conn:
        conn.execute('INSERT INTO queues (name) VALUES (?)', (name,))
        conn.commit()

    return {'msg': 'Queue created successfully'}, 201
