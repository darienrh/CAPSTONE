import time
from typing import Dict, List, Optional
from rich.prompt import Confirm
from utils.telnet_utils import apply_config_commands, send_command
from detection.interface_tree import fix_interface_shutdown, fix_interface_ip, verify_interface_status
from detection.eigrp_tree import get_eigrp_fix_commands, apply_eigrp_fixes, verify_eigrp_neighbors
from detection.ospf_tree import get_ospf_fix_commands, apply_ospf_fixes, verify_ospf_neighbors


class FixApplier:
    def __init__(self, config_manager=None, reporter=None, knowledge_base=None,
                 inference_engine=None):
        self.config_manager = config_manager
        self.reporter = reporter
        self.knowledge_base = knowledge_base
        self.inference_engine = inference_engine
        self.fix_results = []

    # ── IE-driven fix selection ──────────────────────────────────────────────

    def _ie_select_fix(self, problem: Dict) -> Optional[Dict]:
        """
        Ask the IE to select and sequence the best fix for this problem.
        Falls back to decision-tree commands if IE returns nothing.
        """
        if self.inference_engine:
            return self.inference_engine.select_fix_for_problem(problem)
        return None

    def _get_commands_for_problem(self, problem: Dict, device_name: str) -> List[str]:
        """
        IE selects the fix; if it provides pre-formatted commands use them,
        otherwise fall back to the existing decision-tree helpers.
        """
        if device_name and not problem.get('device'):
            problem['device'] = device_name
        ie_fix = self._ie_select_fix(problem)
        if ie_fix and ie_fix.get('commands'):
            cmds = ie_fix['commands']
            if not any('{' in c for c in cmds):
                problem['_ie_rule_id'] = ie_fix.get('rule_id', '')
                problem['_ie_trace_id'] = ie_fix.get('trace_id', '')
                problem['_ie_confidence'] = ie_fix.get('confidence', 0.8)
                return cmds

        category = problem.get('category', '')
        issue_type = problem.get('type', '')
        if category == 'interface':
            return []
        elif category == 'eigrp':
            return get_eigrp_fix_commands(issue_type, problem, device_name)
        elif category == 'ospf':
            return get_ospf_fix_commands(issue_type, problem, device_name)
        return []

    # ── Result recording ─────────────────────────────────────────────────────

    def _record_result(self, device_name: str, problem: Dict, commands,
                       verification, success: bool):
        result = {
            'device': device_name,
            'commands': commands if isinstance(commands, str) else '\n'.join(commands),
            'verification': verification,
            'success': success,
            'problem': problem,
            'rule_id': problem.get('_ie_rule_id') or problem.get('rule_id', ''),
            'trace_id': problem.get('_ie_trace_id', ''),
            'ie_confidence': problem.get('_ie_confidence', 0.8),
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        }
        rule_id = result['rule_id']
        if self.knowledge_base and rule_id:
            self.knowledge_base.update_rule_confidence(rule_id, success=success)
            tag = 'success' if success else 'failure'
            print(f"[Learning] Rule {rule_id} updated ({tag}) for "
                  f"{problem.get('type')} on {device_name}")

        if self.inference_engine and result['trace_id']:
            traces = self.inference_engine.get_explanation_traces()
            matching = [t for t in traces if t.get('trace_id') == result['trace_id']]
            if matching:
                matching[0]['outcome'] = 'success' if success else 'failure'

        return result

    # ── Interface fixes ──────────────────────────────────────────────────────

    def apply_interface_fix(self, device_name, telnet_connection, problem,
                            auto_approve=False):
        problem_type = problem.get('type', 'shutdown')
        interface = problem['interface']

        if problem_type in ('ip address mismatch', 'missing ip address'):
            label = 'IP mismatch' if problem_type == 'ip address mismatch' else 'missing IP'
            if self.reporter:
                self.reporter.print_warning(f"Device: {device_name} | Issue: {interface} {label}")
                if 'current_ip' in problem:
                    self.reporter.print_info(
                        f"  Current: {problem['current_ip']} {problem.get('current_mask','')}"
                    )
                self.reporter.print_info(
                    f"  Expected: {problem['expected_ip']} {problem.get('expected_mask','')}"
                )
            prompt = "Fix IP address?" if problem_type == 'ip address mismatch' else "Configure IP address?"
            if not (auto_approve or Confirm.ask(prompt)):
                return None

            ok = fix_interface_ip(
                telnet_connection, interface,
                problem['expected_ip'], problem['expected_mask']
            )
            if self.reporter:
                (self.reporter.print_success if ok else self.reporter.print_error)(
                    f"{'✔ Fixed' if ok else '✘ Failed'} IP on {interface}"
                )
            if ok:
                time.sleep(1)
            verification = verify_interface_status(telnet_connection, interface)
            return self._record_result(
                device_name, problem,
                f"interface {interface}\nip address {problem['expected_ip']} {problem.get('expected_mask','')}",
                verification, ok
            )
        else:
            if self.reporter:
                self.reporter.print_warning(f"Device: {device_name} | Issue: {interface} is Down")
            if not (auto_approve or Confirm.ask("Apply 'no shutdown'?")):
                return None

            ok = fix_interface_shutdown(telnet_connection, interface)
            if self.reporter:
                (self.reporter.print_success if ok else self.reporter.print_error)(
                    f"{'✔ Fixed' if ok else '✘ Failed'} {interface}"
                )
            if ok:
                time.sleep(1)
            verification = verify_interface_status(telnet_connection, interface)
            return self._record_result(
                device_name, problem,
                f"interface {interface}\nno shutdown",
                verification, ok
            )

    # ── EIGRP fixes ──────────────────────────────────────────────────────────

    def apply_eigrp_fix(self, device_name, telnet_connection, problem,
                        auto_approve=False):
        issue_type = problem['type']
        if issue_type in ('eigrp hello timer mismatch', 'eigrp hold timer mismatch'):
            timer_type = 'Hello' if 'hello' in issue_type else 'Hold'
            if self.reporter:
                self.reporter.print_warning(
                    f"Device: {device_name} | Issue: {problem.get('interface')} {timer_type} timer"
                )
                self.reporter.print_info(
                    f"  Current: {problem.get('current')}s | Expected: {problem.get('expected')}s"
                )
        else:
            if self.reporter:
                self.reporter.print_warning(f"Device: {device_name} | Issue: {issue_type}")

        fix_commands = self._get_commands_for_problem(problem, device_name)
        if not fix_commands:
            if self.reporter:
                self.reporter.print_error("Manual intervention required")
            return None

        if not (auto_approve or Confirm.ask("Apply fix?")):
            return None

        ok = apply_eigrp_fixes(telnet_connection, fix_commands)
        if self.reporter:
            (self.reporter.print_success if ok else self.reporter.print_error)(
                f"{'✔ Fixed' if ok else '✘ Failed'} {issue_type}"
            )
        if ok:
            time.sleep(2)
        verification = verify_eigrp_neighbors(telnet_connection)
        return self._record_result(device_name, problem, fix_commands, verification, ok)

    # ── OSPF fixes ───────────────────────────────────────────────────────────

    def apply_ospf_fix(self, device_name, telnet_connection, problem,
                       auto_approve=False):
        issue_type = problem['type']
        if self.reporter:
            self.reporter.print_warning(f"Device: {device_name} | Issue: {issue_type}")

        fix_commands = self._get_commands_for_problem(problem, device_name)
        if not fix_commands:
            if self.reporter:
                self.reporter.print_error("Manual intervention required")
            return None

        if not (auto_approve or Confirm.ask("Apply fix?")):
            return None

        ok = apply_ospf_fixes(telnet_connection, fix_commands)
        if self.reporter:
            (self.reporter.print_success if ok else self.reporter.print_error)(
                f"{'✔ Fixed' if ok else '✘ Failed'} {issue_type}"
            )
        if ok:
            time.sleep(2)
        verification = verify_ospf_neighbors(telnet_connection)
        return self._record_result(device_name, problem, fix_commands, verification, ok)

    # ── Batch apply ──────────────────────────────────────────────────────────

    def apply_all_fixes(self, detected_issues, device_connections,
                        auto_approve_all=False):
        self.fix_results = []

        all_problems = []
        for device, problems in detected_issues.get('interfaces', {}).items():
            for p in problems:
                all_problems.append(('interface', device, p))
        for device, problems in detected_issues.get('eigrp', {}).items():
            for p in problems:
                all_problems.append(('eigrp', device, p))
        for device, problems in detected_issues.get('ospf', {}).items():
            for p in problems:
                all_problems.append(('ospf', device, p))

        if self.inference_engine and all_problems:
            problem_dicts = [p for _, _, p in all_problems]
            sequenced = self.inference_engine.sequence_fixes(problem_dicts)
            seq_map = {id(p): i for i, p in enumerate(sequenced)}
            all_problems.sort(key=lambda x: seq_map.get(id(x[2]), 999))

        for category, device, problem in all_problems:
            tn = device_connections.get(device)
            if not tn:
                continue
            if category == 'interface':
                result = self.apply_interface_fix(device, tn, problem, auto_approve_all)
            elif category == 'eigrp':
                result = self.apply_eigrp_fix(device, tn, problem, auto_approve_all)
            elif category == 'ospf':
                result = self.apply_ospf_fix(device, tn, problem, auto_approve_all)
            else:
                result = None
            if result:
                self.fix_results.append(result)

        return self.fix_results

    def get_fix_results(self):
        return self.fix_results

    def clear_results(self):
        self.fix_results = []


def apply_fixes_interactive(detected_issues, device_connections,
                             config_manager=None, reporter=None):
    from rich.prompt import Prompt
    fix_mode = Prompt.ask(
        "\n[cyan]Apply fixes:[/cyan]",
        choices=["all", "one-by-one"],
        default="one-by-one"
    )
    applier = FixApplier(config_manager, reporter, knowledge_base=None)
    return applier.apply_all_fixes(
        detected_issues, device_connections, fix_mode == "all"
    )