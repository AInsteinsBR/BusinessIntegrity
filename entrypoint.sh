#!/bin/bash

# Run database configuration
echo "Running database configuration..."
python config.py

# Start Flask application
echo "Starting Flask application..."
flask run --host=0.0.0.0