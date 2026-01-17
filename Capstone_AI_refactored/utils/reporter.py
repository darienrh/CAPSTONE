#!/usr/bin/env python3
"""reporter.py - Reporting and history management (extracted from runner.py)"""

import re
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

console = Console()

HISTORY_DIR = Path.home() / "Capstone_AI" / "history" / "runs"


class Reporter:
    """
    Handles all reporting and history management
    """
    
    def __init__(self, history_dir=None):
        """
        Initialize reporter
        
        Args:
            history_dir: Directory for storing run history
        """
        self.history_dir = Path(history_dir) if history_dir else HISTORY_DIR
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.console = Console()
    
    def print_scan_summary(self, detected_issues):
        """
        Print summary of detected issues
        
        Args:
            detected_issues: Dict with detected problems
        
        Returns:
            True if issues were found, False otherwise
        """
        has_interface_issues = detected_issues.get('interfaces')
        has_eigrp_issues = detected_issues.get('eigrp')
        has_ospf_issues = detected_issues.get('ospf')
        
        if not has_interface_issues and not has_eigrp_issues and not has_ospf_issues:
            self.console.print("\n[bold green]✓ No Problems Detected[/bold green]")
            return False
        
        table = Table(title="Diagnostic Results", show_header=True, header_style="bold magenta")
        table.add_column("Device", style="cyan")
        table.add_column("Category", style="yellow")
        table.add_column("Issue", style="white")
        table.add_column("Status", style="red")
        
        # Interface issues
        for device, problems in detected_issues.get('interfaces', {}).items():
            for p in problems:
                issue_type = p.get('type', 'shutdown')
                if issue_type == 'ip address mismatch':
                    status = f"IP: {p['current_ip']} (expect: {p['expected_ip']})"
                elif issue_type == 'missing ip address':
                    status = f"Missing IP: {p['expected_ip']}"
                else:
                    status = "Admin Down"
                table.add_row(device, "Interface", p['interface'], status)
        
        # EIGRP issues
        for device, problems in detected_issues.get('eigrp', {}).items():
            for p in problems:
                table.add_row(device, "EIGRP", p.get('line', p['type'])[:40], p['type'])
        
        # OSPF issues
        for device, problems in detected_issues.get('ospf', {}).items():
            for p in problems:
                table.add_row(device, "OSPF", p.get('line', p['type'])[:40], p['type'])
        
        self.console.print(table)
        return True
    
    def print_fix_completion_summary(self, fix_results):
        """
        Print summary of applied fixes
        
        Args:
            fix_results: List of fix result dicts
        """
        if not fix_results:
            self.console.print("\n[bold green]✓ No Changes Made[/bold green]")
            return
        
        self.console.print("\n[bold cyan]═══════════════════════════════════════════════════════════[/bold cyan]")
        self.console.print("[bold green]FINAL COMPLETION SUMMARY[/bold green]", justify="center")
        self.console.print("[bold cyan]═══════════════════════════════════════════════════════════[/bold cyan]")
        
        table = Table(show_header=True, header_style="bold magenta", border_style="cyan")
        table.add_column("Device", style="cyan", width=12)
        table.add_column("Commands Executed", style="yellow", width=30)
        table.add_column("Verification", style="green", width=35)
        
        for result in fix_results:
            table.add_row(result['device'], result['commands'], result['verification'])
        
        self.console.print(table)
        self.console.print(f"\n[bold green]✓ Successfully applied {len(fix_results)} fix(es)[/bold green]")
    
    def save_run_history(self, fix_results, timestamp):
        """
        Save run history to file
        
        Args:
            fix_results: List of fix results
            timestamp: Run timestamp string
        
        Returns:
            True if saved successfully
        """
        try:
            filename = self._get_next_filename("run")
            
            with open(filename, 'w') as f:
                f.write(f"Run Timestamp: {timestamp}\n{'=' * 80}\n\n")
                f.write("FINAL COMPLETION SUMMARY\n{'=' * 80}\n\n")
                
                if not fix_results:
                    f.write("No fixes were applied during this run.\n")
                else:
                    for i, result in enumerate(fix_results, 1):
                        f.write(f"Fix #{i}\nDevice: {result['device']}\n")
                        f.write(f"Commands Executed:\n")
                        for line in result['commands'].split('\n'):
                            f.write(f"  {line}\n")
                        f.write(f"Verification: {result['verification']}\n{'-' * 80}\n\n")
                    f.write(f"Total fixes applied: {len(fix_results)}\n")
            
            self.console.print(f"\n[green]History saved to: {filename}[/green]")
            return True
        except Exception as e:
            self.console.print(f"[red]Failed to save history: {e}[/red]")
            return False
    
    def _get_next_filename(self, prefix, extension="txt"):
        """
        Get next available filename with auto-increment
        
        Args:
            prefix: Filename prefix
            extension: File extension
        
        Returns:
            Path object for next filename
        """
        self.history_dir.mkdir(parents=True, exist_ok=True)
        existing_files = list(self.history_dir.glob(f"{prefix}*.{extension}"))
        
        if not existing_files:
            return self.history_dir / f"{prefix}.{extension}"
        
        max_num = 0
        for file in existing_files:
            match = re.match(f'{prefix}(\\d*)\\.{extension}', file.name)
            if match:
                num_str = match.group(1)
                current_num = 0 if num_str == '' else int(num_str)
                max_num = max(max_num, current_num)
        
        next_num = max_num + 10
        return self.history_dir / f"{prefix}{next_num}.{extension}"
    
    def create_progress_bar(self, description, total):
        """
        Create a progress bar context manager
        
        Args:
            description: Progress description
            total: Total items
        
        Returns:
            Progress context manager
        """
        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeElapsedColumn(),
            console=self.console
        )
    
    def print_phase_header(self, phase_name):
        """
        Print a phase header
        
        Args:
            phase_name: Name of the phase
        """
        self.console.print(f"\n[bold cyan]{phase_name}[/bold cyan]")
    
    def print_success(self, message):
        """Print success message"""
        self.console.print(f"[green]{message}[/green]")
    
    def print_error(self, message):
        """Print error message"""
        self.console.print(f"[red]{message}[/red]")
    
    def print_warning(self, message):
        """Print warning message"""
        self.console.print(f"[yellow]{message}[/yellow]")
    
    def print_info(self, message):
        """Print info message"""
        self.console.print(f"[cyan]{message}[/cyan]")
    
    def generate_device_health_report(self, scan_results):
        """
        Generate health report for devices
        
        Args:
            scan_results: Dict of scan results per device
        
        Returns:
            Formatted report string
        """
        table = Table(title="Device Health Summary", show_header=True)
        table.add_column("Device", style="cyan")
        table.add_column("Issues Found", style="yellow")
        table.add_column("Health Score", style="green")
        
        for device, results in scan_results.items():
            issue_count = len(results.get('problems', []))
            health_score = max(0, 100 - (issue_count * 10))
            health_color = "green" if health_score >= 80 else "yellow" if health_score >= 50 else "red"
            
            table.add_row(
                device,
                str(issue_count),
                f"[{health_color}]{health_score}%[/{health_color}]"
            )
        
        self.console.print(table)


# Legacy functions for backward compatibility

def save_history(fix_results, timestamp):
    """Legacy function"""
    reporter = Reporter()
    return reporter.save_run_history(fix_results, timestamp)


def get_next_filename(directory, prefix, extension="txt"):
    """Legacy function"""
    reporter = Reporter(history_dir=directory)
    return reporter._get_next_filename(prefix, extension)