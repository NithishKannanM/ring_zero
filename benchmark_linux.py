"""
Ring Zero — Linux Benchmark Runner
===================================
Runs the Ring Zero orchestrator benchmark. When running as root with cgroup v2 
available, uses the real LinuxBackend. Otherwise, gracefully falls back to the
simulation-based MockBackend so benchmarks can always be generated.

Usage:
    sudo python benchmark_linux.py --limit 200          # Real Linux backend
    python benchmark_linux.py --limit 200               # Auto-fallback to simulation
    python benchmark_linux.py --limit 200 --simulate    # Force simulation mode
"""

import os
import sys
import time
import argparse
import json
import torch

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(__file__))

# --- Simulator / Orchestrator imports (always available) ---
from simulator.workload_generator import WorkloadGenerator
from simulator.memory_simulator import MemoryManager
from simulator.psi_monitor import PSIMonitor
from simulator.kernel_metrics import KernelMetrics
import simulator.cleanup as cleanup

from orchestrator.scoring_engine import ScoringEngine
from orchestrator.budget_manager import BudgetManager
from orchestrator.policy_manager import PolicyManager
from predictor.sasrec import SASRec

# ---------------------------------------------------------------------------
# Detect whether the real Linux backend (cgroup v2 + root) is usable
# ---------------------------------------------------------------------------
def can_use_linux_backend():
    """Return True if running as root and cgroup v2 filesystem is present."""
    if os.geteuid() != 0:
        return False
    return os.path.isdir("/sys/fs/cgroup") and os.path.exists("/sys/fs/cgroup/cgroup.controllers")


# ---------------------------------------------------------------------------
# Unified Memory Manager Wrapper
# ---------------------------------------------------------------------------
class SimulatedMemoryManager:
    """Wraps the simulator MemoryManager to expose the same interface as
    the LinuxMemoryManager used in the real-cgroup path."""

    def __init__(self, budget_mb):
        self.backend = MemoryManager(config_file="../config/simulator.yaml")
        self.backend.total_memory = budget_mb
        self.in_memory_apps = self.backend.in_memory_apps  # shared reference

    def preload(self, profile):
        self.backend.preload(profile)

    def keep(self, profile):
        self.backend.keep(profile)

    def evict(self, app_id):
        self.backend.evict(app_id)

    def launch(self, profile):
        return self.backend.launch(profile)

    def cleanup(self):
        self.backend.reset()

    def get_simulation_metrics(self):
        return self.backend.get_metrics()


class LinuxMemoryManager:
    """Real Linux backend path (cgroup v2 + mmap allocator)."""

    def __init__(self, backend):
        self.backend = backend
        self.in_memory_apps = set()

    def preload(self, profile):
        self.backend.allocate(profile)
        self.in_memory_apps.add(profile['app_id'])

    def keep(self, profile):
        pass

    def evict(self, app_id):
        self.backend.evict(app_id)
        self.in_memory_apps.discard(app_id)

    def cleanup(self):
        self.backend.cleanup()


