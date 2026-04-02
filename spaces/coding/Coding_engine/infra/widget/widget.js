/**
 * Coding Engine Widget - Embeddable JavaScript Client
 */

class CodingEngineWidget {
    constructor(options = {}) {
        // Auto-detect API URL - use port 8000 for the control server
        if (options.apiUrl) {
            this.apiUrl = options.apiUrl;
        } else {
            // Direct string construction for maximum compatibility
            const hostname = window.location.hostname || 'localhost';
            const protocol = window.location.protocol || 'http:';
            this.apiUrl = `${protocol}//${hostname}:8000`;
        }
        // VNC URL uses port 6080
        const hostname = window.location.hostname || 'localhost';
        this.vncUrl = options.vncUrl || `${window.location.protocol}//${hostname}:6080`;
        this.vncPath = options.vncPath || '/vnc/vnc.html';
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.reconnectDelay = 2000;
        this.gitConfigured = false;
        this.uploadedRequirements = null;  // Store uploaded JSON
        
        // Request notification permission on init
        this.requestNotificationPermission();
        
        console.log('CodingEngineWidget initialized with API URL:', this.apiUrl);
        
        this.init();
    }
    
    // Request browser notification permission
    requestNotificationPermission() {
        if ('Notification' in window) {
            if (Notification.permission === 'granted') {
                this.notificationsEnabled = true;
            } else if (Notification.permission !== 'denied') {
                Notification.requestPermission().then(permission => {
                    this.notificationsEnabled = permission === 'granted';
                });
            }
        }
    }
    
    // Send desktop notification
    sendNotification(title, body, icon = '🚀') {
        if (this.notificationsEnabled && 'Notification' in window) {
            new Notification(title, {
                body: body,
                icon: `data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>${icon}</text></svg>`,
                tag: 'coding-engine',
                requireInteraction: true
            });
        }
        // Also play a sound if available
        this.playNotificationSound();
    }
    
    // Play notification sound
    playNotificationSound() {
        try {
            const audio = new Audio('data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1mZGtxc3V2dnZ0c3FtaGNdWVVSUE9OTk9PT1BSVFZZXF9iZWlucnZ5fH5/f35+fXp4dHBsZ2NfW1dUUU9OTExMTE1OT1JUV1pcX2JlZ2ttb3FzdHV1dXRzcnBtamhkYl9cWlhVU1FRUFFSU1RWV1laW11fYGJjZGVmZ2doaGdnZmVkY2JhYF5dXFtaWVlYV1dXVldXV1hYWFlZWVpbW1xcXV1dXl5eXl5fX19fX19fX19fX19fXl5eXl5dXV1dXFxcXFtbWltaWlpaWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVla');
            audio.volume = 0.3;
            audio.play().catch(() => {}); // Ignore errors
        } catch (e) {}
    }
    
    async init() {
        this.bindElements();
        this.bindEvents();
        this.setupTabs();
        await this.checkGitStatus();
        await this.fetchStatus();
        this.connectWebSocket();
        this.startStatusPolling();
    }
    
