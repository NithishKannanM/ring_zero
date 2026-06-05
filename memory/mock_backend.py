from .backend import MemoryBackend

class MockBackend(MemoryBackend):
    def __init__(self, total_memory=2000):
        self.total_memory = total_memory
        self.current_used = 0
        self.major_faults = 0
        self.apps = set()
        
    def allocate(self, app_profile):
        app_id = app_profile['app_id']
        mem = app_profile['memory_mb']
        if app_id not in self.apps:
            self.apps.add(app_id)
            self.current_used += mem
            # Simulate page faults for a cold start
            self.major_faults += mem * 256
            
    def evict(self, app_id):
        if app_id in self.apps:
            self.apps.remove(app_id)
            # We don't have the memory info here unless we store it, 
            # but we just need to satisfy the interface.
            
    def set_used(self, mem):
        self.current_used = mem
        
    def get_metrics(self):
        return {
            "major_faults": self.major_faults,
            "current_used_mb": self.current_used
        }
        
    def cleanup(self):
        pass
