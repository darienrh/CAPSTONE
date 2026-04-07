#!/usr/bin/env python3
import sys
import os
import signal
import threading
import time
import re
import subprocess
import paramiko
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect
from flask_socketio import SocketIO, emit

_PROJECT_ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Load all paths and credentials from ssh_creds.txt ────────────────────────
import configparser as _configparser
_SSH_CREDS_PATH = os.path.join(_PROJECT_ROOT, 'ssh_creds.txt')
_ssh_cfg = _configparser.ConfigParser()
if os.path.exists(_SSH_CREDS_PATH):
    _ssh_cfg.read(_SSH_CREDS_PATH)

_KALI_HOST         = _ssh_cfg.get('kali',    'host',               fallback='192.168.65.129')
_KALI_USER         = _ssh_cfg.get('kali',    'user',               fallback='kali')
_KALI_PASS         = _ssh_cfg.get('kali',    'password',           fallback='kali')
_KALI_TCP_SCRIPT   = _ssh_cfg.get('kali',    'tcp_flood_script',   fallback='/home/kali/tcp_flood.py')
_KALI_OSPF_SCRIPT  = _ssh_cfg.get('kali',    'ospf_attack_script', fallback='/home/kali/ospf_attack_v2.py')
_HOST_PC_HOST      = _ssh_cfg.get('host_pc', 'host',               fallback='192.168.65.1')
_HOST_PC_USER      = _ssh_cfg.get('host_pc', 'user',               fallback='samha')
_HOST_PC_PASS      = _ssh_cfg.get('host_pc', 'password',           fallback='Netpass0')
_COMBIDS_PATH      = _ssh_cfg.get('host_pc', 'ids_script',         fallback='D:/school_code/Capstone_RuleBasedAI/IDS/CombinedIDS.py')
_PROBLEM2_PATH     = _ssh_cfg.get('ubuntu',  'problem2_script',    fallback='/home/user1/inject_problem/problem2.py')

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

# Telemetry state
_telemetry_active = False
_telemetry_lock = threading.Lock()
_interface_prev = {}

# History buffer for telemetry
from collections import deque
_telemetry_history = deque(maxlen=20)

# Log replay buffer — sent to new clients on connect so page navigation doesn't lose history
_log_buffer = deque(maxlen=200)

# Last known status (replayed on reconnect)
_current_status = {'text': 'idle', 'color': 'secondary'}

# Active prompt (re-emitted to new clients if a thread is waiting for a response)
_pending_prompt = None

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
    entry = {'timestamp': timestamp, 'message': message, 'level': level}
    _log_buffer.append(entry)
    socketio.emit('log', entry)

def update_status(text, color='secondary'):
    global _current_status
    _current_status = {'text': text, 'color': color}
    socketio.emit('status', _current_status)

def emit_devices(devices):
    socketio.emit('devices', {'devices': devices})

# ============== PROMPT HANDLING ==============
def show_prompt(prompt_id, question, prompt_type, choices=None, default=None):
    global _pending_prompt
    event = threading.Event()
    response_events[prompt_id] = event

    _pending_prompt = {
        'id': prompt_id,
        'question': question,
        'type': prompt_type,
        'choices': choices,
        'default': default
    }
    socketio.emit('prompt', _pending_prompt)

    event.wait(timeout=300)

    response = user_responses.pop(prompt_id, None)
    response_events.pop(prompt_id, None)
    _pending_prompt = None
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
        self._last_fix_passed = 0
        self._last_fix_failed = 0

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
            self._last_fix_passed = 0
            self._last_fix_failed = 0
            return
        passed = sum(1 for r in fix_results if r.get('success'))
        failed = len(fix_results) - passed
        self._last_fix_passed = passed
        self._last_fix_failed = failed
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

# ============== TELEMETRY ==============
def _parse_interface_stats(output):
    """
    Parse 'show interfaces' output and return a dict of
    {interface_name: {'in_bytes': int, 'out_bytes': int}}
    """
    results = {}
    current_intf = None
    for line in output.splitlines():
        line = line.strip()
        header = re.match(r'^(\S+)\s+is\s+(up|down|administratively down)', line, re.IGNORECASE)
        if header:
            current_intf = header.group(1)
            results[current_intf] = {'in_bytes': 0, 'out_bytes': 0}
            continue
        if current_intf:
            m_in = re.search(r'(\d+)\s+bytes\s+input', line)
            if m_in:
                results[current_intf]['in_bytes'] = int(m_in.group(1))
            m_out = re.search(r'(\d+)\s+bytes\s+output', line)
            if m_out:
                results[current_intf]['out_bytes'] = int(m_out.group(1))
    return results


