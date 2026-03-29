/**
 * Network Diagnostic Tool - Web Interface
 * Client-side JavaScript
 */

const socket = io();
let currentPromptId = null;
let isRunning = false;

// ============================================
// SOCKET EVENTS
// ============================================

socket.on('connect', () => {
    addLog('Connected to server', 'info');
});

socket.on('disconnect', () => {
    addLog('Disconnected from server', 'warning');
});

socket.on('log', (data) => {
    addLog(data.message, data.level);
});

socket.on('status', (data) => {
    updateStatus(data.text, data.color);
});

socket.on('devices', (data) => {
    updateDeviceList(data.devices);
});

socket.on('prompt', (data) => {
    showPrompt(data);
});

// ============================================
// LOGGING FUNCTIONS
// ============================================

function addLog(message, level = 'info') {
    const container = document.getElementById('log-container');
    const entry = document.createElement('div');
    entry.className = 'log-entry';

    const timestamp = new Date().toLocaleTimeString('en-US', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });

    let levelClass = 'log-info';
    switch (level) {
        case 'success': levelClass = 'log-success'; break;
        case 'error': levelClass = 'log-error'; break;
        case 'warning': levelClass = 'log-warning'; break;
        case 'phase': levelClass = 'log-phase'; break;
        case 'dim': levelClass = 'log-dim'; break;
    }

    entry.innerHTML = `<span class="log-timestamp">[${timestamp}]</span><span class="${levelClass}">${escapeHtml(message)}</span>`;
    container.appendChild(entry);
    container.scrollTop = container.scrollHeight;
}

function clearLog() {
    document.getElementById('log-container').innerHTML = '';
}

// ============================================
// STATUS FUNCTIONS
// ============================================

function updateStatus(text, color) {
    const badge = document.getElementById('status-badge');
    const statusClass = `status-${color}`;
    badge.className = `status-badge ${statusClass}`;
    badge.innerHTML = `<i class="bi bi-circle-fill"></i> ${text}`;

    isRunning = (color === 'warning' || color === 'primary' || color === 'danger');
    document.getElementById('btn-start').disabled = isRunning;
    document.getElementById('btn-stop').disabled = !isRunning;
}

function updateDeviceList(devices) {
    const container = document.getElementById('device-list');
    if (devices && devices.length > 0) {
        container.innerHTML = devices.map(d =>
            `<span class="device-badge"><i class="bi bi-router-fill text-success"></i> ${d}</span>`
        ).join('');
    } else {
        container.innerHTML = '<span class="text-secondary fst-italic">No devices found</span>';
    }
}

// ============================================
// PROMPT FUNCTIONS
// ============================================

function showPrompt(data) {
    currentPromptId = data.id;
    const modal = new bootstrap.Modal(document.getElementById('promptModal'));
    document.getElementById('promptQuestion').textContent = data.question;

    const inputContainer = document.getElementById('promptInputContainer');
    const footer = document.getElementById('promptFooter');
    inputContainer.innerHTML = '';
    footer.innerHTML = '';

    if (data.type === 'text') {
        inputContainer.innerHTML = `
            <input type="text" class="form-control" id="promptTextValue" 
                   value="${data.default || ''}" autofocus>
        `;
        footer.innerHTML = `
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
            <button type="button" class="btn btn-primary" onclick="submitPrompt()">OK</button>
        `;
        setTimeout(() => document.getElementById('promptTextValue').focus(), 100);

    } else if (data.type === 'confirm') {
        footer.innerHTML = `
            <button type="button" class="btn btn-secondary" onclick="submitPrompt(false)">No</button>
            <button type="button" class="btn btn-success" onclick="submitPrompt(true)">Yes</button>
        `;

    } else if (data.type === 'choice') {
        if (data.choices) {
            data.choices.forEach(choice => {
                const btn = document.createElement('button');
                btn.className = `btn ${choice === data.default ? 'btn-primary' : 'btn-outline-secondary'} choice-btn`;
                btn.textContent = choice;
                btn.onclick = () => submitPrompt(choice);
                footer.appendChild(btn);
            });
        } else {
            inputContainer.innerHTML = `
                <input type="text" class="form-control" id="promptChoiceValue" 
                       value="${data.default || ''}" autofocus>
            `;
            footer.innerHTML = `
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                <button type="button" class="btn btn-primary" onclick="submitPrompt()">OK</button>
            `;
        }
    }

    modal.show();

    // Handle Enter key for text inputs
    document.getElementById('promptModal').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && (data.type === 'text' || data.type === 'choice')) {
            submitPrompt();
        }
    });
}

function submitPrompt(value) {
    if (arguments.length === 0) {
        const input = document.getElementById('promptTextValue') ||
            document.getElementById('promptChoiceValue');
        value = input ? input.value : '';
    }

    fetch('/api/prompt/response', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            id: currentPromptId,
            response: value
        })
    });

    bootstrap.Modal.getInstance(document.getElementById('promptModal')).hide();
    currentPromptId = null;
}

// ============================================
// DIAGNOSTICS CONTROL
// ============================================

async function startDiagnostics() {
    const gns3Url = document.getElementById('gns3-url').value;
    const devices = document.getElementById('devices').value;

    try {
        const response = await fetch('/api/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ gns3_url: gns3Url, devices: devices })
        });

        if (!response.ok) {
            const data = await response.json();
            addLog(`Error: ${data.error}`, 'error');
        }
    } catch (error) {
        addLog(`Failed to start: ${error.message}`, 'error');
    }
}

async function stopDiagnostics() {
    try {
        await fetch('/api/stop', { method: 'POST' });
        addLog('Stopping diagnostics...', 'warning');
    } catch (error) {
        addLog(`Failed to stop: ${error.message}`, 'error');
    }
}

// ============================================
// UTILITY FUNCTIONS
// ============================================

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}