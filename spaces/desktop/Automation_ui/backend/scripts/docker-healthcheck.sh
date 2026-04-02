#!/bin/bash
set -e

# Health check script for TRAE Backend
if [ "$1" = "backend" ]; then
    # Check if the backend service is responding
    curl -f http://localhost:8010/api/health || exit 1
else
    echo "Unknown service type for health check: $1"
    exit 1
fi

echo "Health check passed"
exit 0