def telemetry_stream_thread(gns3_url, device_names):
    global _telemetry_active
    from influxdb import InfluxDBClient
    client = InfluxDBClient(host='127.0.0.1', port=8086, database='telegraf')

    while _telemetry_active:
        try:
            bps_query = '''
                SELECT non_negative_derivative(sum("ifInOctets"), 1s) * 8 AS bps_in,
                       non_negative_derivative(sum("ifOutOctets"), 1s) * 8 AS bps_out,
                       sum("ifInErrors") AS err_in,
                       sum("ifOutErrors") AS err_out
                FROM "interface"
                WHERE time > now() - 120s
                GROUP BY "hostname", time(30s)
                FILL(none)
            '''
            scalar_query = '''
                SELECT last("cpu_5min") AS cpu,
                       last("mem_used") AS mem_used,
                       last("mem_free") AS mem_free,
                       last("uptime") AS uptime
                FROM "snmp"
                WHERE time > now() - 60s
                GROUP BY "hostname"
            '''
            bps_results = client.query(bps_query)
            scalar_results = client.query(scalar_query)

            chart_data = {}

            for (_, tags), points in scalar_results.items():
                hostname = (tags or {}).get('hostname', 'unknown')
                if device_names and hostname not in device_names:
                    continue
                pts = list(points)
                if not pts:
                    continue
                p = pts[-1]
                mem_used = p.get('mem_used') or 0
                mem_free = p.get('mem_free') or 0
                mem_total = mem_used + mem_free
                chart_data[hostname] = {
                    'in_bps': 0.0,
                    'out_bps': 0.0,
                    'err_in': 0,
                    'err_out': 0,
                    'cpu': round(p.get('cpu') or 0, 1),
                    'mem_used': mem_used,
                    'mem_free': mem_free,
                    'mem_pct': round((mem_used / mem_total * 100) if mem_total else 0, 1),
                    'uptime': int(p.get('uptime') or 0),
                }

            for (_, tags), points in bps_results.items():
                hostname = (tags or {}).get('hostname', '')
                if not hostname or hostname not in chart_data:
                    continue
                pts = [p for p in points if p.get('bps_in') is not None]
                if not pts:
                    continue
                p = pts[-1]
                chart_data[hostname]['in_bps'] = round(p.get('bps_in') or 0, 2)
                chart_data[hostname]['out_bps'] = round(p.get('bps_out') or 0, 2)
                chart_data[hostname]['err_in'] = int(p.get('err_in') or 0)
                chart_data[hostname]['err_out'] = int(p.get('err_out') or 0)


            if chart_data:
                socketio.emit('telemetry_update', {
                    'timestamp': datetime.now().strftime("%H:%M:%S"),
                    'data': chart_data
                })
                _telemetry_history.append({'timestamp': datetime.now().strftime("%H:%M:%S"), 'data': chart_data})
        except Exception as e:
            print(f"[DEBUG] telemetry error: {e}")
            import traceback
            traceback.print_exc()
        time.sleep(10)

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
                initial_rule_ids = set(runner_instance.knowledge_base.rules.keys())
                update_status("applying fixes", 'warning')
                runner_instance.apply_fixes(detected_issues)
                runner_instance.print_completion_summary()

                # Emit diagnostic summary with new-rule tracking
                try:
                    final_rule_ids = set(runner_instance.knowledge_base.rules.keys())
                    new_rule_ids = sorted(final_rule_ids - initial_rule_ids)
                    web_rep = runner_instance.reporter
                    socketio.emit('diagnostic_summary', {
                        'fixed': getattr(web_rep, '_last_fix_passed', 0),
                        'failed': getattr(web_rep, '_last_fix_failed', 0),
                        'new_rules': len(new_rule_ids),
                        'new_rule_ids': new_rule_ids,
                    })
                except Exception as e:
                    log_message(f"[DEBUG] Summary emit: {e}", 'dim')

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
                # Emit IE flowchart only when the user explicitly requests traces
                try:
                    serializable_traces = []
                    for t in traces:
                        try:
                            chosen = t.get('chosen_fix') or {}
                            serializable_traces.append({
                                'trace_id': str(t.get('trace_id', '')),
                                'problem': t.get('problem', {}),
                                'reasoning_steps': list(t.get('reasoning_steps', [])),
                                'chosen_fix': {
                                    'rule_id': str(chosen.get('rule_id', '')),
                                    'confidence': float(chosen.get('confidence') or 0),
                                    'tier': int(chosen.get('tier') or 1),
                                    'description': str(chosen.get('description', '')),
                                    'baseline_validated': bool(chosen.get('baseline_validated', False)),
                                } if chosen else None,
                                'alternatives_considered': [
                                    {
                                        'rule_id': str(a.get('rule_id', '')),
                                        'confidence': float(a.get('confidence') or 0),
                                        'tier': int(a.get('tier') or 1),
                                        'rejected_reason': str(a.get('rejected_reason', '')),
                                    }
                                    for a in (t.get('alternatives_considered') or [])[:5]
                                ],
                                'outcome': t.get('outcome', 'pending'),
                            })
                        except Exception:
                            pass
                    socketio.emit('ie_flow', {'traces': serializable_traces})
                except Exception as e:
                    log_message(f"[DEBUG] IE flow: {e}", 'dim')

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
            runner_instance.save_stable_configurations(available_devices)

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

