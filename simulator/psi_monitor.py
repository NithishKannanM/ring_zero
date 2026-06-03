import os

class PSIMonitor:
    def __init__(self, psi_path="/proc/pressure/memory"):
        self.psi_path = psi_path
        
    def read_pressure(self):
        """
        Reads the current PSI memory values.
        Returns a dictionary with 'some' and 'full' metrics.
        Format of /proc/pressure/memory:
        some avg10=0.00 avg60=0.00 avg300=0.00 total=12345
        full avg10=0.00 avg60=0.00 avg300=0.00 total=12345
        """
        metrics = {
            'some': {'avg10': 0.0, 'avg60': 0.0, 'avg300': 0.0, 'total': 0},
            'full': {'avg10': 0.0, 'avg60': 0.0, 'avg300': 0.0, 'total': 0}
        }
        
        if not os.path.exists(self.psi_path):
            return metrics
            
        try:
            with open(self.psi_path, 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if not parts:
                        continue
                        
                    kind = parts[0] # 'some' or 'full'
                    if kind in metrics:
                        for part in parts[1:]:
                            key, val = part.split('=')
                            if key == 'total':
                                metrics[kind][key] = int(val)
                            else:
                                metrics[kind][key] = float(val)
        except Exception as e:
            print(f"Error reading PSI: {e}")
            
        return metrics
        
    def get_current_stall_ms(self):
        """
        Returns the delta in total 'some' stall time since last check.
        For simplicity, this just returns the raw total in microseconds.
        """
        metrics = self.read_pressure()
        return metrics['some']['total'] / 1000.0 # Convert microseconds to ms
