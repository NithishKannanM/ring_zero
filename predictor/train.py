import os
import json
import torch
import torch.nn as nn
import torch.optim as optim
import argparse
from torch.utils.data import DataLoader
from dataset import get_dataloader
from sasrec import SASRec

def train(args):
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}")
    
    with open(os.path.join(args.data_dir, 'app2id.json'), 'r') as f:
        app2id = json.load(f)
        vocab_size = len(app2id)
        
    print(f"Vocab size: {vocab_size}")
    
    train_loader = get_dataloader(
        os.path.join(args.data_dir, 'train_seqs.json'),
        batch_size=args.batch_size,
        shuffle=True
    )
    
    model = SASRec(
        vocab_size=vocab_size,
        embedding_dim=args.embedding_dim,
        num_heads=args.num_heads,
        num_layers=args.num_layers,
        dropout=args.dropout,
        max_seq_len=args.max_seq_len
    ).to(device)
    
    criterion = nn.CrossEntropyLoss(ignore_index=0) # Ignore padding
    optimizer = optim.Adam(model.parameters(), lr=args.learning_rate)
    
    print("Starting training...")
    
    for epoch in range(args.epochs):
        model.train()
        total_loss = 0.0
        
        for batch_idx, (apps, hours, days, targets) in enumerate(train_loader):
            apps = apps.to(device)
            hours = hours.to(device)
            days = days.to(device)
            targets = targets.to(device)
            
            optimizer.zero_grad()
            
            logits = model(apps, hours, days)
            loss = criterion(logits, targets)
            
            loss.backward()
            optimizer.step()
            
            total_loss += loss.item()
            
            if (batch_idx + 1) % 1000 == 0:
                print(f"Epoch [{epoch+1}/{args.epochs}], Step [{batch_idx+1}/{len(train_loader)}], Loss: {loss.item():.4f}")
                
        avg_loss = total_loss / len(train_loader)
        print(f"Epoch [{epoch+1}/{args.epochs}] completed. Average Loss: {avg_loss:.4f}")
        
        # Save checkpoint
        torch.save(model.state_dict(), os.path.join(args.model_dir, 'sasrec_model.pt'))

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
    parser.add_argument("--learning_rate", type=float, default=1e-3)
    parser.add_argument("--epochs", type=int, default=5) # Default 5 for quick testing, but 30 in final
    
    args = parser.parse_args()
    
    os.makedirs(args.model_dir, exist_ok=True)
    train(args)
