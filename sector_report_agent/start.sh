#!/bin/bash
# Start the FastAPI application
echo "Starting Sector Report Agent..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
