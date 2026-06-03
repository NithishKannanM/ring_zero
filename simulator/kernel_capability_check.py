import os
import sys

def check_root():
    return os.geteuid() == 0

def check_cgroup_v2():
    cgroup_path = "/sys/fs/cgroup"
    if not os.path.ismount(cgroup_path):
        return False
        
    # cgroup v2 uses cgroup.controllers, v1 does not
    if not os.path.exists(os.path.join(cgroup_path, "cgroup.controllers")):
        return False
        
    return True
    
def check_psi():
    psi_path = "/proc/pressure/memory"
    return os.path.exists(psi_path)

def verify_kernel_capabilities():
    capabilities = {
        "is_root": check_root(),
        "cgroup_v2": check_cgroup_v2(),
        "psi_memory": check_psi()
    }
    
    can_use_linux_backend = all(capabilities.values())
    capabilities["can_use_linux_backend"] = can_use_linux_backend
    
    return capabilities

if __name__ == "__main__":
    print("Checking Kernel Capabilities for Ring Zero LinuxBackend...")
    caps = verify_kernel_capabilities()
    print(f"Root Privileges:     {'YES' if caps['is_root'] else 'NO (Required)'}")
    print(f"CGroup V2 Available: {'YES' if caps['cgroup_v2'] else 'NO'}")
    print(f"PSI Memory Monitor:  {'YES' if caps['psi_memory'] else 'NO'}")
    print("-" * 40)
    print(f"LinuxBackend Supported: {'YES' if caps['can_use_linux_backend'] else 'NO (Falling back to MockBackend)'}")
    
    if not caps['can_use_linux_backend']:
        sys.exit(1)
