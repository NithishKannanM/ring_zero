import time
import sys
import os

# Ensure cleanup is registered first
import cleanup
cleanup.register_cleanup_handlers()

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from memory.linux_backend import LinuxBackend
from kernel_metrics import KernelMetrics
from psi_monitor import PSIMonitor

def run_tests():
    print("--- Testing Linux Backend Components ---")
    
    backend = LinuxBackend()
    metrics = KernelMetrics()
    psi_mon = PSIMonitor()
    
    app_profile = {
        'app_id': 'test_app_1',
        'memory_mb': 200
    }
    
    # 1. Allocate process & cgroup
    print("Allocating 200 MB in test_app_1...")
    backend.allocate(app_profile)
    
    # Verify cgroup created and process moved
    cgroup_path = "/sys/fs/cgroup/ring_zero/app_test_app_1"
    if os.path.exists(cgroup_path):
        print("✓ cgroup created")
    else:
        print("✗ cgroup creation failed")
        return
        
    procs_file = os.path.join(cgroup_path, "cgroup.procs")
    with open(procs_file, 'r') as f:
        procs = f.read().strip()
        if procs:
            print("✓ process assigned")
        else:
            print("✗ process not assigned")
            return
            
    # Give it a second to touch all pages
    time.sleep(1)
    
    # Verify memory.current
    mem_current = metrics.get_memory_current()
    mb_used = mem_current / (1024 * 1024)
    if mb_used >= 190: # Should be ~200MB
        print(f"✓ memory.current updated ({mb_used:.1f} MB)")
    else:
        print(f"✗ memory.current unexpected: {mb_used:.1f} MB")
        
    # Read PSI
    psi = psi_mon.get_avg10()
    print(f"✓ PSI readable (current some.avg10 = {psi})")
    
    # Cleanup
    print("Cleaning up...")
    backend.cleanup()
    
    if not os.path.exists(cgroup_path):
        print("✓ cleanup successful")
    else:
        print("✗ cleanup failed")
        
if __name__ == "__main__":
    run_tests()
