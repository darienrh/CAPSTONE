const COLORS = ['#36A2EB', '#FF6384', '#4BC0C0', '#FFCE56', '#9966FF', '#FF9F40'];
const MAX_POINTS = 20;

function getChartTheme() {
    const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    return {
        grid: isDark ? '#333333' : '#e2e8f0',
        text: isDark ? '#aaaaaa' : '#64748b'
    };
}

const chartOptions = {
    responsive: true,
    animation: false,
    scales: {
        y: {
            beginAtZero: true,
            grid: { color: getChartTheme().grid },
            ticks: {
                color: getChartTheme().text,
                callback: v => v >= 1000000 ? (v / 1000000).toFixed(1) + 'M' : v >= 1000 ? (v / 1000).toFixed(1) + 'K' : v
            }
        },
        x: {
            grid: { color: getChartTheme().grid },
            ticks: { color: getChartTheme().text }
        }
    },
    plugins: { legend: { labels: { color: getChartTheme().text } } }
};

const chartIn = new Chart(
    document.getElementById('chartInbound').getContext('2d'),
    { type: 'line', data: { labels: [], datasets: [] }, options: { ...chartOptions } }
);

const chartOut = new Chart(
    document.getElementById('chartOutbound').getContext('2d'),
    { type: 'line', data: { labels: [], datasets: [] }, options: { ...chartOptions } }
);

const devicePeaks = {};
const deviceLastSeen = {};
const socket = io();

socket.on('telemetry_update', function (msg) {
    const ts = msg.timestamp;
    [chartIn, chartOut].forEach(c => {
        c.data.labels.push(ts);
        if (c.data.labels.length > MAX_POINTS) c.data.labels.shift();
    });
    for (const [device, values] of Object.entries(msg.data)) {
        const inBps = values.in_bps ?? 0;
        const outBps = values.out_bps ?? 0;
        const idx = Object.keys(msg.data).indexOf(device) % COLORS.length;
        const color = COLORS[idx];
        if (!devicePeaks[device]) devicePeaks[device] = { in: 0, out: 0 };
        devicePeaks[device].in = Math.max(devicePeaks[device].in, inBps);
        devicePeaks[device].out = Math.max(devicePeaks[device].out, outBps);
        deviceLastSeen[device] = ts;
        updateDataset(chartIn, device, inBps, color);
        updateDataset(chartOut, device, outBps, color);
    }
    chartIn.update();
    chartOut.update();
    updateTable(msg.data);
    updateStatCards(msg.data);
});

socket.on('ids_alert', function (alert) {
    const tbody = document.getElementById('ids-table-body');
    const placeholder = tbody.querySelector('td[colspan]');
    if (placeholder) placeholder.parentElement.remove();

    const severityColor = alert.severity === 'high' ? 'text-danger' :
        alert.severity === 'medium' ? 'text-warning' : 'text-secondary';
    const protocolBadgeColor = alert.protocol === 'EIGRP' ? '#FFCE56' :
        alert.protocol === 'OSPF' ? '#36A2EB' :
            alert.protocol === 'SYS' ? '#7d8590' : '#4BC0C0';
    const ts = alert.timestamp.split('T')[1]?.slice(0, 8) || alert.timestamp;

    const tr = document.createElement('tr');
    tr.innerHTML = `
        <td class="text-secondary" style="font-size:0.8rem;">${ts}</td>
        <td><span class="badge" style="background:${protocolBadgeColor}22;color:${protocolBadgeColor};border:1px solid ${protocolBadgeColor}44">${alert.protocol}</span></td>
        <td><span class="badge bg-secondary">${alert.attack_type}</span></td>
        <td class="${severityColor}" style="font-weight:600;">${alert.severity}</td>
        <td style="font-size:0.82rem;">${alert.details}</td>
    `;
    tbody.insertBefore(tr, tbody.firstChild);

    if (alert.severity === 'high') showAlertPopup(alert);
});

