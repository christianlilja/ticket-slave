DEFAULT_SETTINGS = {
    'allow_registration': {
        'default': '0',
        'label': 'Allow new users to register',
        'type': 'checkbox'
    },
    'enable_api': {
        'default': '0',
        'label': 'Enable API',
        'type': 'checkbox'
    },
    'smtp_server': {
        'default': 'localhost',
        'label': 'SMTP Server',
        'type': 'text'
    },
    'smtp_port': {
        'default': '25',
        'label': 'SMTP Port',
        'type': 'number'
    },
    'smtp_from_email': {
        'default': 'noreply@example.com',
        'label': 'From Email Address',
        'type': 'text'
    },
    'smtp_username': {
        'default': '',
        'label': 'SMTP Username',
        'type': 'text'
    },
    'smtp_password': {
        'default': '',
        'label': 'SMTP Password',
        'type': 'password'
    },
    'smtp_use_tls': {
        'default': '0',
        'label': 'Use TLS for SMTP',
        'type': 'checkbox'
    },
    'admin_username': {
        'default': 'admin',
        'label': 'Default admin username',
        'type': 'text'
    },
    'admin_password': {
        'default': 'changeme',
        'label': 'Default admin password',
        'type': 'password'
    },
    'theme': {
        'default': 'dark',
        'label': 'Default Theme',
        'type': 'text'
    },
    'notify_email': {
        'default': '0',
        'label': 'Enable Email Notifications',
        'type': 'checkbox'
    },
    'notify_pushover': {
        'default': '0',
        'label': 'Enable Pushover Notifications',
        'type': 'checkbox'
    },
    'notify_apprise': {
        'default': '0',
        'label': 'Enable Apprise Notifications',
        'type': 'checkbox'
    },
    'apprise_url': {
        'default': '',
        'label': 'Apprise URL',
        'type': 'text'
    }
}