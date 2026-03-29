const GNS3_URL_KEY = 'gns3_url';

let network = null;
let nodesDataset = null;
let edgesDataset = null;
let selectedNodeName = null;
let pollInterval = null;
let currentGns3Url = 'http://localhost:3080';
let currentUsername = '';
let currentPassword = '';

// ============================================
// INIT
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    const saved = localStorage.getItem(GNS3_URL_KEY);
    if (saved) {
        document.getElementById('topo-gns3-url').value = saved;
        currentGns3Url = saved;
    }
    applyStoredTheme();
    initNetwork();
});

// ============================================
// THEME
// ============================================

function toggleTheme() {
    const html = document.documentElement;
    const icon = document.getElementById('theme-icon');
    const isDark = html.getAttribute('data-theme') === 'dark';
    html.setAttribute('data-theme', isDark ? 'light' : 'dark');
    icon.className = isDark ? 'bi bi-moon-fill' : 'bi bi-sun-fill';
    localStorage.setItem('theme', isDark ? 'light' : 'dark');
    if (network) applyNetworkTheme();
}

function applyStoredTheme() {
    const saved = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', saved);
    const icon = document.getElementById('theme-icon');
    if (icon) icon.className = saved === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
}

// ============================================
// VIS.JS NETWORK INIT
// ============================================

function getNetworkThemeOptions() {
    const dark = document.documentElement.getAttribute('data-theme') === 'dark';
    return {
        nodes: {
            font: { color: dark ? '#e6edf3' : '#1f2328', size: 13, face: 'JetBrains Mono, monospace' },
            color: {
                border: dark ? '#30363d' : '#d0d7de',
                background: dark ? '#161b22' : '#ffffff',
                highlight: { border: '#4493f8', background: dark ? '#1c2a3a' : '#dbeafe' },
                hover: { border: '#4493f8', background: dark ? '#1c2a3a' : '#dbeafe' },
            },
        },
        edges: {
            color: { color: dark ? '#30363d' : '#adb5bd', highlight: '#4493f8', hover: '#4493f8' },
            font: { color: dark ? '#7d8590' : '#656d76', size: 10, face: 'JetBrains Mono, monospace', align: 'middle' },
        },
    };
}

function nodeColor(status) {
    const dark = document.documentElement.getAttribute('data-theme') === 'dark';
    const map = {
        started: { border: '#2ea043', background: dark ? '#0d2114' : '#dcfce7' },
        stopped: { border: '#da3633', background: dark ? '#2a0d0d' : '#fee2e2' },
        suspended: { border: '#bb8009', background: dark ? '#2a1e00' : '#fef3c7' },
        unknown: { border: '#7d8590', background: dark ? '#161b22' : '#f6f8fa' },
    };
    return map[status] || map.unknown;
}

function nodeShape(type) {
    const map = {
        'dynamips': 'box',
        'docker': 'ellipse',
        'vpcs': 'dot',
        'ethernet_switch': 'diamond',
        'ethernet_hub': 'diamond',
        'cloud': 'triangleDown',
    };
    return map[type] || 'box';
}

function initNetwork() {
    const container = document.getElementById('topology-canvas');
    nodesDataset = new vis.DataSet([]);
    edgesDataset = new vis.DataSet([]);

    const themeOpts = getNetworkThemeOptions();

    network = new vis.Network(container, { nodes: nodesDataset, edges: edgesDataset }, {
        physics: { enabled: false },
        interaction: { hover: true, tooltipDelay: 200, zoomView: true, dragView: true },
        nodes: {
            ...themeOpts.nodes,
            shape: 'box',
            borderWidth: 2,
            borderWidthSelected: 3,
            margin: { top: 8, right: 12, bottom: 8, left: 12 },
            shadow: { enabled: true, size: 6, x: 2, y: 2, color: 'rgba(0,0,0,0.3)' },
        },
        edges: {
            ...themeOpts.edges,
            width: 2,
            smooth: { type: 'curvedCW', roundness: 0.1 },
            shadow: false,
        },
    });

    network.on('click', (params) => {
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            const node = nodesDataset.get(nodeId);
            if (node) loadNodeDetail(node.label, node.rawStatus);
        } else {
            closePanel();
        }
    });
}

