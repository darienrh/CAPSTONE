const socket = io(typeof window !== 'undefined' && window.location && window.location.origin ? window.location.origin : undefined, {
    path: '/socket.io/',
    transports: ['websocket', 'polling'],
    reconnectionAttempts: 20,
    reconnectionDelay: 800
});
let currentPromptId = null;
let isRunning = false;
const _idsLastSeen = {};

// ============================================
// LOG FILTERS
// ============================================

const LOG_FILTER_PATTERNS = {
    'ids': (msg, level) =>
        level === 'ids' || msg.includes('[IDS]'),

    'ruleminer': (msg) =>
        msg.includes('[RuleMiner]') || msg.startsWith('RuleMiner'),

    'learning': (msg) =>
        msg.includes('[Learning]'),

    'kbstats': (msg) => {
        const m = msg.trim();
        const ml = m.toLowerCase();
        return ml.includes('knowledge base')          // "Knowledge Base: ..." and "KNOWLEDGE BASE STATISTICS"
            || ml.startsWith('total rules:')
            || ml.startsWith('problems logged:')
            || ml.startsWith('fix attempts:')
            || ml.includes('success rate')            // "Overall Success Rate: 100.0%"
            || ml.startsWith('rules by category')
            || ml.startsWith('config directory:')
            || ml.startsWith('config dir')
            || ml.startsWith('latest stable config')
            || ml.startsWith('top performing rules')
            // category count lines: "interface: 7", "eigrp: 12", "ids_security: 2", etc.
            || /^(interface|eigrp|ospf|general|ids_security|rip|bgp|static):\s+\d+$/i.test(m)
            // rule performance lines: "INT_001: 100.0% (6 attempts)"
            || /^[A-Z][A-Z0-9_]+:\s+\d+\.?\d*%\s+\(\d+\s+attempts\)$/.test(m);
    },
};

function getFilterClass(message, level) {
    // Never filter interactive prompt lines — user needs to see these
    if (/^(CONFIRM:|CHOICE:|PROMPT:)/.test(message)) return null;
    for (const [key, test] of Object.entries(LOG_FILTER_PATTERNS)) {
        if (test(message, level)) return `log-filter-${key}`;
    }
    return null;
}

function applyLogFilters() {
    const show = {
        ids: document.getElementById('filter-ids')?.checked ?? true,
        ruleminer: document.getElementById('filter-ruleminer')?.checked ?? true,
        learning: document.getElementById('filter-learning')?.checked ?? true,
        kbstats: document.getElementById('filter-kbstats')?.checked ?? true,
    };

    // Re-scan every entry so toggling always affects past messages too
    document.querySelectorAll('#log-container .log-entry').forEach(entry => {
        const msgSpan = entry.querySelector('span:last-child');
        const text = msgSpan ? msgSpan.textContent : entry.textContent;
        const levelClass = msgSpan
            ? ([...msgSpan.classList].find(c => c.startsWith('log-')) || '')
            : '';
        const level = levelClass.replace('log-', '');

        const filterClass = getFilterClass(text, level);
        if (filterClass) {
            const key = filterClass.replace('log-filter-', '');
            // Ensure the class is stamped on the element
            if (!entry.classList.contains(filterClass)) entry.classList.add(filterClass);
            entry.style.display = show[key] ? '' : 'none';
        } else {
            // Unfiltered entries are always visible
            entry.style.display = '';
        }
    });

    // Persist filter state across page navigation
    sessionStorage.setItem('diag_filter_state', JSON.stringify(show));
}

// ============================================
// SOCKET EVENTS
// ============================================

socket.on('connect', () => addLog('Connected to server', 'info'));
socket.on('disconnect', () => addLog('Disconnected from server', 'warning'));
socket.on('log', (data) => addLog(data.message, data.level));
socket.on('status', (data) => updateStatus(data.text, data.color));
socket.on('devices', (data) => updateDeviceList(data.devices));
socket.on('prompt', (data) => showPrompt(data));
socket.on('ids_alert', (data) => {
    const key = data.details || '';
    const now = Date.now();
    if (_idsLastSeen[key] && (now - _idsLastSeen[key]) < 5000) return;
    _idsLastSeen[key] = now;
    const container = document.getElementById('log-container');
    const entry = document.createElement('div');
    entry.className = 'log-entry log-filter-ids';
    const idsVisible = document.getElementById('filter-ids')?.checked ?? true;
    if (!idsVisible) entry.style.display = 'none';
    const ts = new Date().toLocaleTimeString('en-US', { hour12: false });
    entry.innerHTML = `<span class="log-timestamp">[${ts}]</span><span class="log-ids">⚠ [IDS] ${escapeHtml(key)}</span>`;
    container.appendChild(entry);
    container.scrollTop = container.scrollHeight;
});