    bindElements() {
        // Status elements
        this.statusIndicator = document.getElementById('status-indicator');
        this.statusText = document.getElementById('status-text');
        this.connectionStatus = document.getElementById('connection-status');
        
        // Preview elements
        this.vncIframe = document.getElementById('vnc-iframe');
        this.previewOverlay = document.getElementById('preview-overlay');
        
        // Log container
        this.logsContainer = document.getElementById('logs-container');
        
        // Metrics
        this.metricIterations = document.getElementById('metric-iterations');
        this.metricFiles = document.getElementById('metric-files');
        this.metricTestsPassed = document.getElementById('metric-tests-passed');
        this.metricTestsFailed = document.getElementById('metric-tests-failed');
        this.metricCliErrors = document.getElementById('metric-cli-errors');
        this.metricConfidence = document.getElementById('metric-confidence');
        this.metricUptime = document.getElementById('metric-uptime');
        
        // Controls
        this.startBtn = document.getElementById('start-btn');
        this.stopBtn = document.getElementById('stop-btn');
        this.projectBadge = document.getElementById('project-type');
        
        // Config inputs
        this.requirementsInput = document.getElementById('requirements-file');
        this.outputDirInput = document.getElementById('output-dir');
        this.maxConcurrentInput = document.getElementById('max-concurrent');
        this.sliceSizeInput = document.getElementById('slice-size');
        this.enablePreviewCheckbox = document.getElementById('enable-preview');
        
        // File upload elements
        this.fileUploadInput = document.getElementById('requirements-upload');
        this.fileDropZone = document.getElementById('file-drop-zone');
        this.uploadedFileName = document.getElementById('uploaded-file-name');
        this.jsonPreviewContainer = document.getElementById('json-preview-container');
        this.jsonPreview = document.getElementById('json-preview');
        this.clearJsonBtn = document.getElementById('clear-json-btn');
        
        // Git elements
        this.enableGitCheckbox = document.getElementById('enable-git');
        this.gitOptions = document.getElementById('git-options');
        this.repoNameInput = document.getElementById('repo-name');
        this.repoDescriptionInput = document.getElementById('repo-description');
        this.repoPrivateCheckbox = document.getElementById('repo-private');
        this.gitStatusBadge = document.getElementById('git-status-badge');
        this.gitWarning = document.getElementById('git-warning');
        this.gitResultBanner = document.getElementById('git-result-banner');
        this.gitRepoLink = document.getElementById('git-repo-link');
        this.gitResultClose = document.getElementById('git-result-close');
    }
    
    bindEvents() {
        // Control buttons
        this.startBtn.addEventListener('click', () => this.startEngine());
        this.stopBtn.addEventListener('click', () => this.stopEngine());
        
        // Fullscreen button
        document.getElementById('fullscreen-btn').addEventListener('click', () => {
            const widget = document.getElementById('coding-engine-widget');
            if (document.fullscreenElement) {
                document.exitFullscreen();
            } else {
                widget.requestFullscreen();
            }
        });
        
        // File upload events
        if (this.fileUploadInput) {
            this.fileUploadInput.addEventListener('change', (e) => this.handleFileSelect(e));
        }
        
        // Drag and drop events
        if (this.fileDropZone) {
            // Click to open file dialog
            this.fileDropZone.addEventListener('click', () => {
                if (this.fileUploadInput) {
                    this.fileUploadInput.click();
                }
            });

            this.fileDropZone.addEventListener('dragover', (e) => {
                e.preventDefault();
                this.fileDropZone.classList.add('drag-over');
            });
            
            this.fileDropZone.addEventListener('dragleave', () => {
                this.fileDropZone.classList.remove('drag-over');
            });
            
            this.fileDropZone.addEventListener('drop', (e) => {
                e.preventDefault();
                this.fileDropZone.classList.remove('drag-over');
                const files = e.dataTransfer.files;
                if (files.length > 0) {
                    this.handleFileUpload(files[0]);
                }
            });
        }
        
        // Clear JSON button
        if (this.clearJsonBtn) {
            this.clearJsonBtn.addEventListener('click', () => this.clearUploadedJson());
        }
        
        // Git checkbox toggle
        if (this.enableGitCheckbox) {
            this.enableGitCheckbox.addEventListener('change', (e) => {
                this.toggleGitOptions(e.target.checked);
            });
        }
        
        // Git result close button
        if (this.gitResultClose) {
            this.gitResultClose.addEventListener('click', () => {
                this.gitResultBanner.style.display = 'none';
            });
        }
    }
    
    // Handle file selection from input
    handleFileSelect(event) {
        const file = event.target.files[0];
        if (file) {
            this.handleFileUpload(file);
        }
    }
    
