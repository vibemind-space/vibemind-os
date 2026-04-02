#!/bin/bash
# SSH Auto-Connect Script for TRAE Remote Desktop
# Automatically establishes SSH connection to host system for desktop switching

set -e

# Configuration from environment variables
SSH_HOST="${SSH_HOST:-host.docker.internal}"
SSH_PORT="${SSH_PORT:-22}"
SSH_USER="${SSH_USER:-}"
SSH_PASS="${SSH_PASS:-}"
SSH_KEY="${SSH_KEY:-}"
SSH_CONNECTION_NAME="${SSH_CONNECTION_NAME:-host_system}"
SSH_TIMEOUT="${SSH_TIMEOUT:-30}"
SSH_RETRY_ATTEMPTS="${SSH_RETRY_ATTEMPTS:-3}"
SSH_RETRY_DELAY="${SSH_RETRY_DELAY:-10}"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] SSH-AutoConnect: $1"
}

# Error handling
error_exit() {
    log "ERROR: $1"
    exit 1
}

# Validate required environment variables
validate_config() {
    log "Validating SSH configuration..."
    
    if [ -z "$SSH_USER" ]; then
        error_exit "SSH_USER environment variable is required"
    fi
    
    if [ -z "$SSH_PASS" ] && [ -z "$SSH_KEY" ]; then
        error_exit "Either SSH_PASS or SSH_KEY must be provided"
    fi
    
    log "Configuration validated successfully"
}

# Test network connectivity to host
test_connectivity() {
    log "Testing network connectivity to $SSH_HOST:$SSH_PORT..."
    
    if ! nc -z "$SSH_HOST" "$SSH_PORT" 2>/dev/null; then
        error_exit "Cannot reach $SSH_HOST:$SSH_PORT - check network configuration"
    fi
    
    log "Network connectivity confirmed"
}

# Setup SSH key if provided
setup_ssh_key() {
    if [ -n "$SSH_KEY" ]; then
        log "Setting up SSH key authentication..."
        
        # Create SSH directory
        mkdir -p /root/.ssh
        chmod 700 /root/.ssh
        
        # Write SSH key
        if [ -f "$SSH_KEY" ]; then
            # SSH_KEY is a file path
            cp "$SSH_KEY" /root/.ssh/id_rsa
        else
            # SSH_KEY is the key content
            echo "$SSH_KEY" > /root/.ssh/id_rsa
        fi
        
        chmod 600 /root/.ssh/id_rsa
        
        # Disable host key checking for Docker environment
        cat > /root/.ssh/config << EOF
Host *
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    LogLevel ERROR
EOF
        chmod 600 /root/.ssh/config
        
        log "SSH key authentication configured"
    fi
}

# Test SSH connection
test_ssh_connection() {
    log "Testing SSH connection to $SSH_USER@$SSH_HOST:$SSH_PORT..."
    
    local ssh_cmd="ssh -o ConnectTimeout=$SSH_TIMEOUT -o BatchMode=yes"
    
    if [ -n "$SSH_KEY" ]; then
        # Key-based authentication
        ssh_cmd="$ssh_cmd -i /root/.ssh/id_rsa"
    else
        # Password-based authentication
        ssh_cmd="sshpass -p '$SSH_PASS' $ssh_cmd"
    fi
    
    ssh_cmd="$ssh_cmd -p $SSH_PORT $SSH_USER@$SSH_HOST"
    
    if $ssh_cmd "echo 'SSH connection test successful'" 2>/dev/null; then
        log "SSH connection test successful"
        return 0
    else
        log "SSH connection test failed"
        return 1
    fi
}

# Add SSH connection to TRAE system
add_ssh_connection() {
    log "Adding SSH connection '$SSH_CONNECTION_NAME' to TRAE system..."
    
    # Wait for TRAE backend to be ready
    local max_wait=60
    local wait_count=0
    
    while [ $wait_count -lt $max_wait ]; do
        if curl -s http://localhost:8010/api/health >/dev/null 2>&1; then
            log "TRAE backend is ready"
            break
        fi
        
        log "Waiting for TRAE backend to start... ($wait_count/$max_wait)"
        sleep 2
        wait_count=$((wait_count + 2))
    done
    
    if [ $wait_count -ge $max_wait ]; then
        error_exit "TRAE backend did not start within $max_wait seconds"
    fi
    
    # Prepare SSH connection data
    local ssh_data
    if [ -n "$SSH_KEY" ]; then
        # Key-based authentication
        ssh_data=$(cat << EOF
{
    "name": "$SSH_CONNECTION_NAME",
    "host": "$SSH_HOST",
    "port": $SSH_PORT,
    "username": "$SSH_USER",
    "private_key_data": "$(cat /root/.ssh/id_rsa | base64 -w 0)",
    "auto_connect": true,
    "desktop_type": "windows",
    "description": "Auto-configured host system connection"
}
EOF
)
    else
        # Password-based authentication
        ssh_data=$(cat << EOF
{
    "name": "$SSH_CONNECTION_NAME",
    "host": "$SSH_HOST",
    "port": $SSH_PORT,
    "username": "$SSH_USER",
    "password": "$SSH_PASS",
    "auto_connect": true,
    "desktop_type": "windows",
    "description": "Auto-configured host system connection"
}
EOF
)
    fi
    
    # Add connection via API
    if curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "$ssh_data" \
        http://localhost:8010/api/desktop/ssh/add >/dev/null 2>&1; then
        log "SSH connection '$SSH_CONNECTION_NAME' added successfully"
    else
        log "Warning: Failed to add SSH connection via API (may already exist)"
    fi
}

# Connect to SSH
connect_ssh() {
    log "Connecting to SSH '$SSH_CONNECTION_NAME'..."
    
    local connect_data=$(cat << EOF
{
    "connection_name": "$SSH_CONNECTION_NAME"
}
EOF
)
    
    if curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "$connect_data" \
        http://localhost:8010/api/desktop/ssh/connect >/dev/null 2>&1; then
        log "SSH connection '$SSH_CONNECTION_NAME' established successfully"
    else
        log "Warning: Failed to establish SSH connection via API"
    fi
}

# Main execution with retry logic
main() {
    log "Starting SSH auto-connect process..."
    
    # Security warning
    if [ -n "$SSH_PASS" ]; then
        log "WARNING: Using password authentication. Consider using SSH keys for better security."
    fi
    
    validate_config
    setup_ssh_key
    test_connectivity
    
    # Retry SSH connection test
    local attempt=1
    while [ $attempt -le $SSH_RETRY_ATTEMPTS ]; do
        log "SSH connection attempt $attempt/$SSH_RETRY_ATTEMPTS"
        
        if test_ssh_connection; then
            log "SSH connection successful on attempt $attempt"
            break
        else
            if [ $attempt -lt $SSH_RETRY_ATTEMPTS ]; then
                log "SSH connection failed, retrying in $SSH_RETRY_DELAY seconds..."
                sleep $SSH_RETRY_DELAY
            else
                error_exit "SSH connection failed after $SSH_RETRY_ATTEMPTS attempts"
            fi
        fi
        
        attempt=$((attempt + 1))
    done
    
    # Add and connect SSH in TRAE system
    add_ssh_connection
    connect_ssh
    
    log "SSH auto-connect process completed successfully"
    log "Host system is now available for desktop switching in TRAE"
}

# Execute main function
main "$@"