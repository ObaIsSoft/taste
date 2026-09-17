import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim

# --------------------------------------------------------
# 1. The Continuous Telemetry Architecture (Nano-Transformer)
# --------------------------------------------------------
class NanoTasteModel(nn.Module):
    def __init__(self, d_model=128, n_heads=4, n_layers=2):
        super().__init__()
        
        # Continuous Linear Projection: Maps a raw float to d_model space
        self.continuous_projection = nn.Linear(1, d_model)
        
        # Positional Encoding: Allows attention to know which variable is which 
        # (0-6 = DOM_A, WS_A, COL_A, ASYM_A, INTENT_A, COHES_A, HIER_A)
        # (7-13 = DOM_B, WS_B, COL_B, ASYM_B, INTENT_B, COHES_B, HIER_B)
        self.pos_embedding = nn.Embedding(14, d_model)
        
        # Nano-Transformer Blocks
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, 
            nhead=n_heads, 
            dim_feedforward=d_model * 4, 
            dropout=0.0, # 0 dropout for overfit sandbox
            batch_first=True
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=n_layers)
        
        # Regression Head
        self.fc = nn.Linear(d_model, 1)

    def forward(self, x):
        # x is shape (batch_size, 14)
        B, seq_len = x.shape
        
        # Expand to (batch, 14, 1) for the linear projection
        x = x.unsqueeze(-1)
        
        # Project floats to (batch, 14, d_model)
        x_emb = self.continuous_projection(x)
        
        # Add positional context
        positions = torch.arange(0, seq_len, device=x.device).unsqueeze(0).expand(B, seq_len)
        pos_emb = self.pos_embedding(positions)
        
        x_emb = x_emb + pos_emb
        
        # Attention Matrix Matrix (discover cross-variable rules)
        out = self.transformer(x_emb)
        
        # Global average pool across the 14 sequence tokens
        pooled = out.mean(dim=1)
        
        # Output probability (0 to 1)
        logits = self.fc(pooled)
        return torch.sigmoid(logits)


# --------------------------------------------------------
# 2. Phase 3: The Overfit Sandbox
# --------------------------------------------------------
def run_overfit_test():
    device = torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    print(f"Running on device: {device}")
    
    # Load Distilled Data
    dataset_path = '/Users/obafemi/Documents/dev/dziner/taste-engine/results/nano_taste_dataset.pt'
    data = torch.load(dataset_path, weights_only=True)
    
    X = data['X'].to(device)         # (456, 8)
    Y = data['Y'].to(device)         # (456, 1)
    margins = data['margins'].to(device) # (456, 1)
    
    # Initialize Micro-Brain
    model = NanoTasteModel(d_model=64, n_heads=4, n_layers=2).to(device)
    total_params = sum(p.numel() for p in model.parameters())
    print(f"Nano-Transformer Architecture Initialized: {total_params:,} parameters")
    
    # Optimizer & Margin-Adaptive Loss
    optimizer = optim.AdamW(model.parameters(), lr=1e-3)
    
    def margin_adaptive_bce(y_pred, y_true, margin_weights):
        # Standard BCE weighted heavily by the TrueSkill margin
        # A high margin (e.g. 0.8) means a mistake here is severely punished.
        bce = F.binary_cross_entropy(y_pred, y_true, reduction='none')
        # Scale loss by margin, add a floor so small margins still train
        weighted_loss = bce * (margin_weights + 0.1) 
        return weighted_loss.mean()

    print("\n[STARTING OVERFIT TEST: GOAL LOSS = 0.000]")
    
    model.train()
    epochs = 1500
    
    for epoch in range(epochs):
        optimizer.zero_grad()
        
        # Forward pass (full batch)
        y_pred = model(X)
        
        # Calculate loss
        loss = margin_adaptive_bce(y_pred, Y, margins)
        
        # Backward pass
        loss.backward()
        optimizer.step()
        
        if (epoch + 1) % 100 == 0:
            # Calculate accuracy
            predictions = (y_pred >= 0.5).float()
            correct = (predictions == Y).sum().item()
            accuracy = correct / len(Y)
            
            print(f"Epoch [{epoch+1}/{epochs}] | Loss: {loss.item():.4f} | Accuracy: {accuracy*100:.1f}%")

    print("\n[OVERFIT TEST COMPLETE]")
    if accuracy > 0.95:
        print("SUCCESS: The PyTorch tensor routing and Continuous Linear Projections are mathematically flawless.")
        print("The network successfully modeled the TrueSkill loss. We are cleared to ingest the 1,000 URL batch.")
    else:
        print("FAILURE: The network failed to overfit. Check the backpropagation graphs.")


if __name__ == "__main__":
    run_overfit_test()
