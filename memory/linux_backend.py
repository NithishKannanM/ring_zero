import os
import subprocess
import signal
import sys
import importlib.util
from .backend import MemoryBackend

# Import cgroup_manager from simulator using absolute path resolution
# (avoids issues when running from different working directories)
_cgroup_mgr_path = os.path.join(os.path.dirname(__file__), '..', 'simulator', 'cgroup_manager.py')
_spec = importlib.util.spec_from_file_location("cgroup_manager", os.path.abspath(_cgroup_mgr_path))
_cgroup_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cgroup_mod)
CGroupManager = _cgroup_mod.CGroupManager

class LinuxBackend(MemoryBackend):
    def __init__(self, memory_limit_mb=None):
        self.cgroup_mgr = CGroupManager()
        self.cgroup_mgr.setup_base_cgroup()
        
        self.memory_limit_mb = memory_limit_mb
        self.allocator_path = os.path.join(os.path.dirname(__file__), '../simulator/mmap_allocator.py')
        
        self.processes = {} # app_id -> subprocess.Popen
        
    def allocate(self, app_profile):
        app_id = app_profile['app_id']
        size_mb = app_profile['memory_mb']
        
        if app_id in self.processes:
            # Already allocated
            return
            
        # 1. Create cgroup
        self.cgroup_mgr.create_app_cgroup(app_id)
        
        # 2. Spawn allocator
        # Stdin is piped so we can send the signal to start allocating
        # Stdout is piped so we can wait for READY/ALLOCATED
        proc = subprocess.Popen(
            [sys.executable, self.allocator_path, str(size_mb)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        # Wait for READY
        line = proc.stdout.readline()
        if "READY" not in line:
            print(f"[{app_id}] Failed to start allocator: {line.strip()}")
            proc.kill()
            return
            
        # 3. Move process to cgroup
        self.cgroup_mgr.move_pid_to_cgroup(app_id, proc.pid)
        
        # 4. Tell it to allocate
        proc.stdin.write("\n")
        proc.stdin.flush()
        
        # 5. Wait for ALLOCATED
        line = proc.stdout.readline()
        if "ALLOCATED" not in line:
            print(f"[{app_id}] Allocation failed: {line.strip()}")
            proc.kill()
            return
            
        self.processes[app_id] = proc
        
    def evict(self, app_id):
        if app_id in self.processes:
            proc = self.processes[app_id]
            try:
                os.kill(proc.pid, signal.SIGKILL)
                proc.wait(timeout=1.0)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                pass
            del self.processes[app_id]
            
        self.cgroup_mgr.remove_app_cgroup(app_id)
        
    def get_metrics(self):
        # We can implement fetching cgroup memory.stat here later if needed
        return {}
        
    def cleanup(self):
        for app_id in list(self.processes.keys()):
            self.evict(app_id)
        self.cgroup_mgr.cleanup_base_cgroup()
