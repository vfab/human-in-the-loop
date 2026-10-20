/**
 * HITL Dashboard - Main JavaScript Controller
 */

class HITLDashboard {
    constructor() {
        this.workflows = [];
        this.currentWorkflow = null;
        this.currentRunId = null;
        this.ws = null;
        this.pendingRequests = {};
        this.init();
    }

    async init() {
        console.log('[Dashboard] Initializing...');
        
        // Fetch workflows
        await this.loadWorkflows();
        
        // Setup event listeners
        this.setupEventListeners();
        
        // Update connection status
        this.updateConnectionStatus();
    }

    async loadWorkflows() {
        try {
            const response = await fetch('/workflows');
            this.workflows = await response.json();
            this.renderWorkflowList();
            console.log(`[Dashboard] Loaded ${this.workflows.length} workflows`);
        } catch (error) {
            console.error('[Dashboard] Failed to load workflows:', error);
            this.showError('Failed to load workflows');
        }
    }

    renderWorkflowList() {
        const list = document.getElementById('workflowList');
        list.innerHTML = '';
        
        for (const workflow of this.workflows) {
            const item = document.createElement('button');
            item.className = 'workflow-item';
            item.innerHTML = `
                <span class="workflow-item-name">${workflow.name}</span>
                <span class="workflow-item-desc">${workflow.description}</span>
            `;
            item.onclick = () => this.selectWorkflow(workflow);
            list.appendChild(item);
        }
    }

    selectWorkflow(workflow) {
        console.log(`[Dashboard] Selected workflow: ${workflow.id}`);
        this.currentWorkflow = workflow;
        
        // Update UI
        this.updateUIForWorkflow();
        
        // Clear previous output
        this.clearOutput();
    }

    updateUIForWorkflow() {
        // Update sidebar
        document.querySelectorAll('.workflow-item').forEach(item => {
            item.classList.remove('active');
        });
        event.target.closest('.workflow-item').classList.add('active');
        
        // Show execution panel
        document.getElementById('selectionPanel').style.display = 'none';
        document.getElementById('executionPanel').style.display = 'flex';
        
        // Update title
        document.getElementById('workflowTitle').textContent = this.currentWorkflow.name;
        
        // Show input section if needed
        const inputSection = document.getElementById('inputSection');
        if (this.currentWorkflow.input_required) {
            inputSection.style.display = 'block';
            document.getElementById('workflowInput').placeholder = 
                this.currentWorkflow.input_placeholder || 'Enter input...';
        } else {
            inputSection.style.display = 'none';
        }
    }