socket.on('ie_flow', (data) => {
    const section = document.getElementById('ie-flowchart-section');
    const container = document.getElementById('ie-flowchart-container');
    if (!section || !container) return;
    container.innerHTML = renderIEFlowchart(data.traces || []);
    section.style.display = 'block';
    section.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
});

socket.on('diagnostic_summary', (data) => {
    const section = document.getElementById('diagnostic-summary-section');
    const content = document.getElementById('diagnostic-summary-content');
    if (!section || !content) return;

    const fixed = data.fixed || 0;
    const failed = data.failed || 0;
    const newRules = data.new_rules || 0;
    const newRuleIds = data.new_rule_ids || [];

    let html = '<div class="diag-summary-stat">';
    html += `<span class="diag-summary-fixed"><i class="bi bi-check-circle-fill"></i> ${fixed} problem${fixed !== 1 ? 's' : ''} fixed</span>`;
    if (failed > 0) {
        html += `<span class="diag-summary-failed"><i class="bi bi-x-circle-fill"></i> ${failed} failure${failed !== 1 ? 's' : ''}</span>`;
    } else {
        html += `<span style="color:var(--success);font-size:0.82rem;">No failures</span>`;
    }
    html += '</div>';
    if (newRules > 0) {
        const tags = newRuleIds.map(r => `<span class="diag-rule-tag">${escapeHtml(r)}</span>`).join('');
        html += `<div class="diag-summary-rules"><i class="bi bi-journal-plus"></i> Created ${newRules} new rule${newRules !== 1 ? 's' : ''}: ${tags}</div>`;
    }
    if (data.custom_message) {
        html += `<div class="diag-summary-custom-msg"><i class="bi bi-robot"></i> ${escapeHtml(data.custom_message)}</div>`;
    }

    content.innerHTML = html;
    section.style.display = 'block';
});

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
        phase: 'log-phase', dim: 'log-dim', ids: 'log-ids'
    };
    const levelClass = levelMap[level] || 'log-info';

    // Tag entry with a filter class if it matches a filter category
    const filterClass = getFilterClass(message, level);
    if (filterClass) {
        entry.classList.add(filterClass);
        const filterKey = filterClass.replace('log-filter-', '');
        const checkbox = document.getElementById(`filter-${filterKey}`);
        if (checkbox && !checkbox.checked) entry.style.display = 'none';
    }

    entry.innerHTML = `<span class="log-timestamp">[${timestamp}]</span><span class="${levelClass}">${escapeHtml(message)}</span>`;
    container.appendChild(entry);
    container.scrollTop = container.scrollHeight;
}

function clearLog() {
    document.getElementById('log-container').innerHTML = '';
    sessionStorage.removeItem('diag_log_html');
}

// ============================================
// SESSION PERSISTENCE (survive page navigation)
// ============================================

function savePageState() {
    const log = document.getElementById('log-container');
    if (log) sessionStorage.setItem('diag_log_html', log.innerHTML);

    const ieSection = document.getElementById('ie-flowchart-section');
    const ieContainer = document.getElementById('ie-flowchart-container');
    if (ieSection) {
        sessionStorage.setItem('diag_ie_visible', ieSection.style.display !== 'none' ? '1' : '0');
        sessionStorage.setItem('diag_ie_html', ieContainer ? ieContainer.innerHTML : '');
    }

    const sumSection = document.getElementById('diagnostic-summary-section');
    const sumContent = document.getElementById('diagnostic-summary-content');
    if (sumSection) {
        sessionStorage.setItem('diag_sum_visible', sumSection.style.display !== 'none' ? '1' : '0');
        sessionStorage.setItem('diag_sum_html', sumContent ? sumContent.innerHTML : '');
    }
}

