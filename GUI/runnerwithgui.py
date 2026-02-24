#!/usr/bin/env python3
"""
GUI wrapper for runner.py - Routes text/questions to a clean Tkinter GUI.
Progress bars remain in the terminal; dialogs/prompts appear in the GUI window.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import queue
import sys
import time
import warnings
warnings.filterwarnings('ignore')

import requests
from requests.auth import HTTPBasicAuth
import atexit
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# Patch rich.prompt so it routes through the GUI instead of the terminal
# Must happen before importing runner modules
# ─────────────────────────────────────────────────────────────────────────────

_gui_app = None   # set after app is created

class _GUIConfirm:
    """Replaces rich.prompt.Confirm"""
    @staticmethod
    def ask(prompt_text, default=True):
        if _gui_app:
            return _gui_app.ask_confirm(prompt_text, default)
        # fallback
        ans = input(f"{prompt_text} [y/n]: ").strip().lower()
        return ans != 'n'

class _GUIPrompt:
    """Replaces rich.prompt.Prompt"""
    @staticmethod
    def ask(prompt_text, choices=None, default=None):
        if _gui_app:
            return _gui_app.ask_prompt(prompt_text, choices, default)
        ans = input(f"{prompt_text}: ").strip()
        return ans or default

import rich.prompt as _rich_prompt
_rich_prompt.Confirm = _GUIConfirm
_rich_prompt.Prompt  = _GUIPrompt

# ─────────────────────────────────────────────────────────────────────────────
# Now import the actual runner components
# ─────────────────────────────────────────────────────────────────────────────

from core.config_manager import ConfigManager
from core.knowledge_base import KnowledgeBase
from detection.problem_detector import ProblemDetector
from resolution.fix_applier import FixApplier
from utils.reporter import Reporter
from utils.telnet_utils import connect_device, close_device, get_running_config


# ─────────────────────────────────────────────────────────────────────────────
# GUI App
# ─────────────────────────────────────────────────────────────────────────────

DARK_BG     = "#0f1117"
PANEL_BG    = "#161b22"
BORDER      = "#30363d"
ACCENT      = "#58a6ff"
ACCENT2     = "#3fb950"
WARN        = "#d29922"
ERR         = "#f85149"
TEXT_MAIN   = "#e6edf3"
TEXT_DIM    = "#8b949e"
FONT_MONO   = ("JetBrains Mono", 11) if sys.platform != "win32" else ("Consolas", 11)
FONT_UI     = ("Segoe UI", 11) if sys.platform == "win32" else ("SF Pro Display", 11)
FONT_TITLE  = ("Segoe UI", 14, "bold") if sys.platform == "win32" else ("SF Pro Display", 14, "bold")


class DiagnosticGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Network Diagnostic Tool")
        self.root.configure(bg=DARK_BG)
        self.root.minsize(820, 600)
        self.root.geometry("960x700")

        self._answer_queue = queue.Queue()
        self._build_ui()

        # Wire global reference
        global _gui_app
        _gui_app = self

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Header bar
        hdr = tk.Frame(self.root, bg=PANEL_BG, height=54)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)

        tk.Label(
            hdr, text="⬡  Network Diagnostic Tool",
            bg=PANEL_BG, fg=ACCENT, font=FONT_TITLE,
            padx=20
        ).pack(side="left", pady=12)

        self.status_dot = tk.Label(hdr, text="●  idle", bg=PANEL_BG, fg=TEXT_DIM, font=FONT_UI)
        self.status_dot.pack(side="right", padx=20)

        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x")

        # Main area: log + sidebar
        body = tk.Frame(self.root, bg=DARK_BG)
        body.pack(fill="both", expand=True, padx=0, pady=0)

        # Log panel
        log_frame = tk.Frame(body, bg=PANEL_BG, bd=0)
        log_frame.pack(side="left", fill="both", expand=True, padx=(16, 8), pady=16)

        tk.Label(log_frame, text="OUTPUT LOG", bg=PANEL_BG, fg=TEXT_DIM,
                 font=("Consolas", 9), padx=8, pady=6).pack(anchor="w")

        self.log = scrolledtext.ScrolledText(
            log_frame,
            bg="#0d1117", fg=TEXT_MAIN,
            font=FONT_MONO,
            bd=0, relief="flat",
            insertbackground=ACCENT,
            selectbackground=ACCENT,
            wrap="word",
            padx=10, pady=8,
            state="disabled"
        )
        self.log.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        # Tag colours
        self.log.tag_config("success",  foreground=ACCENT2)
        self.log.tag_config("error",    foreground=ERR)
        self.log.tag_config("warning",  foreground=WARN)
        self.log.tag_config("info",     foreground=ACCENT)
        self.log.tag_config("phase",    foreground="#c9d1d9", font=("Consolas", 11, "bold"))
        self.log.tag_config("dim",      foreground=TEXT_DIM)
        self.log.tag_config("normal",   foreground=TEXT_MAIN)

        # Right sidebar
        side = tk.Frame(body, bg=DARK_BG, width=260)
        side.pack(side="right", fill="y", padx=(0, 16), pady=16)
        side.pack_propagate(False)

        # Device panel
        self._build_device_panel(side)

        # Prompt panel (hidden until needed)
        self.prompt_outer = tk.Frame(side, bg=PANEL_BG, bd=0)
        self._prompt_label = tk.Label(
            self.prompt_outer, text="", bg=PANEL_BG, fg=TEXT_MAIN,
            font=FONT_UI, wraplength=230, justify="left", padx=10, pady=8
        )
        self._prompt_label.pack(anchor="w")
        self._prompt_buttons_frame = tk.Frame(self.prompt_outer, bg=PANEL_BG)
        self._prompt_buttons_frame.pack(fill="x", padx=8, pady=(0, 10))

        # Footer
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x", side="bottom")
        footer = tk.Frame(self.root, bg=PANEL_BG, height=36)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        self._footer_msg = tk.Label(
            footer, text="Ready.", bg=PANEL_BG, fg=TEXT_DIM, font=FONT_UI, padx=16
        )
        self._footer_msg.pack(side="left", pady=6)

        # Start button
        self.start_btn = tk.Button(
            footer,
            text="▶  Run Diagnostics",
            bg=ACCENT, fg="#0d1117",
            font=(FONT_UI[0], 10, "bold"),
            bd=0, padx=14, pady=4,
            relief="flat",
            activebackground="#79c0ff",
            cursor="hand2",
            command=self._start_runner
        )
        self.start_btn.pack(side="right", padx=14, pady=5)

    def _build_device_panel(self, parent):
        panel = tk.Frame(parent, bg=PANEL_BG)
        panel.pack(fill="x", pady=(0, 12))

        tk.Label(panel, text="DEVICES", bg=PANEL_BG, fg=TEXT_DIM,
                 font=("Consolas", 9), padx=10, pady=6).pack(anchor="w")

        entry_frame = tk.Frame(panel, bg=PANEL_BG)
        entry_frame.pack(fill="x", padx=10, pady=(0, 8))

        tk.Label(entry_frame, text="Target (blank = all):",
                 bg=PANEL_BG, fg=TEXT_DIM, font=FONT_UI).pack(anchor="w")

        self.device_entry = tk.Entry(
            entry_frame,
            bg="#0d1117", fg=TEXT_MAIN,
            font=FONT_MONO,
            bd=0, relief="flat",
            insertbackground=ACCENT,
            highlightthickness=1,
            highlightcolor=ACCENT,
            highlightbackground=BORDER
        )
        self.device_entry.pack(fill="x", ipady=5, pady=(4, 0))
        self.device_entry.insert(0, "e.g. r1, r2, r4")
        self.device_entry.bind("<FocusIn>",  self._clear_placeholder)
        self.device_entry.bind("<FocusOut>", self._restore_placeholder)

        # GNS3 URL
        tk.Label(entry_frame, text="GNS3 URL:",
                 bg=PANEL_BG, fg=TEXT_DIM, font=FONT_UI, pady=(6, 0)).pack(anchor="w")

        self.url_entry = tk.Entry(
            entry_frame,
            bg="#0d1117", fg=TEXT_MAIN,
            font=FONT_MONO,
            bd=0, relief="flat",
            insertbackground=ACCENT,
            highlightthickness=1,
            highlightcolor=ACCENT,
            highlightbackground=BORDER
        )
        self.url_entry.pack(fill="x", ipady=5, pady=(4, 0))
        self.url_entry.insert(0, "http://localhost:3080")

        # Detected devices list
        tk.Label(panel, text="CONNECTED", bg=PANEL_BG, fg=TEXT_DIM,
                 font=("Consolas", 9), padx=10, pady=(10, 2)).pack(anchor="w")

        self.device_listbox = tk.Listbox(
            panel, bg="#0d1117", fg=ACCENT2,
            font=FONT_MONO, bd=0,
            selectbackground=BORDER,
            highlightthickness=0,
            height=6
        )
        self.device_listbox.pack(fill="x", padx=10, pady=(0, 8))

    # ── Placeholder helpers ───────────────────────────────────────────────────

    def _clear_placeholder(self, event):
        if self.device_entry.get() == "e.g. r1, r2, r4":
            self.device_entry.delete(0, "end")
            self.device_entry.configure(fg=TEXT_MAIN)

    def _restore_placeholder(self, event):
        if not self.device_entry.get():
            self.device_entry.insert(0, "e.g. r1, r2, r4")
            self.device_entry.configure(fg=TEXT_DIM)

    # ── Logging ───────────────────────────────────────────────────────────────

    def log_line(self, text, tag="normal"):
        def _write():
            self.log.configure(state="normal")
            ts = datetime.now().strftime("%H:%M:%S")
            self.log.insert("end", f"[{ts}]  ", "dim")
            self.log.insert("end", text + "\n", tag)
            self.log.see("end")
            self.log.configure(state="disabled")
        self.root.after(0, _write)

    def set_status(self, text, colour=TEXT_DIM):
        self.root.after(0, lambda: self.status_dot.configure(text=f"●  {text}", fg=colour))

    def set_footer(self, text):
        self.root.after(0, lambda: self._footer_msg.configure(text=text))

    # ── Prompt helpers (blocking, waits for GUI answer) ───────────────────────

    def ask_confirm(self, prompt_text, default=True):
        """Show a confirm dialog in the sidebar and block until answered."""
        result = threading.Event()
        answer_holder = [default]

        def _build(val):
            answer_holder[0] = val
            self._hide_prompt()
            result.set()

        def _show():
            self._prompt_label.configure(text=prompt_text)
            for w in self._prompt_buttons_frame.winfo_children():
                w.destroy()

            yes_btn = tk.Button(
                self._prompt_buttons_frame,
                text="Yes", bg=ACCENT2, fg="#0d1117",
                font=(FONT_UI[0], 10, "bold"),
                bd=0, padx=12, pady=4, relief="flat",
                cursor="hand2",
                command=lambda: _build(True)
            )
            yes_btn.pack(side="left", padx=(0, 6))

            no_btn = tk.Button(
                self._prompt_buttons_frame,
                text="No", bg=BORDER, fg=TEXT_MAIN,
                font=(FONT_UI[0], 10),
                bd=0, padx=12, pady=4, relief="flat",
                cursor="hand2",
                command=lambda: _build(False)
            )
            no_btn.pack(side="left")

            self.prompt_outer.pack(fill="x", pady=(0, 12))
            self.root.update_idletasks()

        self.root.after(0, _show)
        result.wait()
        return answer_holder[0]

    def ask_prompt(self, prompt_text, choices=None, default=None):
        """Show a choice prompt in the sidebar and block until answered."""
        result = threading.Event()
        answer_holder = [default]

        def _build(val):
            answer_holder[0] = val
            self._hide_prompt()
            result.set()

        def _show():
            self._prompt_label.configure(text=prompt_text)
            for w in self._prompt_buttons_frame.winfo_children():
                w.destroy()

            if choices:
                for choice in choices:
                    style = {
                        "bg": ACCENT if choice == default else BORDER,
                        "fg": "#0d1117" if choice == default else TEXT_MAIN
                    }
                    btn = tk.Button(
                        self._prompt_buttons_frame,
                        text=choice, **style,
                        font=(FONT_UI[0], 10),
                        bd=0, padx=12, pady=4, relief="flat",
                        cursor="hand2",
                        command=lambda c=choice: _build(c)
                    )
                    btn.pack(side="left", padx=(0, 6))
            else:
                # text entry fallback
                entry = tk.Entry(
                    self._prompt_buttons_frame,
                    bg="#0d1117", fg=TEXT_MAIN,
                    font=FONT_MONO, bd=0,
                    highlightthickness=1,
                    highlightcolor=ACCENT,
                    highlightbackground=BORDER
                )
                entry.pack(side="left", fill="x", expand=True, ipady=4)
                if default:
                    entry.insert(0, default)

                ok_btn = tk.Button(
                    self._prompt_buttons_frame,
                    text="OK", bg=ACCENT, fg="#0d1117",
                    font=(FONT_UI[0], 10, "bold"),
                    bd=0, padx=10, pady=4, relief="flat",
                    cursor="hand2",
                    command=lambda: _build(entry.get() or default)
                )
                ok_btn.pack(side="left", padx=(6, 0))

            self.prompt_outer.pack(fill="x", pady=(0, 12))
            self.root.update_idletasks()

        self.root.after(0, _show)
        result.wait()
        return answer_holder[0]

    def ask_device_input(self, prompt_text):
        """Ask for free-text device input via a GUI dialog."""
        result = threading.Event()
        answer_holder = [""]

        def _build():
            val = entry.get().strip()
            answer_holder[0] = val
            self._hide_prompt()
            result.set()

        def _show():
            self._prompt_label.configure(text=prompt_text)
            for w in self._prompt_buttons_frame.winfo_children():
                w.destroy()

            entry = tk.Entry(
                self._prompt_buttons_frame,
                bg="#0d1117", fg=TEXT_MAIN,
                font=FONT_MONO, bd=0,
                highlightthickness=1,
                highlightcolor=ACCENT,
                highlightbackground=BORDER
            )
            entry.pack(side="left", fill="x", expand=True, ipady=4)
            entry.bind("<Return>", lambda e: _build())

            ok_btn = tk.Button(
                self._prompt_buttons_frame,
                text="OK", bg=ACCENT, fg="#0d1117",
                font=(FONT_UI[0], 10, "bold"),
                bd=0, padx=10, pady=4, relief="flat",
                cursor="hand2",
                command=_build
            )
            ok_btn.pack(side="left", padx=(6, 0))

            self.prompt_outer.pack(fill="x", pady=(0, 12))
            self.root.update_idletasks()

        self.root.after(0, _show)
        result.wait()
        return answer_holder[0]

    def _hide_prompt(self):
        self.prompt_outer.pack_forget()

    # ── Populate device list ──────────────────────────────────────────────────

    def populate_devices(self, device_names):
        def _fill():
            self.device_listbox.delete(0, "end")
            for name in device_names:
                self.device_listbox.insert("end", f"  {name}")
        self.root.after(0, _fill)

    # ── Start runner ──────────────────────────────────────────────────────────

    def _start_runner(self):
        self.start_btn.configure(state="disabled", text="Running…")
        self.set_status("running", ACCENT)
        t = threading.Thread(target=self._run_logic, daemon=True)
        t.start()

    def _run_logic(self):
        try:
            self._run_diagnostic_flow()
        except Exception as exc:
            self.log_line(f"Unexpected error: {exc}", "error")
            self.set_status("error", ERR)
        finally:
            self.root.after(0, lambda: self.start_btn.configure(
                state="normal", text="▶  Run Diagnostics"
            ))
            self.set_status("idle", TEXT_DIM)
            self.set_footer("Done.")

    # ── Core diagnostic flow (mirrors main() from runner.py) ─────────────────

    def _run_diagnostic_flow(self):
        gns3_url = self.url_entry.get().strip() or "http://localhost:3080"

        # Build runner
        from runner import DiagnosticRunner   # import here to use patched prompts
        runner = DiagnosticRunner(gns3_url=gns3_url)
        atexit.register(runner.cleanup_all_connections)

        # Redirect reporter output to GUI
        self._patch_reporter(runner.reporter)

        self.log_line("Network Diagnostic Tool", "phase")

        stats = runner.knowledge_base.get_statistics()
        self.log_line(
            f"KB: {stats['total_rules']} rules | "
            f"{stats['total_problems_logged']} problems | "
            f"{stats['overall_success_rate']}% success",
            "info"
        )

        self.set_status("connecting…", WARN)
        self.set_footer("Connecting to GNS3…")

        if not runner.connect():
            self.log_line("Could not connect to GNS3.", "error")
            self.set_status("disconnected", ERR)
            return

        available_devices = [n for n in runner.nodes.keys()
                             if not n.lower().startswith('switch')]
        device_map = {n.lower(): n for n in available_devices}

        self.populate_devices(available_devices)
        self.log_line(f"Available: {', '.join(available_devices)}", "info")

        # Device selection – use the sidebar entry field value
        raw_input = self.device_entry.get().strip()
        if raw_input == "e.g. r1, r2, r4":
            raw_input = ""

        if not raw_input:
            final_target_list = available_devices
        else:
            final_target_list = []
            for req in [d.strip().lower() for d in raw_input.split(',')]:
                if req in device_map:
                    final_target_list.append(device_map[req])

        if not final_target_list:
            self.log_line("No valid devices selected.", "error")
            return

        self.log_line(f"Targeting: {', '.join(final_target_list)}", "info")
        self.set_status("scanning", WARN)
        self.set_footer("Running diagnostics…")

        detected_issues = runner.run_diagnostics(final_target_list)
        has_issues = runner.reporter.print_scan_summary(detected_issues)

        if has_issues:
            proceed = self.ask_confirm("Issues detected. Proceed to fix menu?", default=True)
            if proceed:
                runner.apply_fixes(detected_issues)
                runner.print_completion_summary()
        else:
            runner.reporter.save_run_history([], runner.run_timestamp)

        self.log_line("─" * 50, "dim")

        if self.ask_confirm("View Knowledge Base statistics?", default=False):
            runner.show_kb_statistics()

        self.log_line("─" * 50, "dim")

        if self.ask_confirm("Revert configs to last stable version?", default=False):
            revert_mode = self.ask_prompt(
                "Revert mode:",
                choices=["all", "select"],
                default="all"
            )
            if revert_mode == "all":
                runner.restore_stable_configurations(final_target_list)
            else:
                device_input = self.ask_device_input("Enter devices to revert (e.g. R1, R2):")
                if device_input:
                    dmap = {n.lower(): n for n in final_target_list}
                    revert_devices = []
                    for req in [d.strip().lower() for d in device_input.split(',')]:
                        if req in dmap:
                            revert_devices.append(dmap[req])
                    if revert_devices:
                        runner.restore_stable_configurations(revert_devices)

        self.log_line("─" * 50, "dim")

        if self.ask_confirm("Save stable configurations of all routers now?", default=False):
            runner.save_stable_configurations(final_target_list)

        self.log_line("Script completed successfully!", "success")
        self.set_status("done", ACCENT2)

    # ── Patch reporter to write to GUI log ────────────────────────────────────

    def _patch_reporter(self, reporter):
        gui = self

        def _print_success(msg):
            gui.log_line(msg, "success")

        def _print_error(msg):
            gui.log_line(msg, "error")

        def _print_warning(msg):
            gui.log_line(msg, "warning")

        def _print_info(msg):
            gui.log_line(msg, "info")

        def _print_phase_header(msg):
            gui.log_line(f"\n{'━'*40}", "dim")
            gui.log_line(f"  {msg}", "phase")
            gui.log_line(f"{'━'*40}", "dim")
            gui.set_status(msg.lower(), ACCENT)
            gui.set_footer(msg)

        def _print_scan_summary(issues):
            if not issues:
                gui.log_line("No issues detected.", "success")
                return False
            total = sum(len(v) for v in issues.values())
            gui.log_line(f"Scan complete: {total} issue(s) across {len(issues)} device(s).", "warning")
            for device, device_issues in issues.items():
                for issue in device_issues:
                    gui.log_line(f"  [{device}] {issue.get('description', issue)}", "warning")
            return bool(issues)

        reporter.print_success      = _print_success
        reporter.print_error        = _print_error
        reporter.print_warning      = _print_warning
        reporter.print_info         = _print_info
        reporter.print_phase_header = _print_phase_header
        reporter.print_scan_summary = _print_scan_summary


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    root.resizable(True, True)
    app = DiagnosticGUI(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted")
        sys.exit(0)
