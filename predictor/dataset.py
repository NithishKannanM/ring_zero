import json
import torch
from torch.utils.data import Dataset, DataLoader

class AppSequenceDataset(Dataset):
    def __init__(self, data_path):
        super().__init__()
        with open(data_path, 'r') as f:
            self.data = json.load(f)
            
    def __len__(self):
        return len(self.data)
        
    def __getitem__(self, idx):
        item = self.data[idx]
        
        apps = torch.tensor(item['apps'], dtype=torch.long)
        hours = torch.tensor(item['hours'], dtype=torch.long)
        days = torch.tensor(item['days'], dtype=torch.long)
        target = torch.tensor(item['target'], dtype=torch.long)
        
        return apps, hours, days, target

def get_dataloader(data_path, batch_size=256, shuffle=True, num_workers=4):
    dataset = AppSequenceDataset(data_path)
    return DataLoader(
        dataset, 
        batch_size=batch_size, 
        shuffle=shuffle, 
        num_workers=num_workers,
        pin_memory=True
    )
