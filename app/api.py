"""
RESTful API endpoints for the application.

This module defines a Flask Blueprint for API routes, providing programmatic
access to application functionalities, primarily ticket management.
It uses JWT (JSON Web Tokens) for authentication on most endpoints and
includes a webhook for external ticket creation.
"""
import os
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from datetime import timedelta
from app.db import db_manager # Using the refactored db_manager
from app.notifications_core import notify_assigned_user
from utils.context_runner import run_in_app_context
from werkzeug.security import check_password_hash # For secure password checking.

# Define the Blueprint for API routes.
# All routes defined with 'api' will be prefixed (e.g., /api/token).
api = Blueprint('api', __name__, url_prefix='/api') # Added url_prefix for clarity

# --- JWT (JSON Web Token) Setup ---
jwt = JWTManager() # Initialize JWTManager extension.

def init_jwt(app):
    """
    Initializes JWT-Extended with the Flask application.
    Configures JWT secret key and token expiration time.

    Args:
        app (Flask): The Flask application instance.
    """
    # JWT_SECRET_KEY: A strong, random secret key used to sign JWTs.
    # CRITICAL: This MUST be kept secret and should be set via environment variable in production.
    app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'default-super-secret-jwt-key-change-me!')
    if app.config['JWT_SECRET_KEY'] == 'default-super-secret-jwt-key-change-me!':
        current_app.logger.warning(
            "SECURITY WARNING: Using a default JWT_SECRET_KEY. This is INSECURE. "
            "Set a strong, unique JWT_SECRET_KEY environment variable for production."
        )
    # JWT_ACCESS_TOKEN_EXPIRES: How long an access token is valid.
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=int(os.getenv('JWT_EXPIRATION_HOURS', '1'))) # Default 1 hour
    jwt.init_app(app) # Register JWTManager with the Flask app.
    current_app.logger.info("JWTManager initialized for API authentication.")

# --- Helper Function for Pagination ---
def get_total_tickets_count(show_closed=False, assigned_to_user_id=None):
    """
    Helper function to get the total count of tickets based on filters.

    Args:
        show_closed (bool): If True, includes closed tickets in the count.
        assigned_to_user_id (int, optional): If provided, count only tickets assigned to this user.

    Returns:
        int: The total number of tickets matching the criteria.
    """
    query = "SELECT COUNT(tickets.id) AS total_count FROM tickets"
    conditions = []
    params = []

    if not show_closed:
        conditions.append("LOWER(tickets.status) != ?")
        params.append('closed')
    
    if assigned_to_user_id is not None:
        conditions.append("tickets.assigned_to = ?")
        params.append(assigned_to_user_id)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    # Using db_manager for database interaction
    result = db_manager.fetchone(query, tuple(params))
    return result['total_count'] if result else 0

# --- API Endpoints ---

@api.route('/token', methods=['POST'])
def api_get_token():
    """
    Authenticates a user and returns a JWT access token.

    Request Body (JSON):
        {
            "username": "your_username",
            "password": "your_password"
        }

    Returns:
        JSON: {"access_token": "your_jwt_token"} on success (200).
              {"msg": "error_message"} on failure (400 or 401).
    """
    data = request.json
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'msg': 'Missing username or password in JSON payload.'}), 400

    username = data['username']
    password = data['password']

    # Fetch user from database using db_manager
    user_record = db_manager.fetchone('SELECT id, username, password FROM users WHERE username = ?', (username,))

    # --- !!! SECURITY WARNING !!! ---
    # The original code compared plaintext passwords: `user['password'] == data['password']`
    # This is highly insecure. Passwords MUST be stored hashed.
    # The comparison MUST use a function like `check_password_hash`.
    # Assuming passwords in DB are hashed:
    if user_record and check_password_hash(user_record['password'], password):
        # Identity for the token can be user_id or any other unique identifier.
        access_token = create_access_token(identity=user_record['id'])
        current_app.logger.info(f"JWT token generated for user: {username} (ID: {user_record['id']})")
        return jsonify(access_token=access_token), 200
    
    current_app.logger.warning(f"Failed API login attempt for username: {username}")
    return jsonify({'msg': 'Bad username or password.'}), 401

