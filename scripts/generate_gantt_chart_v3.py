# -*- coding: utf-8 -*-
"""
Gantt Chart Visualization v3
"""

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib import rcParams
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

from typing import List, Dict, Any

# Font setup when matplotlib is available
if MATPLOTLIB_AVAILABLE:
    rcParams['font.sans-serif'] = ['DejaVu Sans']
    rcParams['axes.unicode_minus'] = False


class GanttChartGenerator:
    """Generate gantt chart from process event logs."""

    def __init__(self, figsize=(20, 12)):
        self.figsize = figsize
        self.fig = None
        self.ax = None
        self.colors = {
            'new': '#3498db',
            'rework': '#e74c3c',
            'packed': '#2ecc71',
            'idle': '#ecf0f1',
        }

    def generate(self, env_a, env_b, env_c, output_path: str = 'gantt_chart.png'):
        """Generate and save gantt chart."""
        if not MATPLOTLIB_AVAILABLE:
            print("[Gantt] matplotlib is not installed. Skipping chart generation.")
            return None

        print("[Gantt] Generating gantt chart...")

        all_events = []
        all_events.extend(self._process_events(env_a.event_log, 'A'))
        all_events.extend(self._process_events(env_b.event_log, 'B'))
        all_events.extend(self._process_events(env_c.event_log, 'C'))

        max_time = max((e['end_time'] for e in all_events), default=100)
        machines = self._get_machines(env_a, env_b, env_c)

        self.fig, self.ax = plt.subplots(figsize=self.figsize)

        for event in all_events:
            self._draw_bar(event, machines)

        self._setup_axes(machines, max_time)
        self._add_legend()

        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"[Gantt] Saved chart: {output_path}")
        plt.close()

        return output_path

    def _process_events(self, event_log: List[Dict[str, Any]], process: str) -> List[Dict[str, Any]]:
        """Convert raw log events to gantt rows."""
        processed = []

        for event in event_log:
            if event['event_type'] == 'task_assigned':
                processed.append({
                    'process': process,
                    'machine_id': event['machine_id'],
                    'task_uids': event['task_uids'],
                    'start_time': event['start_time'],
                    'end_time': event['end_time'],
                    'task_type': event['task_type'],
                    'event_type': 'assigned',
                })
            elif event['event_type'] == 'pack_completed':
                processed.append({
                    'process': process,
                    'machine_id': event['machine_id'],
                    'task_uids': event['task_uids'],
                    'start_time': event['start_time'],
                    'end_time': event['end_time'],
                    'task_type': 'packed',
                    'event_type': 'completed',
                })

        return processed

    def _get_machines(self, env_a, env_b, env_c) -> Dict[str, int]:
        """Build machine -> y-axis index map."""
        machines = {}
        y_pos = 0

        for m_id in sorted(env_a.machines.keys()):
            machines[f'A_{m_id}'] = y_pos
            y_pos += 1

        for m_id in sorted(env_b.machines.keys()):
            machines[f'B_{m_id}'] = y_pos
            y_pos += 1

        for m_id in sorted(env_c.machines.keys()):
            machines[f'C_{m_id}'] = y_pos
            y_pos += 1

        return machines

    def _draw_bar(self, event: Dict[str, Any], machines: Dict[str, int]):
        """Draw one gantt bar."""
        machine_name = event['machine_id']
        if machine_name not in machines:
            return

        y_pos = machines[machine_name]
        start = event['start_time']
        duration = event['end_time'] - event['start_time']
        task_type = event['task_type']
        task_uids = event['task_uids']

        color = self.colors.get(task_type, '#95a5a6')

        self.ax.barh(
            y_pos,
            duration,
            left=start,
            height=0.8,
            color=color,
            edgecolor='black',
            linewidth=1.5,
            alpha=0.8,
        )

        label_text = f"[{','.join(map(str, task_uids))}]"
        if duration > 0:
            self.ax.text(start + duration / 2, y_pos, label_text, ha='center', va='center', fontsize=8, fontweight='bold')

    def _setup_axes(self, machines: Dict[str, int], max_time: int):
        """Configure chart axes."""
        y_labels = list(machines.keys())
        y_positions = list(machines.values())
        self.ax.set_yticks(y_positions)
        self.ax.set_yticklabels(y_labels, fontsize=10)

        self.ax.set_xlim(0, max_time + 5)
        self.ax.set_xlabel('Time', fontsize=12, fontweight='bold')
        self.ax.set_ylabel('Process & Machine', fontsize=12, fontweight='bold')
        self.ax.set_title('Gantt Chart - Task Scheduling', fontsize=14, fontweight='bold')

        self.ax.grid(True, axis='x', alpha=0.3)
        self.ax.set_axisbelow(True)

    def _add_legend(self):
        """Add legend."""
        legend_elements = [
            mpatches.Patch(color=self.colors['new'], label='New Task'),
            mpatches.Patch(color=self.colors['rework'], label='Rework Task'),
            mpatches.Patch(color=self.colors['packed'], label='Packed'),
        ]
        self.ax.legend(handles=legend_elements, loc='upper right', fontsize=10)


