from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from utils.decorators import login_required, admin_required
from db import get_db  # Adjust path as needed

settings_bp = Blueprint('settings_bp', __name__)  # Consistent naming

@settings_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def system_settings():
    if not session.get('is_admin'):
        return redirect(url_for('main_bp.index'))

    with get_db() as conn:
        cur = conn.cursor()

        if request.method == 'POST':
            allow_registration = 1 if 'allow_registration' in request.form else 0
            enable_api = 1 if 'enable_api' in request.form else 0
            smtp_server = request.form.get('smtp_server', '')
            smtp_port = request.form.get('smtp_port', '25')
            smtp_from_email = request.form.get('smtp_from_email', '')
            smtp_username = request.form.get('smtp_username', '')
            smtp_password = request.form.get('smtp_password', '')
            smtp_use_tls = 1 if 'smtp_use_tls' in request.form else 0

            cur.execute("UPDATE settings SET value = ? WHERE key = 'allow_registration'", (allow_registration,))
            cur.execute("UPDATE settings SET value = ? WHERE key = 'enable_api'", (enable_api,))
            cur.execute("UPDATE settings SET value = ? WHERE key = 'smtp_server'", (smtp_server,))
            cur.execute("UPDATE settings SET value = ? WHERE key = 'smtp_port'", (smtp_port,))
            cur.execute("UPDATE settings SET value = ? WHERE key = 'smtp_from_email'", (smtp_from_email,))
            cur.execute("UPDATE settings SET value = ? WHERE key = 'smtp_username'", (smtp_username,))
            cur.execute("UPDATE settings SET value = ? WHERE key = 'smtp_password'", (smtp_password,))
            cur.execute("UPDATE settings SET value = ? WHERE key = 'smtp_use_tls'", (smtp_use_tls,))
            conn.commit()

            flash('Settings updated.', 'success')

        settings_dict = {
            row['key']: row['value']
            for row in cur.execute("SELECT key, value FROM settings").fetchall()
        }

    return render_template('settings.html', settings=settings_dict)
