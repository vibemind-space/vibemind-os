# =============================================================================
# Tahlamus Brain System - Dockerfile
# =============================================================================
# Multi-service container for unified-brain (5003) and dashboard (5000).
# The CMD is intentionally omitted; each service sets its own command
# in docker-compose.yml.
# =============================================================================

FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies needed by numpy/scipy wheels
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better Docker layer caching
COPY requirements.txt requirements-minimal.txt requirements-tahlamus.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the full application source
COPY . .

# Create the data directory for persistent volumes
RUN mkdir -p /app/data

# Expose ports for unified-brain and dashboard
EXPOSE 5000 5003

# No default CMD -- each service specifies its own in docker-compose.yml