    setupEventListeners() {
        // Start button
        document.getElementById('startButton').addEventListener('click', () => this.startWorkflow());
        
        // Close button
        document.getElementById('closeButton').addEventListener('click', () => this.closeWorkflow());
        
        // Approval modal
        document.getElementById('approveButton').addEventListener('click', () => this.submitApproval(true));
        document.getElementById('rejectButton').addEventListener('click', () => this.submitApproval(false));
        
        // Input modal
        document.getElementById('submitInputButton').addEventListener('click', () => this.submitInput());
        document.getElementById('cancelInputButton').addEventListener('click', () => this.closeInputModal());
        
        // Allow Enter key to submit input
        document.getElementById('inputField').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.submitInput();
        });
        
        // Close workflow input
        document.getElementById('workflowInput').addEventListener('keypress', (e) => {
            if (e.ctrlKey && e.key === 'Enter') this.startWorkflow();
        });
    }

    async startWorkflow() {
        if (!this.currentWorkflow) return;
        
        const input = document.getElementById('workflowInput').value;
        
        try {
            // Start the workflow
            const response = await fetch(
                `/api/workflows/${this.currentWorkflow.id}/start`,
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ input })
                }
            );
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            const result = await response.json();
            this.currentRunId = result.run_id;
            
            console.log(`[Dashboard] Started workflow run: ${this.currentRunId}`);
            this.setStatus('running');
            this.clearOutput();
            this.addMessage('system', `Workflow starting...`);
            
            // Connect WebSocket
            this.connectWebSocket();
            
        } catch (error) {
            console.error('[Dashboard] Failed to start workflow:', error);
            this.showError(`Failed to start workflow: ${error.message}`);
        }
    }

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${protocol}//${window.location.host}/ws/workflow/${this.currentWorkflow.id}/${this.currentRunId}`;
        
        console.log(`[Dashboard] Connecting WebSocket: ${url}`);
        
        this.ws = new WebSocket(url);
        
        this.ws.onopen = () => {
            console.log('[WebSocket] Connected');
            this.updateConnectionStatus();
        };
        
        this.ws.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);
                this.handleWorkflowEvent(message);
            } catch (error) {
                console.error('[WebSocket] Failed to parse message:', error);
            }
        };
        
        this.ws.onerror = (error) => {
            console.error('[WebSocket] Error:', error);
            this.updateConnectionStatus();
        };
        
        this.ws.onclose = () => {
            console.log('[WebSocket] Disconnected');
            this.updateConnectionStatus();
        };
    }

    handleWorkflowEvent(event) {
        console.log(`[Event] ${event.type}:`, event);
        
        switch (event.type) {
            case 'agent_message':
                this.addMessage(event.agent_name || 'agent', event.content, event.severity);
                break;
                
            case 'approval_required':
                this.showApprovalModal(event);
                break;
                
            case 'input_required':
                this.showInputModal(event);
                break;
                
            case 'workflow_complete':
                this.setStatus('complete');
                this.addMessage('system', '✓ Workflow completed');
                break;
                
            case 'error':
                this.setStatus('error');
                this.addMessage('error', event.data.message || 'Unknown error');
                break;
                
            case 'workflow_start':
                this.addMessage('system', event.content);
                break;
        }
    }

    addMessage(agent, content, severity = 'info') {
        const output = document.getElementById('outputContent');
        const message = document.createElement('div');
        message.className = `output-message ${severity === 'error' ? 'error' : agent === 'system' ? 'system' : 'agent'}`;
        
        const timestamp = new Date().toLocaleTimeString();
        const header = document.createElement('div');
        header.className = 'message-header';
        header.innerHTML = `
            <span class="message-agent">${agent}</span>
            <span class="message-time">${timestamp}</span>
        `;
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.textContent = content;
        
        message.appendChild(header);
        message.appendChild(contentDiv);
        
        // Remove placeholder
        if (output.querySelector('.placeholder')) {
            output.innerHTML = '';
        }
        
        output.appendChild(message);
        
        // Scroll to bottom
        output.scrollTop = output.scrollHeight;
    }

    clearOutput() {
        const output = document.getElementById('outputContent');
        output.innerHTML = '<p class="placeholder">Waiting for workflow output...</p>';
    }

    showApprovalModal(event) {
        const modal = document.getElementById('approvalModal');
        document.getElementById('approvalPrompt').textContent = event.data.prompt;
        
        const content = document.getElementById('approvalContent');
        content.textContent = event.data.content || '';
        
        // Store request ID for later submission
        this.currentRequestId = event.data.request_id;
        
        modal.style.display = 'flex';
    }

    showInputModal(event) {
        const modal = document.getElementById('inputModal');
        document.getElementById('inputPrompt').textContent = event.data.prompt;
        
        const field = document.getElementById('inputField');
        field.value = '';
        field.focus();
        
        // Store request ID for later submission
        this.currentRequestId = event.data.request_id;
        
        modal.style.display = 'flex';
    }

    closeApprovalModal() {
        document.getElementById('approvalModal').style.display = 'none';
    }

    closeInputModal() {
        document.getElementById('inputModal').style.display = 'none';
    }

    async submitApproval(approved) {
        if (!this.currentWorkflow || !this.currentRunId) return;
        
        try {
            const response = await fetch(
                `/api/workflows/${this.currentWorkflow.id}/approve`,
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        run_id: this.currentRunId,
                        request_id: this.currentRequestId,
                        approved: approved,
                        feedback: ''
                    })
                }
            );
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            this.closeApprovalModal();
            this.addMessage(
                'system',
                approved ? '✓ Response approved' : '✗ Response rejected'
            );
            
        } catch (error) {
            console.error('[Dashboard] Failed to submit approval:', error);
            this.showError(`Failed to submit approval: ${error.message}`);
        }
    }

    async submitInput() {
        if (!this.currentWorkflow || !this.currentRunId) return;
        
        const input = document.getElementById('inputField').value.trim();
        if (!input) return;
        
        try {
            const response = await fetch(
                `/api/workflows/${this.currentWorkflow.id}/input`,
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        run_id: this.currentRunId,
                        request_id: this.currentRequestId,
                        input: input
                    })
                }
            );
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            this.closeInputModal();
            this.addMessage('user', input);
            
        } catch (error) {
            console.error('[Dashboard] Failed to submit input:', error);
            this.showError(`Failed to submit input: ${error.message}`);
        }
    }

    closeWorkflow() {
        console.log('[Dashboard] Closing workflow');
        
        // Close WebSocket
        if (this.ws) {
            this.ws.close();
        }
        
        // Reset UI
        this.currentWorkflow = null;
        this.currentRunId = null;
        
        document.getElementById('executionPanel').style.display = 'none';
        document.getElementById('selectionPanel').style.display = 'flex';
        
        document.querySelectorAll('.workflow-item').forEach(item => {
            item.classList.remove('active');
        });
        
        this.setStatus('ready');
    }

    setStatus(status) {
        const badge = document.getElementById('statusBadge');
        badge.textContent = status.charAt(0).toUpperCase() + status.slice(1);
        badge.className = `status-badge ${status}`;
    }

    updateConnectionStatus() {
        const indicator = document.getElementById('connectionStatus');
        const text = document.getElementById('statusText');
        
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            indicator.classList.add('connected');
            indicator.classList.remove('disconnected');
            text.textContent = 'Connected';
        } else {
            indicator.classList.remove('connected');
            indicator.classList.add('disconnected');
            text.textContent = this.ws ? 'Disconnected' : 'Disconnected';
        }
    }

    showError(message) {
        this.addMessage('error', message, 'error');
    }
}

// Initialize dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new HITLDashboard();
});
