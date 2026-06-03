import yaml
import json
import os

class WorkloadGenerator:
    def __init__(self, seqs_file, apps_config_file, app2id_file):
        with open(seqs_file, 'r') as f:
            self.seqs = json.load(f)
            
        with open(apps_config_file, 'r') as f:
            self.apps_config = yaml.safe_load(f)
            
        with open(app2id_file, 'r') as f:
            self.app2id = json.load(f)
            
        # Create id2app mapping for lookups in apps_config
        self.id2app = {v: k for k, v in self.app2id.items()}
        self.default_config = self.apps_config.get('default', {'memory_mb': 150, 'launch_ms': 1000})

    def get_app_profile(self, app_id):
        app_name = self.id2app.get(app_id, "")
        
        # Exact match or find substring in config (e.g. "Google Chrome" -> "Chrome")
        config = None
        for config_key in self.apps_config.keys():
            if config_key != 'default' and config_key.lower() in app_name.lower():
                config = self.apps_config[config_key]
                break
                
        if not config:
            config = self.default_config
            
        return {
            "app_id": app_id,
            "app_name": app_name,
            "memory_mb": config.get("memory_mb", 150),
            "launch_ms": config.get("launch_ms", 1000)
        }

    def generate(self, limit=None):
        """
        Yields simulated launch events based on the test sequences.
        For benchmarking, we simulate the 'target' app being launched.
        We also pass the sequence context so the orchestrator can make predictions.
        """
        count = 0
        for seq in self.seqs:
            if limit and count >= limit:
                break
                
            target_app_id = seq['target']
            profile = self.get_app_profile(target_app_id)
            
            yield {
                "context": {
                    "apps": seq['apps'],
                    "hours": seq['hours'],
                    "days": seq['days']
                },
                "target": profile
            }
            count += 1

if __name__ == "__main__":
    generator = WorkloadGenerator(
        seqs_file="../datasets/test_seqs.json",
        apps_config_file="../config/apps.yaml",
        app2id_file="../datasets/app2id.json"
    )
    
    print("Sample events:")
    for i, event in enumerate(generator.generate(limit=3)):
        print(f"Event {i+1}:")
        print(f"  Target: {event['target']['app_name']} (ID: {event['target']['app_id']})")
        print(f"  Memory: {event['target']['memory_mb']} MB, Cost: {event['target']['launch_ms']} ms")
        print(f"  Context length: {len(event['context']['apps'])}")
        print()