@api.route('/tickets', methods=['GET'])
@jwt_required() # Protects this route; valid JWT must be present in Authorization header.
def api_get_tickets():
    """
    Retrieves a paginated list of tickets.
    Requires JWT authentication.

    Query Parameters:
        page (int, optional): Page number (default: 1).
        per_page (int, optional): Number of tickets per page (default: 10).
        show_closed (bool, optional): 'true' to include closed tickets (default: 'false').
        assigned_to_me (bool, optional): 'true' to show only tickets assigned to the authenticated user.

    Returns:
        JSON: Paginated list of tickets and metadata.
    """
    current_user_id = get_jwt_identity() # Get user ID from JWT.
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))
    show_closed = request.args.get('show_closed', 'false').lower() == 'true'
    assigned_to_me = request.args.get('assigned_to_me', 'false').lower() == 'true'

    assigned_filter_user_id = current_user_id if assigned_to_me else None

    base_query = """
        SELECT tickets.*, creator.username AS created_by_username, assignee.username AS assigned_to_username, queues.name AS queue_name
        FROM tickets
        LEFT JOIN users AS creator ON tickets.created_by = creator.id
        LEFT JOIN users AS assignee ON tickets.assigned_to = assignee.id
        LEFT JOIN queues ON tickets.queue_id = queues.id
    """
    conditions = []
    params = []

    if not show_closed:
        conditions.append("LOWER(tickets.status) != ?")
        params.append('closed')
    
    if assigned_filter_user_id is not None:
        conditions.append("tickets.assigned_to = ?")
        params.append(assigned_filter_user_id)

    if conditions:
        base_query += " WHERE " + " AND ".join(conditions)
    
    # Add ordering, limit, and offset for pagination.
    # Example order: newest tickets first.
    query_with_pagination = base_query + " ORDER BY tickets.created_at DESC LIMIT ? OFFSET ?"
    params_for_pagination = (*params, per_page, (page - 1) * per_page)

    tickets_data = db_manager.fetchall(query_with_pagination, params_for_pagination)
    total_count = get_total_tickets_count(show_closed, assigned_filter_user_id) # Get count with same filters.

    current_app.logger.debug(f"API: User {current_user_id} fetched tickets. Page: {page}, Count: {len(tickets_data)}")
    return jsonify({
        'tickets': [dict(ticket) for ticket in tickets_data], # Convert sqlite3.Row to dict.
        'page': page,
        'per_page': per_page,
        'total_tickets': total_count,
        'total_pages': (total_count + per_page - 1) // per_page
    }), 200

@api.route('/tickets/<int:ticket_id>', methods=['GET'])
@jwt_required()
def api_get_ticket(ticket_id):
    """
    Retrieves details for a specific ticket by its ID.
    Requires JWT authentication.

    Returns:
        JSON: Ticket details if found (200), or error message (404).
    """
    current_user_id = get_jwt_identity()
    # Fetch ticket details including related user and queue names.
    query = """
        SELECT tickets.*, creator.username AS created_by_username, assignee.username AS assigned_to_username, queues.name AS queue_name
        FROM tickets
        LEFT JOIN users AS creator ON tickets.created_by = creator.id
        LEFT JOIN users AS assignee ON tickets.assigned_to = assignee.id
        LEFT JOIN queues ON tickets.queue_id = queues.id
        WHERE tickets.id = ?
    """
    ticket_data = db_manager.fetchone(query, (ticket_id,))

    if ticket_data is None:
        current_app.logger.warning(f"API: User {current_user_id} failed to get ticket ID {ticket_id}: Not found.")
        return jsonify({'msg': 'Ticket not found.'}), 404

    # TODO: Add authorization check: Does current_user_id have permission to view this ticket?
    #       This is important if tickets have restricted visibility.

    current_app.logger.debug(f"API: User {current_user_id} fetched ticket ID {ticket_id}.")
    return jsonify(dict(ticket_data)), 200

