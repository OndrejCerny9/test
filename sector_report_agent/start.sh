#!/bin/bash
# Install Playwright Chromium browser (needed for rendering JS charts)
echo "Installing Playwright Chromium..."
playwright install chromium
playwright install-deps chromium

# Start the FastAPI application
echo "Starting Sector Report Agent..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
