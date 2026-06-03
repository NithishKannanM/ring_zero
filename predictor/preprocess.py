import pandas as pd
import json
import os

def preprocess_lsapp(filepath, output_dir, seq_len=20):
    print(f"Loading data from {filepath}...")
    df = pd.read_csv(filepath, sep='\t')
    
    # Filter only 'Opened' events
    df = df[df['event_type'] == 'Opened'].copy()
    
    # Parse timestamps
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Sort by user and timestamp
    df = df.sort_values(['user_id', 'timestamp'])
    
    # Create App ID Mapping
    unique_apps = df['app_name'].unique()
    app2id = {'<PAD>': 0}
    for idx, app in enumerate(unique_apps):
        app2id[app] = idx + 1
        
    with open(os.path.join(output_dir, 'app2id.json'), 'w') as f:
        json.dump(app2id, f)
        
    df['app_id'] = df['app_name'].map(app2id)
    df['hour'] = df['timestamp'].dt.hour
    df['day'] = df['timestamp'].dt.dayofweek
    
    print("Generating sequences...")
    sequences = []
    
    for user_id, group in df.groupby('user_id'):
        user_apps = group['app_id'].tolist()
        user_hours = group['hour'].tolist()
        user_days = group['day'].tolist()
        
        if len(user_apps) <= seq_len:
            continue
            
        for i in range(len(user_apps) - seq_len):
            seq_apps = user_apps[i:i+seq_len]
            seq_hours = user_hours[i:i+seq_len]
            seq_days = user_days[i:i+seq_len]
            target = user_apps[i+seq_len]
            
            sequences.append({
                'user_id': int(user_id),
                'apps': seq_apps,
                'hours': seq_hours,
                'days': seq_days,
                'target': int(target)
            })
            
    # Chronological Train/Test Split (80/20)
    split_idx = int(len(sequences) * 0.8)
    train_seqs = sequences[:split_idx]
    test_seqs = sequences[split_idx:]
    
    with open(os.path.join(output_dir, 'train_seqs.json'), 'w') as f:
        json.dump(train_seqs, f)
    with open(os.path.join(output_dir, 'test_seqs.json'), 'w') as f:
        json.dump(test_seqs, f)
        
    print(f"Preprocessing complete. Total sequences: {len(sequences)}")
    print(f"Train: {len(train_seqs)}, Test: {len(test_seqs)}")
    print(f"Vocabulary size: {len(app2id)}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, default="datasets/lsapp.tsv")
    parser.add_argument("--output", type=str, default="datasets")
    parser.add_argument("--seq_len", type=int, default=20)
    args = parser.parse_args()
    
    os.makedirs(args.output, exist_ok=True)
    preprocess_lsapp(args.input, args.output, args.seq_len)
