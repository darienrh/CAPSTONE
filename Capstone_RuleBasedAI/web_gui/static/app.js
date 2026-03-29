const socket = io();
let currentPromptId = null;
let isRunning = false;

// ============================================
// SOCKET EVENTS
// ============================================

socket.on('connect', () => addLog('Connected to server', 'info'));
socket.on('disconnect', () => addLog('Disconnected from server', 'warning'));
socket.on('log', (data) => addLog(data.message, data.level));
socket.on('status', (data) => updateStatus(data.text, data.color));
socket.on('devices', (data) => updateDeviceList(data.devices));
socket.on('prompt', (data) => showPrompt(data));

// ============================================
// LOGGING
// ============================================

function addLog(message, level = 'info') {
    const container = document.getElementById('log-container');
    const entry = document.createElement('div');
    entry.className = 'log-entry';

    const timestamp = new Date().toLocaleTimeString('en-US', {
        hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit'
    });

    const levelMap = {
        success: 'log-success', error: 'log-error', warning: 'log-warning',
        phase: 'log-phase', dim: 'log-dim'
    };
    const levelClass = levelMap[level] || 'log-info';

    entry.innerHTML = `<span class="log-timestamp">[${timestamp}]</span><span class="${levelClass}">${escapeHtml(message)}</span>`;
    container.appendChild(entry);
    container.scrollTop = container.scrollHeight;
}

function clearLog() {
    document.getElementById('log-container').innerHTML = '';
}

// ============================================
// STATUS
// ============================================

function updateStatus(text, color) {
    const badge = document.getElementById('status-badge');
    badge.className = `status-badge status-${color}`;
    badge.innerHTML = `<i class="bi bi-circle-fill"></i> ${text}`;

    isRunning = ['warning', 'primary', 'danger'].includes(color);
    document.getElementById('btn-start').disabled = isRunning;
    document.getElementById('btn-stop').disabled = !isRunning;
}

function updateDeviceList(devices) {
    const container = document.getElementById('device-list');
    container.innerHTML = devices?.length
        ? devices.map(d => `<span class="device-badge"><i class="bi bi-router-fill text-success"></i> ${d}</span>`).join('')
        : '<span class="text-secondary fst-italic">No devices found</span>';
}

// ============================================
// PROMPT
// ============================================

function showPrompt(data) {
    currentPromptId = data.id;
    const container = document.getElementById('prompt-container');
    const footer = document.getElementById('promptFooter');
    const inputContainer = document.getElementById('promptInputContainer');

    document.getElementById('promptQuestion').textContent = data.question;
    inputContainer.innerHTML = '';
    footer.innerHTML = '';

    if (data.type === 'text') {
        inputContainer.innerHTML = `<input type="text" class="form-control" id="promptTextValue" value="${data.default || ''}">`;
        footer.innerHTML = `
            <button class="btn btn-secondary btn-sm" onclick="submitPrompt(null)">Cancel</button>
            <button class="btn btn-primary btn-sm" onclick="submitPrompt()">OK</button>
        `;
        setTimeout(() => document.getElementById('promptTextValue')?.focus(), 50);

    } else if (data.type === 'confirm') {
        footer.innerHTML = `
            <button class="btn btn-secondary btn-sm" onclick="submitPrompt(false)">No</button>
            <button class="btn btn-success btn-sm" onclick="submitPrompt(true)">Yes</button>
        `;

    } else if (data.type === 'choice') {
        if (data.choices) {
            data.choices.forEach(choice => {
                const btn = document.createElement('button');
                btn.className = `btn btn-sm ${choice === data.default ? 'btn-primary' : 'btn-outline-secondary'}`;
                btn.textContent = choice;
                btn.onclick = () => submitPrompt(choice);
                footer.appendChild(btn);
            });
        } else {
            inputContainer.innerHTML = `<input type="text" class="form-control" id="promptTextValue" value="${data.default || ''}">`;
            footer.innerHTML = `
                <button class="btn btn-secondary btn-sm" onclick="submitPrompt(null)">Cancel</button>
                <button class="btn btn-primary btn-sm" onclick="submitPrompt()">OK</button>
            `;
            setTimeout(() => document.getElementById('promptTextValue')?.focus(), 50);
        }
    }

    container.style.display = 'block';
    container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function submitPrompt(value) {
    if (arguments.length === 0) {
        const input = document.getElementById('promptTextValue');
        value = input ? input.value : '';
    }

    fetch('/api/prompt/response', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: currentPromptId, response: value })
    });

    document.getElementById('prompt-container').style.display = 'none';
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
            body: JSON.stringify({ gns3_url: gns3Url, devices })
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
// THEME TOGGLE
// ============================================

function toggleTheme() {
    const html = document.documentElement;
    const icon = document.getElementById('theme-icon');
    const isDark = html.getAttribute('data-theme') === 'dark';
    html.setAttribute('data-theme', isDark ? 'light' : 'dark');
    icon.className = isDark ? 'bi bi-moon-fill' : 'bi bi-sun-fill';
    localStorage.setItem('theme', isDark ? 'light' : 'dark');
}

(function applyStoredTheme() {
    const saved = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', saved);
    const icon = document.getElementById('theme-icon');
    if (icon) icon.className = saved === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
})();

// ============================================
// UTILITY
// ============================================

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}