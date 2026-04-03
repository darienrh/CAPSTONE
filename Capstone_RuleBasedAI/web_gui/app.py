#!/usr/bin/env python3
import sys
import os
import signal
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import runner

app = Flask(__name__)
app.config['SECRET_KEY'] = 'network-diagnostic-tool-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ============== GLOBAL STATE ==============
execution_thread = None
is_running = False
runner_instance = None
user_responses = {}
response_events = {}

# ============== SIGNAL HANDLING ==============
def _shutdown(sig, frame):
    global is_running, runner_instance
    is_running = False
    if runner_instance:
        runner_instance.cleanup_all_connections()
    sys.exit(0)

signal.signal(signal.SIGINT, _shutdown)
signal.signal(signal.SIGTERM, _shutdown)

# ============== LOGGING & STATUS ==============
def log_message(message, level='info'):
    timestamp = datetime.now().strftime("%H:%M:%S")
    socketio.emit('log', {
        'timestamp': timestamp,
        'message': message,
        'level': level
    })

def update_status(text, color='secondary'):
    socketio.emit('status', {'text': text, 'color': color})

def emit_devices(devices):
    socketio.emit('devices', {'devices': devices})

# ============== PROMPT HANDLING ==============
def show_prompt(prompt_id, question, prompt_type, choices=None, default=None):
    event = threading.Event()
    response_events[prompt_id] = event

    socketio.emit('prompt', {
        'id': prompt_id,
        'question': question,
        'type': prompt_type,
        'choices': choices,
        'default': default
    })

    event.wait(timeout=300)

    response = user_responses.pop(prompt_id, None)
    response_events.pop(prompt_id, None)
    return response

class WebInputHandler:
    @staticmethod
    def ask_text(prompt_text):
        prompt_id = f"text_{datetime.now().timestamp()}"
        log_message(f"PROMPT: {prompt_text}", 'info')
        response = show_prompt(prompt_id, prompt_text, 'text')
        return response if response is not None else ""

    @staticmethod
    def ask_confirm(prompt_text, default=True):
        prompt_id = f"confirm_{datetime.now().timestamp()}"
        log_message(f"CONFIRM: {prompt_text}", 'warning')
        response = show_prompt(prompt_id, prompt_text, 'confirm', default=default)
        return response if response is not None else default

    @staticmethod
    def ask_choice(prompt_text, choices=None, default=None):
        prompt_id = f"choice_{datetime.now().timestamp()}"
        log_message(f"CHOICE: {prompt_text}", 'info')
        response = show_prompt(prompt_id, prompt_text, 'choice',
                               choices=choices, default=default)
        return response if response is not None else default

# ============== I/O PATCHING ==============
import builtins
import rich.prompt as _rp
import re as _re

_original_input = builtins.input
_original_confirm = _rp.Confirm.ask
_original_prompt = _rp.Prompt.ask
_original_print = builtins.print

def web_input(prompt=""):
    if is_running:
        return WebInputHandler.ask_text(prompt)
    return _original_input(prompt)

def web_confirm_ask(prompt_text, default=True):
    if is_running:
        return WebInputHandler.ask_confirm(prompt_text, default)
    return _original_confirm(prompt_text, default)

def web_prompt_ask(prompt_text, choices=None, default=None):
    if is_running:
        return WebInputHandler.ask_choice(prompt_text, choices, default)
    return _original_prompt(prompt_text, choices=choices, default=default)

def web_print(*args, **kwargs):
    if is_running:
        msg = ' '.join(str(a) for a in args)
        msg = _re.sub(r'\[/?(?:bold|cyan|green|red|yellow|magenta|white|dim|italic|underline)[^\]]*\]', '', msg).strip()
        if msg and not _re.match(r"^[=\-━─]+$", msg):
            log_message(msg, 'dim')
    else:
        _original_print(*args, **kwargs)

builtins.input = web_input
builtins.print = web_print
_rp.Confirm.ask = web_confirm_ask
_rp.Prompt.ask = web_prompt_ask