function restorePageState() {
    // Restore filter checkbox state before restoring log so applyLogFilters is correct
    const savedFilters = sessionStorage.getItem('diag_filter_state');
    if (savedFilters) {
        try {
            const state = JSON.parse(savedFilters);
            for (const [key, checked] of Object.entries(state)) {
                const cb = document.getElementById(`filter-${key}`);
                if (cb) cb.checked = checked;
            }
        } catch (_) { }
    }

    const logHtml = sessionStorage.getItem('diag_log_html');
    if (logHtml) {
        const log = document.getElementById('log-container');
        if (log) {
            log.innerHTML = logHtml;
            log.scrollTop = log.scrollHeight;
            applyLogFilters();
        }
    }

    const ieHtml = sessionStorage.getItem('diag_ie_html');
    const ieVisible = sessionStorage.getItem('diag_ie_visible') === '1';
    if (ieHtml && ieVisible) {
        const ieSection = document.getElementById('ie-flowchart-section');
        const ieContainer = document.getElementById('ie-flowchart-container');
        if (ieSection && ieContainer) {
            ieContainer.innerHTML = ieHtml;
            ieSection.style.display = 'block';
        }
    }

    const sumHtml = sessionStorage.getItem('diag_sum_html');
    const sumVisible = sessionStorage.getItem('diag_sum_visible') === '1';
    if (sumHtml && sumVisible) {
        const sumSection = document.getElementById('diagnostic-summary-section');
        const sumContent = document.getElementById('diagnostic-summary-content');
        if (sumSection && sumContent) {
            sumContent.innerHTML = sumHtml;
            sumSection.style.display = 'block';
        }
    }
}

window.addEventListener('beforeunload', savePageState);

function normalizedPathname() {
    let p = location.pathname.replace(/\/+$/, '');
    if (p === '') p = '/';
    return p;
}

function getViewFromPathname() {
    const fromBody = document.body?.dataset?.initialView;
    if (fromBody === 'telemetry' || fromBody === 'diagnostics') return fromBody;
    return normalizedPathname() === '/telemetry' ? 'telemetry' : 'diagnostics';
}

function setVisibleView(view) {
    ['diagnostics', 'telemetry'].forEach(v => {
        const el = document.getElementById(`view-${v}`);
        if (el) el.style.display = (v === view) ? '' : 'none';
    });
    document.getElementById('nav-diagnostics')?.classList.toggle('active', view === 'diagnostics');
    document.getElementById('nav-telemetry')?.classList.toggle('active', view === 'telemetry');
    if (view === 'telemetry' && typeof initTelemetryView === 'function') {
        void initTelemetryView().catch(() => { });
        setTimeout(() => {
            if (typeof chartIn !== 'undefined' && chartIn) {
                chartIn.resize();
                chartOut.resize();
            }
        }, 50);
    }
}

function showView(view, historyMode = 'push') {
    setVisibleView(view);
    if (historyMode === 'none') return;
    const url = view === 'diagnostics' ? '/' : `/${view}`;
    if (historyMode === 'replace') {
        history.replaceState({ view }, '', url);
        return;
    }
    const pathMatches = normalizedPathname() === url;
    const stateView = history.state && history.state.view;
    if (!pathMatches || stateView !== view) {
        history.pushState({ view }, '', url);
    } else {
        history.replaceState({ view }, '', url);
    }
}

window.addEventListener('popstate', () => {
    setVisibleView(getViewFromPathname());
});

window.addEventListener('DOMContentLoaded', () => {
    restorePageState();
    const initial = getViewFromPathname();
    setVisibleView(initial);
    history.replaceState({ view: initial }, '', initial === 'telemetry' ? '/telemetry' : '/');
});

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

    // Clear previous run's flowchart and summary
    const ieSection = document.getElementById('ie-flowchart-section');
    const sumSection = document.getElementById('diagnostic-summary-section');
    if (ieSection) ieSection.style.display = 'none';
    if (sumSection) sumSection.style.display = 'none';
    ['diag_ie_visible', 'diag_ie_html', 'diag_sum_visible', 'diag_sum_html'].forEach(k => sessionStorage.removeItem(k));

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
// IE FLOWCHART
// ============================================

