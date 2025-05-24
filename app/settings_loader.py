"""
Default application settings definition.

This module defines the `DEFAULT_SETTINGS` dictionary, which serves as a
schema and source of default values for all application-level settings
that are managed and stored in the database.

The structure of `DEFAULT_SETTINGS` is a dictionary where each key is the
setting's unique identifier (as stored in the 'key' column of the 'settings'
database table). The value for each key is another dictionary containing:
    - 'default' (str): The default value for the setting. Note that all values
                       are typically stored as strings in the database, even if
                       they represent booleans ('0' or '1') or numbers.
    - 'label' (str): A human-readable label for the setting, suitable for display
                     in user interfaces (e.g., the admin settings page).
    - 'type' (str):  Indicates the type of input field that should be used to
                     represent this setting in a UI. Common types include 'checkbox'
                     (for boolean-like settings), 'text', 'password', 'number'.

This `DEFAULT_SETTINGS` dictionary is primarily used by:
1.  `app.db.ensure_default_settings()`: To populate the 'settings' table in the
    database with these default values if they don't already exist during
    application initialization.
2.  The settings page template (`templates/settings.html`): To dynamically render
    the form fields for managing these settings, using the 'label' and 'type'
    information.
"""

DEFAULT_SETTINGS = {
    # --- General Application Settings ---
    'allow_registration': {
        'default': '0',  # '0' for false (disabled), '1' for true (enabled)
        'label': 'Allow New User Registration',
        'type': 'checkbox',
        'description': 'If checked, new users can register accounts. If unchecked, registration is disabled.'
    },
    'enable_api': {
        'default': '0',
        'label': 'Enable API Access',
        'type': 'checkbox',
        'description': 'If checked, the application\'s REST API endpoints will be active.'
    },
    'theme': { # This might be a global default theme, user-specific themes are in 'users' table.
        'default': 'dark',
        'label': 'Default System Theme', # Clarified label
        'type': 'select', # Changed to 'select' as an example, could also be 'text'
        'options': ['light', 'dark'], # Example options if type is 'select'
        'description': 'Sets the default visual theme for the application (e.g., for login page or new users).'
    },

    # --- SMTP (Email Notification) Settings ---
    'smtp_server': {
        'default': 'localhost',
        'label': 'SMTP Server Address',
        'type': 'text',
        'description': 'Hostname or IP address of your SMTP server (e.g., smtp.example.com).'
    },
    'smtp_port': {
        'default': '587', # Common port for TLS, 25 for non-encrypted, 465 for SSL.
        'label': 'SMTP Server Port',
        'type': 'number',
        'description': 'Port number for the SMTP server (e.g., 25, 465, 587).'
    },
    'smtp_from_email': {
        'default': 'noreply@example.com',
        'label': 'Sender Email Address (From)',
        'type': 'email', # Changed to 'email' for more specific input type
        'description': 'The email address from which application notifications will be sent.'
    },
    'smtp_username': {
        'default': '',
        'label': 'SMTP Username',
        'type': 'text',
        'description': 'Username for SMTP authentication (if required by your server).'
    },
    'smtp_password': {
        'default': '',
        'label': 'SMTP Password',
        'type': 'password', # Input field will mask the characters.
        'description': 'Password for SMTP authentication. Stored in the database; ensure DB security.'
    },
    'smtp_use_tls': {
        'default': '1', # Default to using TLS for better security.
        'label': 'Use STARTTLS for SMTP',
        'type': 'checkbox',
        'description': 'If checked, attempts to upgrade the SMTP connection to use TLS encryption.'
    },

    # --- Default Administrator Account Settings ---
    # These are typically used only once during initial setup by `ensure_admin_user`.
    # It's highly recommended to change the default admin password immediately after setup.
    'admin_username': {
        'default': 'admin',
        'label': 'Default Administrator Username',
        'type': 'text',
        'description': 'Username for the initial administrator account (used if no admin exists on first run).'
    },
    'admin_password': {
        'default': 'changeme', # CRITICAL: This default password MUST be changed.
        'label': 'Default Administrator Password',
        'type': 'password',
        'description': 'Password for the initial administrator account. CHANGE THIS IMMEDIATELY after setup.'
    },

    # --- User Notification Preferences (Global Defaults or Overrides - Clarify Usage) ---
    # The 'notify_*' settings here might represent global defaults if user-specific settings are also available.
    # Or, if these are the *only* place these are configured, they apply to all users for whom notifications are triggered.
    # The current implementation seems to use these as part of the settings page, but user-specific toggles
    # are in the 'users' table and managed via profile/notifications pages.
    # These might be less relevant if user-specific preferences always take precedence.
    # For now, assuming they might be global fallbacks or for system-level notifications.
    'notify_email_globally': { # Renamed for clarity if these are global toggles
        'default': '0', # Default to off for global email notifications
        'label': 'Enable Email Notifications Globally (System-Wide)',
        'type': 'checkbox',
        'description': 'Master switch for enabling/disabling email notifications for all relevant system events (if not overridden by user preferences).'
    },
    # Similar global toggles could exist for Pushover and Apprise if needed.
    # The individual user notification settings (notify_email, notify_pushover, notify_apprise)
    # are stored per-user in the 'users' table and managed via their profile.
    # The 'apprise_url' here might be a system-wide default Apprise URL if multiple are not supported per user.
    'default_apprise_url': { # Renamed for clarity
        'default': '',
        'label': 'Default System Apprise URL',
        'type': 'text',
        'description': 'A default Apprise service URL for system-level notifications, or as a fallback if a user has not configured their own.'
    }
}

# Note on 'type' field:
# The 'type' field (e.g., 'checkbox', 'text', 'password', 'number', 'email', 'select')
# is used by the `templates/settings.html` (or similar admin UI template) to render
# the appropriate HTML input element for each setting.
# For 'select', an 'options' key (list of strings or dicts) would also be needed in DEFAULT_SETTINGS.