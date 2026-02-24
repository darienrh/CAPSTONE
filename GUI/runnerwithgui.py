#!/usr/bin/env python3
"""
gui_runner.py - GUI wrapper for runner.py
Run this file instead of runner.py.

- All text output / questions appear in the GUI window
- Rich progress bars remain in the terminal
- runner.py logic is completely untouched
"""

import tkinter as tk
from tkinter import scrolledtext
import threading
import sys
import builtins
import warnings
warnings.filterwarnings('ignore')
from datetime import datetime
_app = None


#gui inputs fix
_real_input = builtins.input

def _gui_input(prompt=""):
    if _app:
        return _app.ask_text(prompt)
    return _real_input(prompt)

builtins.input = _gui_input


#run rich prompt before gui so it works
import rich.prompt as _rp

class _GUIConfirm:
    @staticmethod
    def ask(prompt_text, default=True):
        if _app:
            return _app.ask_confirm(prompt_text, default)
        ans = _real_input(f"{prompt_text} [y/n]: ").strip().lower()
        return ans != 'n'

class _GUIPrompt:
    @staticmethod
    def ask(prompt_text, choices=None, default=None):
        if _app:
            return _app.ask_choice(prompt_text, choices, default)
        return _real_input(f"{prompt_text}: ").strip() or default

_rp.Confirm = _GUIConfirm
_rp.Prompt  = _GUIPrompt


#path the prints to gui logs
_real_print = builtins.print

def _gui_print(*args, **kwargs):
    _real_print(*args, **kwargs)      # keep terminal output
    if _app:
        text = " ".join(str(a) for a in args)
        _app.log_line(text, "normal")

builtins.print = _gui_print


#this makes it safe to run the runner
from utils.reporter import Reporter
import runner as _runner_module



# Colours & fonts

BG       = "#0d1117"
PANEL    = "#161b22"
BORDER   = "#30363d"
ACCENT   = "#58a6ff"
GREEN    = "#3fb950"
YELLOW   = "#d29922"
RED      = "#f85149"
FG       = "#e6edf3"
FG_DIM   = "#8b949e"

MONO  = ("Consolas", 10)    if sys.platform == "win32" else ("Menlo", 11)
UI    = ("Segoe UI", 10)    if sys.platform == "win32" else ("Helvetica Neue", 11)
TITLE = ("Segoe UI", 13, "bold") if sys.platform == "win32" else ("Helvetica Neue", 13, "bold")


