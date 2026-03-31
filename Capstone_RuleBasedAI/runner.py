import warnings
import time
warnings.filterwarnings('ignore')

import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests.auth import HTTPBasicAuth
import sys
import atexit
from datetime import datetime
from rich.prompt import Confirm, Prompt

from core.config_manager import ConfigManager
from core.knowledge_base import KnowledgeBase
from core.inference_engine import InferenceEngine
from core.rule_miner import RuleMiner
from detection.problem_detector import ProblemDetector
from resolution.fix_applier import FixApplier
from utils.reporter import Reporter
from utils.telnet_utils import connect_device, close_device, get_running_config

_GNS3_SKIP_NODE_TYPES = frozenset({
    "vpcs",
    "ethernet_switch",
    "ethernet_hub",
})


def include_gns3_node(node):
    if node.get("status") != "started":
        return False
    name = (node.get("name") or "").lower()
    if name.startswith("switch"):
        return False
    if name.startswith("pc"):
        return False
    nt = (node.get("node_type") or "").lower()
    if nt in _GNS3_SKIP_NODE_TYPES:
        return False
    return True


class DiagnosticRunner:
    def __init__(self, gns3_url="http://localhost:3080", username="admin",
                 password="qrWaprDfbrbUaYw8eMZTRz6cXRfV96PltLIT0gzTIMo7u5vksgVCIjz1iOSIbelS"):
        self.gns3_url = gns3_url.rstrip('/')
        self.api_base = f"{self.gns3_url}/v2"
        self.auth = HTTPBasicAuth(username, password) if username else None

        self.config_manager = ConfigManager()
        self.knowledge_base = KnowledgeBase(config_manager=self.config_manager)
        self.inference_engine = InferenceEngine(self.knowledge_base)
        self.rule_miner = RuleMiner(self.knowledge_base)
        self.problem_detector = ProblemDetector(self.config_manager)
        self.reporter = Reporter()
        self.fix_applier = FixApplier(
            self.config_manager,
            self.reporter,
            self.knowledge_base,
            self.inference_engine
        )

        self.nodes = {}
        self.connections = {}
        self.run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def connect(self):
        try:
            response = requests.get(f"{self.api_base}/version", auth=self.auth, timeout=3)
            if response.status_code == 401:
                self.auth = None
                response = requests.get(f"{self.api_base}/version", timeout=3)
            if response.status_code != 200:
                self.reporter.print_error(f"API Error: Status Code {response.status_code}")
                return False

            response = requests.get(f"{self.api_base}/projects", auth=self.auth, timeout=5)
            projects = response.json()
            for project in projects:
                if project['status'] == 'opened':
                    response = requests.get(
                        f"{self.api_base}/projects/{project['project_id']}/nodes",
                        auth=self.auth, timeout=5
                    )
                    nodes = response.json()
                    for node in nodes:
                        if include_gns3_node(node):
                            self.nodes[node['name']] = node.get('console')
                    if not self.nodes:
                        self.reporter.print_warning("No running routers found")
                        return False
                    self.reporter.print_success(f"Found {len(self.nodes)} running router(s).")
                    return True
            self.reporter.print_error("No open project found.")
            return False
        except requests.exceptions.ConnectionError:
            self.reporter.print_error(f"Could not reach GNS3 at {self.gns3_url}")
            return False
        except Exception as e:
            self.reporter.print_error(f"Connection Error: {str(e)[:100]}")
            return False

    def connect_to_devices(self, device_names):
        if not device_names:
            return self.connections

        def connect_one(device_name):
            console_port = self.nodes.get(device_name)
            if not console_port:
                return device_name, None
            tn = connect_device(console_port)
            return device_name, tn if tn else None

        if len(device_names) <= 1:
            for device_name in device_names:
                name, tn = connect_one(device_name)
                if tn:
                    self.connections[name] = tn
            return self.connections

        max_workers = min(len(device_names), 8)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(connect_one, dn) for dn in device_names]
            for future in as_completed(futures):
                device_name, tn = future.result()
                if tn:
                    self.connections[device_name] = tn
        return self.connections

    def cleanup_all_connections(self):
        for tn in self.connections.values():
            close_device(tn)
        self.connections.clear()

    def run_diagnostics(self, device_names):
        self.reporter.print_phase_header("PHASE 1: DETECTING ISSUES")
        if not self.connections:
            self.connect_to_devices(device_names)

        with self.reporter.create_progress_bar("Scanning devices...", len(device_names)) as progress:
            task = progress.add_task("[cyan]Scanning...", total=len(device_names))
            detected_issues = self.problem_detector.scan_all_devices(
                self.connections,
                scan_options={
                    'check_interfaces': True,
                    'check_eigrp': True,
                    'check_ospf': True
                },
                parallel=True
            )
            progress.update(task, completed=len(device_names))

        return detected_issues

    def apply_fixes(self, detected_issues):
        if _detected_problem_count(detected_issues) == 0:
            return []
        self.reporter.print_phase_header("PHASE 2: APPLYING FIXES")
        fix_mode = Prompt.ask(
            "\n[cyan]Apply fixes:[/cyan]",
            choices=["all", "one-by-one"],
            default="one-by-one"
        )
        auto_approve_all = (fix_mode == "all")
        fix_results = self.fix_applier.apply_all_fixes(
            detected_issues,
            self.connections,
            auto_approve_all
        )
        return fix_results

    def print_completion_summary(self):
        fix_results = self.fix_applier.get_fix_results()
        self.reporter.print_fix_completion_summary(fix_results)
        self.reporter.save_run_history(fix_results, self.run_timestamp)

        for result in fix_results:
            problem = result.get('problem', {})
            problem['device'] = result['device']
            problem_type = problem.get('type', 'unknown')
            category = problem.get('category', 'unknown')

            rule_id = result.get('rule_id') or \
                      self.knowledge_base.get_rule_id_for_problem(problem_type, category)
            solution = {
                'commands': result['commands'],
                'verification': result['verification'],
                'rule_id': rule_id,
                'fix_type': problem.get('fix_type', ''),
                'confidence': result.get('ie_confidence', result.get('confidence', 0.8)),
            }
            success = result.get('success', True)
            self.knowledge_base.add_problem_solution_pair(problem, solution, success=success)

            if rule_id:
                self.knowledge_base.update_rule_confidence(rule_id, success)
                print(f"[Learning] Rule {rule_id} {'succeeded' if success else 'failed'} "
                      f"for {problem_type} on {result['device']}")
            else:
                print(f"[Learning] No matching rule for {problem_type} ({category}) "
                      f"on {result['device']}")

        self._run_post_session_learning()
        self.knowledge_base.flush_knowledge()

    def _run_post_session_learning(self):
        """After each session: mine new rules and optionally show IE traces."""
        history_len = len(self.knowledge_base.problem_history)
        if history_len >= RuleMiner.MIN_OCCURRENCES:
            print(f"\n[RuleMiner] Running post-session mining "
                  f"({history_len} history entries)...")
            added = self.rule_miner.mine_and_add_to_kb()
            if added:
                print(f"[RuleMiner] {added} new rule(s) added to KB from this session's data")
        else:
            print(f"[RuleMiner] Skipping mining — need {RuleMiner.MIN_OCCURRENCES}+ history entries "
                  f"(have {history_len})")

    def show_explanation_traces(self):
        traces = self.inference_engine.get_explanation_traces()
        if not traces:
            print("No explanation traces recorded this session.")
            return
        print(f"\nExplanation traces from this session ({len(traces)} total):")
        for trace in traces:
            self.inference_engine.print_trace(trace)

    def show_kb_statistics(self):
        self.reporter.print_phase_header("KNOWLEDGE BASE STATISTICS")
        self.knowledge_base.print_statistics()

    def save_stable_configurations(self, device_names):
        self.reporter.print_phase_header("SAVING STABLE CONFIGURATIONS")
        device_configs = {}

        with self.reporter.create_progress_bar("Saving configurations...", len(device_names)) as progress:
            task = progress.add_task("[cyan]Saving...", total=len(device_names))
            for device_name in device_names:
                console_port = self.nodes.get(device_name)
                if not console_port:
                    progress.advance(task)
                    continue
                tn = self.connections.get(device_name) or connect_device(console_port)
                if not tn:
                    progress.advance(task)
                    continue
                config = get_running_config(tn)
                if config:
                    device_configs[device_name] = config
                if device_name not in self.connections:
                    close_device(tn)
                progress.advance(task)

        if device_configs:
            saved_file = self.config_manager.save_baseline(device_configs, tag="stable")
            if saved_file:
                self.reporter.print_success(f"✓ Saved {len(device_configs)} stable configuration(s)")
                return True
        else:
            self.reporter.print_warning("No configurations were saved")
        return False

    def restore_stable_configurations(self, device_names=None):
        import re as regex_module

        self.reporter.print_phase_header("RESTORING STABLE CONFIGURATIONS")
        config_files = list(self.config_manager.config_dir.glob("config_stable*.txt"))
        if not config_files:
            self.reporter.print_error("No stable configuration file found!")
            return False

        config_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        latest_config = config_files[0]

        with open(latest_config, 'r') as f:
            content = f.read()

        devices = regex_module.split(r'DEVICE:\s+(\w+)', content)
        device_configs = {}
        for i in range(1, len(devices), 2):
            device_configs[devices[i]] = devices[i + 1]

        devices_to_restore = (
            list(device_configs.keys()) if device_names is None
            else [d for d in device_names if d in device_configs]
        )

        if not devices_to_restore:
            self.reporter.print_error("No matching devices found in baseline!")
            return False

        self.reporter.print_info(f"Using baseline: {latest_config.name}")
        self.reporter.print_info(f"Will restore: {', '.join(devices_to_restore)}")

        if not Confirm.ask(f"Restore {len(devices_to_restore)} device(s)?"):
            return False

        def restore_single_device(device_name, config):
            try:
                console_port = self.nodes.get(device_name)
                if not console_port:
                    return device_name, False, "No console port"
                tn = self.connections.get(device_name) or connect_device(console_port)
                if not tn:
                    return device_name, False, "Connection failed"

                for cmd in (b'\x03\r\n', b'end\r\n', b'configure terminal\r\n'):
                    tn.write(cmd)
                    time.sleep(0.2)
                    tn.read_very_eager()

                is_eigrp = device_name.upper() in ['R1', 'R2', 'R3']
                is_ospf = device_name.upper() in ['R4', 'R5', 'R6']
                if is_eigrp:
                    tn.write(b'no router eigrp 1\r\n')
                    time.sleep(0.3)
                    tn.read_very_eager()
                if is_ospf:
                    tn.write(b'no router ospf 10\r\n')
                    time.sleep(0.3)
                    tn.read_very_eager()

                for intf in regex_module.findall(r'interface\s+(\S+)', config, regex_module.IGNORECASE):
                    tn.write(f'default interface {intf}\r\n'.encode('ascii'))
                    time.sleep(0.2)
                    tn.read_very_eager()

                tn.write(b'end\r\n')
                time.sleep(0.2)
                tn.read_very_eager()

                interface_states = {}
                current_interface = None
                for line in config.split('\n'):
                    line = line.strip()
                    if not line or line.startswith('!'):
                        continue
                    if line.lower().startswith('interface '):
                        parts = line.split()
                        current_interface = parts[1] if len(parts) > 1 else None
                        if current_interface:
                            interface_states[current_interface] = False
                    elif current_interface and line.lower() == 'shutdown':
                        interface_states[current_interface] = True
                    elif line.lower().startswith(('router ', 'ip classless', 'line ', 'end', '!')):
                        current_interface = None

                tn.write(b'configure terminal\r\n')
                time.sleep(0.2)
                tn.read_very_eager()

                skip = ('version', 'hostname', 'service ', 'enable ', 'line ', 'boot-')
                for line in config.split('\n'):
                    line = line.strip()
                    if not line or line.startswith('!') or line.startswith('Building') or \
                            line.startswith('Current'):
                        continue
                    if any(s in line.lower() for s in skip):
                        continue
                    if line.lower() == 'shutdown':
                        continue
                    tn.write(line.encode('ascii') + b'\r\n')
                    time.sleep(0.05)
                    tn.read_very_eager()

                tn.write(b'end\r\n')
                time.sleep(0.2)
                tn.read_very_eager()
                tn.write(b'configure terminal\r\n')
                time.sleep(0.2)
                tn.read_very_eager()

                for intf, should_shutdown in interface_states.items():
                    tn.write(f'interface {intf}\r\n'.encode('ascii'))
                    time.sleep(0.1)
                    tn.read_very_eager()
                    tn.write(b'shutdown\r\n' if should_shutdown else b'no shutdown\r\n')
                    time.sleep(0.1)
                    tn.read_very_eager()

                tn.write(b'end\r\n')
                time.sleep(0.3)
                tn.read_very_eager()
                tn.write(b'write memory\r\n')
                time.sleep(1)
                tn.read_very_eager()

                if device_name not in self.connections:
                    close_device(tn)
                return device_name, True, "Success"
            except Exception as e:
                return device_name, False, str(e)

        success_count = 0
        failed_devices = []

        self.reporter.print_info(f"Starting parallel restore of {len(devices_to_restore)} devices...")
        with self.reporter.create_progress_bar("Restoring...", len(devices_to_restore)) as progress:
            task = progress.add_task("[cyan]Restoring...", total=len(devices_to_restore))
            max_workers = min(8, len(devices_to_restore))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_device = {
                    executor.submit(restore_single_device, d, device_configs.get(d, '')): d
                    for d in devices_to_restore
                }
                for future in concurrent.futures.as_completed(future_to_device):
                    device_name = future_to_device[future]
                    try:
                        device, success, message = future.result(timeout=30)
                        if success:
                            progress.update(task, advance=1, description=f"[green]✓ {device_name}")
                            success_count += 1
                        else:
                            progress.update(task, advance=1, description=f"[red]✗ {device_name}")
                            failed_devices.append((device_name, message))
                    except concurrent.futures.TimeoutError:
                        progress.update(task, advance=1, description=f"[red]⏰ {device_name}")
                        failed_devices.append((device_name, "Timeout"))
                    except Exception as e:
                        progress.update(task, advance=1, description=f"[red]✗ {device_name}")
                        failed_devices.append((device_name, str(e)))

        if success_count == len(devices_to_restore):
            self.reporter.print_success(f"✓ All {success_count} devices restored successfully!")
        elif success_count > 0:
            self.reporter.print_warning(f"✓ {success_count}/{len(devices_to_restore)} devices restored")
            for device, error in failed_devices:
                self.reporter.print_error(f"  {device}: {error[:100]}")
        else:
            self.reporter.print_error("✗ No devices were restored successfully")

        return success_count > 0


