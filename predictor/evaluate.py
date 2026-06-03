import os
import json
import torch
import argparse
from torch.utils.data import DataLoader
from dataset import get_dataloader
from sasrec import SASRec
from baselines import calculate_metrics

def evaluate(args):
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}")
    
    with open(os.path.join(args.data_dir, 'app2id.json'), 'r') as f:
        app2id = json.load(f)
        vocab_size = len(app2id)
        
    test_loader = get_dataloader(
        os.path.join(args.data_dir, 'test_seqs.json'),
        batch_size=args.batch_size,
        shuffle=False
    )
    
    model = SASRec(
        vocab_size=vocab_size,
        embedding_dim=args.embedding_dim,
        num_heads=args.num_heads,
        num_layers=args.num_layers,
        dropout=args.dropout,
        max_seq_len=args.max_seq_len
    ).to(device)
    
    model_path = os.path.join(args.model_dir, 'sasrec_model.pt')
    if not os.path.exists(model_path):
        print(f"Error: Model checkpoint not found at {model_path}")
        return
        
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.eval()
    
    all_preds = []
    all_targets = []
    
    print("Evaluating SASRec on test set...")
    with torch.no_grad():
        for apps, hours, days, targets in test_loader:
            apps = apps.to(device)
            hours = hours.to(device)
            days = days.to(device)
            
            logits = model(apps, hours, days)
            
            # Get top 5 predictions
            top_k_indices = torch.topk(logits, k=5, dim=1).indices.cpu().numpy()
            
            for idx in range(len(targets)):
                all_preds.append(top_k_indices[idx].tolist())
                all_targets.append(targets[idx].item())
                
    metrics = calculate_metrics(all_preds, all_targets)
    
    print("\n--- SASRec Evaluation Results ---")
    for k, v in metrics.items():
        print(f"{k}: {v:.4f}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", type=str, default=os.path.join(os.path.dirname(__file__), "../datasets"))
    parser.add_argument("--model_dir", type=str, default=os.path.dirname(__file__))
    parser.add_argument("--embedding_dim", type=int, default=128)
    parser.add_argument("--num_heads", type=int, default=4)
    parser.add_argument("--num_layers", type=int, default=2)
    parser.add_argument("--dropout", type=float, default=0.2)
    parser.add_argument("--max_seq_len", type=int, default=20)
    parser.add_argument("--batch_size", type=int, default=256)
    
    args = parser.parse_args()
    
    evaluate(args)