function showAlertPopup(alert) {
    const existing = document.getElementById('ids-popup');
    if (existing) existing.remove();

    const popup = document.createElement('div');
    popup.id = 'ids-popup';
    popup.style.cssText = `
        position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);
        z-index:9999;min-width:420px;max-width:560px;
        background:var(--bg-secondary);border:2px solid var(--danger);
        border-radius:12px;box-shadow:0 0 40px rgba(218,54,51,0.4);padding:0;
    `;
    popup.innerHTML = `
        <div style="background:var(--danger-soft);border-bottom:1px solid var(--danger);padding:12px 16px;border-radius:10px 10px 0 0;display:flex;align-items:center;gap:10px;">
            <i class="bi bi-exclamation-triangle-fill" style="color:var(--danger);font-size:1.2rem;"></i>
            <span style="font-weight:700;color:var(--danger);font-size:1rem;">HIGH SEVERITY ALERT</span>
        </div>
        <div style="padding:16px;">
            <div style="font-family:'JetBrains Mono',monospace;font-size:0.85rem;color:var(--text-primary);margin-bottom:12px;">${alert.details}</div>
            <div style="display:flex;gap:8px;font-size:0.75rem;color:var(--text-secondary);margin-bottom:16px;">
                <span>Device: <strong style="color:var(--text-primary);">${alert.target_device}</strong></span>
                <span>•</span>
                <span>Protocol: <strong style="color:var(--text-primary);">${alert.protocol}</strong></span>
                <span>•</span>
                <span>${alert.timestamp.split('T')[1]?.slice(0, 8)}</span>
            </div>
            
            <div style="display:flex;gap:8px;justify-content:flex-end;">
                <button onclick="runTroubleshooter('${alert.target_device}')"
                    style="background:var(--accent);color:#fff;border:none;padding:8px 16px;border-radius:7px;font-weight:600;cursor:pointer;">
                    <i class="bi bi-tools"></i> Run Troubleshooter
                </button>
                <button onclick="document.getElementById('ids-popup').remove()"
                    style="background:var(--bg-tertiary);color:var(--text-secondary);border:1px solid var(--border-color);padding:8px 16px;border-radius:7px;font-weight:600;cursor:pointer;">
                    Dismiss
                </button>
            </div>
        </div>
    `;
    document.body.appendChild(popup);
}

function runTroubleshooter(device) {
    document.getElementById('ids-popup')?.remove();
    const gns3Url = document.getElementById('gns3-url').value || 'http://192.168.231.1:3080';
    fetch('/api/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ gns3_url: gns3Url, devices: device })
    }).then(() => {
        window.location.href = '/';
    });
}

function clearAlerts() {
    document.getElementById('ids-table-body').innerHTML =
        '<tr><td colspan="5" class="text-center text-secondary fst-italic">No alerts</td></tr>';
}

function updateDataset(chart, label, value, color) {
    let ds = chart.data.datasets.find(d => d.label === label);
    if (!ds) {
        ds = { label, data: [], borderColor: color, backgroundColor: color + '22', tension: 0.4, fill: false };
        chart.data.datasets.push(ds);
    }
    ds.data.push(value);
    if (ds.data.length > MAX_POINTS) ds.data.shift();
}

function fmtBps(v) {
    if (v >= 1000000) return (v / 1000000).toFixed(2) + ' Mbps';
    if (v >= 1000) return (v / 1000).toFixed(2) + ' Kbps';
    return v + ' bps';
}

