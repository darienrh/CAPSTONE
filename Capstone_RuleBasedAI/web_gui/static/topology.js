const GNS3_URL_KEY = 'gns3_webui_url';
const TOPOLOGY_AUTH_KEY = 'gns3_auth';

let network = null;
let pollTimer = null;
let currentNodeData = null;

document.addEventListener('DOMContentLoaded', () => {
    const saved = localStorage.getItem(GNS3_URL_KEY);
    if (saved) document.getElementById('gns3-url').value = saved;
    applyStoredTheme();

    // Set up auth fields if they exist in localStorage
    const savedAuth = localStorage.getItem(TOPOLOGY_AUTH_KEY);
    if (savedAuth) {
        try {
            const auth = JSON.parse(savedAuth);
            if (document.getElementById('gns3-username')) {
                document.getElementById('gns3-username').value = auth.username || '';
                document.getElementById('gns3-password').value = auth.password || '';
            }
        } catch (e) { }
    }
});

function openGns3() {
    const url = document.getElementById('gns3-url').value.trim();
    if (!url) return;
    localStorage.setItem(GNS3_URL_KEY, url);
    window.open(url, '_blank');
}

function toggleTheme() {
    const html = document.documentElement;
    const icon = document.getElementById('theme-icon');
    const isDark = html.getAttribute('data-theme') === 'dark';
    html.setAttribute('data-theme', isDark ? 'light' : 'dark');
    icon.className = isDark ? 'bi bi-moon-fill' : 'bi bi-sun-fill';
    localStorage.setItem('theme', isDark ? 'light' : 'dark');

    // Re-render network if it exists to update colors
    if (network && currentNodeData) {
        const nodes = new vis.DataSet(currentNodeData.nodes);
        const edges = new vis.DataSet(currentNodeData.edges);
        network.setData({ nodes, edges });
    }
}

function applyStoredTheme() {
    const saved = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', saved);
    const icon = document.getElementById('theme-icon');
    if (icon) icon.className = saved === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
}

function setPollInterval() {
    if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
    }

    const interval = parseInt(document.getElementById('poll-interval').value);
    if (interval > 0) {
        pollTimer = setInterval(() => {
            loadTopology(true);
        }, interval * 1000);
    }
}

async function loadTopology(silent = false) {
    const gns3Url = document.getElementById('gns3-url').value.trim();
    if (!gns3Url) {
        if (!silent) showStatus('Please enter GNS3 URL', 'error');
        return;
    }

    localStorage.setItem(GNS3_URL_KEY, gns3Url);

    if (!silent) showStatus('Loading topology...', 'loading');

    try {
        const username = document.getElementById('gns3-username')?.value || '';
        const password = document.getElementById('gns3-password')?.value || '';

        let url = `/api/topology?gns3_url=${encodeURIComponent(gns3Url)}`;
        if (username && password) {
            url += `&username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`;
            localStorage.setItem(TOPOLOGY_AUTH_KEY, JSON.stringify({ username, password }));
        }

        const response = await fetch(url);
        const data = await response.json();

        if (response.status !== 200) {
            throw new Error(data.error || 'Failed to load topology');
        }

        renderTopology(data);
        showStatus(`Loaded ${data.nodes.length} devices, ${data.links.length} links`, 'ok');

        // Hide empty state
        document.getElementById('topo-empty').style.display = 'none';

    } catch (error) {
        console.error('Error loading topology:', error);
        if (!silent) showStatus(error.message, 'error');
        document.getElementById('topo-empty').style.display = 'flex';
    }
}

