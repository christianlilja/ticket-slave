TicketSlave is a lightweight and modular ticketing system built with Flask. It provides a clean interface for creating, managing, and tracking support tickets, making it suitable for small to medium-sized teams. The application is designed to be run with Docker for easy deployment but can also be set up for local development.

## Key Features

*   **User Authentication:** Secure user registration and login system.
*   **Ticket Management:** Create, view, update, and close tickets.
*   **Commenting System:** Add comments to tickets for collaborative issue resolution.
*   **File Attachments:** Upload and download files associated with tickets.
*   **Ticket Assignment:** Assign tickets to specific users for clear ownership.
*   **Notifications:** (Future Implementation) Core logic for user notifications is in place.
*   **Modular Architecture:** Organized with Flask Blueprints for scalability and maintainability.
*   **Customizable Queues:** Group tickets into different queues for better organization.

## Getting Started

### Prerequisites

*   Docker and Docker Compose
*   Python 3.8+ and `pip` (for local development)

### Docker Installation (Recommended)

1.  **Initialize the Environment:**
    The `init-ticketslave.sh` script creates the necessary directories for the database and file uploads.

    ```bash
    bash init-ticketslave.sh
    ```

2.  **Build and Run the Container:**
    Use Docker Compose to build the image and run the application.

    ```bash
    docker-compose up --build
    ```

    The application will be available at `http://localhost:5000`.

### Local Development Setup

1.  **Create a Virtual Environment:**

    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

2.  **Install Dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

3.  **Set Environment Variables:**
    Create a `.env` file in the root directory and add a `SECRET_KEY`.

    ```
    SECRET_KEY='a-very-strong-and-secret-key'
    ```

4.  **Initialize the Database:**
    The application will create and initialize the SQLite database on the first run.

5.  **Run the Application:**

    ```bash
    python run.py
    ```

    The application will be available at `http://localhost:5000`.

## Project Structure

```
.
├── app/                # Core application logic
│   ├── __init__.py
│   ├── app.py          # Main Flask application setup
│   ├── database_manager.py # Low-level database interaction
│   ├── db.py           # Database initialization and helpers
│   ├── error.py        # Custom error handlers
│   └── ...
├── routes/             # Flask Blueprints for different features
│   ├── auth.py
│   ├── tickets.py
│   └── ...
├── static/             # Static assets (CSS, JS, images)
├── templates/          # Jinja2 templates
├── utils/              # Utility functions and decorators
├── docker-compose.yml  # Docker Compose configuration
├── Dockerfile          # Dockerfile for the application
├── requirements.txt    # Python dependencies
└── run.py              # Entry point for running the application
```

## Default Admin User

Upon first launch, the application creates a default admin user with the following credentials:

*   **Username:** `admin`
*   **Password:** `admin`

It is highly recommended to change the default password immediately after the first login.