# ============== IDS SECURITY RESPONSE ==============
_IDS_TRIGGER_MAP = {
    'tcp_flood': (
        'ids_tcp_flood',
        'IDS_TCP_001',
        'TCP flood detected by NB model',
        (
            "After examining network statistics, R6's outbound traffic was abnormally high, "
            "exhibiting TCP flood patterns detected by the Naive Bayes model. "
            "The attack source was identified at R6 Fa0/0. "
            "I have shut down that interface until manual intervention can be done."
        )
    ),
    'ospf_attack': (
        'ids_ospf_attack',
        'IDS_OSPF_001',
        'OSPF attack detected by RF model',
        (
            "After examining network statistics, R6's outbound traffic was abnormally high, "
            "with malicious OSPF Hello packets detected at a rate inconsistent with normal routing. "
            "The attack source is coming from R6 Fa0/0. "
            "I have shut down that interface until manual intervention can be done."
        )
    ),
}

def run_ids_response_thread(gns3_url, ids_trigger_type):
    """
    Hardcoded IDS security response: connect to R6, look up the KB rule
    for the detected attack type, and shut FastEthernet0/0.
    """
    global runner_instance, is_running
    try:
        is_running = True
        update_status("IDS response — initializing", 'warning')

        trigger_info = _IDS_TRIGGER_MAP.get(ids_trigger_type)
        if not trigger_info:
            log_message(f"Unknown IDS trigger type: {ids_trigger_type}", 'error')
            update_status("error", 'danger')
            return

        problem_type, rule_id, alert_label, custom_message = trigger_info

        log_message("━" * 60, 'dim')
        log_message(f"  IDS SECURITY RESPONSE", 'phase')
        log_message("━" * 60, 'dim')
        log_message(f"Trigger: {alert_label}", 'warning')
        log_message(f"Rule:    {rule_id} → Shut R6 FastEthernet0/0", 'info')

        runner_instance = runner.DiagnosticRunner(gns3_url=gns3_url)
        runner_instance.reporter = WebReporter(runner_instance.reporter)
        runner_instance.fix_applier.reporter = WebReporter(runner_instance.fix_applier.reporter)

        update_status("connecting to GNS3", 'warning')
        if not runner_instance.connect():
            log_message("Failed to connect to GNS3", 'error')
            update_status("connection failed", 'danger')
            return

        # Only connect to R6 — the target for IDS security shutdowns
        update_status("connecting to R6", 'warning')
        runner_instance.connect_to_devices(['R6'])
        if 'R6' not in runner_instance.connections:
            log_message("Could not establish telnet connection to R6", 'error')
            update_status("error", 'danger')
            return

        log_message("Connected to R6. Applying security fix...", 'success')

        # Build a synthetic problem that matches the KB rule
        synthetic_problem = {
            'type': problem_type,
            'category': 'ids_security',
            'device': 'R6',
            'interface': 'FastEthernet0/0',
            'symptoms': ['attack_detected'],
            'rule_id': rule_id,
        }

        detected_issues = {
            'ids_security': {'R6': [synthetic_problem]},
            'interfaces': {},
            'eigrp': {},
            'ospf': {},
        }

        update_status("applying IDS fix", 'warning')
        # Auto-approve: IDS responses are automated
        runner_instance.fix_applier.apply_all_fixes(
            detected_issues,
            runner_instance.connections,
            auto_approve_all=True
        )
        runner_instance.print_completion_summary()

        # Emit diagnostic summary with IDS-specific reasoning message
        try:
            web_rep = runner_instance.reporter
            socketio.emit('diagnostic_summary', {
                'fixed': getattr(web_rep, '_last_fix_passed', 0),
                'failed': getattr(web_rep, '_last_fix_failed', 0),
                'new_rules': 0,
                'new_rule_ids': [],
                'custom_message': custom_message,
            })
        except Exception:
            pass

        log_message("IDS security response complete.", 'success')
        update_status("completed", 'success')

    except Exception as e:
        log_message(f"IDS response error: {str(e)}", 'error')
        update_status("error", 'danger')
        import traceback
        log_message(traceback.format_exc(), 'error')
    finally:
        if runner_instance:
            runner_instance.cleanup_all_connections()
        runner_instance = None
        update_status("idle", 'secondary')
        is_running = False


