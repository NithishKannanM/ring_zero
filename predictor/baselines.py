import json
import os
import argparse
from collections import Counter

def calculate_metrics(predictions, targets):
    """
    predictions: list of lists (top K predicted apps for each sequence)
    targets: list of actual next apps
    """
    hits_at_1 = 0
    hits_at_3 = 0
    hits_at_5 = 0
    mrr_sum = 0.0
    
    total = len(targets)
    
    for preds, target in zip(predictions, targets):
        if target in preds[:1]:
            hits_at_1 += 1
        if target in preds[:3]:
            hits_at_3 += 1
        if target in preds[:5]:
            hits_at_5 += 1
            
        try:
            rank = preds.index(target) + 1
            mrr_sum += 1.0 / rank
        except ValueError:
            pass
            
    return {
        'Hit@1': hits_at_1 / total,
        'Hit@3': hits_at_3 / total,
        'Hit@5': hits_at_5 / total,
        'MRR': mrr_sum / total
    }

def evaluate_baselines(test_file):
    print(f"Loading test sequences from {test_file}...")
    with open(test_file, 'r') as f:
        test_seqs = json.load(f)
        
    targets = [seq['target'] for seq in test_seqs]
    
    # Baseline 1: Last App Repetition
    # Predicts the most recent app in the sequence as the next app
    last_app_preds = [[seq['apps'][-1]] for seq in test_seqs]
    print("\n--- Last App Repetition ---")
    last_app_metrics = calculate_metrics(last_app_preds, targets)
    for k, v in last_app_metrics.items():
        print(f"{k}: {v:.4f}")
        
    # Baseline 2: Most Frequently Used (MFU)
    # Predicts the most frequent app in the sequence
    mfu_preds = []
    for seq in test_seqs:
        counts = Counter(seq['apps'])
        # Top 5 most common apps
        top_apps = [app for app, count in counts.most_common(5)]
        mfu_preds.append(top_apps)
        
    print("\n--- Most Frequently Used (MFU) ---")
    mfu_metrics = calculate_metrics(mfu_preds, targets)
    for k, v in mfu_metrics.items():
        print(f"{k}: {v:.4f}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test_data", type=str, default=os.path.join(os.path.dirname(__file__), "../datasets/test_seqs.json"))
    args = parser.parse_args()
    
    evaluate_baselines(args.test_data)
