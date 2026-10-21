/**
 * HITL Dashboard - Main JavaScript Controller
 */

// Sample inputs offered in the drop-down, keyed by workflow id.
const SAMPLE_INPUTS = {
    concurrent: [
        'Analyze the impact of large language models on software development.',
        'Evaluate the risks and benefits of migrating our monolith to microservices.',
        'Assess how remote work affects team productivity and company culture.',
        'Compare renewable energy options for a mid-sized data center.',
        'Analyze the security implications of adopting AI coding assistants.',
    ],
    group_chat: [
        'Discuss how our team should approach adopting AI tools for productivity.',
        'Debate whether we should build or buy a customer support chatbot.',
        'Discuss a rollout plan for a four-day work week.',
        'Plan the launch of a new mobile app with a limited budget.',
        'Discuss how to handle technical debt versus new feature work.',
    ],
    sequential: [
        'Write a brief introduction to artificial intelligence.',
        'Write a product announcement for a new project management tool.',
        'Draft a short explanation of cloud computing for non-technical executives.',
        'Write a one-paragraph summary of the benefits of unit testing.',
        'Write a friendly email inviting the team to a quarterly planning meeting.',
    ],
    // These workflows have no text box: the selected value is sent as the run input.
    approval: [
        { label: 'Default: status update + urgent budget review (2 emails)', value: 'default' },
        { label: 'Project status update request', value: 'status_update' },
        { label: 'Urgent Q4 budget review', value: 'budget_review' },
        { label: 'Meeting request for next week', value: 'meeting_request' },
        { label: 'Customer complaint: damaged order', value: 'customer_complaint' },
        { label: 'Question about an invoice total', value: 'invoice_question' },
    ],
    game: [
        { label: 'Number between 1 and 10 (default)', value: '10' },
        { label: 'Number between 1 and 20', value: '20' },
        { label: 'Number between 1 and 50', value: '50' },
        { label: 'Number between 1 and 100', value: '100' },
    ],
};

class HITLDashboard {
    constructor() {
        this.workflows = [];
        this.currentWorkflow = null;
        this.currentRunId = null;
        this.savedInputs = {};
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
        this.saveCurrentInput();
        if (!this.currentWorkflow || this.currentWorkflow.id !== workflow.id) {
            this.abortRun();
        }
        this.currentWorkflow = workflow;
        
        // Update UI
        this.updateUIForWorkflow();
        
        // Restore this workflow's previously entered input (blank if none)
        this.restoreSavedInput();
        
        // Clear previous output
        this.clearOutput();
    }

    usesTextBox(workflow = this.currentWorkflow) {
        return !!(workflow && workflow.input_required);
    }

    // The value sent to the workflow: the text box, or the drop-down choice for workflows without one.
    currentInputValue() {
        return this.usesTextBox()
            ? document.getElementById('workflowInput').value
            : document.getElementById('sampleSelect').value;
    }

    saveCurrentInput() {
        if (this.currentWorkflow) {
            this.savedInputs[this.currentWorkflow.id] = this.currentInputValue();
        }
    }

    restoreSavedInput() {
        const saved = this.savedInputs[this.currentWorkflow.id] || '';
        if (this.usesTextBox()) {
            document.getElementById('workflowInput').value = saved;
        } else {
            document.getElementById('sampleSelect').value = saved;
        }
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
        
        // The Start button lives in the input section, so it is always shown.
        // Workflows without a text box offer only the sample drop-down.
        const inputSection = document.getElementById('inputSection');
        const textBox = this.usesTextBox();
        inputSection.style.display = 'flex';
        inputSection.classList.toggle('sample-only', !textBox);
        document.getElementById('workflowInput').style.display = textBox ? '' : 'none';
        if (textBox) {
            document.getElementById('workflowInput').placeholder = 
                this.currentWorkflow.input_placeholder || 'Enter input...';
        }
        this.populateSamples(this.currentWorkflow.id);
    }

    populateSamples(workflowId) {
        const select = document.getElementById('sampleSelect');
        const header = document.querySelector('#inputSection .input-header');
        select.length = 1;
        (SAMPLE_INPUTS[workflowId] || []).forEach(sample => {
            const { label, value } = typeof sample === 'string'
                ? { label: sample, value: sample }
                : sample;
            const option = document.createElement('option');
            option.value = value;
            option.textContent = label.length > 70 ? label.slice(0, 67) + '…' : label;
            select.appendChild(option);
        });
        select.value = '';
        const hasSamples = select.options.length > 1;
        select.style.display = hasSamples ? '' : 'none';
        header.style.display = this.usesTextBox() || hasSamples ? '' : 'none';
    }

