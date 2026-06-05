import os
import sys
import signal
import atexit
import subprocess
import glob

def kill_all_ring_zero_processes():
    """
    Finds and kills any leftover mmap_allocator.py processes.
    """
    try:
        # Find all python processes running mmap_allocator
        cmd = "ps -ef | grep mmap_allocator.py | grep -v grep | awk '{print $2}'"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        pids = result.stdout.strip().split()
        for pid in pids:
            if pid:
                try:
                    os.kill(int(pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
    except Exception as e:
        print(f"Error cleaning up processes: {e}")

def remove_all_ring_zero_cgroups():
    """
    Removes all cgroups under /sys/fs/cgroup/ring_zero.
    Requires root, which should be active if we reached this point.
    """
    base_cgroup = "/sys/fs/cgroup/ring_zero"
    if not os.path.exists(base_cgroup):
        return
        
    try:
        # First, find all child cgroups (apps)
        app_cgroups = glob.glob(f"{base_cgroup}/app_*")
        
        # Kill any processes still stuck in these cgroups (just in case)
        for cg in app_cgroups:
            procs_file = os.path.join(cg, "cgroup.procs")
            if os.path.exists(procs_file):
                with open(procs_file, 'r') as f:
                    for line in f:
                        pid = line.strip()
                        if pid:
                            try:
                                os.kill(int(pid), signal.SIGKILL)
                            except ProcessLookupError:
                                pass
        
        import time
        time.sleep(1) # Give kernel time to reap processes
        
        # Now remove the directories
        for cg in app_cgroups:
            try:
                os.rmdir(cg)
            except Exception as e:
                print(f"Failed to remove cgroup {cg}: {e}")
                
        # Finally remove base cgroup
        try:
            os.rmdir(base_cgroup)
        except Exception as e:
            print(f"Failed to remove base cgroup {base_cgroup}: {e}")
            
    except Exception as e:
        print(f"Error cleaning up cgroups: {e}")

def run_cleanup(signum=None, frame=None):
    kill_all_ring_zero_processes()
    remove_all_ring_zero_cgroups()
    if signum is not None:
        sys.exit(0)

def register_cleanup_handlers():
    atexit.register(run_cleanup)
    try:
        signal.signal(signal.SIGINT, run_cleanup)
        signal.signal(signal.SIGTERM, run_cleanup)
    except ValueError:
        # Ignore if not in main thread
        pass

if __name__ == "__main__":
    print("Running manual cleanup...")
    run_cleanup()
    print("Cleanup complete.")