# ============== CUSTOM REPORTER ==============
class WebReporter:
    def __init__(self, original_reporter):
        self._original = original_reporter

    def print_success(self, msg):
        log_message(msg, 'success')
        return self

    def print_error(self, msg):
        log_message(msg, 'error')
        return self

    def print_warning(self, msg):
        log_message(msg, 'warning')
        return self

    def print_info(self, msg):
        log_message(msg, 'info')
        return self

    def print_phase_header(self, msg):
        import re
        clean = re.sub(r'\[/?[a-zA-Z_ ]+\]', '', msg)
        log_message("━" * 60, 'dim')
        log_message(f"  {clean}", 'phase')
        log_message("━" * 60, 'dim')
        update_status(clean.lower(), 'primary')
        return self

    def print_scan_summary(self, issues):
        has_issues = False
        for category in ('interfaces', 'eigrp', 'ospf'):
            for device, problems in (issues.get(category) or {}).items():
                for p in (problems or []):
                    has_issues = True
                    desc = p.get('type', str(p)) if isinstance(p, dict) else str(p)
                    log_message(f"  [{device}] {category}: {desc}", 'warning')
        if not has_issues:
            log_message("✓ No Problems Detected", 'success')
        return has_issues

    def print_fix_completion_summary(self, fix_results):
        if not fix_results:
            log_message("No fixes were applied.", 'dim')
            return
        passed = sum(1 for r in fix_results if r.get('success'))
        failed = len(fix_results) - passed
        log_message(f"Fix summary: {passed} succeeded, {failed} failed.",
                    'success' if failed == 0 else 'warning')
        for r in fix_results:
            log_message(f"  [{r['device']}] {r['commands']}", 'dim')

    def print_dim(self, msg):
        log_message(msg.strip(), 'dim')
        return self

    def save_run_history(self, fix_results, timestamp):
        result = self._original.save_run_history(fix_results, timestamp)
        history_file = self._original._get_next_filename.__func__
        try:
            files = sorted(self._original.history_dir.glob('run*.txt'), key=lambda x: x.stat().st_mtime, reverse=True)
            if files:
                log_message(f'History saved to: {files[0]}', 'dim')
        except Exception:
            pass
        return result

    def create_progress_bar(self, description, total):
        class ProgressBar:
            def __init__(self, desc, total_count):
                self.desc = desc
                self.total = total_count
                self.current = 0

            def __enter__(self):
                log_message(f"{self.desc} (0/{self.total})", 'info')
                return self

            def __exit__(self, *args):
                pass

            def add_task(self, desc, total):
                return 0

            def update(self, task, completed=None, advance=0, description=None):
                if completed is not None:
                    self.current = completed
                else:
                    self.current += advance
                desc_text = description or self.desc
                log_message(f"{desc_text} ({self.current}/{self.total})", 'info')

        return ProgressBar(description, total)

# ============== DIAGNOSTICS EXECUTION ==============
def run_diagnostics_thread(gns3_url, devices):
    global runner_instance, is_running

    try:
        is_running = True
        update_status("initializing", 'warning')

        runner_instance = runner.DiagnosticRunner(gns3_url=gns3_url)

        runner_instance.reporter = WebReporter(runner_instance.reporter)
        runner_instance.fix_applier.reporter = WebReporter(runner_instance.fix_applier.reporter)

        log_message("Network Diagnostic Tool", 'phase')
        stats = runner_instance.knowledge_base.get_statistics()
        log_message(
            f"Knowledge Base: {stats['total_rules']} rules, "
            f"{stats['total_problems_logged']} problems logged, "
            f"{stats['overall_success_rate']}% success rate",
            'info'
        )

        update_status("connecting to GNS3", 'warning')
        if not runner_instance.connect():
            update_status("connection failed", 'danger')
            log_message("Failed to connect to GNS3", 'error')
            return

        available_devices = list(runner_instance.nodes.keys())
        device_map = {name.lower(): name for name in available_devices}

        log_message(f"Available devices: {', '.join(available_devices)}", 'info')
        emit_devices(available_devices)

        if not devices or devices == 'all':
            final_target_list = available_devices
        else:
            final_target_list = []
            for req in [d.strip().lower() for d in devices.split(',')]:
                if req in device_map:
                    final_target_list.append(device_map[req])

        if not final_target_list:
            log_message("No valid devices selected.", 'error')
            update_status("error", 'danger')
            return

        log_message(f"Targeting: {', '.join(final_target_list)}", 'info')

        update_status("scanning devices", 'warning')
        detected_issues = runner_instance.run_diagnostics(final_target_list)
        has_issues = runner_instance.reporter.print_scan_summary(detected_issues)

        if has_issues:
            if WebInputHandler.ask_confirm("Proceed to fix menu?"):
                update_status("applying fixes", 'warning')
                runner_instance.apply_fixes(detected_issues)
                runner_instance.print_completion_summary()

        log_message("─" * 60, 'dim')
        if WebInputHandler.ask_confirm("View Knowledge Base statistics?", default=False):
            runner_instance.show_kb_statistics()

        log_message("─" * 60, 'dim')
        if WebInputHandler.ask_confirm("View IE explanation traces?", default=False):
            traces = runner_instance.inference_engine.get_explanation_traces()
            if not traces:
                log_message("No explanation traces recorded this session.", 'dim')
            else:
                log_message(f"Explanation traces from this session ({len(traces)} total):", 'info')
                for trace in traces:
                    runner_instance.inference_engine.print_trace(trace)

        log_message("─" * 60, 'dim')
        if WebInputHandler.ask_confirm("Revert configs to last stable version?", default=False):
            revert_mode = WebInputHandler.ask_choice(
                "Revert mode:",
                choices=["all", "select"],
                default="all"
            )
            if revert_mode == "all":
                runner_instance.restore_stable_configurations(final_target_list)
            else:
                device_input = WebInputHandler.ask_text("Devices to revert (e.g. R1, R2, R4):")
                if device_input:
                    dmap = {n.lower(): n for n in final_target_list}
                    revert_devices = [
                        dmap[r.strip().lower()]
                        for r in device_input.split(',')
                        if r.strip().lower() in dmap
                    ]
                    if revert_devices:
                        runner_instance.restore_stable_configurations(revert_devices)

        log_message("─" * 60, 'dim')
        if WebInputHandler.ask_confirm("Save stable configurations of all routers now?"):
            runner_instance.save_stable_configurations(final_target_list)

        log_message("Script completed successfully!", 'success')
        update_status("completed", 'success')

    except Exception as e:
        log_message(f"Fatal error: {str(e)}", 'error')
        update_status("error", 'danger')
        import traceback
        log_message(traceback.format_exc(), 'error')
    finally:
        if runner_instance:
            runner_instance.cleanup_all_connections()
        runner_instance = None
        update_status("idle", 'secondary')
        is_running = False