function renderTopology(topologyData) {
    const container = document.getElementById('topology-canvas');
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';

    // Get theme colors
    const bgColor = isDark ? '#090c10' : '#f0f2f5';
    const nodeColor = isDark ? '#4493f8' : '#0969da';
    const nodeBorderColor = isDark ? '#79b8ff' : '#0550ae';
    const edgeColor = isDark ? '#30363d' : '#d0d7de';
    const textColor = isDark ? '#e6edf3' : '#1f2328';

    // Create nodes
    const nodes = topologyData.nodes.map(node => ({
        id: node.id,
        label: node.name,
        title: `${node.name}\nType: ${node.type}\nStatus: ${node.status}\nConsole: ${node.console || 'N/A'}`,
        shape: node.type === 'router' ? 'box' : 'ellipse',
        color: {
            background: nodeColor,
            border: nodeBorderColor,
            highlight: {
                background: nodeColor,
                border: nodeBorderColor
            }
        },
        font: { color: textColor, face: 'JetBrains Mono', size: 12 },
        x: node.x || undefined,
        y: node.y || undefined,
        fixed: node.x && node.y,
        physics: !(node.x && node.y)
    }));

    // Create edges (links)
    const edges = topologyData.links.map(link => ({
        id: link.id,
        from: link.source,
        to: link.target,
        label: link.link_type || 'ethernet',
        title: `${link.source_name} → ${link.target_name}\nPort: ${link.source_port} → ${link.target_port}`,
        color: { color: edgeColor, highlight: edgeColor },
        font: { color: textColor, size: 9, align: 'middle' },
        smooth: { type: 'cubicBezier', roundness: 0.5 }
    }));

    // Store for theme switching
    currentNodeData = { nodes, edges };

    const data = { nodes: new vis.DataSet(nodes), edges: new vis.DataSet(edges) };

    const options = {
        nodes: {
            shape: 'box',
            margin: 10,
            widthConstraint: { minimum: 60, maximum: 100 },
            heightConstraint: { minimum: 30 },
            font: { face: 'JetBrains Mono', size: 12 }
        },
        edges: {
            arrows: { to: { enabled: true, scaleFactor: 0.8 } },
            smooth: { type: 'cubicBezier', roundness: 0.5 },
            width: 1.5
        },
        physics: {
            enabled: true,
            stabilization: { iterations: 100 },
            solver: 'forceAtlas2Based',
            forceAtlas2Based: { gravitationalConstant: -50, centralGravity: 0.01 }
        },
        interaction: {
            hover: true,
            tooltipDelay: 200,
            navigationButtons: true,
            keyboard: true
        },
        layout: {
            randomSeed: 42,
            improvedLayout: true
        },
        background: bgColor
    };

    if (network) {
        network.setData(data);
        network.setOptions(options);
    } else {
        network = new vis.Network(container, data, options);
    }

    // Add click handler for node details
    network.on('click', function (params) {
        if (params.nodes && params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            const node = topologyData.nodes.find(n => n.id === nodeId);
            if (node) {
                showNodeDetails(node.name);
            }
        }
    });
}

async function showNodeDetails(nodeName) {
    const gns3Url = document.getElementById('gns3-url').value.trim();
    const username = document.getElementById('gns3-username')?.value || '';
    const password = document.getElementById('gns3-password')?.value || '';

    let url = `/api/topology/node/${encodeURIComponent(nodeName)}?gns3_url=${encodeURIComponent(gns3Url)}`;
    if (username && password) {
        url += `&username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`;
    }

    try {
        const response = await fetch(url);
        const data = await response.json();

        if (response.status !== 200) {
            throw new Error(data.error || 'Failed to load node details');
        }

        renderNodeDetails(data);

    } catch (error) {
        console.error('Error loading node details:', error);
        renderNodeDetailsError(nodeName, error.message);
    }
}

