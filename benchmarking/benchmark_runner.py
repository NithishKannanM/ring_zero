import os
import sys
import torch
import json
import argparse
import psutil
import pandas as pd
import matplotlib.pyplot as plt

sys.path.append(os.path.join(os.path.dirname(__file__), '../simulator'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../orchestrator'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../predictor'))

from memory_simulator import MemoryManager
from budget_manager import BudgetManager
from scoring_engine import ScoringEngine
from policy_manager import PolicyManager
from workload_generator import WorkloadGenerator
from sasrec import SASRec

def get_rss():
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)

# DummyScoringEngine removed in favor of real ScoringEngine

def run_simulation(mode, budget, generator_limit, args, model, app2id, device):
    mem_mgr = MemoryManager(config_file=os.path.join(args.config_dir, "simulator.yaml"))
    # Override budget
    mem_mgr.total_memory = budget
    bud_mgr = BudgetManager(total_budget_mb=budget)
    scorer = ScoringEngine(mode=mode)
    
    workload_gen = WorkloadGenerator(
        seqs_file=os.path.join(args.data_dir, "test_seqs.json"),
        apps_config_file=os.path.join(args.config_dir, "apps.yaml"),
        app2id_file=os.path.join(args.data_dir, "app2id.json")
    )
    
    policy_mgr = PolicyManager(mem_mgr, bud_mgr, scorer, workload_gen)
    
    current_psi = 0.0
    
    with torch.no_grad():
        for i, event in enumerate(workload_gen.generate(limit=generator_limit)):
            ctx = event['context']
            apps_t = torch.tensor([ctx['apps']], dtype=torch.long, device=device)
            hours_t = torch.tensor([ctx['hours']], dtype=torch.long, device=device)
            days_t = torch.tensor([ctx['days']], dtype=torch.long, device=device)
            
            logits = model(apps_t, hours_t, days_t)
            probs = torch.softmax(logits[0], dim=0)
            
            top_k = torch.topk(probs, k=5)
            predictions = [(top_k.indices[j].item(), top_k.values[j].item()) for j in range(5)]
            
            current_psi = max(0.0, current_psi * 0.9)
            if mem_mgr.metrics["psi_stall_ms"] > 0:
                 current_psi += (mem_mgr.metrics["psi_stall_ms"] / 1000.0) * 5.0
                 mem_mgr.metrics["psi_stall_ms"] = 0
            
            if mode != "lru":
                policy_mgr.execute_policy(predictions, current_psi)
            
            target_profile = event['target']
            
            if mode == "lru":
                if target_profile['app_id'] not in mem_mgr.in_memory_apps:
                    while not bud_mgr.has_budget_for(target_profile['memory_mb']) and len(mem_mgr.in_memory_apps) > 0:
                        app_to_evict = list(mem_mgr.in_memory_apps)[0]
                        mem_mgr.evict(app_to_evict)
                        bud_mgr.remove_app(app_to_evict)
                        
            is_cold = target_profile['app_id'] not in mem_mgr.in_memory_apps
            mem_mgr.launch(target_profile)
            
            if is_cold:
                bud_mgr.add_app(target_profile['app_id'], target_profile['memory_mb'])
                if mode != "lru":
                    while bud_mgr.current_ram_mb > bud_mgr.total_budget_mb and len(mem_mgr.in_memory_apps) > 1:
                        evict_candidates = [app for app in mem_mgr.in_memory_apps if app != target_profile['app_id']]
                        if not evict_candidates: break
                        app_to_evict = evict_candidates[0]
                        mem_mgr.evict(app_to_evict)
                        bud_mgr.remove_app(app_to_evict)
                        
    metrics = mem_mgr.get_metrics()
    kpis = policy_mgr.kpi if mode != "lru" else {}
    return metrics, kpis

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", type=str, default=os.path.join(os.path.dirname(__file__), "../datasets"))
    parser.add_argument("--model_dir", type=str, default=os.path.join(os.path.dirname(__file__), "../predictor"))
    parser.add_argument("--config_dir", type=str, default=os.path.join(os.path.dirname(__file__), "../config"))
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()

    print("--- Memory Accounting ---")
    rss_base = get_rss()
    print(f"Base Python RSS: {rss_base:.2f} MB")
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    with open(os.path.join(args.data_dir, 'app2id.json'), 'r') as f:
        app2id = json.load(f)
        vocab_size = len(app2id)
        
    model = SASRec(vocab_size=vocab_size, max_seq_len=20).to(device)
    model.load_state_dict(torch.load(os.path.join(args.model_dir, 'sasrec_model.pt'), map_location=device, weights_only=True))
    model.eval()
    
    rss_after_model = get_rss()
    print(f"Predictor RSS (Model + PyTorch): {rss_after_model - rss_base:.2f} MB")
    
    budgets = [400, 300, 200, 100]
    modes = ["lru", "prediction_only", "prediction_cost", "full_ring_zero"]
    
    results = []
    
    print("\n--- Starting Benchmark Sweep ---")
    for budget in budgets:
        print(f"\nEvaluating Budget: {budget} MB")
        for mode in modes:
            print(f"  -> Running {mode}...", end="", flush=True)
            metrics, kpis = run_simulation(mode, budget, args.limit, args, model, app2id, device)
            
            results.append({
                "Budget": budget,
                "Policy": mode,
                "Warm Launch Rate (%)": metrics['warm_launch_rate'] * 100,
                "Avg Latency (ms)": metrics['avg_latency_ms'],
                "Major Faults": metrics['major_page_faults'],
                "PSI Triggers": kpis.get("psi_triggers", 0),
                "Cost Penalties": kpis.get("cost_penalties", 0),
                "Actions Keep": kpis.get("actions_keep", 0),
                "Actions Prewarm": kpis.get("actions_prewarm", 0),
                "Actions Evict": kpis.get("actions_evict", 0),
            })
            print(f" (Warm Rate: {metrics['warm_launch_rate']*100:.1f}%)")
            
    df = pd.DataFrame(results)
    
    os.makedirs(os.path.join(os.path.dirname(__file__), "plots"), exist_ok=True)
    
    # Plotting
    metrics_to_plot = [
        ("Warm Launch Rate (%)", "warm_rate.png"),
        ("Avg Latency (ms)", "latency.png"),
        ("Major Faults", "faults.png")
    ]
    
    for metric, filename in metrics_to_plot:
        plt.figure(figsize=(10, 6))
        for mode in modes:
            subset = df[df["Policy"] == mode]
            plt.plot(subset["Budget"], subset[metric], marker='o', label=mode)
            
        plt.title(f"{metric} vs Memory Budget")
        plt.xlabel("Memory Budget (MB)")
        plt.ylabel(metric)
        plt.gca().invert_xaxis() # Show constrained on the right
        plt.legend()
        plt.grid(True)
        plt.savefig(os.path.join(os.path.dirname(__file__), "plots", filename))
        plt.close()
        
    print("\nBenchmark Complete! Plots saved to benchmarking/plots/")
    
    print("\n--- Summary for Budget 400 MB ---")
    print(df[df["Budget"] == 400].to_string(index=False))

if __name__ == "__main__":
    main()