# ============== FLASK ROUTES ==============
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def api_status():
    return jsonify({
        'running': is_running,
        'runner_active': runner_instance is not None
    })

@app.route('/api/start', methods=['POST'])
def api_start():
    global execution_thread

    if is_running:
        return jsonify({'error': 'Already running'}), 400

    data = request.json
    gns3_url = data.get('gns3_url', 'http://192.168.231.1:3080')
    devices = data.get('devices', 'all')

    execution_thread = threading.Thread(
        target=run_diagnostics_thread,
        args=(gns3_url, devices),
        daemon=True
    )
    execution_thread.start()

    return jsonify({'status': 'started'})

@app.route('/api/stop', methods=['POST'])
def api_stop():
    global is_running
    if is_running:
        is_running = False
        return jsonify({'status': 'stopping'})
    return jsonify({'error': 'Not running'}), 400

@app.route('/api/prompt/response', methods=['POST'])
def api_prompt_response():
    data = request.json
    prompt_id = data.get('id')
    response = data.get('response')

    if prompt_id in response_events:
        user_responses[prompt_id] = response
        response_events[prompt_id].set()
        return jsonify({'status': 'ok'})

    return jsonify({'error': 'Invalid prompt'}), 400

# ============== TOPOLOGY ROUTES ==============
import requests as _requests
from requests.auth import HTTPBasicAuth as _HTTPBasicAuth
from utils.telnet_utils import connect_device, close_device, send_command

