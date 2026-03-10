FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /code

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt /code/
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . /code/

# The Django app is in the compsocsite subdirectory
WORKDIR /code/compsocsite

# Ensure entrypoint script is executable
RUN chmod +x /code/docker-entrypoint.sh

# Use the root entrypoint script
ENTRYPOINT ["/code/docker-entrypoint.sh"]