    setupEventListeners() {
        // Sample input drop-down: fills the text box when there is one
        document.getElementById('sampleSelect').addEventListener('change', (e) => {
            if (!e.target.value || !this.usesTextBox()) return;
            const field = document.getElementById('workflowInput');
            field.value = e.target.value;
            field.focus();
        });
        // Start button
        document.getElementById('startButton').addEventListener('click', () => this.startWorkflow());
        
        // Close button
        document.getElementById('closeButton').addEventListener('click', () => this.closeWorkflow());
        
        // Approval modal
        document.getElementById('approveButton').addEventListener('click', () => this.submitApproval(true));
        document.getElementById('rejectButton').addEventListener('click', () => this.submitApproval(false));
        
        // Input modal
        document.getElementById('submitInputButton').addEventListener('click', () => this.submitInput());
        document.getElementById('cancelInputButton').addEventListener('click', () => this.submitInput(''));
        
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
        
        const input = this.currentInputValue();
        
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
            this.setRunning(true);
            this.clearOutput();
            this.addMessage('system', `Workflow starting...`);
            
            // Connect WebSocket
            this.connectWebSocket();
            
        } catch (error) {
            console.error('[Dashboard] Failed to start workflow:', error);
            this.setRunning(false);
            this.showError(`Failed to start workflow: ${error.message}`);
        }
    }

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${protocol}//${window.location.host}/ws/workflow/${this.currentWorkflow.id}/${this.currentRunId}`;
        
        console.log(`[Dashboard] Connecting WebSocket: ${url}`);
        
        if (this.ws) {
            this.ws.onclose = null;
            this.ws.close();
        }
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
                this.closeModals();
                this.setStatus('complete');
                this.setRunning(false);
                this.addMessage('system', '✓ Workflow completed');
                break;
                
            case 'error':
                this.closeModals();
                this.setStatus('error');
                this.setRunning(false);
                this.addMessage('error', event.content || 'Unknown error', 'error');
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
        document.getElementById('approvalPrompt').textContent = event.prompt || 'Approve?';
        
        const content = document.getElementById('approvalContent');
        content.textContent = event.content || '';
        content.style.display = event.content ? '' : 'none';
        
        // Store request ID for later submission
        this.currentRequestId = event.request_id;
        
        modal.style.display = 'flex';
    }

    showInputModal(event) {
        const modal = document.getElementById('inputModal');
        document.getElementById('inputPrompt').textContent = event.prompt || 'Enter input:';
        
        // Quick-answer buttons for workflows that offer fixed options (e.g. the guessing game)
        const options = document.getElementById('inputOptions');
        options.innerHTML = '';
        (event.options || []).forEach(value => {
            const button = document.createElement('button');
            button.className = 'btn btn-secondary';
            button.textContent = value;
            button.addEventListener('click', () => this.submitInput(value));
            options.appendChild(button);
        });
        
        const field = document.getElementById('inputField');
        field.value = '';
        field.focus();
        
        // Store request ID for later submission
        this.currentRequestId = event.request_id;
        
        modal.style.display = 'flex';
    }

    closeApprovalModal() {
        document.getElementById('approvalModal').style.display = 'none';
    }

    closeModals() {
        this.closeApprovalModal();
        this.closeInputModal();
    }

    setRunning(running) {
        document.getElementById('startButton').disabled = running;
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

    async submitInput(overrideValue) {
        if (!this.currentWorkflow || !this.currentRunId) return;
        
        // A blank answer is valid: it means "no steering"
        const input = (typeof overrideValue === 'string'
            ? overrideValue
            : document.getElementById('inputField').value).trim();
        
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
            
        } catch (error) {
            console.error('[Dashboard] Failed to submit input:', error);
            this.showError(`Failed to submit input: ${error.message}`);
        }
    }

    abortRun() {
        if (this.ws) {
            this.ws.onclose = null;
            this.ws.close();
            this.ws = null;
        }
        this.currentRunId = null;
        this.closeModals();
        this.setRunning(false);
        this.setStatus('ready');
        this.updateConnectionStatus();
    }

    closeWorkflow() {
        console.log('[Dashboard] Closing workflow');
        this.saveCurrentInput();
        this.abortRun();
        
        // Reset UI
        this.currentWorkflow = null;
        
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
