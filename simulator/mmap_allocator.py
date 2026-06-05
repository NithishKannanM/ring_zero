import mmap
import os
import time
import sys

def allocate_and_touch(size_mb):
    """
    Allocates size_mb of anonymous memory and touches every page to ensure it's backed by RAM.
    This simulates an app loading into memory.
    """
    bytes_to_allocate = size_mb * 1024 * 1024
    
    # Anonymous mapping, private, backed by swap if needed
    try:
        mem = mmap.mmap(-1, bytes_to_allocate, flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS)
    except Exception as e:
        print(f"Failed to allocate {size_mb}MB: {e}")
        return None
        
    # Touch every page (4KB) to force physical allocation and trigger page faults if needed
    page_size = 4096
    for i in range(0, bytes_to_allocate, page_size):
        mem[i] = 1 # write a byte to force allocation
        
    return mem

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python mmap_allocator.py <size_mb>")
        sys.exit(1)
        
    size_mb = int(sys.argv[1])
    # Signal readiness
    print(f"READY")
    sys.stdout.flush()
    
    # Wait for the orchestrator to move us to a cgroup before allocating
    sys.stdin.readline()
    
    # print(f"[{os.getpid()}] Allocating {size_mb} MB...")
    mem = allocate_and_touch(size_mb)
    
    if mem:
        print(f"ALLOCATED")
        sys.stdout.flush()
        try:
            # Keep alive until killed
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            mem.close()