# ============== DEMO THREADS ==============

def run_inject_misconfig_thread():
    global is_running
    try:
        is_running = True
        update_status("injecting misconfigurations", 'warning')
        log_message("━" * 60, 'dim')
        log_message("  DEMO: INJECT EIGRP + OSPF MISCONFIGURATIONS", 'phase')
        log_message("━" * 60, 'dim')
        log_message("Running problem2.py — injecting faults on R1–R6...", 'info')

        proc = subprocess.Popen(
            [sys.executable, _PROBLEM2_PATH],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                log_message(line, 'dim')
        proc.wait()

        if proc.returncode == 0:
            log_message("✓ Misconfigurations injected successfully!", 'success')
            log_message("Click 'Run Diagnostics' to detect and fix the issues.", 'info')
        else:
            log_message(f"problem2.py exited with code {proc.returncode}", 'error')

    except Exception as e:
        log_message(f"Inject error: {str(e)}", 'error')
        update_status("error", 'danger')
    finally:
        is_running = False
        update_status("idle", 'secondary')


def run_attack_thread(attack_type):
    global is_running
    kali_client = None
    host_client = None
    ids_channel = None

    kali_script = _KALI_TCP_SCRIPT if attack_type == 'tcp_flood' else _KALI_OSPF_SCRIPT
    script_name = kali_script.split('/')[-1]
    demo_label = 'TCP SYN FLOOD ATTACK' if attack_type == 'tcp_flood' else 'OSPF HELLO FLOOD ATTACK'

    startup_timeout_sec = 20
    capture_window_sec = 15

    kill_combinedids_cmd = (
        "powershell -NoProfile -Command "
        "\"Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*CombinedIDS.py*' } "
        "| ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }\""
    )

    try:
        is_running = True
        update_status(f"demo: {demo_label.lower()}", 'warning')
        log_message("━" * 60, 'dim')
        log_message(f"  DEMO: {demo_label}", 'phase')
        log_message("━" * 60, 'dim')

        log_message(f"[1/3] Connecting to Kali VM ({_KALI_HOST})...", 'info')
        kali_client = paramiko.SSHClient()
        kali_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kali_client.connect(_KALI_HOST, username=_KALI_USER, password=_KALI_PASS, timeout=10)
        log_message("Connected to Kali.", 'success')

        kali_cmd = f"echo '{_KALI_PASS}' | sudo -S python3 {kali_script} 2>&1"
        log_message(f"Starting: sudo python3 {kali_script}", 'info')
        kali_client.exec_command(kali_cmd)
        time.sleep(1)
        log_message("Attack script launched.", 'success')

        log_message(f"[2/3] Connecting to Host PC ({_HOST_PC_HOST})...", 'info')
        host_client = paramiko.SSHClient()
        host_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        host_client.connect(_HOST_PC_HOST, username=_HOST_PC_USER, password=_HOST_PC_PASS, timeout=10)
        log_message("Connected to Host PC.", 'success')

        try:
            host_client.exec_command(kill_combinedids_cmd)
            time.sleep(0.5)
            log_message("Killed any existing CombinedIDS.py instances.", 'info')
        except Exception:
            pass

        ids_cmd = f'python3 "{_COMBIDS_PATH}"'
        log_message(f"Starting CombinedIDS.py ({capture_window_sec} seconds after startup)...", 'info')
        ids_channel = host_client.get_transport().open_session()
        ids_channel.get_pty()
        ids_channel.exec_command(ids_cmd)

        _ansi_re = re.compile(
            r'(\x9b|\x1b\[)[0-?]*[ -\/]*[@-~]'
            r'|\x1b[()][AB012]'
            r'|\x1b[NOPQRST\\X^_].*?[\x07\x1b]'
            r'|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]'
        )

        _line_buf = []

        def _read_ids_lines():
            saw_ready_line = False
            while ids_channel and ids_channel.recv_ready():
                chunk = ids_channel.recv(65536).decode('utf-8', errors='replace')
                _line_buf.append(chunk)
            if not _line_buf:
                return saw_ready_line
            raw = ''.join(_line_buf)
            _line_buf.clear()
            for line in raw.splitlines():
                line = _ansi_re.sub('', line).strip()
                if not line:
                    continue
                if line.startswith(']0;') or line.lower().startswith('title '):
                    continue
                log_message(f"[IDS] {line}", 'ids')
                if 'hybrid ids active' in line.lower():
                    saw_ready_line = True
            return saw_ready_line

        ready = False
        startup_deadline = time.time() + startup_timeout_sec
        while time.time() < startup_deadline:
            if _read_ids_lines():
                ready = True
                break
            if ids_channel.exit_status_ready():
                log_message("CombinedIDS.py exited early.", 'warning')
                break
            time.sleep(0.2)

        if ready:
            log_message("CombinedIDS.py is active; starting capture window.", 'success')
        else:
            log_message("CombinedIDS.py did not report readiness before capture window; continuing anyway.", 'warning')

        capture_deadline = time.time() + capture_window_sec
        while time.time() < capture_deadline:
            _read_ids_lines()
            if ids_channel.exit_status_ready():
                log_message("CombinedIDS.py exited before capture window ended.", 'warning')
                break
            time.sleep(0.2)

        log_message("[3/3] Terminating CombinedIDS.py...", 'warning')
        try:
            ids_channel.send('\x03')
            time.sleep(1.0)
            for _ in range(10):
                _read_ids_lines()
                if ids_channel.exit_status_ready():
                    break
                time.sleep(0.2)
        except Exception:
            pass

        try:
            if ids_channel:
                ids_channel.close()
        except Exception:
            pass

        try:
            host_client.exec_command(kill_combinedids_cmd)
        except Exception:
            pass

        log_message(f"Stopping {script_name} on Kali...", 'warning')
        try:
            kali_client.exec_command(
                f"echo '{_KALI_PASS}' | sudo -S pkill -f {kali_script} 2>/dev/null || true"
            )
        except Exception:
            pass

        time.sleep(0.5)
        log_message("━" * 60, 'dim')
        log_message("Demo complete. Check above for IDS detection output.", 'success')
        log_message("You can now run diagnostics to apply the fix.", 'info')

    except Exception as e:
        log_message(f"Demo error: {str(e)}", 'error')
        update_status("error", 'danger')
        import traceback
        log_message(traceback.format_exc(), 'error')

    finally:
        try:
            if host_client:
                host_client.exec_command(kill_combinedids_cmd)
        except Exception:
            pass

        try:
            if kali_client:
                _, stdout, _ = kali_client.exec_command(
                    f"echo '{_KALI_PASS}' | sudo -S pkill -f {script_name} 2>/dev/null; sleep 2; echo DONE"
                )
                stdout.read()
        except Exception:
            pass

        for c in (kali_client, host_client):
            try:
                if c:
                    c.close()
            except Exception:
                pass

        is_running = False
        update_status("idle", 'secondary')


# ============== FLASK ROUTES ==============
@app.route('/')
def index():
    return render_template('index.html', initial_view='diagnostics')

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
    ids_trigger = data.get('ids_trigger')  # e.g. 'tcp_flood' or 'ospf_attack'

    if ids_trigger:
        execution_thread = threading.Thread(
            target=run_ids_response_thread,
            args=(gns3_url, ids_trigger),
            daemon=True
        )
    else:
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

@app.route('/api/demo/inject_misconfig', methods=['POST'])
def api_demo_inject_misconfig():
    global execution_thread
    if is_running:
        return jsonify({'error': 'Already running'}), 400
    execution_thread = threading.Thread(target=run_inject_misconfig_thread, daemon=True)
    execution_thread.start()
    return jsonify({'status': 'started'})

@app.route('/api/demo/attack', methods=['POST'])
def api_demo_attack():
    global execution_thread
    if is_running:
        return jsonify({'error': 'Already running'}), 400
    attack_type = (request.json or {}).get('attack_type', 'tcp_flood')
    execution_thread = threading.Thread(
        target=run_attack_thread, args=(attack_type,), daemon=True
    )
    execution_thread.start()
    return jsonify({'status': 'started'})

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

# ============== TELEMETRY ROUTES ==============
@app.route('/telemetry')
def telemetry_page():
    return render_template('index.html', initial_view='telemetry')


@app.route('/telemetry.html')
def telemetry_page_legacy():
    return redirect('/telemetry', code=302)

@app.route('/api/telemetry/start', methods=['POST'])
def api_telemetry_start():
    global _telemetry_active
    with _telemetry_lock:
        if _telemetry_active:
            return jsonify({'error': 'Already running'}), 400
        _telemetry_active = True

    data = request.json or {}
    gns3_url = data.get('gns3_url', 'http://192.168.231.1:3080')
    devices = data.get('devices', [])

    threading.Thread(
        target=telemetry_stream_thread,
        args=(gns3_url, devices),
        daemon=True
    ).start()

    return jsonify({'status': 'started'})

@app.route('/api/telemetry/stop', methods=['POST'])
def api_telemetry_stop():
    global _telemetry_active
    _telemetry_active = False
    return jsonify({'status': 'stopped'})

@app.route('/api/telemetry/status')
def api_telemetry_status():
    return jsonify({'active': _telemetry_active})

@app.route('/api/telemetry/history')
def api_telemetry_history():
    return jsonify(list(_telemetry_history))

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

# ============== IDS ALERT ROUTE ==============
_ids_alerts = []

_ids_last_seen = {}

@app.route('/api/ids/alert', methods=['POST'])
def api_ids_alert():
    alert = request.json or {}
    alert.setdefault('timestamp', datetime.now().isoformat())
    
    key = alert.get('details', '')
    now = time.time()
    if now - _ids_last_seen.get(key, 0) < 5:
        return jsonify({'status': 'suppressed'})
    _ids_last_seen[key] = now
    
    _ids_alerts.append(alert)
    socketio.emit('ids_alert', alert)
    return jsonify({'status': 'received'})

@app.route('/api/ids/alerts', methods=['GET'])
def api_ids_alerts():
    return jsonify(_ids_alerts)

# ============== SYSLOG WATCHER ==============
_syslog_ospf_pattern = re.compile(
    r'(OSPF|ospf|adjacency|neighbor|flood|LSA|CONFIG_I|SYS-5-CONFIG|LINEPROTO|LINK-3-UPDOWN)',
    re.IGNORECASE
)

def syslog_watcher_thread():
    log_path = '/var/log/gns3-routers.log'
    import subprocess
    _ip_pattern = re.compile(r'(\d+\.\d+\.\d+\.\d+)')
    _router_map = {
        '192.168.231.101': 'R1', '192.168.231.102': 'R2',
        '192.168.231.103': 'R3', '192.168.231.104': 'R4',
        '192.168.231.105': 'R5', '192.168.231.106': 'R6',
        '192.168.231.107': 'R7'
    }
    _eigrp_routers = {'R1', 'R2', 'R3', 'R7'}
    _ospf_routers = {'R4', 'R5', 'R6', 'R7'}

    def _parse_alert(line, device):
        msg = re.sub(r'^.*?%', '%', line).strip()

        if re.search(r'DUAL.*NBRCHANGE|EIGRP.*[Nn]eighbor', msg):
            down = bool(re.search(r'down|fail', msg, re.IGNORECASE))
            nbr = re.search(r'Neighbor (\S+)', msg)
            intf = re.search(r'\((\S+)\)', msg)
            nbr_ip = nbr.group(1) if nbr else '?'
            intf_name = intf.group(1) if intf else '?'
            protocol = 'EIGRP'
            severity = 'high' if down else 'medium'
            details = f"{device} {intf_name}: EIGRP neighbor {nbr_ip} {'DOWN' if down else 'UP'}"
            return protocol, 'neighbor_change', severity, details

        if re.search(r'OSPF.*[Nn]eighbor|OSPF.*[Aa]djacency', msg):
            down = bool(re.search(r'down|fail|dead', msg, re.IGNORECASE))
            nbr = re.search(r'[Nn]eighbor (\S+)', msg)
            intf = re.search(r'[Ii]nterface (\S+)|[Oo]n (\S+)', msg)
            nbr_ip = nbr.group(1) if nbr else '?'
            intf_name = (intf.group(1) or intf.group(2)) if intf else '?'
            severity = 'high' if down else 'medium'
            details = f"{device} {intf_name}: OSPF neighbor {nbr_ip} {'DOWN' if down else 'UP'}"
            return 'OSPF', 'neighbor_change', severity, details

        if re.search(r'LINEPROTO.*UPDOWN|LINK.*UPDOWN', msg):
            down = bool(re.search(r'down', msg, re.IGNORECASE))
            intf = re.search(r'[Ii]nterface (\S+),', msg)
            intf_name = intf.group(1) if intf else '?'
            protocol = 'EIGRP' if device in _eigrp_routers else 'OSPF' if device in _ospf_routers else 'RP'
            severity = 'high' if down else 'low'
            details = f"{device} {intf_name}: interface {'DOWN' if down else 'UP'}"
            return protocol, 'interface_event', severity, details

        if re.search(r'CONFIG_I', msg):
            details = f"{device}: configuration changed via console"
            return 'SYS', 'config_change', 'low', details

        details = f"{device}: {msg[:80]}"
        return 'SYS', 'sys_event', 'low', details

    try:
        proc = subprocess.Popen(
            ['tail', '-F', log_path],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
        )
        for line in proc.stdout:
            line = line.strip()
            if not line or not _syslog_ospf_pattern.search(line):
                continue
            ip_match = _ip_pattern.search(line)
            source_ip = ip_match.group(1) if ip_match else 'unknown'
            device = _router_map.get(source_ip, source_ip)
            protocol, attack_type, severity, details = _parse_alert(line, device)
            alert = {
                'attack_type': attack_type,
                'protocol': protocol,
                'source_ip': source_ip,
                'target_device': device,
                'severity': severity,
                'details': details,
                'timestamp': datetime.now().isoformat()
            }
            _ids_alerts.append(alert)
            socketio.emit('ids_alert', alert)
    except Exception:
        pass

threading.Thread(target=syslog_watcher_thread, daemon=True).start()

# ============== SOCKETIO EVENTS ==============
@socketio.on('connect')
def handle_connect():
    # Replay buffered log so page navigation doesn't lose history
    for entry in list(_log_buffer):
        emit('log', entry)
    # Restore current status badge
    emit('status', _current_status)
    # Re-emit any prompt the backend thread is waiting on
    if _pending_prompt:
        emit('prompt', _pending_prompt)
    # Replay recent IDS alerts (telemetry table repopulates after navigation)
    for alert in list(_ids_alerts)[-30:]:
        emit('ids_alert', alert)

@socketio.on('disconnect')
def handle_disconnect():
    log_message("Client disconnected", 'info')

# ============== ENTRY POINT ==============
def _free_port(port):
    import platform
    import subprocess
    import time
    try:
        if platform.system().lower().startswith('win'):
            result = subprocess.run(['netstat', '-ano'], capture_output=True, text=True, check=False)
            pids = set()
            port_suffix = f':{port}'
            for line in result.stdout.splitlines():
                if port_suffix not in line:
                    continue
                parts = line.split()
                if len(parts) < 5:
                    continue
                local_addr = parts[1]
                state = parts[3].upper() if len(parts) > 3 else ''
                if local_addr.endswith(port_suffix) and state in {'LISTENING', 'ESTABLISHED', 'TIME_WAIT'}:
                    pids.add(parts[-1])
            for pid in pids:
                subprocess.run(['taskkill', '/PID', pid, '/F'], capture_output=True, check=False)
        else:
            subprocess.run(['fuser', '-k', f'{port}/tcp'], capture_output=True, check=False)
    except Exception:
        pass
    time.sleep(1)

if __name__ == '__main__':
    _free_port(5000)
    import socket
    lan_ip = '127.0.0.1'
    try:
        lan_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        pass
    print("=" * 60)
    print("  Network Diagnostic Tool - Web Interface")
    print("=" * 60)
    print(f"  Open http://127.0.0.1:5000 to access locally")
    print(f"  Open http://{lan_ip}:5000 to access from host PC")
    print("=" * 60)
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)