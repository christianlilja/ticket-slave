"""
Main application routes.

This module defines the primary routes for the application, including the
main ticket listing page (index) and the favicon.
"""
from flask import Blueprint, render_template, request, session, abort, redirect, url_for, send_from_directory, current_app
from utils.decorators import login_required # Custom decorator to ensure user is logged in.
from datetime import datetime
from app.db import db_manager # Use the global db_manager instance for database operations.
import os

# Define the Blueprint for main application routes.
main_bp = Blueprint('main_bp', __name__)

@main_bp.route('/favicon.ico')
def favicon():
    """
    Serves the favicon for the application.
    Uses a specific PNG file for better browser compatibility over .ico.
    """
    # send_from_directory securely serves files from a specific directory.
    # current_app.root_path refers to the root directory of the Flask application.
    return send_from_directory(
        os.path.join(current_app.root_path, 'static'), # Path to the 'static' folder.
        'favicon-32x32.png', # Filename of the favicon.
        mimetype='image/png' # Explicitly set the MIME type.
    )

@main_bp.route("/")
# @login_required # Uncomment this if the index page should always require login.
                  # Current logic redirects if not logged in, but decorator is cleaner.
def index():
    """
    Displays the main ticket listing page (index/dashboard).

    Features:
    - Redirects to login if the user is not authenticated.
    - Filters tickets based on 'assigned_only' and 'show_closed' query parameters.
    - Sorts tickets based on 'sort_by' query parameter.
    - Paginates results.
    - Processes ticket data for display (e.g., deadline overdue check, date formatting).
    """
    current_app.logger.info(
        "Index page accessed.",
        extra={
            'user_id': session.get('user_id'),
            'username': session.get('username'),
            'query_params': dict(request.args) # Log query parameters for debugging.
        }
    )

    # If user is not logged in, redirect to the login page.
    if not session.get('user_id'):
        flash("Please log in to view this page.", "info") # Optional: provide a message.
        return redirect(url_for('auth_bp.login')) # Use url_for for robust routing.

    # --- Get and process request arguments for filtering, sorting, and pagination ---
    assigned_only = request.args.get('assigned_only', 'false').lower() == 'true'
    show_closed = request.args.get('show_closed', 'false').lower() == 'true'
    sort_by = request.args.get('sort_by', 'created_at') # Default sort: newest first.
    page = request.args.get('page', 1, type=int) # Default to page 1.
    per_page = 15 # Number of tickets to display per page.

    # --- Define allowed sort options and their corresponding SQL ORDER BY clauses ---
    # This dictionary maps user-friendly sort keys to SQL expressions.
    sort_columns = {
        'created_at': 'tickets.created_at DESC', # Newest tickets first.
        'deadline': 'tickets.deadline ASC NULLS LAST', # Approaching deadlines first, NULLs at the end.
        'priority': '''CASE LOWER(tickets.priority)
                        WHEN 'high' THEN 1
                        WHEN 'medium' THEN 2
                        WHEN 'low' THEN 3
                        ELSE 4
                      END, tickets.created_at DESC''', # Sort by priority, then by creation date.
        'queue': 'queues.name ASC, tickets.created_at DESC', # Sort by queue name, then by creation date.
        'assigned_to': 'COALESCE(users.username, "zzzzzz") ASC, tickets.created_at DESC' # Sort by assignee, unassigned last, then by creation date.
                                                                                    # "zzzzzz" pushes NULL usernames (unassigned) to the end.
    }

    # Validate the 'sort_by' parameter; default if invalid.
    if sort_by not in sort_columns:
        sort_by = 'created_at' # Fallback to default sort option.
    order_by_clause = sort_columns[sort_by]

    # --- Construct SQL query components ---
    # Base FROM and JOIN clauses for fetching ticket data.
    base_query_joins = '''
        FROM tickets
        LEFT JOIN queues ON tickets.queue_id = queues.id
        LEFT JOIN users ON tickets.assigned_to = users.id
    '''

    # WHERE clauses for filtering.
    where_clauses = [] # List to hold individual WHERE conditions.
    params = []        # List to hold parameters for the SQL query (prevents SQL injection).

    if not show_closed:
        where_clauses.append('LOWER(tickets.status) != ?')
        params.append('closed')

    if assigned_only:
        user_id = session.get('user_id')
        # This check is redundant if @login_required is used, but good for clarity here.
        if not user_id:
            current_app.logger.warning("Attempt to filter by 'assigned_only' without a logged-in user.")
            abort(401) # Unauthorized access.
        where_clauses.append('tickets.assigned_to = ?')
        params.append(user_id)

    # Combine WHERE clauses if any exist.
    where_clause_sql = ''
    if where_clauses:
        where_clause_sql = 'WHERE ' + ' AND '.join(where_clauses)

    # --- Pagination: Calculate total number of tickets matching filters ---
    count_query = f'SELECT COUNT(tickets.id) AS total_count {base_query_joins} {where_clause_sql}'
    current_app.logger.debug(f"Executing count query: {count_query} with params: {tuple(params)}")
    total_row = db_manager.fetchone(count_query, tuple(params)) # Ensure params is a tuple.
    total_tickets = total_row['total_count'] if total_row else 0
    current_app.logger.debug(f"Total tickets matching criteria: {total_tickets}")

    total_pages = (total_tickets + per_page - 1) // per_page # Calculate total pages.
    offset = (page - 1) * per_page # Calculate offset for the current page.

    # --- Main ticket data query ---
    # Selects all necessary ticket fields and related data (queue name, assignee username).
    main_data_query = f'''
        SELECT
            tickets.*,
            queues.name AS queue_name,
            users.username AS assigned_to_username
        {base_query_joins}
        {where_clause_sql}
        ORDER BY {order_by_clause}
        LIMIT ? OFFSET ?
    '''
    current_app.logger.debug(f"Executing main data query: {main_data_query} with params: {(*params, per_page, offset)}")
    
    # Fetch ticket rows from the database.
    ticket_rows = db_manager.fetchall(main_data_query, (*params, per_page, offset))

    # --- Process fetched ticket data for display ---
    processed_tickets = []
    for row in ticket_rows:
        deadline_str = row['deadline']
        is_overdue = False
        if deadline_str:
            try:
                # Attempt to parse deadline from ISO format first.
                deadline_dt = datetime.fromisoformat(deadline_str)
            except ValueError:
                try:
                    # Fallback to common datetime format if ISO parsing fails.
                    deadline_dt = datetime.strptime(deadline_str, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    deadline_dt = None # Unable to parse deadline.
                    current_app.logger.warning(f"Could not parse deadline string: '{deadline_str}' for ticket ID {row['id']}")
            
            if deadline_dt and row['status'].lower() != 'closed': # Only check overdue if not closed
                is_overdue = datetime.now() > deadline_dt

        # Format 'created_at' for display.
        try:
            created_at_dt = datetime.fromisoformat(row['created_at'])
            created_at_formatted = created_at_dt.strftime('%Y-%m-%d %H:%M') # More readable format.
        except Exception as e:
            created_at_formatted = "Unknown" # Fallback if parsing fails.
            current_app.logger.warning(f"Could not parse created_at string: '{row['created_at']}' for ticket ID {row['id']}: {e}")

        processed_tickets.append({
            'id': row['id'],
            'title': row['title'],
            'description': row['description'], # Consider truncating for list view if too long.
            'status': row['status'],
            'priority': row['priority'],
            'deadline': deadline_str, # Original deadline string.
            'created_at_raw': row['created_at'], # Raw created_at for potential further use.
            'created_at_formatted': created_at_formatted, # Formatted for display.
            'is_overdue': is_overdue,
            'queue': row['queue_name'],
            'assigned_to': row['assigned_to_username'] or "Unassigned" # Display "Unassigned" if no assignee.
        })
    current_app.logger.debug(f"Processed {len(processed_tickets)} tickets for display on page {page}.")

    # --- Render the template with processed data and view options ---
    return render_template(
        'index.html',
        tickets=processed_tickets,
        show_closed=show_closed,
        assigned_only=assigned_only,
        sort_by=sort_by,
        current_page=page, # Renamed 'page' to 'current_page' for clarity in template.
        total_pages=total_pages,
        per_page=per_page,
        total_tickets=total_tickets
    )
