import torch
import torch.nn as nn

class SASRec(nn.Module):
    def __init__(self, vocab_size, embedding_dim=128, num_heads=4, num_layers=2, dropout=0.2, max_seq_len=20):
        super(SASRec, self).__init__()
        self.vocab_size = vocab_size
        self.embedding_dim = embedding_dim
        self.max_seq_len = max_seq_len
        
        # Embeddings
        self.app_embedding = nn.Embedding(vocab_size, embedding_dim, padding_idx=0)
        self.pos_embedding = nn.Embedding(max_seq_len, embedding_dim)
        self.hour_embedding = nn.Embedding(24, embedding_dim)
        self.day_embedding = nn.Embedding(7, embedding_dim)
        
        # Transformer
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=embedding_dim,
            nhead=num_heads,
            dim_feedforward=embedding_dim * 4,
            dropout=dropout,
            activation='gelu',
            batch_first=True
        )
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        
        # Output layer
        self.layer_norm = nn.LayerNorm(embedding_dim)
        self.fc = nn.Linear(embedding_dim, vocab_size)
        
        self.dropout = nn.Dropout(dropout)
        
    def forward(self, apps, hours, days):
        """
        apps: (batch_size, seq_len)
        hours: (batch_size, seq_len)
        days: (batch_size, seq_len)
        """
        batch_size, seq_len = apps.size()
        
        # Positions
        positions = torch.arange(seq_len, dtype=torch.long, device=apps.device)
        positions = positions.unsqueeze(0).expand(batch_size, seq_len)
        
        # Look-ahead mask for self-attention
        mask = nn.Transformer.generate_square_subsequent_mask(seq_len).to(apps.device)
        
        # Padding mask (True for padded positions)
        padding_mask = (apps == 0)
        
        # Embeddings
        app_emb = self.app_embedding(apps)
        pos_emb = self.pos_embedding(positions)
        hour_emb = self.hour_embedding(hours)
        day_emb = self.day_embedding(days)
        
        # Combine embeddings
        x = app_emb + pos_emb + hour_emb + day_emb
        x = self.dropout(x)
        
        # Transformer
        # TransformerEncoder with batch_first=True takes (batch, seq, feature)
        # mask is (seq_len, seq_len)
        # src_key_padding_mask is (batch_size, seq_len)
        out = self.transformer_encoder(x, mask=mask, src_key_padding_mask=padding_mask)
        
        # We only care about the last item in the sequence for next-app prediction
        last_out = out[:, -1, :]
        last_out = self.layer_norm(last_out)
        
        logits = self.fc(last_out)
        
        return logits
