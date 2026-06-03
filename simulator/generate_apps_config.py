import json
import yaml
import random
import os

def generate_apps_yaml(app2id_file, out_file):
    with open(app2id_file, 'r') as f:
        app2id = json.load(f)
        
    apps = {}
    apps['default'] = {'memory_mb': 150, 'launch_ms': 1000}
    
    # Let's categorize some apps to specific buckets based on heuristics
    heavy_keywords = ['chrome', 'browser', 'game', 'camera', 'maps', 'youtube', 'netflix']
    medium_keywords = ['slack', 'gmail', 'messenger', 'whatsapp', 'instagram', 'facebook']
    light_keywords = ['calculator', 'clock', 'settings', 'notes']
    
    for app_name in app2id.keys():
        name_lower = app_name.lower()
        
        is_heavy = any(k in name_lower for k in heavy_keywords)
        is_medium = any(k in name_lower for k in medium_keywords)
        is_light = any(k in name_lower for k in light_keywords)
        
        if is_heavy:
            mem = random.randint(500, 1000)
            cost = random.randint(2000, 3500)
        elif is_medium:
            mem = random.randint(200, 400)
            cost = random.randint(800, 1500)
        elif is_light:
            mem = random.randint(30, 80)
            cost = random.randint(50, 200)
        else:
            # Random distribution for the rest
            mem = random.randint(100, 300)
            cost = random.randint(400, 1200)
            
        apps[app_name] = {'memory_mb': mem, 'launch_ms': cost}
        
    with open(out_file, 'w') as f:
        yaml.dump(apps, f, default_flow_style=False)
        
    print(f"Generated profile for {len(app2id)} apps in {out_file}")

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    generate_apps_yaml(
        app2id_file=os.path.join(base_dir, "datasets/app2id.json"),
        out_file=os.path.join(base_dir, "config/apps.yaml")
    )