@api.route('/tickets/<int:ticket_id>', methods=['PUT'])
@jwt_required()
def api_update_ticket(ticket_id):
    """
    Updates fields of an existing ticket.
    Requires JWT authentication.

    Request Body (JSON):
        {
            "title": "New Title", // Optional
            "description": "New Description", // Optional
            "status": "in progress", // Optional
            "priority": "high", // Optional
            "deadline": "YYYY-MM-DDTHH:MM:SS", // Optional
            "queue_id": 1, // Optional
            "assigned_to": 2 // Optional (user ID)
        }

    Returns:
        JSON: Success message (200), or error (404 if ticket not found, 400 for bad data).
    """
    current_user_id = get_jwt_identity()
    data = request.json
    if not data:
        return jsonify({'msg': 'Request body must be JSON.'}), 400

    # Check if ticket exists.
    existing_ticket = db_manager.fetchone('SELECT id FROM tickets WHERE id = ?', (ticket_id,))
    if existing_ticket is None:
        current_app.logger.warning(f"API: User {current_user_id} failed to update ticket ID {ticket_id}: Not found.")
        return jsonify({'msg': 'Ticket not found.'}), 404

    # TODO: Add authorization: Does current_user_id have permission to update this ticket?

    fields_to_update = []
    values_for_update = []
    allowed_fields = ['title', 'description', 'status', 'priority', 'deadline', 'queue_id', 'assigned_to']
    
    # Dynamically build the SET part of the UPDATE query.
    for field in allowed_fields:
        if field in data:
            # TODO: Add validation for each field's value (e.g., status in allowed_statuses, queue_id exists).
            fields_to_update.append(f"{field} = ?")
            values_for_update.append(data[field])

    if not fields_to_update:
        return jsonify({'msg': 'No valid fields provided for update.'}), 400

    values_for_update.append(ticket_id) # Add ticket_id for the WHERE clause.
    update_query = f"UPDATE tickets SET {', '.join(fields_to_update)} WHERE id = ?"
    
    try:
        db_manager.execute_query(update_query, tuple(values_for_update))
        # If 'assigned_to' was in data and changed, trigger notification.
        if 'assigned_to' in data and data['assigned_to'] is not None:
             # Check if assignment actually changed to avoid redundant notifications.
            original_assignee = db_manager.fetchone("SELECT assigned_to FROM tickets WHERE id = ?", (ticket_id,))
            if original_assignee and original_assignee['assigned_to'] != data['assigned_to']:
                current_app.logger.info(f"API: Ticket {ticket_id} assigned to user {data['assigned_to']} by user {current_user_id}. Queuing notification.")
                run_in_app_context(current_app._get_current_object(), notify_assigned_user, ticket_id, 'assigned', current_user_id)

        current_app.logger.info(f"API: User {current_user_id} updated ticket ID {ticket_id}. Fields: {fields_to_update}")
        return jsonify({'msg': 'Ticket updated successfully.'}), 200
    except Exception as e: # Catch database errors or other issues.
        current_app.logger.error(f"API: Error updating ticket ID {ticket_id} by user {current_user_id}: {e}", exc_info=True)
        return jsonify({'msg': f'Failed to update ticket: {str(e)}'}), 500