    // Handle uploaded file
    handleFileUpload(file) {
        if (!file.name.endsWith('.json')) {
            this.addLog('error', 'Only JSON files are allowed');
            return;
        }
        
        const reader = new FileReader();
        reader.onload = (e) => {
            try {
                const json = JSON.parse(e.target.result);
                this.uploadedRequirements = json;
                this.showJsonPreview(json, file.name);
                this.addLog('success', `Loaded requirements from ${file.name}`);
                
                // Clear the server file input when uploading a file
                if (this.requirementsInput) {
                    this.requirementsInput.value = '';
                }
            } catch (error) {
                this.addLog('error', `Invalid JSON: ${error.message}`);
                this.uploadedRequirements = null;
            }
        };
        reader.readAsText(file);
    }
    
    // Show JSON preview
    showJsonPreview(json, fileName) {
        if (this.uploadedFileName) {
            this.uploadedFileName.textContent = `✓ ${fileName}`;
        }
        if (this.jsonPreviewContainer) {
            this.jsonPreviewContainer.style.display = 'block';
        }
        if (this.jsonPreview) {
            // Pretty print with truncation for large files
            const preview = JSON.stringify(json, null, 2);
            const maxLength = 2000;
            this.jsonPreview.textContent = preview.length > maxLength 
                ? preview.substring(0, maxLength) + '\n... (truncated)'
                : preview;
        }
    }
    
    // Clear uploaded JSON
    clearUploadedJson() {
        this.uploadedRequirements = null;
        if (this.uploadedFileName) {
            this.uploadedFileName.textContent = '';
        }
        if (this.jsonPreviewContainer) {
            this.jsonPreviewContainer.style.display = 'none';
        }
        if (this.jsonPreview) {
            this.jsonPreview.textContent = '';
        }
        if (this.fileUploadInput) {
            this.fileUploadInput.value = '';
        }
        this.addLog('info', 'Cleared uploaded requirements');
    }
    