# ---------------------------------------------------------------------------
# Core benchmark function
# ---------------------------------------------------------------------------
def run_benchmark(mode, budget_mb, limit, model, device, use_linux):
    print(f"\n{'='*60}")
    print(f"  {mode.upper()}  @  {budget_mb} MB  ({'Linux' if use_linux else 'Simulation'})")
    print(f"{'='*60}")

    # --- Build components ---
    workload = WorkloadGenerator(
        seqs_file="datasets/test_seqs.json",
        apps_config_file="config/apps.yaml",
        app2id_file="datasets/app2id.json",
    )

    bud_mgr = BudgetManager(total_budget_mb=budget_mb)
    scorer = ScoringEngine(mode=mode)

    if use_linux:
        from memory.linux_backend import LinuxBackend

        backend = LinuxBackend(memory_limit_mb=budget_mb)
        # Try to set the base cgroup memory.max
        base_cgroup_max = "/sys/fs/cgroup/ring_zero/memory.max"
        if os.path.exists(base_cgroup_max):
            try:
                with open(base_cgroup_max, 'w') as f:
                    f.write(str(budget_mb * 1024 * 1024))
            except PermissionError:
                print("  Warning: Could not write memory.max (Permission denied)")

        mem_mgr = LinuxMemoryManager(backend)
        metrics_reader = KernelMetrics()
        metrics_reader.snapshot_baseline()  # baseline before any allocations
        psi_mon = PSIMonitor()
    else:
        mem_mgr = SimulatedMemoryManager(budget_mb)
        metrics_reader = None
        psi_mon = None

    policy_mgr = PolicyManager(mem_mgr, bud_mgr, scorer, workload)

    # --- Stats ---
    warm_launches = 0
    cold_launches = 0
    total_latency = 0.0

    start_time = time.time()
    events = workload.generate(limit)

    try:
        with torch.no_grad():
            for i, event in enumerate(events):
                app_id = event['target']['app_id']
                profile = workload.get_app_profile(app_id)

                # --- PSI ---
                if use_linux:
                    current_psi = psi_mon.get_avg10()
                else:
                    # Simulated PSI from mock metrics
                    current_psi = 0.0
                    if hasattr(mem_mgr.backend, 'metrics'):
                        stall = mem_mgr.backend.metrics.get("psi_stall_ms", 0)
                        if stall > 0:
                            current_psi = (stall / 1000.0) * 5.0
                            mem_mgr.backend.metrics["psi_stall_ms"] = 0

                # 1. Orchestrate (skip for pure LRU baseline)
                if mode != "lru":
                    ctx = event['context']
                    apps_t = torch.tensor([ctx['apps']], dtype=torch.long, device=device)
                    hours_t = torch.tensor([ctx['hours']], dtype=torch.long, device=device)
                    days_t = torch.tensor([ctx['days']], dtype=torch.long, device=device)

                    logits = model(apps_t, hours_t, days_t)
                    probs = torch.softmax(logits[0], dim=0)

                    top_k = torch.topk(probs, k=5)
                    predictions = [
                        (top_k.indices[j].item(), top_k.values[j].item()) for j in range(5)
                    ]
                    policy_mgr.execute_policy(predictions, current_psi)

                # 2. Launch
                if use_linux:
                    if app_id in mem_mgr.in_memory_apps:
                        warm_launches += 1
                        total_latency += profile['launch_ms'] * 0.1
                        bud_mgr.remove_app(app_id)
                        bud_mgr.add_app(app_id, profile['memory_mb'])
                    else:
                        cold_launches += 1
                        total_latency += profile['launch_ms']
                        mem_mgr.preload(profile)
                        bud_mgr.add_app(app_id, profile['memory_mb'])
                else:
                    # Simulation path — use MemoryManager.launch()
                    is_cold = app_id not in mem_mgr.in_memory_apps
                    latency = mem_mgr.launch(profile)
                    total_latency += latency
                    if is_cold:
                        cold_launches += 1
                        bud_mgr.add_app(app_id, profile['memory_mb'])
                    else:
                        warm_launches += 1
                        bud_mgr.remove_app(app_id)
                        bud_mgr.add_app(app_id, profile['memory_mb'])

                # 3. LRU eviction if over budget
                while bud_mgr.current_ram_mb > bud_mgr.total_budget_mb:
                    evict_id = bud_mgr.get_lru_app()
                    if evict_id:
                        mem_mgr.evict(evict_id)
                        bud_mgr.remove_app(evict_id)
                    else:
                        break

                if (i + 1) % 50 == 0:
                    print(f"  Processed {i + 1}/{limit} events...")

        end_time = time.time()

        total_launches = warm_launches + cold_launches
        warm_rate = warm_launches / total_launches if total_launches > 0 else 0
        avg_latency = total_latency / total_launches if total_launches > 0 else 0

        # Faults
        if use_linux:
            time.sleep(0.5)
            fault_metrics = metrics_reader.get_all_fault_metrics()
            page_faults = fault_metrics["page_faults"]
            major_faults = fault_metrics["major_page_faults"]
        else:
            sim_metrics = mem_mgr.get_simulation_metrics()
            # Simulation reports minor+major combined as 'major_page_faults'
            page_faults = int(sim_metrics.get('major_page_faults', 0))
            major_faults = 0

        result = {
            "Budget": budget_mb,
            "Policy": mode,
            "Warm Launch Rate (%)": round(warm_rate * 100, 2),
            "Avg Latency (ms)": round(avg_latency, 2),
            "Page Faults": page_faults,
            "Major Faults": major_faults,
            "Time (s)": round(end_time - start_time, 2),
            "Evictions": policy_mgr.kpi.get("actions_evict", 0),
            "Prewarms": policy_mgr.kpi.get("actions_prewarm", 0),
            "PSI Throttles": policy_mgr.kpi.get("psi_throttles", 0),
            "Final PSI": psi_mon.get_avg10() if psi_mon else current_psi,
        }

        print(f"\n  Warm Rate:    {result['Warm Launch Rate (%)']:.2f}%")
        print(f"  Avg Latency:  {result['Avg Latency (ms)']:.2f} ms")
        print(f"  Page Faults:  {result['Page Faults']:,}")
        print(f"  Major Faults: {result['Major Faults']:,}")
        print(f"  Evictions:    {result['Evictions']}")
        print(f"  Prewarms:     {result['Prewarms']}")
        print(f"  Time:         {result['Time (s)']:.2f} s")

    finally:
        mem_mgr.cleanup()

    return result