function applyNetworkTheme() {
    const themeOpts = getNetworkThemeOptions();
    network.setOptions({ nodes: themeOpts.nodes, edges: themeOpts.edges });

    const all = nodesDataset.get();
    nodesDataset.update(all.map(n => ({
        id: n.id,
        color: nodeColor(n.rawStatus),
        font: themeOpts.nodes.font,
    })));
}

// ============================================
// LOAD TOPOLOGY
// ============================================

async function loadTopology() {
    currentGns3Url = document.getElementById('topo-gns3-url').value.trim();
    currentUsername = document.getElementById('topo-username').value.trim();
    currentPassword = document.getElementById('topo-password').value.trim();
    localStorage.setItem(GNS3_URL_KEY, currentGns3Url);

    setTopoStatus('loading', 'Connecting to GNS3...');
    closePanel();

    try {
        const res = await fetch(`/api/topology?gns3_url=${encodeURIComponent(currentGns3Url)}&username=${encodeURIComponent(currentUsername)}&password=${encodeURIComponent(currentPassword)}`);
        if (!res.ok) {
            const err = await res.json();
            setTopoStatus('error', err.error || 'Failed');
            return;
        }

        const data = await res.json();
        renderTopology(data);
        setTopoStatus('ok', `Project: ${data.project} — ${data.nodes.length} nodes, ${data.links.length} links`);

        document.getElementById('btn-refresh').disabled = false;
        startPolling();
    } catch (e) {
        setTopoStatus('error', `Error: ${e.message}`);
    }
}

function renderTopology(data) {
    const themeOpts = getNetworkThemeOptions();

    const nodes = data.nodes.map(n => ({
        id: n.id,
        label: n.name,
        x: n.x,
        y: n.y,
        shape: nodeShape(n.type),
        color: nodeColor(n.status),
        font: themeOpts.nodes.font,
        rawStatus: n.status,
        console: n.console,
        nodeType: n.type,
        title: `${n.name}\nType: ${n.type}\nStatus: ${n.status}\nConsole: ${n.console || 'N/A'}`,
    }));

    const edges = data.links.map(lk => ({
        id: lk.id,
        from: lk.source,
        to: lk.target,
        label: `${lk.source_port !== '' ? 'f' + lk.source_port : ''} / ${lk.target_port !== '' ? 'f' + lk.target_port : ''}`,
        title: `${lk.source_name} ↔ ${lk.target_name}`,
    }));

    nodesDataset.clear();
    edgesDataset.clear();
    nodesDataset.add(nodes);
    edgesDataset.add(edges);

    network.fit({ animation: { duration: 600, easingFunction: 'easeInOutQuad' } });
}

async function refreshTopology() {
    try {
        const res = await fetch(`/api/topology?gns3_url=${encodeURIComponent(currentGns3Url)}&username=${encodeURIComponent(currentUsername)}&password=${encodeURIComponent(currentPassword)}`);
        if (!res.ok) return;
        const data = await res.json();

        data.nodes.forEach(n => {
            const existing = nodesDataset.get(n.id);
            if (existing && existing.rawStatus !== n.status) {
                nodesDataset.update({
                    id: n.id, color: nodeColor(n.status), rawStatus: n.status,
                    title: `${n.name}\nType: ${n.type}\nStatus: ${n.status}\nConsole: ${n.console || 'N/A'}`
                });
            }
        });

        setTopoStatus('ok', `Project: ${data.project} — ${data.nodes.length} nodes, ${data.links.length} links`);
    } catch (_) { }
}

function startPolling() {
    if (pollInterval) clearInterval(pollInterval);
    const interval = parseInt(document.getElementById('poll-interval').value) * 1000;
    if (interval > 0) pollInterval = setInterval(refreshTopology, interval);
}

