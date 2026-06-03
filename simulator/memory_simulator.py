import yaml
import os
from abc import ABC, abstractmethod

class MemoryBackend(ABC):
    @abstractmethod
    def preload(self, app_profile):
        pass
        
    @abstractmethod
    def evict(self, app_id):
        pass
        
    @abstractmethod
    def launch(self, app_profile):
        pass
        
    @abstractmethod
    def get_metrics(self):
        pass
        
    @abstractmethod
    def reset(self):
        pass


class MockBackend(MemoryBackend):
    def __init__(self, total_memory):
        self.total_memory = total_memory
        self.in_memory_apps = set()
        self.metrics = {
            "warm_launches": 0,
            "cold_launches": 0,
            "total_latency_ms": 0,
            "evictions": 0,
            "prewarms": 0,
            "major_page_faults": 0, 
            "psi_stall_ms": 0
        }
        
    def reset(self):
        self.in_memory_apps = set()
        for k in self.metrics.keys():
            self.metrics[k] = 0
            
    def preload(self, app_profile):
        app_id = app_profile['app_id']
        if app_id not in self.in_memory_apps:
            self.in_memory_apps.add(app_id)
            self.metrics["prewarms"] += 1
            # Prewarming causes background page faults and PSI stalls
            self.metrics["major_page_faults"] += (app_profile['memory_mb'] * 1024) / 4
            self.metrics["psi_stall_ms"] += app_profile['launch_ms'] * 0.3 # 30% overhead compared to cold launch
            
    def evict(self, app_id):
        if app_id in self.in_memory_apps:
            self.in_memory_apps.remove(app_id)
            self.metrics["evictions"] += 1
            
    def launch(self, app_profile):
        app_id = app_profile['app_id']
        latency = 0
        
        if app_id in self.in_memory_apps:
            self.metrics["warm_launches"] += 1
            latency = app_profile['launch_ms'] * 0.1
        else:
            self.metrics["cold_launches"] += 1
            latency = app_profile['launch_ms']
            self.metrics["major_page_faults"] += (app_profile['memory_mb'] * 1024) / 4
            self.metrics["psi_stall_ms"] += latency * 0.5
            self.in_memory_apps.add(app_id)
            
        self.metrics["total_latency_ms"] += latency
        return latency

    def get_metrics(self):
        total = self.metrics["warm_launches"] + self.metrics["cold_launches"]
        warm_rate = self.metrics["warm_launches"] / total if total > 0 else 0
        avg_latency = self.metrics["total_latency_ms"] / total if total > 0 else 0
        
        return {
            **self.metrics,
            "warm_launch_rate": warm_rate,
            "avg_latency_ms": avg_latency
        }


class MemoryManager:
    """
    Facade for interacting with memory. Delegates to the underlying Backend.
    """
    def __init__(self, config_file="../config/simulator.yaml"):
        config_path = os.path.join(os.path.dirname(__file__), config_file)
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
            
        self.total_memory = self.config.get("total_memory_mb", 2000)
        self.mock_mode = self.config.get("mock_mode", True)
        
        if self.mock_mode:
            self.backend = MockBackend(self.total_memory)
        else:
            # We will implement LinuxBackend later
            from kernel_capability_check import verify_kernel_capabilities
            caps = verify_kernel_capabilities()
            if not caps['can_use_linux_backend']:
                print("WARNING: Missing Kernel Capabilities. Falling back to MockBackend.")
                self.backend = MockBackend(self.total_memory)
            else:
                # Placeholder for LinuxBackend instantiation
                # self.backend = LinuxBackend(self.total_memory)
                raise NotImplementedError("LinuxBackend is not implemented yet")

    @property
    def metrics(self):
        return self.backend.metrics
        
    @property
    def in_memory_apps(self):
        return self.backend.in_memory_apps
        
    def reset(self):
        self.backend.reset()
        
    def preload(self, app_profile):
        self.backend.preload(app_profile)
            
    def evict(self, app_id):
        self.backend.evict(app_id)
            
    def keep(self, app_profile):
        pass
        
    def launch(self, app_profile):
        return self.backend.launch(app_profile)

    def get_metrics(self):
        return self.backend.get_metrics()