def _detected_problem_count(detected_issues):
    n = 0
    for key in ('interfaces', 'eigrp', 'ospf'):
        for problems in (detected_issues.get(key) or {}).values():
            if isinstance(problems, list):
                n += len(problems)
    return n


def main():
    runner = DiagnosticRunner()
    atexit.register(runner.cleanup_all_connections)

    runner.reporter.print_info("Network Diagnostic Tool")
    stats = runner.knowledge_base.get_statistics()
    runner.reporter.print_info(
        f"Knowledge Base: {stats['total_rules']} rules, "
        f"{stats['total_problems_logged']} problems logged, "
        f"{stats['overall_success_rate']}% success rate"
    )

    if not runner.connect():
        sys.exit(1)

    available_devices = list(runner.nodes.keys())
    device_map = {n.lower(): n for n in available_devices}
    runner.reporter.print_info(f"\nAvailable: {', '.join(available_devices)}")

    user_input = input("Enter devices (e.g. 'r1, r2') or press Enter for all: ").strip()
    if not user_input or user_input.lower() == 'all':
        final_target_list = available_devices
    else:
        final_target_list = [
            device_map[r.strip().lower()]
            for r in user_input.split(',')
            if r.strip().lower() in device_map
        ]

    if not final_target_list:
        runner.reporter.print_error("No valid devices selected. Exiting.")
        sys.exit(1)

    detected_issues = runner.run_diagnostics(final_target_list)
    runner.reporter.print_scan_summary(detected_issues)
    has_issues = _detected_problem_count(detected_issues) > 0

    if has_issues:
        if Confirm.ask("\nProceed to fix menu?"):
            runner.apply_fixes(detected_issues)
            runner.print_completion_summary()
    else:
        runner.reporter.save_run_history([], runner.run_timestamp)

    print("\n" + "=" * 60)
    if Confirm.ask("View Knowledge Base statistics?", default=False):
        runner.show_kb_statistics()

    print("\n" + "=" * 60)
    if Confirm.ask("View IE explanation traces?", default=False):
        runner.show_explanation_traces()

    print("\n" + "=" * 60)
    if Confirm.ask("Revert configs to last stable version?", default=False):
        revert_mode = Prompt.ask(
            "[cyan]Revert:[/cyan]", choices=["all", "select"], default="all"
        )
        if revert_mode == "all":
            runner.restore_stable_configurations(final_target_list)
        else:
            device_input = input("Enter devices to revert (e.g. 'R1, R2, R4'): ").strip()
            if device_input:
                dmap = {n.lower(): n for n in final_target_list}
                revert_devices = [
                    dmap[r.strip().lower()]
                    for r in device_input.split(',')
                    if r.strip().lower() in dmap
                ]
                if revert_devices:
                    runner.restore_stable_configurations(revert_devices)

    print("\n" + "=" * 60)
    if Confirm.ask("Save stable configurations of all routers now?"):
        runner.save_stable_configurations(final_target_list)

    runner.reporter.print_success("\nScript completed successfully!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[bold red]Interrupted[/bold red]")
        sys.exit(0)