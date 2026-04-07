const COLORS = ['#36A2EB', '#FF6384', '#4BC0C0', '#FFCE56', '#9966FF', '#FF9F40'];
const MAX_POINTS = 20;

function getChartTheme() {
    const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    return {
        grid: isDark ? '#333333' : '#e2e8f0',
        text: isDark ? '#aaaaaa' : '#64748b'
    };
}

const BPS_TICKS = [
    100, 200, 300, 400, 500, 600, 700, 800, 900,
    1000, 1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900, 2000
];
const KBPS_TICKS = [
    100000, 200000, 300000, 400000, 500000, 600000, 700000, 800000, 900000
];
const MBPS_TICKS = [
    1000000, 1100000, 1200000, 1300000, 1400000, 1500000, 1600000, 1700000, 1800000, 1900000, 2000000
];

function getDynamicTicks(chart) {
    const max = Math.max(0, ...chart.data.datasets.flatMap(ds => ds.data));
    let pool;
    if (max >= 1000000) pool = [0, ...KBPS_TICKS, ...MBPS_TICKS];
    else if (max >= 2000) pool = [0, ...KBPS_TICKS];
    else pool = [0, ...BPS_TICKS];
    return pool.filter(v => v <= Math.max(max * 1.2, pool[1])).map(v => ({ value: v }));
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
                callback: v => v >= 1000000 ? (v / 1000000).toFixed(1) + 'M' : v >= 1000 ? (v / 1000).toFixed(0) + 'K' : v
            },
            afterBuildTicks: axis => { axis.ticks = getDynamicTicks(axis.chart); }
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

