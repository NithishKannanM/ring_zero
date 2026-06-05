import os


class KernelMetrics:
    def __init__(self, cgroup_path="/sys/fs/cgroup/ring_zero"):
        self.cgroup_path = cgroup_path
        # Snapshot the initial counters so we can report deltas
        self._initial_pgfault = 0
        self._initial_pgmajfault = 0
        self._snapshot_taken = False

    def _read_stat_field(self, field_name):
        """
        Read a named field from the base cgroup's memory.stat.
        Returns 0 if the file or field is missing.
        """
        stat_file = os.path.join(self.cgroup_path, "memory.stat")
        if not os.path.exists(stat_file):
            return 0

        try:
            with open(stat_file, 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) == 2 and parts[0] == field_name:
                        return int(parts[1])
        except Exception as e:
            print(f"Error reading {stat_file}: {e}")

        return 0

    def snapshot_baseline(self):
        """
        Take a baseline snapshot of fault counters at the start of a benchmark.
        Call this AFTER setting up the base cgroup but BEFORE any allocations.
        """
        self._initial_pgfault = self._read_stat_field("pgfault")
        self._initial_pgmajfault = self._read_stat_field("pgmajfault")
        self._snapshot_taken = True

    def get_aggregate_faults(self):
        """
        Returns the TOTAL page faults (minor + major) accumulated since
        snapshot_baseline() was called.  Falls back to absolute count
        if no snapshot was taken.

        Note: anonymous mmap allocations generate *minor* page faults
        (pgfault), not major page faults (pgmajfault).  Major faults
        only occur when pages are fetched from disk/swap.
        """
        current = self._read_stat_field("pgfault")
        if self._snapshot_taken:
            return max(0, current - self._initial_pgfault)
        return current

    def get_major_faults(self):
        """Returns only major page faults (pages fetched from disk/swap)."""
        current = self._read_stat_field("pgmajfault")
        if self._snapshot_taken:
            return max(0, current - self._initial_pgmajfault)
        return current

    def get_all_fault_metrics(self):
        """Returns a dict with both fault types as deltas."""
        pgfault = self._read_stat_field("pgfault")
        pgmajfault = self._read_stat_field("pgmajfault")

        if self._snapshot_taken:
            pgfault = max(0, pgfault - self._initial_pgfault)
            pgmajfault = max(0, pgmajfault - self._initial_pgmajfault)

        return {
            "page_faults": pgfault,           # minor + major (the real signal)
            "major_page_faults": pgmajfault,   # disk/swap only
        }

    def get_memory_current(self):
        """
        Reads memory.current from the base cgroup.
        """
        curr_file = os.path.join(self.cgroup_path, "memory.current")
        if not os.path.exists(curr_file):
            return 0

        try:
            with open(curr_file, 'r') as f:
                return int(f.read().strip())
        except Exception as e:
            print(f"Error reading {curr_file}: {e}")

        return 0
