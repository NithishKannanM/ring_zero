from budget_manager import BudgetManager
from scoring_engine import ScoringEngine
from constants import PSI_LOW, PSI_MEDIUM, PSI_HIGH
import sys
import os
import time

# Ensure workload_generator is in path
sys.path.append(os.path.join(os.path.dirname(__file__), '../simulator'))
from workload_generator import WorkloadGenerator

class PolicyManager:
    def __init__(self, memory_manager, budget_manager, scoring_engine, workload_generator):
        self.memory_manager = memory_manager
        self.budget = budget_manager
        self.scorer = scoring_engine
        self.workload = workload_generator
        
        # KPI Tracking
        self.kpi = {
            "total_evaluations": 0,
            "total_eval_time_ms": 0.0,
            "max_eval_time_ms": 0.0,
            "actions_keep": 0,
            "actions_prewarm": 0,
            "actions_evict": 0,
            "psi_triggers": 0,
            "psi_throttles": 0,
            "psi_rejected_predictions": 0,
            "budget_rejected_apps": 0,
        }
        
    def _get_rss_mb(self):
        try:
            import psutil
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / (1024 * 1024)
        except ImportError:
            return 0.0
        
    def execute_policy(self, predictions, current_psi=0.0):
        start_time = time.perf_counter()
        
        # Throttling Top-K predictions based on PSI (Full Ring Zero logic)
        original_pred_len = len(predictions)
        if self.scorer.mode == "full_ring_zero":
            if current_psi > PSI_MEDIUM:
                predictions = predictions[:1]
                self.kpi["psi_throttles"] += 1
            elif current_psi > PSI_LOW:
                predictions = predictions[:2]
                self.kpi["psi_throttles"] += 1
            else:
                predictions = predictions[:3]
                
        self.kpi["psi_rejected_predictions"] += (original_pred_len - len(predictions))
        
        scores = {}
        for app_id, prob in predictions:
            profile = self.workload.get_app_profile(app_id)
            score = self.scorer.compute_score(prob, profile['launch_ms'], current_psi, profile['memory_mb'])
            
            # Record if PSI actively degraded the score
            if self.scorer.get_psi_modifier(current_psi) < 1.0:
                self.kpi["psi_triggers"] += 1
                
            scores[app_id] = {'score': score, 'profile': profile, 'prob': prob}
            
        for app_id in list(self.memory_manager.in_memory_apps):
            if app_id not in scores:
                profile = self.workload.get_app_profile(app_id)
                score = self.scorer.compute_score(0.01, profile['launch_ms'], current_psi, profile['memory_mb'])
                scores[app_id] = {'score': score, 'profile': profile, 'prob': 0.01}
                
        sorted_apps = sorted(scores.items(), key=lambda x: x[1]['score'], reverse=True)
        
        new_memory_state = set()
        current_budget_used = 0
        
        effective_budget = self.budget.total_budget_mb
        
        # Exponential budget reduction for Full Ring Zero
        if self.scorer.mode == "full_ring_zero":
            if current_psi > PSI_HIGH:
                effective_budget *= 0.4
            elif current_psi > PSI_MEDIUM:
                effective_budget *= 0.6
            elif current_psi > PSI_LOW:
                effective_budget *= 0.8
                
        for app_id, data in sorted_apps:
            profile = data['profile']
            mem = profile['memory_mb']
            
            if current_budget_used + mem <= effective_budget:
                new_memory_state.add(app_id)
                current_budget_used += mem
            else:
                self.kpi["budget_rejected_apps"] += 1
                
        # 4. Execute Actions
        for app_id in list(self.memory_manager.in_memory_apps):
            if app_id not in new_memory_state:
                self.memory_manager.evict(app_id)
                self.budget.remove_app(app_id)
                self.kpi["actions_evict"] += 1
                
        for app_id in new_memory_state:
            profile = scores[app_id]['profile']
            if app_id not in self.memory_manager.in_memory_apps:
                self.memory_manager.preload(profile)
                self.kpi["actions_prewarm"] += 1
            else:
                self.memory_manager.keep(profile)
                self.kpi["actions_keep"] += 1
            self.budget.add_app(app_id, profile['memory_mb'])
            
        end_time = time.perf_counter()
        eval_time_ms = (end_time - start_time) * 1000
        
        self.kpi["total_evaluations"] += 1
        self.kpi["total_eval_time_ms"] += eval_time_ms
        if eval_time_ms > self.kpi["max_eval_time_ms"]:
            self.kpi["max_eval_time_ms"] = eval_time_ms
            
    def print_kpis(self):
        avg_eval = self.kpi["total_eval_time_ms"] / max(1, self.kpi["total_evaluations"])
        rss_mb = self._get_rss_mb()
        print("\n--- Orchestrator KPIs ---")
        print(f"Avg Policy Eval Time: {avg_eval:.4f} ms")
        print(f"Max Policy Eval Time: {self.kpi['max_eval_time_ms']:.4f} ms")
        print(f"Total KEEP actions:   {self.kpi['actions_keep']}")
        print(f"Total PREWARM actions:{self.kpi['actions_prewarm']}")
        print(f"Total EVICT actions:  {self.kpi['actions_evict']}")
        print(f"PSI Score Triggers:   {self.kpi['psi_triggers']}")
        print(f"PSI Throttles:        {self.kpi['psi_throttles']}")
        print(f"PSI Rejected Preds:   {self.kpi['psi_rejected_predictions']}")
        print(f"Budget Rejected Apps: {self.kpi['budget_rejected_apps']}")
        if rss_mb > 0:
            print(f"Daemon Memory Footprint (RSS): {rss_mb:.2f} MB")
        print("-------------------------\n")