# Main GUI class
class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Network Diagnostic Tool")
        self.root.configure(bg=BG)
        self.root.geometry("1000x680")
        self.root.minsize(800, 560)

        self._answer_event = threading.Event()
        self._answer_value = None

        self._build_ui()
        self._patch_reporter()

        global _app
        _app = self

    # UI Construction

    def _build_ui(self):
        # Top bar
        topbar = tk.Frame(self.root, bg=PANEL, height=50)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)

        tk.Label(topbar, text="⬡  Network Diagnostic Tool",
                 bg=PANEL, fg=ACCENT, font=TITLE, padx=18).pack(side="left", pady=10)

        self._status_lbl = tk.Label(topbar, text="● idle",
                                    bg=PANEL, fg=FG_DIM, font=UI)
        self._status_lbl.pack(side="right", padx=18)

        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x")

        # Body
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True)

        # Left: log
        log_wrap = tk.Frame(body, bg=PANEL)
        log_wrap.pack(side="left", fill="both", expand=True, padx=(12, 6), pady=12)

        tk.Label(log_wrap, text="OUTPUT", bg=PANEL, fg=FG_DIM,
                 font=("Consolas", 8), padx=8, pady=4).pack(anchor="w")

        self.log = scrolledtext.ScrolledText(
            log_wrap,
            bg="#0d1117", fg=FG, font=MONO,
            bd=0, relief="flat",
            insertbackground=ACCENT,
            selectbackground=BORDER,
            wrap="word", padx=10, pady=8,
            state="disabled"
        )
        self.log.pack(fill="both", expand=True, padx=6, pady=(0, 8))

        for tag, colour in [
            ("success", GREEN), ("error", RED), ("warning", YELLOW),
            ("info", ACCENT), ("phase", FG), ("dim", FG_DIM), ("normal", FG),
        ]:
            self.log.tag_config(tag, foreground=colour)
        self.log.tag_config("phase", font=("Consolas", 10, "bold"))

        # Right: sidebar
        self.sidebar = tk.Frame(body, bg=BG, width=250)
        self.sidebar.pack(side="right", fill="y", padx=(0, 12), pady=12)
        self.sidebar.pack_propagate(False)

        self._build_config_panel()
        self._build_device_panel()

        # Prompt area (shown dynamically)
        self.prompt_card = tk.Frame(self.sidebar, bg=PANEL)
        self._prompt_lbl = tk.Label(self.prompt_card, text="", bg=PANEL, fg=FG,
                                    font=UI, wraplength=220, justify="left",
                                    padx=10, pady=8)
        self._prompt_lbl.pack(anchor="w")
        self._prompt_btn_row = tk.Frame(self.prompt_card, bg=PANEL)
        self._prompt_btn_row.pack(fill="x", padx=8, pady=(0, 10))

        # Bottom bar
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x", side="bottom")
        botbar = tk.Frame(self.root, bg=PANEL, height=38)
        botbar.pack(fill="x", side="bottom")
        botbar.pack_propagate(False)

        self._footer = tk.Label(botbar, text="Configure settings then click Run.",
                                bg=PANEL, fg=FG_DIM, font=UI, padx=14)
        self._footer.pack(side="left", pady=6)

        self._run_btn = tk.Button(
            botbar, text="▶  Run Diagnostics",
            bg=ACCENT, fg="#0d1117",
            font=(UI[0], 10, "bold"),
            bd=0, padx=14, pady=3, relief="flat",
            activebackground="#79c0ff",
            cursor="hand2",
            command=self._start
        )
        self._run_btn.pack(side="right", padx=12, pady=5)

    def _build_config_panel(self):
        card = tk.Frame(self.sidebar, bg=PANEL)
        card.pack(fill="x", pady=(0, 10))

        tk.Label(card, text="CONFIGURATION", bg=PANEL, fg=FG_DIM,
                 font=("Consolas", 8), padx=10, pady=6).pack(anchor="w")

        def _lbl(text):
            tk.Label(card, text=text, bg=PANEL, fg=FG_DIM,
                     font=UI, padx=10).pack(anchor="w", pady=(4, 0))

        def _entry(default):
            e = tk.Entry(card, bg="#0d1117", fg=FG, font=MONO,
                         bd=0, relief="flat", insertbackground=ACCENT,
                         highlightthickness=1,
                         highlightcolor=ACCENT,
                         highlightbackground=BORDER)
            e.pack(fill="x", padx=10, ipady=5, pady=(2, 0))
            e.insert(0, default)
            return e

        _lbl("GNS3 URL")
        self.url_entry = _entry("http://localhost:3080")

        _lbl("Devices  (blank = all)")
        self.dev_entry = _entry("")
        self.dev_entry.insert(0, "e.g. r1, r2")
        self.dev_entry.configure(fg=FG_DIM)
        self.dev_entry.bind("<FocusIn>",  lambda e: self._ph_clear())
        self.dev_entry.bind("<FocusOut>", lambda e: self._ph_restore())

        tk.Frame(card, bg=BORDER, height=1).pack(fill="x", padx=10, pady=8)

    def _ph_clear(self):
        if self.dev_entry.get() == "e.g. r1, r2":
            self.dev_entry.delete(0, "end")
            self.dev_entry.configure(fg=FG)

    def _ph_restore(self):
        if not self.dev_entry.get():
            self.dev_entry.insert(0, "e.g. r1, r2")
            self.dev_entry.configure(fg=FG_DIM)

    def _build_device_panel(self):
        card = tk.Frame(self.sidebar, bg=PANEL)
        card.pack(fill="x", pady=(0, 10))

        tk.Label(card, text="DISCOVERED ROUTERS", bg=PANEL, fg=FG_DIM,
                 font=("Consolas", 8), padx=10, pady=6).pack(anchor="w")

        self.dev_list = tk.Listbox(
            card, bg="#0d1117", fg=GREEN,
            font=MONO, bd=0,
            selectbackground=BORDER,
            highlightthickness=0,
            height=6, activestyle="none"
        )
        self.dev_list.pack(fill="x", padx=10, pady=(0, 8))

    # Logging 

    def log_line(self, text, tag="normal"):
        import re
        clean = re.sub(r'\[/?[a-zA-Z_ ]+\]', '', str(text))
        def _w():
            self.log.configure(state="normal")
            ts = datetime.now().strftime("%H:%M:%S")
            self.log.insert("end", f"[{ts}] ", "dim")
            self.log.insert("end", clean + "\n", tag)
            self.log.see("end")
            self.log.configure(state="disabled")
        self.root.after(0, _w)

    def set_status(self, text, colour=FG_DIM):
        self.root.after(0, lambda: self._status_lbl.configure(
            text=f"● {text}", fg=colour))

    def set_footer(self, text):
        self.root.after(0, lambda: self._footer.configure(text=text))

    def set_devices(self, names):
        def _f():
            self.dev_list.delete(0, "end")
            for n in names:
                self.dev_list.insert("end", f"  {n}")
        self.root.after(0, _f)

    #Prompt helpers

    def _show_prompt(self, label_text, build_buttons_fn):
        def _f():
            self._prompt_lbl.configure(text=label_text)
            for w in self._prompt_btn_row.winfo_children():
                w.destroy()
            build_buttons_fn(self._prompt_btn_row)
            self.prompt_card.pack(fill="x", pady=(0, 10))
            self.root.update_idletasks()
        self.root.after(0, _f)

    def _hide_prompt(self):
        self.root.after(0, lambda: self.prompt_card.pack_forget())

    def _resolve(self, value):
        self._answer_value = value
        self._hide_prompt()
        self._answer_event.set()

    def ask_confirm(self, prompt_text, default=True):
        self._answer_event.clear()

        def _btns(row):
            tk.Button(row, text="Yes", bg=GREEN, fg="#0d1117",
                      font=(UI[0], 10, "bold"), bd=0, padx=12, pady=3,
                      relief="flat", cursor="hand2",
                      command=lambda: self._resolve(True)).pack(side="left", padx=(0, 6))
            tk.Button(row, text="No", bg=BORDER, fg=FG,
                      font=(UI[0], 10), bd=0, padx=12, pady=3,
                      relief="flat", cursor="hand2",
                      command=lambda: self._resolve(False)).pack(side="left")

        self._show_prompt(prompt_text, _btns)
        self._answer_event.wait()
        return self._answer_value

    def ask_choice(self, prompt_text, choices=None, default=None):
        self._answer_event.clear()

        def _btns(row):
            if choices:
                for c in choices:
                    is_def = (c == default)
                    tk.Button(
                        row, text=c,
                        bg=ACCENT if is_def else BORDER,
                        fg="#0d1117" if is_def else FG,
                        font=(UI[0], 10, "bold") if is_def else (UI[0], 10),
                        bd=0, padx=12, pady=3, relief="flat", cursor="hand2",
                        command=lambda v=c: self._resolve(v)
                    ).pack(side="left", padx=(0, 5))
            else:
                e = tk.Entry(row, bg="#0d1117", fg=FG, font=MONO, bd=0,
                             highlightthickness=1, highlightcolor=ACCENT,
                             highlightbackground=BORDER)
                e.pack(side="left", fill="x", expand=True, ipady=4)
                if default:
                    e.insert(0, default)
                e.bind("<Return>", lambda _: self._resolve(e.get() or default))
                tk.Button(row, text="OK", bg=ACCENT, fg="#0d1117",
                          font=(UI[0], 10, "bold"), bd=0, padx=10, pady=3,
                          relief="flat", cursor="hand2",
                          command=lambda: self._resolve(e.get() or default)
                          ).pack(side="left", padx=(6, 0))

        self._show_prompt(prompt_text, _btns)
        self._answer_event.wait()
        return self._answer_value

    def ask_text(self, prompt_text):
        """Intercepts raw input() calls."""
        self._answer_event.clear()

        def _btns(row):
            e = tk.Entry(row, bg="#0d1117", fg=FG, font=MONO, bd=0,
                         highlightthickness=1, highlightcolor=ACCENT,
                         highlightbackground=BORDER)
            e.pack(side="left", fill="x", expand=True, ipady=4)
            e.bind("<Return>", lambda _: self._resolve(e.get()))
            tk.Button(row, text="OK", bg=ACCENT, fg="#0d1117",
                      font=(UI[0], 10, "bold"), bd=0, padx=10, pady=3,
                      relief="flat", cursor="hand2",
                      command=lambda: self._resolve(e.get())
                      ).pack(side="left", padx=(6, 0))
            # focus entry after it's rendered
            self.root.after(50, e.focus_set)

        self._show_prompt(prompt_text, _btns)
        self._answer_event.wait()
        return self._answer_value or ""

    #Reporter patch

    def _patch_reporter(self):
        gui = self

        def _make_method(tag):
            def method(self_r, msg):
                gui.log_line(msg, tag)
            return method

        Reporter.print_success = _make_method("success")
        Reporter.print_error   = _make_method("error")
        Reporter.print_warning = _make_method("warning")
        Reporter.print_info    = _make_method("info")

        def _phase_header(self_r, msg):
            import re
            clean = re.sub(r'\[/?[a-zA-Z_ ]+\]', '', msg)
            gui.log_line("━" * 44, "dim")
            gui.log_line(f"  {clean}", "phase")
            gui.log_line("━" * 44, "dim")
            gui.set_status(clean.lower(), ACCENT)
            gui.set_footer(clean)

        Reporter.print_phase_header = _phase_header

        def _scan_summary(self_r, issues):
            if not issues:
                gui.log_line("✓ No issues detected on any device.", "success")
                return False
            total = sum(len(v) for v in issues.values())
            gui.log_line(
                f"Scan complete — {total} issue(s) across {len(issues)} device(s).",
                "warning"
            )
            for device, dev_issues in issues.items():
                for issue in dev_issues:
                    desc = issue.get('description', str(issue)) if isinstance(issue, dict) else str(issue)
                    gui.log_line(f"  [{device}]  {desc}", "warning")
            return True

        Reporter.print_scan_summary = _scan_summary

        def _fix_summary(self_r, fix_results):
            if not fix_results:
                gui.log_line("No fixes were applied.", "dim")
                return
            passed = sum(1 for r in fix_results if r.get('success'))
            failed = len(fix_results) - passed
            gui.log_line(
                f"Fix summary: {passed} succeeded, {failed} failed.",
                "success" if failed == 0 else "warning"
            )

        Reporter.print_fix_completion_summary = _fix_summary

    #Run

    def _start(self):
        self._run_btn.configure(state="disabled", text="Running…")
        self.set_status("running", YELLOW)
        t = threading.Thread(target=self._run_in_thread, daemon=True)
        t.start()

    def _run_in_thread(self):
        try:
            self._execute()
        except SystemExit:
            pass
        except Exception as exc:
            self.log_line(f"Fatal error: {exc}", "error")
            self.set_status("error", RED)
        finally:
            self.root.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Run Diagnostics"))
            self.set_status("idle", FG_DIM)
            self.set_footer("Done.")

    def _execute(self):
        import atexit

        gns3_url = self.url_entry.get().strip() or "http://localhost:3080"

        runner = _runner_module.DiagnosticRunner(gns3_url=gns3_url)
        atexit.register(runner.cleanup_all_connections)

        self.log_line("Network Diagnostic Tool", "phase")

        stats = runner.knowledge_base.get_statistics()
        self.log_line(
            f"Knowledge Base: {stats['total_rules']} rules, "
            f"{stats['total_problems_logged']} problems logged, "
            f"{stats['overall_success_rate']}% success rate",
            "info"
        )

        self.set_footer("Connecting to GNS3…")
        self.set_status("connecting", YELLOW)

        if not runner.connect():
            self.set_status("connection failed", RED)
            return

        available_devices = [
            name for name in runner.nodes.keys()
            if not name.lower().startswith('switch')
        ]
        device_map = {name.lower(): name for name in available_devices}

        self.set_devices(available_devices)
        self.log_line(f"Available: {', '.join(available_devices)}", "info")

        raw = self.dev_entry.get().strip()
        if raw in ("", "e.g. r1, r2"):
            final_target_list = available_devices
        else:
            final_target_list = []
            for req in [d.strip().lower() for d in raw.split(',')]:
                if req in device_map:
                    final_target_list.append(device_map[req])

        if not final_target_list:
            self.log_line("No valid devices selected.", "error")
            return

        self.log_line(f"Targeting: {', '.join(final_target_list)}", "info")

        self.set_status("scanning", YELLOW)
        detected_issues = runner.run_diagnostics(final_target_list)
        has_issues = runner.reporter.print_scan_summary(detected_issues)

        if has_issues and _GUIConfirm.ask("\nProceed to fix menu?"):
            runner.apply_fixes(detected_issues)
            runner.print_completion_summary()
        else:
            if not has_issues:
                runner.reporter.save_run_history([], runner.run_timestamp)

        self.log_line("─" * 44, "dim")

        if _GUIConfirm.ask("View Knowledge Base statistics?", default=False):
            runner.show_kb_statistics()

        self.log_line("─" * 44, "dim")

        if _GUIConfirm.ask("Revert configs to last stable version?", default=False):
            revert_mode = _GUIPrompt.ask(
                "Revert mode:",
                choices=["all", "select"],
                default="all"
            )
            if revert_mode == "all":
                runner.restore_stable_configurations(final_target_list)
            else:
                device_input = self.ask_text("Devices to revert (e.g. R1, R2, R4):")
                if device_input:
                    dmap = {n.lower(): n for n in final_target_list}
                    revert_devices = [
                        dmap[r.strip().lower()]
                        for r in device_input.split(',')
                        if r.strip().lower() in dmap
                    ]
                    if revert_devices:
                        runner.restore_stable_configurations(revert_devices)

        self.log_line("─" * 44, "dim")

        if _GUIConfirm.ask("Save stable configurations of all routers now?"):
            runner.save_stable_configurations(final_target_list)

        self.log_line("Script completed successfully!", "success")


# Entry point into runner

def main():
    root = tk.Tk()
    root.resizable(True, True)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
