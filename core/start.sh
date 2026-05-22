#!/bin/bash

# Kill any process using port 8000
fuser -k 8000/tcp

# Activate the virtual environment
. /opt/h_dose/eapts_backend/venv/bin/activate

# Change to the directory where your application is located
cd /opt/h_dose/eapts_backend

# Start the FastAPI application
python manage.py runserver 0.0.0.0:8000