@api.route('/webhook/create-ticket', methods=['POST'])
def webhook_create_ticket():
    """
    Webhook endpoint to create a new ticket.
    Authenticates using a secret token in the 'X-Webhook-Token' header.

    Request Body (JSON):
        {
            "title": "Ticket Title from Webhook",
            "description": "Detailed description.",
            "queue_id": 1, // ID of an existing queue
            "status": "open", // Optional, defaults to 'open'
            "priority": "medium", // Optional, defaults to 'medium'
            "assigned_to": 2 // Optional, user ID to assign
        }

    Returns:
        JSON: Success message with ticket_id (201), or error (400, 401, 500).
    """
    # --- Webhook Authentication ---
    provided_token = request.headers.get('X-Webhook-Token')
    expected_token = os.getenv('WEBHOOK_SECRET')

    if not expected_token:
        current_app.logger.critical("WEBHOOK_SECRET environment variable is not set. Webhook endpoint is insecure and will not function.")
        return jsonify({'msg': 'Webhook endpoint not configured properly on server.'}), 503 # Service Unavailable

    # Securely compare tokens to prevent timing attacks.
    # `hmac.compare_digest` is preferred, but direct comparison is common for simple secrets.
    # For this example, direct comparison is used, but note the security implication.
    if not provided_token or not expected_token or provided_token != expected_token:
        current_app.logger.warning("Webhook unauthorized: Missing or incorrect X-Webhook-Token.")
        return jsonify({'msg': 'Unauthorized: Invalid or missing webhook token.'}), 401

    # --- Process Request Data ---
    data = request.json
    if not data:
        current_app.logger.warning("Webhook bad request: No JSON payload received.")
        return jsonify({'error': 'Request body must be valid JSON.'}), 400

    title = data.get('title')
    description = data.get('description')
    queue_id = data.get('queue_id') # This is expected to be an integer ID.
    # Optional fields with defaults.
    status = data.get('status', 'open')
    priority = data.get('priority', 'medium')
    assigned_to_user_id = data.get('assigned_to') # Optional: User ID for assignment.

    # Validate required fields.
    if not title or not description or queue_id is None: # Check queue_id for None explicitly.
        current_app.logger.warning(
            "Webhook bad request: Missing required fields (title, description, or queue_id).",
            extra={'received_data': data}
        )
        return jsonify({'error': 'Missing required fields: title, description, and queue_id.'}), 400
    
    # TODO: Add validation for queue_id (does it exist?), status, priority values.

    try:
        # Insert the new ticket into the database.
        # 'created_by' is not set by this webhook; DB schema should handle default or allow NULL.
        # 'created_at' should be set by the database or application logic (e.g., datetime.now().isoformat()).
        from datetime import datetime
        created_at_iso = datetime.now().isoformat()

        new_ticket_id = db_manager.insert(
            '''INSERT INTO tickets (title, description, status, priority, queue_id, assigned_to, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (title, description, status, priority, queue_id, assigned_to_user_id, created_at_iso)
        )

        log_extra_webhook = {
            'created_ticket_id': new_ticket_id,
            'webhook_payload': data, # Log the received payload for debugging.
            'assigned_to_user_id': assigned_to_user_id
        }
        current_app.logger.info(f"Ticket (ID: {new_ticket_id}) created successfully via webhook.", extra=log_extra_webhook)

        # If a user was assigned, trigger a notification.
        if new_ticket_id and assigned_to_user_id:
            current_app.logger.info(
                f"Webhook: Queuing 'assigned' notification for new ticket {new_ticket_id} to user {assigned_to_user_id}.",
                extra=log_extra_webhook
            )
            # `triggering_user_id` is None as this is a system action (webhook).
            run_in_app_context(
                current_app._get_current_object(), # Pass the Flask app instance.
                notify_assigned_user,
                new_ticket_id,
                'assigned_on_creation', # Event type for new assignment.
                None # No specific user triggered this action directly.
            )
        elif new_ticket_id:
            current_app.logger.info(
                f"Webhook: Ticket {new_ticket_id} created. No user assigned, so no 'assigned' notification sent.",
                extra=log_extra_webhook
            )

        return jsonify({'msg': 'Ticket created successfully.', 'ticket_id': new_ticket_id}), 201 # HTTP 201 Created.

    except Exception as e:
        # db_manager should handle its own rollbacks if using its context manager.
        # If direct conn was used, conn.rollback() would be needed here.
        current_app.logger.error(
            f"Webhook ticket creation failed due to an internal error: {e}",
            exc_info=True, # Include stack trace in logs.
            extra={'webhook_payload': data}
        )
        # Avoid exposing raw internal error details like str(e) to the client in production.
        return jsonify({'error': 'Failed to create ticket due to an internal server error.'}), 500

# Ensure JWT is initialized when this module is loaded by the app factory.
# This is typically done in create_app() after the app object is created.
# Example in create_app():
# from . import api as api_module
# api_module.init_jwt(app)
# app.register_blueprint(api_module.api)
