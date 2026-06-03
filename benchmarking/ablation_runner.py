import os
import sys
import torch
import json
import argparse

sys.path.append(os.path.join(os.path.dirname(__file__), '../simulator'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../orchestrator'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../predictor'))

from memory_simulator import MemoryManager
from budget_manager import BudgetManager
from scoring_engine import ScoringEngine
from policy_manager import PolicyManager
from workload_generator import WorkloadGenerator
from sasrec import SASRec

# DummyScoringEngine removed in favor of real ScoringEngine

def run_ablation(mode, generator_limit, args):
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    
    # Init predictor
    with open(os.path.join(args.data_dir, 'app2id.json'), 'r') as f:
        app2id = json.load(f)
        vocab_size = len(app2id)
        
    model = SASRec(vocab_size=vocab_size, max_seq_len=20).to(device)
    model.load_state_dict(torch.load(os.path.join(args.model_dir, 'sasrec_model.pt'), map_location=device, weights_only=True))
    model.eval()
    
    # Init Simulator components
    mem_mgr = MemoryManager(config_file=os.path.join(args.config_dir, "simulator.yaml"))
    bud_mgr = BudgetManager(total_budget_mb=mem_mgr.total_memory)
    scorer = ScoringEngine(mode=mode)
    
    workload_gen = WorkloadGenerator(
        seqs_file=os.path.join(args.data_dir, "test_seqs.json"),
        apps_config_file=os.path.join(args.config_dir, "apps.yaml"),
        app2id_file=os.path.join(args.data_dir, "app2id.json")
    )
    
    policy_mgr = PolicyManager(mem_mgr, bud_mgr, scorer, workload_gen)
    
    print(f"\n--- Running Ablation: {mode.upper()} ---")
    print(f"Memory Budget: {bud_mgr.total_budget_mb} MB")
    
    current_psi = 0.0 # Simulated PSI
    
    with torch.no_grad():
        for i, event in enumerate(workload_gen.generate(limit=generator_limit)):
            # 1. Run predictor
            ctx = event['context']
            apps_t = torch.tensor([ctx['apps']], dtype=torch.long, device=device)
            hours_t = torch.tensor([ctx['hours']], dtype=torch.long, device=device)
            days_t = torch.tensor([ctx['days']], dtype=torch.long, device=device)
            
            logits = model(apps_t, hours_t, days_t)
            probs = torch.softmax(logits[0], dim=0)
            
            # Top 5 predictions
            top_k = torch.topk(probs, k=5)
            predictions = [(top_k.indices[j].item(), top_k.values[j].item()) for j in range(5)]
            
            # 2. Update simulated PSI (decay old, add from last event's stall)
            current_psi = max(0.0, current_psi * 0.9)
            if mem_mgr.metrics["psi_stall_ms"] > 0:
                 current_psi += (mem_mgr.metrics["psi_stall_ms"] / 1000.0) * 5.0
                 mem_mgr.metrics["psi_stall_ms"] = 0 # reset simulated stall after absorbing
            
            # 3. Policy Manager executes orchestration BEFORE launch (prewarming/evicting)
            if mode != "lru":
                policy_mgr.execute_policy(predictions, current_psi)
            
            # 4. The actual app is launched by the user
            target_profile = event['target']
            
            # LRU logic (baseline) - purely reactive
            if mode == "lru":
                if target_profile['app_id'] not in mem_mgr.in_memory_apps:
                    # Need to make space if out of budget for cold launch
                    while not bud_mgr.has_budget_for(target_profile['memory_mb']) and len(mem_mgr.in_memory_apps) > 0:
                        app_to_evict = list(mem_mgr.in_memory_apps)[0]
                        mem_mgr.evict(app_to_evict)
                        bud_mgr.remove_app(app_to_evict)
                        
            # Execute launch
            is_cold = target_profile['app_id'] not in mem_mgr.in_memory_apps
            mem_mgr.launch(target_profile)
            
            # Post-launch budget sync
            if is_cold:
                bud_mgr.add_app(target_profile['app_id'], target_profile['memory_mb'])
                # If prediction policy caused a cold launch, we need to ensure budget is maintained
                if mode != "lru":
                    while bud_mgr.current_ram_mb > bud_mgr.total_budget_mb and len(mem_mgr.in_memory_apps) > 1:
                        # Evict randomly to simulate OS OOM killer / reactive reclaim
                        evict_candidates = [app for app in mem_mgr.in_memory_apps if app != target_profile['app_id']]
                        if not evict_candidates: break
                        app_to_evict = evict_candidates[0]
                        mem_mgr.evict(app_to_evict)
                        bud_mgr.remove_app(app_to_evict)
            
    # Results
    metrics = mem_mgr.get_metrics()
    print(f"Warm Launch Rate:  {metrics['warm_launch_rate']*100:.2f}%")
    print(f"Avg Latency:       {metrics['avg_latency_ms']:.2f} ms")
    print(f"Total Evictions:   {metrics['evictions']}")
    print(f"Major Page Faults: {metrics['major_page_faults']}")
    
    if mode != "lru":
        policy_mgr.print_kpis()
        
    return metrics

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", type=str, default=os.path.join(os.path.dirname(__file__), "../datasets"))
    parser.add_argument("--model_dir", type=str, default=os.path.join(os.path.dirname(__file__), "../predictor"))
    parser.add_argument("--config_dir", type=str, default=os.path.join(os.path.dirname(__file__), "../config"))
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()
    
    modes = ["lru", "prediction_only", "prediction_cost", "full_ring_zero"]
    
    for mode in modes:
        run_ablation(mode, args.limit, args)


#micromamba run -n ai python benchmarking/ablation_runner.py --limit 1000