class ValidationReport:
    """Generate synchronization validation report."""

    def __init__(self):
        self.checks = {}

    def validate_sync(self, env_a, env_b, env_c, expect_rework: bool = False) -> bool:
        """
        Validate sync rules.

        Args:
            expect_rework: when True, at least one task should be assigned to A more than once.
        """
        print("\n[Validation] Starting sync validation...")

        issues = []

        print("[Check 1] Process time consistency...")
        issues_time = self._check_process_times(env_a, env_b, env_c)
        if issues_time:
            print(f"  - Warning: found {len(issues_time)} process time mismatch(es)")
            issues.extend(issues_time)
        else:
            print("  [OK] Process times are consistent")

        print("[Check 2] Task flow consistency (A->B->C)...")
        issues_flow = self._check_task_flow(env_a, env_b, env_c)
        if issues_flow:
            print(f"  - Warning: found {len(issues_flow)} task flow issue(s)")
            issues.extend(issues_flow)
        else:
            print("  [OK] Task flow is consistent")

        print("[Check 3] Rework policy...")
        issues_rework = self._check_rework(env_a, env_b, env_c, expect_rework=expect_rework)
        if issues_rework:
            print(f"  - Warning: found {len(issues_rework)} rework issue(s)")
            issues.extend(issues_rework)
        else:
            print("  [OK] Rework policy check passed")

        print("[Check 4] Machine overlap...")
        issues_machine = self._check_machine_state(env_a, env_b, env_c)
        if issues_machine:
            print(f"  - Warning: found {len(issues_machine)} machine overlap issue(s)")
            issues.extend(issues_machine)
        else:
            print("  [OK] No machine overlap detected")

        self.checks = {
            'time_sync': len(issues_time) == 0,
            'task_flow': len(issues_flow) == 0,
            'rework': len(issues_rework) == 0,
            'machine_state': len(issues_machine) == 0,
            'total_issues': len(issues),
        }

        print(f"\n[Validation] Total issues: {len(issues)}")
        return len(issues) == 0

    def _check_process_times(self, env_a, env_b, env_c) -> List[str]:
        """Validate per-process durations."""
        issues = []

        for event in env_a.event_log:
            if event['event_type'] == 'task_assigned':
                expected_duration = env_a.process_time
                actual_duration = event['end_time'] - event['start_time']
                if actual_duration != expected_duration:
                    issues.append(f"A process task {event['task_uids']}: expected {expected_duration}, got {actual_duration}")

        for event in env_b.event_log:
            if event['event_type'] == 'task_assigned':
                expected_duration = env_b.process_time
                actual_duration = event['end_time'] - event['start_time']
                if actual_duration != expected_duration:
                    issues.append(f"B process task {event['task_uids']}: expected {expected_duration}, got {actual_duration}")

        return issues

    def _check_task_flow(self, env_a, env_b, env_c) -> List[str]:
        """Validate A completion precedes B assignment."""
        issues = []

        a_completed_by_time = {}
        for event in env_a.event_log:
            if event['event_type'] == 'task_completed':
                for uid in event['task_uids']:
                    if uid not in a_completed_by_time:
                        a_completed_by_time[uid] = []
                    a_completed_by_time[uid].append(event['end_time'])

        for event in env_b.event_log:
            if event['event_type'] == 'task_assigned':
                b_assign_time = event['start_time']
                for uid in event['task_uids']:
                    if uid not in a_completed_by_time:
                        issues.append(f"Task {uid}: assigned in B at {b_assign_time}, but no A completion found")
                    else:
                        prior_completions = [t for t in a_completed_by_time[uid] if t <= b_assign_time]
                        if not prior_completions:
                            min_a_time = min(a_completed_by_time[uid])
                            issues.append(f"Task {uid}: A complete at {min_a_time} after B assign at {b_assign_time}")

        return issues

    def _check_rework(self, env_a, env_b, env_c, expect_rework: bool = False) -> List[str]:
        """Validate rework presence only when required."""
        issues = []

        a_assigned = {}
        for event in env_a.event_log:
            if event['event_type'] == 'task_assigned':
                for uid in event['task_uids']:
                    if uid not in a_assigned:
                        a_assigned[uid] = []
                    a_assigned[uid].append(event)

        if expect_rework:
            rework_found = any(len(assignments) > 1 for assignments in a_assigned.values())
            if not rework_found and len(a_assigned) > 0:
                issues.append("Expected rework but no task was assigned more than once in process A")

        return issues

    def _check_machine_state(self, env_a, env_b, env_c) -> List[str]:
        """Validate no overlapping assignment on the same machine."""
        issues = []

        def check_overlaps(events):
            machine_timings = {}
            for event in events:
                if event['event_type'] == 'task_assigned':
                    m_id = event['machine_id']
                    if m_id not in machine_timings:
                        machine_timings[m_id] = []
                    machine_timings[m_id].append((event['start_time'], event['end_time']))

            issues_local = []
            for m_id, timings in machine_timings.items():
                for i, (s1, e1) in enumerate(timings):
                    for j, (s2, e2) in enumerate(timings):
                        if i < j and not (e1 <= s2 or e2 <= s1):
                            issues_local.append(f"Machine {m_id}: overlapping ranges ({s1}~{e1}) and ({s2}~{e2})")
            return issues_local

        issues.extend(check_overlaps(env_a.event_log))
        issues.extend(check_overlaps(env_b.event_log))

        return issues

    def print_report(self):
        """Print validation report."""
        print("\n" + "=" * 60)
        print("VALIDATION REPORT")
        print("=" * 60)
        print(f"Time Sync: {'PASS' if self.checks.get('time_sync') else 'FAIL'}")
        print(f"Task Flow: {'PASS' if self.checks.get('task_flow') else 'FAIL'}")
        print(f"Rework:    {'PASS' if self.checks.get('rework') else 'FAIL'}")
        print(f"Machine State: {'PASS' if self.checks.get('machine_state') else 'FAIL'}")
        print(f"Total Issues: {self.checks.get('total_issues', 0)}")
        print("=" * 60)


if __name__ == '__main__':
    print("[Test] Gantt Chart Generator test module")
    print("Use as: from generate_gantt_chart_v3 import GanttChartGenerator, ValidationReport")
