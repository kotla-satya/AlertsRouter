#!/bin/sh
set -e

echo "Initialising database..."
python init_db.py

echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8080