function renderIEFlowchart(traces) {
    if (!traces || traces.length === 0) {
        return '<em class="text-secondary" style="font-size:0.85rem;">No inference traces recorded.</em>';
    }
    return '<div class="ie-traces-wrap">' + traces.map((trace, idx) => {
        const prob = trace.problem || {};
        const probLabel = `${prob.type || 'unknown'} on ${prob.device || '?'}` +
            (prob.interface ? ` [${prob.interface}]` : '');
        const chosen = trace.chosen_fix || null;
        const outcome = trace.outcome || 'pending';
        const outcomeClass = outcome === 'success' ? 'ie-outcome-success'
            : outcome === 'failure' ? 'ie-outcome-failure' : 'ie-outcome-pending';
        const outcomeIcon = outcome === 'success' ? '✓' : outcome === 'failure' ? '✗' : '●';

        const stepsHtml = (trace.reasoning_steps || []).map(s =>
            `<div class="ie-rule-item">${escapeHtml(s)}</div>`
        ).join('');

        const altHtml = (trace.alternatives_considered || []).length > 0
            ? `<div class="ie-alternatives"><strong>Alternatives rejected:</strong>
                ${trace.alternatives_considered.map(a =>
                `<div class="ie-alt-item">
                        <span style="color:var(--danger);font-size:0.72rem;">✗</span>
                        <span>${escapeHtml(a.rule_id || '?')}</span>
                        <span style="color:var(--text-muted);">— ${escapeHtml(a.rejected_reason || '')}</span>
                    </div>`
            ).join('')}
              </div>`
            : '';

        return `
        <div class="ie-trace">
            <div class="ie-trace-header">
                <span class="ie-trace-num">${idx + 1}</span>
                <span class="ie-trace-problem">${escapeHtml(probLabel)}</span>
                ${outcome !== 'pending' ? `<span class="${outcomeClass}" style="margin-left:auto;font-size:0.8rem;">${outcomeIcon} ${outcome}</span>` : ''}
            </div>
            <div class="ie-flow-steps">
                <div class="ie-flow-node ie-node-problem">
                    <div class="ie-node-label">Problem Detected</div>
                    <div class="ie-node-value">${escapeHtml(probLabel)}</div>
                </div>
                <div class="ie-flow-arrow">▼</div>
                <div class="ie-flow-node ie-node-rules">
                    <div class="ie-node-label">Reasoning Path</div>
                    ${stepsHtml || '<div class="ie-rule-item text-muted">No steps recorded</div>'}
                </div>
                <div class="ie-flow-arrow">▼</div>
                <div class="ie-flow-node ie-node-${outcome === 'success' ? 'success' : chosen ? 'warning' : 'rules'}">
                    <div class="ie-node-label">Fix Selected</div>
                    <div class="ie-node-value">${chosen ? escapeHtml(chosen.rule_id || 'N/A') : '<em>None</em>'}</div>
                    ${chosen ? `<div class="ie-node-meta">${escapeHtml(chosen.description || '')} &nbsp;|&nbsp; CF: ${((chosen.confidence || 0) * 100).toFixed(0)}% &nbsp;|&nbsp; Tier ${chosen.tier || '?'}${chosen.baseline_validated ? ' &nbsp;|&nbsp; <span style="color:var(--success);">Baseline ✓</span>' : ''}</div>` : ''}
                    ${altHtml}
                </div>
            </div>
        </div>`;
    }).join('') + '</div>';
}

// ============================================
// THEME TOGGLE
// ============================================

function toggleTheme() {
    const html = document.documentElement;
    const icon = document.getElementById('theme-icon');
    const isDark = html.getAttribute('data-theme') === 'dark';
    const newTheme = isDark ? 'light' : 'dark';

    html.setAttribute('data-theme', newTheme);
    html.setAttribute('data-bs-theme', newTheme);
    icon.className = newTheme === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
    localStorage.setItem('theme', newTheme);
}

(function applyStoredTheme() {
    const saved = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', saved);
    document.documentElement.setAttribute('data-bs-theme', saved);

    window.addEventListener('DOMContentLoaded', () => {
        const icon = document.getElementById('theme-icon');
        if (icon) icon.className = saved === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
    });
})();

// ============================================
// UTILITY
// ============================================

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============================================
// DEMO SCENARIOS
// ============================================

async function demoInjectMisconfig() {
    const gns3Url = document.getElementById('gns3-url').value || 'http://192.168.231.1:3080';
    try {
        const r = await fetch('/api/demo/inject_misconfig', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ gns3_url: gns3Url })
        });
        if (!r.ok) {
            const d = await r.json();
            addLog(`Demo error: ${d.error}`, 'error');
        }
    } catch (e) {
        addLog(`Demo failed: ${e.message}`, 'error');
    }
}

async function demoAttack(attackType) {
    try {
        const r = await fetch('/api/demo/attack', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ attack_type: attackType })
        });
        if (!r.ok) {
            const d = await r.json();
            addLog(`Demo error: ${d.error}`, 'error');
        }
    } catch (e) {
        addLog(`Demo failed: ${e.message}`, 'error');
    }
}
