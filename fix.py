import sqlite3
from datetime import datetime

DB_PATH = 'database.db'

def fix_timestamps():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        # Fix tickets
        cursor.execute("SELECT id, created_at, deadline FROM tickets")
        for row in cursor.fetchall():
            ticket_id, created_at, deadline = row
            try:
                datetime.fromisoformat(created_at)
            except Exception:
                fallback = deadline if deadline else datetime.now().isoformat()
                print(f"[Ticket ID {ticket_id}] Invalid or missing created_at. Setting to: {fallback}")
                cursor.execute("UPDATE tickets SET created_at=? WHERE id=?", (fallback, ticket_id))

        # Fix comments
        cursor.execute("SELECT id, created_at FROM comments")
        for row in cursor.fetchall():
            comment_id, created_at = row
            try:
                datetime.fromisoformat(created_at)
            except Exception:
                fallback = datetime.now().isoformat()
                print(f"[Comment ID {comment_id}] Invalid or missing created_at. Setting to: {fallback}")
                cursor.execute("UPDATE comments SET created_at=? WHERE id=?", (fallback, comment_id))

        conn.commit()
        print("✅ Timestamps fixed.")

if __name__ == '__main__':
    fix_timestamps()
