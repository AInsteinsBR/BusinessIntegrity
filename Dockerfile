FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential git \
    && rm -rf /var/lib/apt/lists/*

# Clone the repository
RUN git clone https://github.com/AInsteinsBR/BusinessIntegrity.git . \
    && git config --global --add safe.directory /app

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set environment variables
ENV FLASK_APP=app/app.py
ENV FLASK_ENV=production

# Expose port
EXPOSE 5000

# Create entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Use entrypoint script
ENTRYPOINT ["/entrypoint.sh"]