from flask import Blueprint, render_template, request, session, flash, jsonify
from utils.decorators import login_required, admin_required
from app.db import get_db
import smtplib

settings_bp = Blueprint('settings_bp', __name__)

@settings_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def system_settings():


    with get_db() as conn:
        cur = conn.cursor()

        if request.method == 'POST':
            action = request.form.get('action')

            if action == 'save_settings':
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

            elif action == 'test_email':
                cur.execute("SELECT key, value FROM settings")
                settings = {row['key']: row['value'] for row in cur.fetchall()}

                smtp_server = settings.get('smtp_server')
                smtp_port = int(settings.get('smtp_port', 25))
                smtp_user = settings.get('smtp_username')
                smtp_password = settings.get('smtp_password')
                use_tls = settings.get('smtp_use_tls') == '1'

                try:
                    with smtplib.SMTP(smtp_server, smtp_port, timeout=5) as server:
                        if use_tls:
                            server.starttls()
                        if smtp_user and smtp_password:
                            server.login(smtp_user, smtp_password)
                    flash("SMTP connection successful!", "success")
                except Exception as e:
                    flash(f"SMTP connection failed: {e}", "danger")

        # Load current settings for display
        settings_dict = {
            row['key']: row['value']
            for row in cur.execute("SELECT key, value FROM settings").fetchall()
        }

    return render_template('settings.html', settings=settings_dict)

@settings_bp.route('/settings/test-email', methods=['POST'])
@login_required
@admin_required
def test_email_settings():
    try:
        with get_db() as conn:
            settings = {
                row['key']: row['value']
                for row in conn.execute("SELECT key, value FROM settings").fetchall()
            }

        smtp_server = settings.get('smtp_server')
        smtp_port = int(settings.get('smtp_port', 587))
        smtp_user = settings.get('smtp_username')
        smtp_password = settings.get('smtp_password')

        if not smtp_server:
            raise Exception("SMTP server not configured")

        # Attempt to connect
        with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
            if smtp_user and smtp_password:
                server.starttls()
                server.login(smtp_user, smtp_password)

        return jsonify({'message': 'SMTP connection successful.', 'category': 'success'}), 200

    except Exception as e:
        return jsonify({'message': f'SMTP test failed: {str(e)}', 'category': 'danger'}), 500