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

_original_input = builtins.input
_original_confirm = _rp.Confirm.ask
_original_prompt = _rp.Prompt.ask

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

builtins.input = web_input
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

    def print_scan_summary(self, detected_issues):
        has_interface = detected_issues.get('interfaces')
        has_eigrp = detected_issues.get('eigrp')
        has_ospf = detected_issues.get('ospf')
        if not has_interface and not has_eigrp and not has_ospf:
            log_message("✓ No Problems Detected", 'success')
            return False
        log_message("Diagnostic Results", 'phase')
        log_message(f"{'Device':<12} {'Category':<12} {'Issue':<24} Status", 'info')
        for device, problems in detected_issues.get('interfaces', {}).items():
            for p in problems:
                issue_type = p.get('type', 'shutdown')
                if issue_type == 'ip address mismatch':
                    status = f"IP: {p['current_ip']} (expect: {p['expected_ip']})"
                elif issue_type == 'missing ip address':
                    status = f"Missing IP: {p['expected_ip']}"
                else:
                    status = "Admin Down"
                intf = p.get('interface', '')
                log_message(
                    f"{device:<12} {'Interface':<12} {str(intf)[:24]:<24} {status}",
                    'warning'
                )
        for device, problems in detected_issues.get('eigrp', {}).items():
            for p in problems:
                line = (p.get('line', p.get('type', '')) or '')[:40]
                log_message(
                    f"{device:<12} {'EIGRP':<12} {line:<24} {p.get('type', '')}",
                    'warning'
                )
        for device, problems in detected_issues.get('ospf', {}).items():
            for p in problems:
                line = (p.get('line', p.get('type', '')) or '')[:40]
                log_message(
                    f"{device:<12} {'OSPF':<12} {line:<24} {p.get('type', '')}",
                    'warning'
                )
        return True

    def print_fix_completion_summary(self, fix_results):
        if not fix_results:
            log_message("✓ No Changes Made", 'success')
            return
        log_message("═" * 59, 'dim')
        log_message("FINAL COMPLETION SUMMARY", 'phase')
        log_message("═" * 59, 'dim')
        log_message(f"{'Device':<12} Commands / Verification", 'info')
        for result in fix_results:
            dev = result.get('device', '')
            cmd = (result.get('commands', '') or '')[:80]
            ver = (result.get('verification', '') or '')[:60]
            log_message(f"{dev:<12} cmds: {cmd}", 'warning')
            log_message(f"{'':12} verify: {ver}", 'dim')
        log_message(f"✓ Successfully applied {len(fix_results)} fix(es)", 'success')

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

    def save_run_history(self, fix_results, timestamp):
        ok = self._original.save_run_history(fix_results, timestamp)
        if ok:
            log_message("Run history saved.", 'success')
        return ok

def _print_to_log(*args, **kwargs):
    line = ' '.join(str(a) for a in args)
    log_message(line if line else ' ', 'info')

def _install_log_print():
    orig = builtins.print
    builtins.print = _print_to_log
    return orig

def _restore_print(orig):
    builtins.print = orig

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
        runner_instance.reporter.print_scan_summary(detected_issues)
        has_issues = runner._detected_problem_count(detected_issues) > 0

        if has_issues:
            if WebInputHandler.ask_confirm("\nProceed to fix menu?"):
                update_status("applying fixes", 'warning')
                op = _install_log_print()
                try:
                    runner_instance.apply_fixes(detected_issues)
                    runner_instance.print_completion_summary()
                finally:
                    _restore_print(op)
        else:
            runner_instance.reporter.save_run_history([], runner_instance.run_timestamp)

        log_message("\n" + "=" * 60, 'dim')
        if WebInputHandler.ask_confirm("View Knowledge Base statistics?", default=False):
            op = _install_log_print()
            try:
                runner_instance.show_kb_statistics()
            finally:
                _restore_print(op)

        log_message("\n" + "=" * 60, 'dim')
        if WebInputHandler.ask_confirm("View IE explanation traces?", default=False):
            op = _install_log_print()
            try:
                runner_instance.show_explanation_traces()
            finally:
                _restore_print(op)

        log_message("\n" + "=" * 60, 'dim')
        if WebInputHandler.ask_confirm("Revert configs to last stable version?", default=False):
            revert_mode = WebInputHandler.ask_choice(
                "[cyan]Revert:[/cyan]",
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

        log_message("\n" + "=" * 60, 'dim')
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
        is_running = False
        runner_instance = None
        update_status("idle", 'secondary')

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
    gns3_url = data.get('gns3_url', 'http://localhost:3080')
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