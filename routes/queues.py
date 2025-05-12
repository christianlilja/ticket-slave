from flask import Blueprint, render_template, request
from utils.decorators import login_required
from app.db import get_db  # Adjust this import based on your project structure

queues_bp = Blueprint('queues_bp', __name__)  # Use 'queue' consistently

@queues_bp.route("/queues", methods=["GET", "POST"])
@login_required
def manage_queues():
    with get_db() as conn:
        cursor = conn.cursor()
        if request.method == "POST":
            name = request.form.get("name")
            if name:  # Basic validation
                cursor.execute("INSERT INTO queues (name) VALUES (?)", (name,))
                conn.commit()
        cursor.execute("SELECT * FROM queues")
        queues = cursor.fetchall()
    return render_template("queues.html", queues=queues)
