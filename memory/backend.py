from abc import ABC, abstractmethod

class MemoryBackend(ABC):
    @abstractmethod
    def allocate(self, app_profile):
        """Simulate or perform memory allocation for an app."""
        pass
        
    @abstractmethod
    def evict(self, app_id):
        """Simulate or perform memory eviction for an app."""
        pass
        
    @abstractmethod
    def get_metrics(self):
        """Return a dictionary of backend metrics."""
        pass
        
    @abstractmethod
    def cleanup(self):
        """Clean up backend resources."""
        pass