def _gns3_get(path, gns3_url='http://localhost:3080', username=None, password=None):
    auth = _HTTPBasicAuth(username, password) if username and password else None
    try:
        r = _requests.get(f"{gns3_url}/v2{path}", auth=auth, timeout=5)
        if r.status_code == 401 and auth:
            r = _requests.get(f"{gns3_url}/v2{path}", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

@app.route('/topology')
def topology_page():
    return render_template('topology.html')

@app.route('/api/topology')
def api_topology():
    gns3_url = request.args.get('gns3_url', 'http://192.168.231.1:3080')
    username = request.args.get('username') or None
    password = request.args.get('password') or None

    projects = _gns3_get('/projects', gns3_url, username, password)
    if not projects:
        return jsonify({'error': 'Cannot reach GNS3'}), 503

    project = next((p for p in projects if p['status'] == 'opened'), None)
    if not project:
        return jsonify({'error': 'No open project'}), 404

    pid = project['project_id']
    nodes_raw = _gns3_get(f'/projects/{pid}/nodes', gns3_url, username, password) or []
    links_raw = _gns3_get(f'/projects/{pid}/links', gns3_url, username, password) or []

    node_map = {}
    nodes = []
    for n in nodes_raw:
        node_map[n['node_id']] = n
        nodes.append({
            'id':      n['node_id'],
            'name':    n['name'],
            'type':    n.get('node_type', 'unknown'),
            'status':  n.get('status', 'unknown'),
            'console': n.get('console'),
            'x':       n.get('x', 0),
            'y':       n.get('y', 0),
            'symbol':  n.get('symbol', ''),
        })

    links = []
    for lk in links_raw:
        eps = lk.get('nodes', [])
        if len(eps) < 2:
            continue
        a, b = eps[0], eps[1]
        na = node_map.get(a['node_id'], {})
        nb = node_map.get(b['node_id'], {})
        links.append({
            'id':        lk['link_id'],
            'source':    a['node_id'],
            'target':    b['node_id'],
            'source_name': na.get('name', ''),
            'target_name': nb.get('name', ''),
            'source_port': a.get('adapter_number', ''),
            'target_port': b.get('adapter_number', ''),
            'link_type': lk.get('link_type', 'ethernet'),
        })

    return jsonify({
        'project': project['name'],
        'project_id': pid,
        'nodes': nodes,
        'links': links,
    })

@app.route('/api/topology/node/<node_name>')
def api_topology_node(node_name):
    gns3_url = request.args.get('gns3_url', 'http://192.168.231.1:3080')
    username = request.args.get('username') or None
    password = request.args.get('password') or None

    projects = _gns3_get('/projects', gns3_url, username, password)
    if not projects:
        return jsonify({'error': 'Cannot reach GNS3'}), 503

    project = next((p for p in projects if p['status'] == 'opened'), None)
    if not project:
        return jsonify({'error': 'No open project'}), 404

    nodes_raw = _gns3_get(f"/projects/{project['project_id']}/nodes", gns3_url, username, password) or []
    node = next((n for n in nodes_raw if n['name'].lower() == node_name.lower()), None)
    if not node:
        return jsonify({'error': 'Node not found'}), 404

    console_port = node.get('console')
    if not console_port or node.get('status') != 'started':
        return jsonify({'name': node['name'], 'status': node.get('status'), 'interfaces': [], 'routes': []})

    tn = connect_device(console_port)
    if not tn:
        return jsonify({'name': node['name'], 'status': 'unreachable', 'interfaces': [], 'routes': []})

    try:
        raw_iface = send_command(tn, 'show ip interface brief', wait_time=2) or ''
        raw_route = send_command(tn, 'show ip route', wait_time=2) or ''
    finally:
        close_device(tn)

    interfaces = _parse_ip_interface_brief(raw_iface)
    routes = _parse_ip_route(raw_route)

    return jsonify({
        'name':       node['name'],
        'status':     node.get('status'),
        'console':    console_port,
        'interfaces': interfaces,
        'routes':     routes,
    })

def _parse_ip_interface_brief(output):
    import re
    results = []
    for line in output.splitlines():
        m = re.match(
            r'(\S+)\s+(\S+)\s+\S+\s+\S+\s+(\S+)\s+(\S+)',
            line.strip()
        )
        if m and not line.strip().startswith('Interface'):
            results.append({
                'interface': m.group(1),
                'ip':        m.group(2),
                'status':    m.group(3),
                'protocol':  m.group(4),
            })
    return results

def _parse_ip_route(output):
    import re
    results = []
    for line in output.splitlines():
        line = line.strip()
        m = re.match(r'^([CSROBEILD\*][\s\*]*)\s+([\d./]+|[\d.]+)\s+(.*)', line)
        if m:
            results.append({
                'code':    m.group(1).strip(),
                'network': m.group(2).strip(),
                'detail':  m.group(3).strip(),
            })
    return results

# ============== SOCKETIO EVENTS ==============
@socketio.on('connect')
def handle_connect():
    log_message("Client connected", 'info')
    emit('status', {'text': 'idle', 'color': 'secondary'})

@socketio.on('disconnect')
def handle_disconnect():
    log_message("Client disconnected", 'info')

# ============== ENTRY POINT ==============
def _free_port(port):
    import subprocess
    subprocess.run(['fuser', '-k', f'{port}/tcp'], capture_output=True)
    import time; time.sleep(1)

if __name__ == '__main__':
    _free_port(5000)
    print("=" * 60)
    print("  Network Diagnostic Tool - Web Interface")
    print("=" * 60)
    print(f"  Starting server on http://0.0.0.0:5000")
    print(f"  Open http://localhost:5000 in your browser")
    print("=" * 60)
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, use_reloader=False, allow_unsafe_werkzeug=True)