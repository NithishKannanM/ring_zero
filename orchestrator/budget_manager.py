class BudgetManager:
    def __init__(self, total_budget_mb):
        self.total_budget_mb = total_budget_mb
        self.current_ram_mb = 0
        self.app_allocations = {} # app_id -> memory_mb
        
    def add_app(self, app_id, memory_mb):
        if app_id not in self.app_allocations:
            self.app_allocations[app_id] = memory_mb
            self.current_ram_mb += memory_mb
            
    def remove_app(self, app_id):
        if app_id in self.app_allocations:
            self.current_ram_mb -= self.app_allocations[app_id]
            del self.app_allocations[app_id]
            
    def has_budget_for(self, memory_mb):
        return (self.current_ram_mb + memory_mb) <= self.total_budget_mb
        
    def get_deficit(self, memory_mb):
        """Returns how much memory needs to be freed to fit memory_mb"""
        if self.has_budget_for(memory_mb):
            return 0
        return (self.current_ram_mb + memory_mb) - self.total_budget_mb

    def get_lru_app(self):
        """Return the oldest (least recently used) app_id, or None if empty."""
        if not self.app_allocations:
            return None
        return next(iter(self.app_allocations))

    def reset(self):
        self.current_ram_mb = 0
        self.app_allocations.clear()