    setupTabs() {
        const tabs = document.querySelectorAll('.tab');
        const panes = document.querySelectorAll('.tab-pane');
        
        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const target = tab.dataset.tab;
                
                tabs.forEach(t => t.classList.remove('active'));
                panes.forEach(p => p.classList.remove('active'));
                
                tab.classList.add('active');
                document.getElementById(`${target}-tab`).classList.add('active');
            });
        });
    }
    
    toggleGitOptions(enabled) {
        if (this.gitOptions) {
            this.gitOptions.style.display = enabled ? 'block' : 'none';
        }
        
        // Show warning if git not configured on server
        if (enabled && !this.gitConfigured && this.gitWarning) {
            this.gitWarning.style.display = 'block';
        } else if (this.gitWarning) {
            this.gitWarning.style.display = 'none';
        }
    }
    
    async checkGitStatus() {
        try {
            const response = await fetch(`${this.apiUrl}/api/git/status`);
            const data = await response.json();
            
            this.gitConfigured = data.configured;
            
            if (this.gitStatusBadge) {
                if (data.configured) {
                    this.gitStatusBadge.textContent = data.username ? `@${data.username}` : 'Enabled';
                    this.gitStatusBadge.className = 'badge badge-enabled';
                } else {
                    this.gitStatusBadge.textContent = 'Not Configured';
                    this.gitStatusBadge.className = 'badge badge-warning';
                }
            }
            
            this.addLog('info', `Git: ${data.message}`);
        } catch (error) {
            console.error('Failed to check git status:', error);
            this.gitConfigured = false;
        }
    }
    
    showGitResult(repoUrl, cloneUrl) {
        if (this.gitResultBanner && this.gitRepoLink) {
            this.gitRepoLink.href = repoUrl;
            this.gitRepoLink.textContent = repoUrl;
            this.gitResultBanner.style.display = 'block';
        }
    }
    
    async fetchStatus() {
        try {
            const response = await fetch(`${this.apiUrl}/api/status`);
            const data = await response.json();
            this.updateState(data.state);
            this.updateUptime(data.uptime_seconds);
            
            // Check if git result should be shown
            if (data.state.git_repo_url && data.state.git_pushed) {
                this.showGitResult(data.state.git_repo_url);
            }
        } catch (error) {
            console.error('Failed to fetch status:', error);
        }
    }
    
    connectWebSocket() {
        // Use the API URL's hostname for WebSocket
        const apiHost = new URL(this.apiUrl).host;
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${apiHost}/ws`;
        
        console.log('Connecting WebSocket to:', wsUrl);
        
        try {
            this.ws = new WebSocket(wsUrl);
            // Note: binaryType defaults to 'blob', we handle both blob and text in handleWebSocketMessage
            
            this.ws.onopen = ()  =>  {
                this.reconnectAttempts = 0;
                this.setConnectionStatus(true);
                this.addLog('info', 'WebSocket connected');
                console.log('WebSocket connected successfully to', wsUrl);
            };
            
            this.ws.onclose = () => {
                this.setConnectionStatus(false);
                this.addLog('warning', 'WebSocket disconnected');
                this.scheduleReconnect();
            };
            
            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.addLog('error', 'WebSocket error');
            };
            
            this.ws.onmessage = (event) => this.handleWebSocketMessage(event);
        } catch (error) {
            console.error('Failed to connect WebSocket:', error);
            this.scheduleReconnect();
        }
    }
    
    scheduleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            setTimeout(() => this.connectWebSocket(), this.reconnectDelay);
        }
    }
    
    handleWebSocketMessage(event) {
        let data;
        
        // Handle both text and blob data
        if (event.data instanceof Blob) {
            // Read blob as text
            const reader = new FileReader();
            reader.onload = () => {
                try {
                    data = JSON.parse(reader.result);
                    this.processWebSocketData(data);
                } catch (e) {
                    console.error('Failed to parse WebSocket blob:', e);
                }
            };
            reader.readAsText(event.data);
            return;
        }
        
        try {
            data = JSON.parse(event.data);
            this.processWebSocketData(data);
        } catch (e) {
            console.error('Failed to parse WebSocket message:', e);
        }
    }
    
    processWebSocketData(data) {
        // Handle initial connection state
        if (data.type === 'connected' || data.type === 'status') {
            if (data.state) {
                this.updateState(data.state);
            }
            if (data.git_configured !== undefined) {
                this.gitConfigured = data.git_configured;
            }
            return;
        }
        
        // Handle events
        switch (data.type) {
            case 'engine_started':
                this.addLog('success', data.message || 'Engine started');
                this.updateStatus('running');
                break;
                
            case 'engine_stopped':
                this.addLog('info', data.message || 'Engine stopped');
                this.updateStatus('stopped');
                if (data.data) {
                    this.updateMetrics(data.data);
                    if (data.data.git_repo_url) {
                        this.showGitResult(data.data.git_repo_url);
                    }
                }
                // Send completion notification with details
                const completionMsg = data.data 
                    ? `${data.data.files_generated || 0} Dateien generiert in ${data.data.iterations || 0} Iterationen`
                    : 'Code-Generierung abgeschlossen';
                this.sendNotification('✅ Engine fertig!', completionMsg, '✅');
                break;
                
            case 'engine_error':
                this.addLog('error', data.message || 'Engine error');
                this.updateStatus('error');
                break;
                
            case 'cli_error':
                // Handle CLI errors prominently
                const errorType = data.data?.error_type || 'UNKNOWN';
                const hint = data.data?.hint || 'Check container logs for details';
                const totalErrors = data.data?.total_cli_errors || 0;
                
                // Show prominent error message
                this.addLog('error', `🚨 CLI ERROR [${errorType}]: ${data.message}`);
                this.addLog('warning', `💡 Hint: ${hint}`);
                
                // Update CLI errors metric
                if (this.metricCliErrors) {
                    this.metricCliErrors.textContent = totalErrors;
                    this.metricCliErrors.classList.add('error-highlight');
                }
                
                // Show notification for first error
                if (totalErrors === 1) {
                    this.sendNotification('⚠️ CLI Fehler!', `${errorType}: ${hint}`, '⚠️');
                }
                break;
                
            case 'cli_success':
                this.addLog('success', data.message || 'Code generated successfully');
                break;
                
            case 'iteration_complete':
                this.addLog('info', data.message || `Iteration ${data.data?.iteration}`);
                if (data.data?.iteration) {
                    this.metricIterations.textContent = data.data.iteration;
                }
                break;
                
            case 'file_generated':
                this.addLog('success', data.message || 'File generated');
                if (data.data?.total_files) {
                    this.metricFiles.textContent = data.data.total_files;
                }
                break;
                
            case 'test_result':
                const logType = data.message?.includes('failed') ? 'warning' : 'info';
                this.addLog(logType, data.message || 'Test result');
                if (data.data) {
                    this.metricTestsPassed.textContent = data.data.passed || 0;
                    this.metricTestsFailed.textContent = data.data.failed || 0;
                }
                break;
                
            case 'preview_ready':
                this.addLog('success', 'Preview ready');
                this.showPreview();
                break;
                
            // Git events
            case 'git_repo_created':
                this.addLog('success', data.message || 'Repository created');
                break;
                
            case 'git_push_started':
                this.addLog('info', data.message || 'Pushing to GitHub...');
                break;
                
            case 'git_push_complete':
                this.addLog('success', data.message || 'Code pushed to GitHub!');
                if (data.data?.repo_url) {
                    this.showGitResult(data.data.repo_url, data.data.clone_url);
                }
                // Send git notification with repo URL
                const repoUrl = data.data?.repo_url || 'GitHub';
                this.sendNotification('🚀 Code gepusht!', `Dein Code wurde zu ${repoUrl} hochgeladen!`, '🚀');
                break;
                
            case 'git_error':
                this.addLog('error', data.message || 'Git error');
                break;
                
            case 'log_info':
            case 'log_warning':
            case 'log_error':
                const level = data.type.replace('log_', '');
                this.addLog(level, data.message);
                break;
                
            default:
                if (data.message) {
                    this.addLog('info', data.message);
                }
        }
    }
    
    updateState(state) {
        this.updateStatus(state.status);
        
        // Update metrics
        this.metricIterations.textContent = state.iterations || 0;
        this.metricFiles.textContent = state.files_generated || 0;
        this.metricTestsPassed.textContent = state.tests_passed || 0;
        this.metricTestsFailed.textContent = state.tests_failed || 0;
        this.metricConfidence.textContent = `${Math.round((state.confidence_score || 0) * 100)}%`;
        
        // Update CLI errors metric if it exists
        if (this.metricCliErrors) {
            this.metricCliErrors.textContent = state.cli_errors || 0;
            if (state.cli_errors > 0) {
                this.metricCliErrors.classList.add('error-highlight');
            } else {
                this.metricCliErrors.classList.remove('error-highlight');
            }
        }
        
        // Update controls
        this.startBtn.disabled = state.engine_running;
        this.stopBtn.disabled = !state.engine_running;
        
        // Update project type badge
        if (state.project_type && state.project_type !== 'unknown') {
            this.projectBadge.textContent = state.project_type;
        } else {
            this.projectBadge.textContent = '';
        }
        
        // Show preview if running
        if (state.engine_running) {
            this.showPreview();
        }
        
        // Show git result if available
        if (state.git_repo_url && state.git_pushed) {
            this.showGitResult(state.git_repo_url);
        }
    }
    
    updateStatus(status) {
        this.statusText.textContent = status.charAt(0).toUpperCase() + status.slice(1);
        this.statusIndicator.className = `status-indicator ${status}`;
        
        // Update button states
        const isRunning = status === 'running' || status === 'starting';
        this.startBtn.disabled = isRunning;
        this.stopBtn.disabled = !isRunning;
    }
    
    updateMetrics(data) {
        if (data.iterations !== undefined) {
            this.metricIterations.textContent = data.iterations;
        }
        if (data.files_generated !== undefined) {
            this.metricFiles.textContent = data.files_generated;
        }
    }
    
    updateUptime(seconds) {
        if (seconds > 0) {
            const mins = Math.floor(seconds / 60);
            const secs = Math.floor(seconds % 60);
            this.metricUptime.textContent = `${mins}m ${secs}s`;
        }
    }
    
    setConnectionStatus(connected) {
        this.connectionStatus.textContent = connected ? 'Connected' : 'Disconnected';
        this.connectionStatus.className = `connection ${connected ? 'connected' : 'disconnected'}`;
    }
    
    showPreview() {
        if (!this.vncIframe.src || this.vncIframe.src === '') {
            // Use the separate VNC URL for the iframe
            this.vncIframe.src = `${this.vncUrl}${this.vncPath}`;
        }
        this.previewOverlay.classList.add('hidden');
    }
    
    hidePreview() {
        this.previewOverlay.classList.remove('hidden');
    }
    
    addLog(level, message) {
        const entry = document.createElement('div');
        entry.className = `log-entry ${level}`;
        
        const time = new Date().toLocaleTimeString();
        entry.innerHTML = `
            <span class="log-time">${time}</span>
            <span class="log-message">${this.escapeHtml(message)}</span>
        `;
        
        this.logsContainer.appendChild(entry);
        this.logsContainer.scrollTop = this.logsContainer.scrollHeight;
        
        // Keep max 200 entries
        while (this.logsContainer.children.length > 200) {
            this.logsContainer.removeChild(this.logsContainer.firstChild);
        }
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    async startEngine() {
        // Check WebSocket connection
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            this.addLog('error', 'Not connected to server');
            return;
        }

        // Use correct element IDs from bindElements()
        const reqFile = this.requirementsInput?.value?.trim() || '';
        const outDir = this.outputDirInput?.value?.trim() || '';
        const runMode = document.getElementById('run-mode')?.value || 'hybrid';
        
        // Git config (use correct IDs)
        const gitEnabled = this.enableGitCheckbox?.checked || false;

        const body = {
            requirements_file: reqFile || null,
            output_dir: outDir || '/output',
            run_mode: runMode
        };
        
        // Use uploaded JSON if available
        if (this.uploadedRequirements) {
            body.requirements_json = this.uploadedRequirements;
            body.requirements_file = null;
        }
        
        // Add git config if enabled
        if (gitEnabled && this.gitConfigured) {
            body.git_config = {
                repo_name: this.repoNameInput?.value?.trim() || null,
                description: this.repoDescriptionInput?.value?.trim() || 'Generated by Coding Engine',
                private: this.repoPrivateCheckbox?.checked || false,
                create_repo: true,
                push_on_complete: true
            };
        }
        
        try {
            this.addLog('info', 'Starting engine...');
            
            // Hide any previous git result
            if (this.gitResultBanner) {
                this.gitResultBanner.style.display = 'none';
            }
            
            const response = await fetch(`${this.apiUrl}/api/start`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(body)
            });
            
            const data = await response.json();
            
            if (response.ok) {
                this.addLog('success', data.message || 'Engine starting');
                if (data.git_enabled) {
                    this.addLog('info', 'Git integration enabled - will push on completion');
                }
                this.updateStatus('starting');
            } else {
                this.addLog('error', data.detail || 'Failed to start engine');
            }
        } catch (error) {
            this.addLog('error', `Error: ${error.message}`);
        }
    }
    
    async stopEngine() {
        try {
            this.addLog('info', 'Stopping engine...');
            
            const response = await fetch(`${this.apiUrl}/api/stop`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ graceful: true, save_state: true })
            });
            
            const data = await response.json();
            
            if (response.ok) {
                this.addLog('info', 'Engine stopped');
                this.updateStatus('stopping');
            } else {
                this.addLog('error', data.detail || 'Failed to stop engine');
            }
        } catch (error) {
            this.addLog('error', `Error: ${error.message}`);
        }
    }
    
    startStatusPolling() {
        // Poll status every 5 seconds as backup
        setInterval(() => this.fetchStatus(), 5000);
    }
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CodingEngineWidget;
}