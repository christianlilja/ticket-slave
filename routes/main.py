from flask import Blueprint, render_template, request, session, abort
from utils.decorators import login_required
from datetime import datetime
from app.db import get_db  # Ensure you have this helper for DB connection

main_bp = Blueprint('main_bp', __name__)

@main_bp.route("/")
@login_required
def index():
    assigned_only = request.args.get('assigned_only', 'false').lower() == 'true'
    show_closed = request.args.get('show_closed', 'false').lower() == 'true'
    sort_by = request.args.get('sort_by', 'created_at')
    page = request.args.get('page', 1, type=int)
    per_page = 15

    # Define allowed sort options
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

    # Validate sort_by value
    if sort_by not in sort_columns:
        sort_by = 'created_at'
    order_by_clause = sort_columns[sort_by]

    # SQL JOINs
    base_query = '''
        FROM tickets
        LEFT JOIN queues ON tickets.queue_id = queues.id
        LEFT JOIN users ON tickets.assigned_to = users.id
    '''

    # WHERE filters
    where_clauses = []
    params = []

    if not show_closed:
        where_clauses.append('LOWER(tickets.status) != "closed"')

    if assigned_only:
        user_id = session.get('user_id')
        if not user_id:
            abort(401)
        where_clauses.append('tickets.assigned_to = ?')
        params.append(user_id)

    where_clause = ''
    if where_clauses:
        where_clause = 'WHERE ' + ' AND '.join(where_clauses)

    # Count total for pagination
    count_query = f'SELECT COUNT(*) {base_query} {where_clause}'

    with get_db() as conn:
        total = conn.execute(count_query, params).fetchone()[0]

    total_pages = (total + per_page - 1) // per_page
    offset = (page - 1) * per_page

    # Main ticket query
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
            # Parse deadline
            deadline = row['deadline']
            is_overdue = False
            if deadline:
                try:
                    deadline_dt = datetime.fromisoformat(deadline)
                except ValueError:
                    try:
                        deadline_dt = datetime.strptime(deadline, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        deadline_dt = None
                if deadline_dt:
                    is_overdue = datetime.now() > deadline_dt

            # Format created_at
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