# ---------------------------------------------------------------------------
# Plot generation
# ---------------------------------------------------------------------------
def generate_plots(results, output_dir):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print("\n[!] matplotlib not installed — skipping plot generation.")
        return

    os.makedirs(output_dir, exist_ok=True)

    policies = sorted(set(r["Policy"] for r in results))
    budgets = sorted(set(r["Budget"] for r in results), reverse=True)

    # Color palette — premium look
    colors = {
        "lru": "#6b7280",
        "prediction_only": "#3b82f6",
        "prediction_cost": "#f59e0b",
        "full_ring_zero": "#10b981",
    }

    metrics_to_plot = [
        ("Warm Launch Rate (%)", "warm_rate.png", "Warm Launch Rate (%) vs Memory Budget"),
        ("Avg Latency (ms)", "latency.png", "Avg Latency (ms) vs Memory Budget"),
        ("Page Faults", "faults.png", "Page Faults vs Memory Budget"),
    ]

    for metric, filename, title in metrics_to_plot:
        fig, ax = plt.subplots(figsize=(10, 6))
        fig.patch.set_facecolor('#0f172a')
        ax.set_facecolor('#1e293b')

        for policy in policies:
            data = [r for r in results if r["Policy"] == policy]
            data.sort(key=lambda r: r["Budget"], reverse=True)
            xs = [r["Budget"] for r in data]
            ys = [r[metric] for r in data]
            color = colors.get(policy, "#ffffff")
            ax.plot(xs, ys, marker='o', label=policy, color=color, linewidth=2.5, markersize=8)

        ax.set_title(title, fontsize=14, fontweight='bold', color='white', pad=15)
        ax.set_xlabel("Memory Budget (MB)", fontsize=12, color='#94a3b8')
        ax.set_ylabel(metric, fontsize=12, color='#94a3b8')
        ax.invert_xaxis()
        ax.legend(fontsize=10, facecolor='#334155', edgecolor='#475569', labelcolor='white')
        ax.grid(True, alpha=0.2, color='#475569')
        ax.tick_params(colors='#94a3b8')
        for spine in ax.spines.values():
            spine.set_color('#475569')

        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, filename), dpi=150, facecolor=fig.get_facecolor())
        plt.close()
        print(f"  Saved: {os.path.join(output_dir, filename)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    cleanup.register_cleanup_handlers()

    parser = argparse.ArgumentParser(description="Ring Zero Benchmark Runner")
    parser.add_argument("--limit", type=int, default=100, help="Number of events to process")
    parser.add_argument("--simulate", action="store_true", help="Force simulation mode (no cgroups)")
    args = parser.parse_args()

    # Detect mode
    use_linux = can_use_linux_backend() and not args.simulate
    mode_label = "LINUX (cgroup v2)" if use_linux else "SIMULATION (MockBackend)"
    print(f"\n{'#'*60}")
    print(f"  Ring Zero Benchmark — {mode_label}")
    print(f"  Events: {args.limit}")
    print(f"{'#'*60}")

    if not use_linux:
        print("\n  [i] Not running as root or cgroup v2 unavailable.")
        print("      Using simulation fallback (MockBackend).\n")

    # Load model
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    with open('datasets/app2id.json', 'r') as f:
        app2id = json.load(f)
        vocab_size = len(app2id)

    model = SASRec(vocab_size=vocab_size, max_seq_len=20).to(device)
    model.load_state_dict(
        torch.load('predictor/sasrec_model.pt', map_location=device, weights_only=True)
    )
    model.eval()
    print(f"  Model loaded ({vocab_size} apps, device={device})")

    # Sweep
    budgets = [400, 300, 200, 100]
    modes = ["lru", "prediction_cost", "full_ring_zero"]
    all_results = []

    for budget in budgets:
        for mode in modes:
            try:
                result = run_benchmark(mode, budget, args.limit, model, device, use_linux)
                all_results.append(result)
            except Exception as e:
                import traceback
                print(f"\n  FAILED: {mode} @ {budget}MB")
                traceback.print_exc()
            time.sleep(0.5)

    # --- Save results ---
    results_dir = os.path.join(os.path.dirname(__file__), "benchmarking")
    plots_dir = os.path.join(results_dir, "plots")
    os.makedirs(plots_dir, exist_ok=True)

    results_file = os.path.join(results_dir, "benchmark_results.json")
    with open(results_file, 'w') as f:
        json.dump(all_results, f, indent=2)
    print(f"\n  Results saved to: {results_file}")

    # --- Generate plots ---
    print("\n  Generating plots...")
    generate_plots(all_results, plots_dir)

    print(f"\n{'='*90}")
    print(f"  {'Policy':<20} {'Budget':>8} {'Warm%':>8} {'Latency':>10} {'Page Faults':>14} {'Maj Faults':>12} {'Evict':>8} {'Prewarm':>8}")
    print(f"  {'-'*84}")
    for r in all_results:
        print(
            f"  {r['Policy']:<20} {r['Budget']:>6}MB"
            f" {r['Warm Launch Rate (%)']:>7.1f}%"
            f" {r['Avg Latency (ms)']:>9.1f}ms"
            f" {r['Page Faults']:>13,}"
            f" {r['Major Faults']:>11,}"
            f" {r['Evictions']:>7}"
            f" {r['Prewarms']:>7}"
        )
    print(f"{'='*90}\n")
    print("Benchmark complete!")