function renderNodeDetails(node) {
    const panel = document.getElementById('node-detail-panel');
    if (!panel) return;

    const statusClass = `detail-status-${node.status === 'started' ? 'started' : (node.status === 'stopped' ? 'stopped' : 'unknown')}`;
    const statusText = node.status === 'started' ? 'Running' : (node.status === 'stopped' ? 'Stopped' : 'Unknown');

    let interfacesHtml = '';
    if (node.interfaces && node.interfaces.length > 0) {
        interfacesHtml = `
            <div class="detail-section-label"><i class="bi bi-hdd-stack"></i> Interfaces</div>
            <table class="detail-table">
                <thead>
                    <tr>
                        <th>Interface</th>
                        <th>IP Address</th>
                        <th>Status</th>
                        <th>Protocol</th>
                    </tr>
                </thead>
                <tbody>
                    ${node.interfaces.map(iface => `
                        <tr>
                            <td><span class="iface-dot ${iface.status === 'up' ? 'dot-up' : 'dot-down'}"></span>${iface.interface}</td>
                            <td>${iface.ip || '-'}</td>
                            <td>${iface.status}</td>
                            <td>${iface.protocol}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } else {
        interfacesHtml = `<div class="detail-empty"><i class="bi bi-info-circle"></i> No interface data available</div>`;
    }

    let routesHtml = '';
    if (node.routes && node.routes.length > 0) {
        const routeCodes = {
            'C': 'route-c', 'S': 'route-s', 'O': 'route-o',
            'E': 'route-e', 'R': 'route-r', 'B': 'route-b'
        };

        routesHtml = `
            <div class="detail-section-label"><i class="bi bi-signpost"></i> Routing Table</div>
            <table class="detail-table">
                <thead>
                    <tr>
                        <th>Code</th>
                        <th>Network</th>
                        <th>Details</th>
                    </tr>
                </thead>
                <tbody>
                    ${node.routes.map(route => {
            const codeClass = routeCodes[route.code] || '';
            return `
                            <tr>
                                <td><span class="route-code ${codeClass}">${route.code}</span></td>
                                <td>${route.network}</td>
                                <td class="route-detail">${route.detail}</td>
                            </tr>
                        `;
        }).join('')}
                </tbody>
            </table>
        `;
    } else {
        routesHtml = `<div class="detail-empty"><i class="bi bi-info-circle"></i> No routes available</div>`;
    }

    panel.innerHTML = `
        <div class="detail-panel-header">
            <span class="detail-panel-title"><i class="bi bi-router"></i> ${node.name}</span>
            <div>
                <button class="detail-refresh-btn" onclick="refreshNodeDetails('${node.name}')">
                    <i class="bi bi-arrow-repeat"></i>
                </button>
                <button class="detail-close-btn" onclick="closeNodeDetails()">
                    <i class="bi bi-x-lg"></i>
                </button>
            </div>
        </div>
        <div class="detail-panel-body">
            <div class="detail-badges">
                <span class="detail-status-badge ${statusClass}">${statusText}</span>
                ${node.console ? `<span class="detail-console-badge"><i class="bi bi-plug"></i> Console: ${node.console}</span>` : ''}
            </div>
            ${interfacesHtml}
            ${routesHtml}
        </div>
    `;

    panel.style.display = 'flex';
}

function renderNodeDetailsError(nodeName, error) {
    const panel = document.getElementById('node-detail-panel');
    if (!panel) return;

    panel.innerHTML = `
        <div class="detail-panel-header">
            <span class="detail-panel-title"><i class="bi bi-router"></i> ${nodeName}</span>
            <button class="detail-close-btn" onclick="closeNodeDetails()">
                <i class="bi bi-x-lg"></i>
            </button>
        </div>
        <div class="detail-panel-body">
            <div class="detail-offline">
                <i class="bi bi-exclamation-triangle"></i> ${error}
            </div>
        </div>
    `;

    panel.style.display = 'flex';
}

function refreshNodeDetails(nodeName) {
    showNodeDetails(nodeName);
}

function closeNodeDetails() {
    const panel = document.getElementById('node-detail-panel');
    if (panel) {
        panel.style.display = 'none';
        panel.innerHTML = '';
    }
}

function showStatus(message, type) {
    const statusBar = document.getElementById('topo-status');
    if (!statusBar) return;

    const icon = type === 'ok' ? 'check-circle' : (type === 'error' ? 'exclamation-triangle' : 'info-circle');
    statusBar.innerHTML = `<i class="bi bi-${icon}"></i> ${message}`;
    statusBar.className = `topo-status-bar topo-status-${type}`;

    if (type !== 'loading') {
        setTimeout(() => {
            if (statusBar.innerHTML === `<i class="bi bi-${icon}"></i> ${message}`) {
                statusBar.className = 'topo-status-bar topo-status-loading';
                statusBar.innerHTML = '<i class="bi bi-info-circle"></i> Idle';
            }
        }, 3000);
    }
}

// Create detail panel element if it doesn't exist
(function createDetailPanel() {
    if (!document.getElementById('node-detail-panel')) {
        const panel = document.createElement('div');
        panel.id = 'node-detail-panel';
        panel.className = 'topo-detail-panel';
        panel.style.display = 'none';
        document.querySelector('.topo-workspace').appendChild(panel);
    }
})();