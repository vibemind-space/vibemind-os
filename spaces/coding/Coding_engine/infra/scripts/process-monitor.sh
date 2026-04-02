#!/bin/bash
# Process Monitor for Supervisor
# Logs process state changes

LOG_FILE="/data/logs/process-monitor.log"

while read line; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ${line}" >> "${LOG_FILE}"
    
    # Parse event
    event_type=$(echo "$line" | grep -oP 'eventname:\K\w+' || echo "")
    process_name=$(echo "$line" | grep -oP 'processname:\K\w+' || echo "")
    
    if [ -n "$event_type" ] && [ -n "$process_name" ]; then
        echo "[MONITOR] ${process_name}: ${event_type}" >> "${LOG_FILE}"
        
        # Handle critical process failures
        case "$event_type" in
            PROCESS_STATE_FATAL)
                echo "[ALERT] Process ${process_name} entered FATAL state!" >> "${LOG_FILE}"
                ;;
            PROCESS_STATE_EXITED)
                echo "[INFO] Process ${process_name} exited" >> "${LOG_FILE}"
                ;;
        esac
    fi
    
    echo "RESULT 2"
    echo "OK"
done