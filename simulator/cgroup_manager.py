import os
import shutil

class CGroupManager:
    def __init__(self, base_path="/sys/fs/cgroup/ring_zero"):
        self.base_path = base_path
        
    def setup_base_cgroup(self):
        if not os.path.exists(self.base_path):
            try:
                os.makedirs(self.base_path, exist_ok=True)
            except PermissionError:
                raise PermissionError(f"Root privileges required to create cgroup at {self.base_path}")
                
        # Enable memory controller for child cgroups
        try:
            subtree_file = os.path.join(self.base_path, "cgroup.subtree_control")
            with open(subtree_file, 'w') as f:
                f.write("+memory")
        except Exception as e:
            print(f"Warning: Could not enable memory controller in subtree: {e}")
                
    def cleanup_base_cgroup(self):
        if os.path.exists(self.base_path):
            try:
                # We can only remove cgroups if they are empty of processes and children
                os.rmdir(self.base_path)
            except Exception as e:
                print(f"Warning: Could not remove base cgroup {self.base_path}: {e}")

    def create_app_cgroup(self, app_id, memory_max_bytes=None, memory_high_bytes=None):
        cgroup_path = os.path.join(self.base_path, f"app_{app_id}")
        if not os.path.exists(cgroup_path):
            os.makedirs(cgroup_path, exist_ok=True)
            
        if memory_max_bytes:
            self.set_memory_max(app_id, memory_max_bytes)
        if memory_high_bytes:
            self.set_memory_high(app_id, memory_high_bytes)
            
        return cgroup_path
        
    def remove_app_cgroup(self, app_id):
        cgroup_path = os.path.join(self.base_path, f"app_{app_id}")
        if os.path.exists(cgroup_path):
            try:
                os.rmdir(cgroup_path)
            except Exception as e:
                print(f"Warning: Could not remove cgroup {cgroup_path}: {e}")

    def set_memory_max(self, app_id, memory_max_bytes):
        cgroup_path = os.path.join(self.base_path, f"app_{app_id}")
        mem_max_file = os.path.join(cgroup_path, "memory.max")
        with open(mem_max_file, 'w') as f:
            f.write(str(memory_max_bytes))
            
    def set_memory_high(self, app_id, memory_high_bytes):
        cgroup_path = os.path.join(self.base_path, f"app_{app_id}")
        mem_high_file = os.path.join(cgroup_path, "memory.high")
        with open(mem_high_file, 'w') as f:
            f.write(str(memory_high_bytes))
            
    def move_pid_to_cgroup(self, app_id, pid):
        cgroup_path = os.path.join(self.base_path, f"app_{app_id}")
        procs_file = os.path.join(cgroup_path, "cgroup.procs")
        with open(procs_file, 'w') as f:
            f.write(str(pid))
