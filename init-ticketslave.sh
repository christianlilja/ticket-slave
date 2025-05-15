#!/bin/bash

TARGET_DIR="./ticketslave"

echo "Initializing ticket system data directory..."

# Create required directories
mkdir -p "$TARGET_DIR/uploads"
mkdir -p "$TARGET_DIR/instance"

# Create an empty database if not exists
DB_PATH="$TARGET_DIR/instance/database.db"
if [ ! -f "$DB_PATH" ]; then
    echo "Creating empty database at $DB_PATH"
    sqlite3 "$DB_PATH" "VACUUM;"
else
    echo "Database already exists at $DB_PATH"
fi

echo "✅ Initialization complete. You can now run: docker-compose up"
