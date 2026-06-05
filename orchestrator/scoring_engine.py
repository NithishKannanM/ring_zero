from orchestrator.constants import PSI_LOW, PSI_MEDIUM, PSI_HIGH

class ScoringEngine:
    def __init__(self, mode="full_ring_zero"):
        """
        mode: one of 'prediction_only', 'prediction_cost', 'full_ring_zero'
        """
        self.mode = mode

    def get_psi_modifier(self, current_psi):
        """
        Returns a small penalty multiplier if PSI is elevated, preserving ranking mostly.
        """
        if self.mode == "full_ring_zero" and current_psi > PSI_MEDIUM:
            return 0.9
        return 1.0
        
    def compute_score(self, prediction_prob, launch_cost_ms, current_psi, memory_mb):
        if self.mode == "prediction_only":
            return prediction_prob
            
        mem = memory_mb if memory_mb > 0 else 1
        
        if self.mode == "prediction_cost":
            return (prediction_prob * launch_cost_ms) / mem
            
        if self.mode == "full_ring_zero":
            score = (prediction_prob * launch_cost_ms) / mem
            score *= self.get_psi_modifier(current_psi)
            return score
            
        return 0.0