function updatePolling() {
    startPolling();
}

// ============================================
// NODE DETAIL PANEL
// ============================================

async function loadNodeDetail(nodeName, status) {
    selectedNodeName = nodeName;
    const panel = document.getElementById('detail-panel');
    const title = document.getElementById('detail-title');
    const body = document.getElementById('detail-body');

    panel.style.display = 'flex';
    title.textContent = nodeName;
    body.innerHTML = `<div class="detail-loading"><i class="bi bi-arrow-repeat spin"></i> Fetching device data...</div>`;

    if (status !== 'started') {
        body.innerHTML = `<div class="detail-offline"><i class="bi bi-x-circle"></i> Device is ${status}</div>`;
        return;
    }

    try {
        const res = await fetch(`/api/topology/node/${encodeURIComponent(nodeName)}?gns3_url=${encodeURIComponent(currentGns3Url)}&username=${encodeURIComponent(currentUsername)}&password=${encodeURIComponent(currentPassword)}`);
        const data = await res.json();
        renderNodeDetail(data);
    } catch (e) {
        body.innerHTML = `<div class="detail-offline"><i class="bi bi-exclamation-triangle"></i> ${e.message}</div>`;
    }
}

function renderNodeDetail(data) {
    const body = document.getElementById('detail-body');

    const statusBadge = `<span class="detail-status-badge detail-status-${data.status}">${data.status}</span>`;
    const consoleBadge = data.console
        ? `<span class="detail-console-badge"><i class="bi bi-terminal"></i> :${data.console}</span>`
        : '';

    let ifaceHtml = '';
    if (data.interfaces && data.interfaces.length > 0) {
        const rows = data.interfaces.map(i => {
            const up = i.status === 'up' && i.protocol === 'up';
            const dot = `<span class="iface-dot ${up ? 'dot-up' : 'dot-down'}"></span>`;
            return `<tr>
                <td>${dot} ${i.interface}</td>
                <td>${i.ip}</td>
                <td>${i.status}</td>
                <td>${i.protocol}</td>
            </tr>`;
        }).join('');
        ifaceHtml = `
            <div class="detail-section-label">Interfaces</div>
            <table class="detail-table">
                <thead><tr><th>Interface</th><th>IP</th><th>Status</th><th>Protocol</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>`;
    } else {
        ifaceHtml = `<div class="detail-section-label">Interfaces</div><div class="detail-empty">No interface data</div>`;
    }

    let routeHtml = '';
    if (data.routes && data.routes.length > 0) {
        const codeColor = { C: 'route-c', S: 'route-s', O: 'route-o', E: 'route-e', R: 'route-r', B: 'route-b' };
        const rows = data.routes.map(r => {
            const cls = codeColor[r.code[0]] || '';
            return `<tr>
                <td><span class="route-code ${cls}">${r.code}</span></td>
                <td>${r.network}</td>
                <td class="route-detail">${r.detail}</td>
            </tr>`;
        }).join('');
        routeHtml = `
            <div class="detail-section-label" style="margin-top:12px;">Routing Table</div>
            <table class="detail-table">
                <thead><tr><th>Code</th><th>Network</th><th>Via</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>`;
    } else {
        routeHtml = `<div class="detail-section-label" style="margin-top:12px;">Routing Table</div><div class="detail-empty">No route data</div>`;
    }

    body.innerHTML = `
        <div class="detail-badges">${statusBadge}${consoleBadge}</div>
        ${ifaceHtml}
        ${routeHtml}`;
}

function closePanel() {
    document.getElementById('detail-panel').style.display = 'none';
    selectedNodeName = null;
    if (network) network.unselectAll();
}

// ============================================
// STATUS BAR
// ============================================

function setTopoStatus(type, msg) {
    const el = document.getElementById('topo-status');
    const map = { ok: 'topo-status-ok', error: 'topo-status-error', loading: 'topo-status-loading' };
    el.className = `topo-status-bar ${map[type] || ''}`;
    el.textContent = msg;
}