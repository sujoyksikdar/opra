#!/bin/bash

# Wait for database
echo "Waiting for database..."
sleep 3

# Apply database migrations
echo "Applying database migrations..."
# manage.py is in the current WORKDIR (compsocsite)
python manage.py migrate --noinput

# Create cache table if missing
echo "Creating cache table..."
python manage.py createcachetable || true

# Start server
echo "Starting server..."
python manage.py runserver 0.0.0.0:8000
