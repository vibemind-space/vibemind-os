#!/bin/bash
# SSH Health Check Script for TRAE Remote Desktop
# Monitors SSH connection status and provides health information

set -e

# Configuration from environment variables
SSH_HOST="${SSH_HOST:-host.docker.internal}"
SSH_PORT="${SSH_PORT:-22}"
SSH_USER="${SSH_USER:-}"
SSH_CONNECTION_NAME="${SSH_CONNECTION_NAME:-host_system}"
HEALTHCHECK_TIMEOUT="${HEALTHCHECK_TIMEOUT:-10}"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] SSH-HealthCheck: $1"
}

# Check if TRAE backend is running
check_backend() {
    if curl -s --max-time $HEALTHCHECK_TIMEOUT http://localhost:8010/api/health >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Check SSH connection status via TRAE API
check_ssh_status() {
    local response
    response=$(curl -s --max-time $HEALTHCHECK_TIMEOUT http://localhost:8010/api/desktop/ssh/list 2>/dev/null)
    
    if [ $? -eq 0 ] && echo "$response" | grep -q "$SSH_CONNECTION_NAME"; then
        # Check if connection is active
        if echo "$response" | grep -A 10 "$SSH_CONNECTION_NAME" | grep -q '"connected": true'; then
            return 0
        else
            return 1
        fi
    else
        return 1
    fi
}

# Check network connectivity to host
check_network() {
    if nc -z "$SSH_HOST" "$SSH_PORT" 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

# Get detailed SSH status
get_ssh_details() {
    local response
    response=$(curl -s --max-time $HEALTHCHECK_TIMEOUT http://localhost:8010/api/desktop/targets 2>/dev/null)
    
    if [ $? -eq 0 ]; then
        echo "$response" | jq -r '.[] | select(.target_type == "ssh") | "SSH Target: " + .name + " (" + .target_id + ") - Active: " + (.is_active | tostring)' 2>/dev/null || echo "SSH targets information available"
    else
        echo "Unable to retrieve SSH targets information"
    fi
}

# Main health check function
main() {
    local exit_code=0
    local status_message=""
    
    log "Starting SSH health check..."
    
    # Check TRAE backend
    if check_backend; then
        log "✓ TRAE backend is running"
        status_message="$status_message Backend: OK; "
    else
        log "✗ TRAE backend is not responding"
        status_message="$status_message Backend: FAIL; "
        exit_code=1
    fi
    
    # Check network connectivity
    if check_network; then
        log "✓ Network connectivity to $SSH_HOST:$SSH_PORT is OK"
        status_message="$status_message Network: OK; "
    else
        log "✗ Cannot reach $SSH_HOST:$SSH_PORT"
        status_message="$status_message Network: FAIL; "
        exit_code=1
    fi
    
    # Check SSH connection status
    if [ $exit_code -eq 0 ]; then
        if check_ssh_status; then
            log "✓ SSH connection '$SSH_CONNECTION_NAME' is active"
            status_message="$status_message SSH: CONNECTED; "
        else
            log "✗ SSH connection '$SSH_CONNECTION_NAME' is not active"
            status_message="$status_message SSH: DISCONNECTED; "
            exit_code=1
        fi
        
        # Get detailed SSH information
        log "SSH Details:"
        get_ssh_details | while read -r line; do
            log "  $line"
        done
    fi
    
    # Summary
    log "Health check completed: $status_message"
    
    if [ $exit_code -eq 0 ]; then
        log "✓ All SSH health checks passed"
        echo "SSH_HEALTH_STATUS=OK"
    else
        log "✗ SSH health check failed"
        echo "SSH_HEALTH_STATUS=FAIL"
    fi
    
    exit $exit_code
}

# Handle different modes
case "${1:-check}" in
    "check")
        main
        ;;
    "status")
        # Quick status check for monitoring
        if check_backend && check_network && check_ssh_status; then
            echo "SSH_STATUS=HEALTHY"
            exit 0
        else
            echo "SSH_STATUS=UNHEALTHY"
            exit 1
        fi
        ;;
    "network")
        # Network connectivity only
        if check_network; then
            echo "NETWORK_STATUS=OK"
            exit 0
        else
            echo "NETWORK_STATUS=FAIL"
            exit 1
        fi
        ;;
    "details")
        # Detailed information
        echo "=== SSH Health Check Details ==="
        echo "Host: $SSH_HOST:$SSH_PORT"
        echo "User: $SSH_USER"
        echo "Connection Name: $SSH_CONNECTION_NAME"
        echo "Timestamp: $(date)"
        echo ""
        main
        ;;
    *)
        echo "Usage: $0 [check|status|network|details]"
        echo "  check   - Full health check (default)"
        echo "  status  - Quick status check"
        echo "  network - Network connectivity only"
        echo "  details - Detailed health information"
        exit 1
        ;;
esac