function updateTable(data) {
    const tbody = document.getElementById('stats-table-body');
    tbody.innerHTML = '';
    for (const [device, v] of Object.entries(data)) {
        const peaks = devicePeaks[device] || { in: 0, out: 0 };
        const uptimeSec = Math.floor((v.uptime || 0) / 100);
        const h = Math.floor(uptimeSec / 3600), m = Math.floor((uptimeSec % 3600) / 60);
        const uptimeStr = `${h}h ${m}m`;
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${device}</strong></td>
            <td class="text-info">${fmtBps(v.in_bps ?? 0)}</td>
            <td class="text-warning">${fmtBps(v.out_bps ?? 0)}</td>
            <td>${v.cpu ?? '-'}%</td>
            <td>${v.mem_pct ?? '-'}%</td>
            <td class="${(v.err_in + v.err_out) > 0 ? 'text-danger' : 'text-secondary'}">${(v.err_in ?? 0) + (v.err_out ?? 0)}</td>
            <td class="text-secondary">${uptimeStr}</td>
            <td class="text-secondary">${deviceLastSeen[device] || '-'}</td>
        `;
        tbody.appendChild(tr);
    }
}

function updateStatCards(data) {
    const row = document.getElementById('stats-row');
    row.innerHTML = '';
    for (const [device, v] of Object.entries(data)) {
        const idx = Object.keys(data).indexOf(device) % COLORS.length;
        const color = COLORS[idx];
        const col = document.createElement('div');
        col.className = 'col-md-3 col-6';
        col.innerHTML = `
            <div class="card text-center" style="border-color:${color}44">
                <div class="card-body py-2">
                    <div class="fw-bold" style="color:${color}">${device}</div>
                    <div style="font-size:1.1rem;">${fmtBps(v.in_bps ?? 0)}</div>
                    <div class="text-secondary" style="font-size:0.72rem;">CPU: ${v.cpu ?? '-'}% | MEM: ${v.mem_pct ?? '-'}%</div>
                </div>
            </div>
        `;
        row.appendChild(col);
    }
}

function startTelemetry() {
    const gns3Url = document.getElementById('gns3-url').value || 'http://192.168.231.1:3080';
    const devicesRaw = document.getElementById('devices').value.trim();
    const devices = devicesRaw ? devicesRaw.split(',').map(d => d.trim()).filter(Boolean) : [];
    fetch('/api/telemetry/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ gns3_url: gns3Url, devices })
    }).then(r => r.json()).then(data => {
        if (data.error) { alert(data.error); return; }
        document.getElementById('btn-start').disabled = true;
        document.getElementById('btn-stop').disabled = false;
    });
}

function stopTelemetry() {
    fetch('/api/telemetry/stop', { method: 'POST' }).then(() => {
        document.getElementById('btn-start').disabled = false;
        document.getElementById('btn-stop').disabled = true;
    });
}

function updateChartColors() {
    if (typeof chartIn !== 'undefined' && typeof chartOut !== 'undefined') {
        const theme = getChartTheme();
        [chartIn, chartOut].forEach(c => {
            c.options.scales.x.grid.color = theme.grid;
            c.options.scales.x.ticks.color = theme.text;
            c.options.scales.y.grid.color = theme.grid;
            c.options.scales.y.ticks.color = theme.text;
            c.options.plugins.legend.labels.color = theme.text;
            c.update();
        });
    }
}

function toggleTheme() {
    const html = document.documentElement;
    const icon = document.getElementById('theme-icon');
    const isDark = html.getAttribute('data-theme') === 'dark';
    const newTheme = isDark ? 'light' : 'dark';

    html.setAttribute('data-theme', newTheme);
    html.setAttribute('data-bs-theme', newTheme);
    icon.className = newTheme === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
    localStorage.setItem('theme', newTheme);

    updateChartColors();
}

function openTopology() {
    const gns3Url = document.getElementById('gns3-url').value || 'http://192.168.231.1:3080';
    const match = gns3Url.match(/^https?:\/\/([^:\/]+)(?::(\d+))?/);
    const host = match ? match[1] : '192.168.231.1';
    const port = match ? (match[2] || '3080') : '3080';
    window.open(`http://${host}:${port}/static/web-ui/server/1/project/efcd850a-ea6b-4846-855f-0513dad86b65?host=${host}&port=${port}&ssl=false`, '_blank');
}

(function applyStoredTheme() {
    const saved = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', saved);
    document.documentElement.setAttribute('data-bs-theme', saved);

    window.addEventListener('DOMContentLoaded', () => {
        const icon = document.getElementById('theme-icon');
        if (icon) icon.className = saved === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
        // Defer initial chart update until canvas is ready
        setTimeout(updateChartColors, 50);
    });
})();

fetch('/api/telemetry/status').then(r => r.json()).then(data => {
    document.getElementById('btn-start').disabled = data.active;
    document.getElementById('btn-stop').disabled = !data.active;
});