socket.on('telemetry_update', function (msg) {
    if (!msg || !msg.data || typeof msg.data !== 'object') return;
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
    if (!tbody) return;
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
    document.getElementById('ids-popup')?.remove();

    const popup = document.createElement('div');
    popup.id = 'ids-popup';
    popup.style.cssText = `
        position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);
        z-index:9999;min-width:420px;max-width:560px;
        background:var(--bg-secondary);border:2px solid var(--danger);
        border-radius:12px;box-shadow:0 0 40px rgba(218,54,51,0.4);padding:0;
    `;

    const head = document.createElement('div');
    head.style.cssText = 'background:var(--danger-soft);border-bottom:1px solid var(--danger);padding:12px 16px;border-radius:10px 10px 0 0;display:flex;align-items:center;gap:10px;';
    head.innerHTML = '<i class="bi bi-exclamation-triangle-fill" style="color:var(--danger);font-size:1.2rem;"></i><span style="font-weight:700;color:var(--danger);font-size:1rem;">HIGH SEVERITY ALERT</span>';

    const body = document.createElement('div');
    body.style.padding = '16px';

    const detailEl = document.createElement('div');
    detailEl.style.cssText = 'font-family:\'JetBrains Mono\',monospace;font-size:0.85rem;color:var(--text-primary);margin-bottom:12px;';
    detailEl.textContent = alert.details || '';

    const meta = document.createElement('div');
    meta.style.cssText = 'display:flex;gap:8px;font-size:0.75rem;color:var(--text-secondary);margin-bottom:16px;flex-wrap:wrap;align-items:center;';
    const dev = document.createElement('span');
    dev.innerHTML = 'Device: <strong style="color:var(--text-primary);"></strong>';
    dev.querySelector('strong').textContent = alert.target_device || '';
    const proto = document.createElement('span');
    proto.innerHTML = 'Protocol: <strong style="color:var(--text-primary);"></strong>';
    proto.querySelector('strong').textContent = alert.protocol || '';
    const timeSp = document.createElement('span');
    timeSp.textContent = (alert.timestamp && alert.timestamp.split('T')[1]?.slice(0, 8)) || '';
    meta.appendChild(dev);
    meta.appendChild(document.createTextNode('•'));
    meta.appendChild(proto);
    meta.appendChild(document.createTextNode('•'));
    meta.appendChild(timeSp);

    const actions = document.createElement('div');
    actions.style.cssText = 'display:flex;gap:8px;justify-content:flex-end;';

    const runBtn = document.createElement('button');
    runBtn.type = 'button';
    runBtn.style.cssText = 'background:var(--accent);color:#fff;border:none;padding:8px 16px;border-radius:7px;font-weight:600;cursor:pointer;';
    runBtn.innerHTML = '<i class="bi bi-tools"></i> Run Troubleshooter';
    runBtn.addEventListener('click', () => {
        runTroubleshooter(alert.target_device, alert.protocol, alert.attack_type);
    });

    const dismissBtn = document.createElement('button');
    dismissBtn.type = 'button';
    dismissBtn.style.cssText = 'background:var(--bg-tertiary);color:var(--text-secondary);border:1px solid var(--border-color);padding:8px 16px;border-radius:7px;font-weight:600;cursor:pointer;';
    dismissBtn.textContent = 'Dismiss';
    dismissBtn.addEventListener('click', () => popup.remove());

    actions.appendChild(runBtn);
    actions.appendChild(dismissBtn);

    body.appendChild(detailEl);
    body.appendChild(meta);
    body.appendChild(actions);
    popup.appendChild(head);
    popup.appendChild(body);
    document.body.appendChild(popup);
}

function runTroubleshooter(_device, protocol, attackType) {
    document.getElementById('ids-popup')?.remove();
    const raw =
        (document.getElementById('telemetry-gns3-url')?.value ||
            document.getElementById('gns3-url')?.value ||
            '').trim();
    const gns3Url = raw || 'http://192.168.231.1:3080';
    const idsMap = { 'TCP': 'tcp_flood', 'OSPF': 'ospf_attack' };
    const idsTrigger = (attackType === 'ml_detection' && idsMap[protocol]) || null;
    if (typeof showView === 'function') showView('diagnostics');
    fetch('/api/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ gns3_url: gns3Url, devices: 'all', ids_trigger: idsTrigger })
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

function updatePacketDropWarnings(droppingDevices) {
    const row = document.getElementById('packet-drop-row');
    const container = document.getElementById('packet-drop-warnings');
    if (!row || !container) return;
    if (droppingDevices.length === 0) {
        row.style.display = 'none';
        container.innerHTML = '';
        return;
    }
    row.style.display = '';
    container.innerHTML = droppingDevices.map(dev => `
        <div class="packet-drop-message">
            <i class="bi bi-exclamation-triangle-fill"></i>
            <strong>${dev}</strong> is experiencing irregular traffic patterns, and dropping packets.
            <span class="suggestion">Suggestion: Investigate ${dev} and its corresponding End-Devices.</span>
        </div>
    `).join('');
}

function updateTable(data) {
    const tbody = document.getElementById('stats-table-body');
    tbody.innerHTML = '';
    const droppingDevices = [];
    for (const [device, v] of Object.entries(data)) {
        const uptimeSec = Math.floor((v.uptime || 0) / 100);
        const h = Math.floor(uptimeSec / 3600), m = Math.floor((uptimeSec % 3600) / 60);
        const uptimeStr = `${h}h ${m}m`;
        const errTotal = (v.err_in ?? 0) + (v.err_out ?? 0);
        if (errTotal > 1) droppingDevices.push(device);
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${device}</strong></td>
            <td class="text-info">${fmtBps(v.in_bps ?? 0)}</td>
            <td class="text-warning">${fmtBps(v.out_bps ?? 0)}</td>
            <td>${v.cpu ?? '-'}%</td>
            <td>${v.mem_pct ?? '-'}%</td>
            <td class="${errTotal > 0 ? 'text-danger' : 'text-secondary'}">${errTotal}</td>
            <td class="text-secondary">${uptimeStr}</td>
            <td class="text-secondary">${deviceLastSeen[device] || '-'}</td>
        `;
        tbody.appendChild(tr);
    }
    updatePacketDropWarnings(droppingDevices);
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

async function startTelemetry() {
    const gns3El = document.getElementById('telemetry-gns3-url');
    const devEl = document.getElementById('telemetry-devices');
    const gns3Url = (gns3El && gns3El.value) || 'http://192.168.231.1:3080';
    const devicesRaw = (devEl && devEl.value) ? devEl.value.trim() : '';
    const devices = devicesRaw ? devicesRaw.split(',').map(d => d.trim()).filter(Boolean) : [];
    let r;
    try {
        r = await fetch('/api/telemetry/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ gns3_url: gns3Url, devices })
        });
    } catch (_) {
        return;
    }
    const data = await r.json().catch(() => ({}));
    if (data.error) { alert(data.error); return; }
    const btnStart = document.getElementById('telemetry-btn-start');
    const btnStop = document.getElementById('telemetry-btn-stop');
    if (btnStart) btnStart.disabled = true;
    if (btnStop) btnStop.disabled = false;
}

function stopTelemetry() {
    fetch('/api/telemetry/stop', { method: 'POST' }).then(() => {
        document.getElementById('telemetry-btn-start').disabled = false;
        document.getElementById('telemetry-btn-stop').disabled = true;
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


let _telemetryInited = false;

async function initTelemetryView() {
    if (_telemetryInited) return;
    let status;
    let history;
    try {
        const [statusRes, historyRes] = await Promise.all([
            fetch('/api/telemetry/status'),
            fetch('/api/telemetry/history')
        ]);
        if (!statusRes.ok || !historyRes.ok) return;
        status = await statusRes.json();
        history = await historyRes.json();
    } catch (_) {
        return;
    }

    const btnStart = document.getElementById('telemetry-btn-start');
    const btnStop = document.getElementById('telemetry-btn-stop');
    if (btnStart) btnStart.disabled = status.active;
    if (btnStop) btnStop.disabled = !status.active;

    for (const snapshot of history) {
        if (!snapshot || !snapshot.data || typeof snapshot.data !== 'object') continue;
        [chartIn, chartOut].forEach(c => {
            c.data.labels.push(snapshot.timestamp);
            if (c.data.labels.length > MAX_POINTS) c.data.labels.shift();
        });
        for (const [device, values] of Object.entries(snapshot.data)) {
            const idx = Object.keys(snapshot.data).indexOf(device) % COLORS.length;
            updateDataset(chartIn, device, values.in_bps ?? 0, COLORS[idx]);
            updateDataset(chartOut, device, values.out_bps ?? 0, COLORS[idx]);
            if (!devicePeaks[device]) devicePeaks[device] = { in: 0, out: 0 };
            devicePeaks[device].in = Math.max(devicePeaks[device].in, values.in_bps ?? 0);
            devicePeaks[device].out = Math.max(devicePeaks[device].out, values.out_bps ?? 0);
            deviceLastSeen[device] = snapshot.timestamp;
        }
        updateTable(snapshot.data);
        updateStatCards(snapshot.data);
    }
    if (history.length) {
        chartIn.update();
        chartOut.update();
    }

    _telemetryInited = true;

    if (!status.active) {
        await startTelemetry().catch(() => { });
    }
}