import json
import re
import torch
import os

def prepare_dataset(input_file, output_tensor_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        data = [json.loads(line) for line in f]

    X = []
    Y = []
    margins = []

    def get_val(text, pattern):
        match = re.search(pattern, text)
        return float(match.group(1)) if match else 0.0

    for idx, item in enumerate(data):
        prompt_msgs = item.get("prompt", [])
        chosen_msgs = item.get("chosen", [])
        
        if len(prompt_msgs) < 2:
            continue
            
        user_content = prompt_msgs[1]["content"]
        
        split_b = re.split(r'VARIANT\s+B\s+METRICS:', user_content, flags=re.IGNORECASE)
        if len(split_b) < 2: continue
        split_a = re.split(r'VARIANT\s+A\s+METRICS:', split_b[0], flags=re.IGNORECASE)
        if len(split_a) < 2: continue
            
        metrics_a = split_a[1].strip()
        metrics_b = split_b[1].strip()
        
        # Extract the 4 core metrics for A
        dom_a = get_val(metrics_a, r'Total DOM depth:\s*(\d+)')
        ws_a = get_val(metrics_a, r'Whitespace Ratio:\s*([\d\.]+)')
        cv_a = get_val(metrics_a, r'Color Variance:\s*([\d\.]+)')
        asym_a = get_val(metrics_a, r'Asymmetry Score:\s*([\d\.]+)')
        
        # Extract the 4 core metrics for B
        dom_b = get_val(metrics_b, r'Total DOM depth:\s*(\d+)')
        ws_b = get_val(metrics_b, r'Whitespace Ratio:\s*([\d\.]+)')
        cv_b = get_val(metrics_b, r'Color Variance:\s*([\d\.]+)')
        asym_b = get_val(metrics_b, r'Asymmetry Score:\s*([\d\.]+)')
        
        # Create continuous feature vector (length 8)
        feature_vector = [dom_a, ws_a, cv_a, asym_a, dom_b, ws_b, cv_b, asym_b]
        
        # Determine target: 1 if A wins, 0 if B wins
        winner_is_a = 1.0 if re.search(r'\bVariant A\b', chosen_msgs[0]["content"], re.IGNORECASE) else 0.0
        
        margin = item.get("margin", 0.1) # Default to 0.1 if missing
        
        X.append(feature_vector)
        Y.append([winner_is_a])
        margins.append([margin])

    # Convert to PyTorch Tensors
    X_tensor = torch.tensor(X, dtype=torch.float32)
    Y_tensor = torch.tensor(Y, dtype=torch.float32)
    Margins_tensor = torch.tensor(margins, dtype=torch.float32)

    # We need to normalize the DOM depth since it's in the thousands, while others are 0-1
    # We will normalize each column independently (StandardScaler logic)
    means = X_tensor.mean(dim=0, keepdim=True)
    stds = X_tensor.std(dim=0, keepdim=True)
    stds[stds == 0] = 1.0 # Prevent div by zero
    
    X_normalized = (X_tensor - means) / stds

    # Save to disk for fast PyTorch loading
    dataset = {
        'X': X_normalized,
        'Y': Y_tensor,
        'margins': Margins_tensor,
        'normalization_params': {'means': means, 'stds': stds}
    }
    
    torch.save(dataset, output_tensor_file)
    print(f"Data distillation complete. Processed {len(X)} tuples.")
    print(f"Saved highly-optimized tensors to {output_tensor_file}")

if __name__ == "__main__":
    prepare_dataset(
        '/Users/obafemi/Documents/dev/dziner/taste-engine/results/master_dpo_dataset_v3.jsonl',
        '/Users/obafemi/Documents/dev/dziner/taste-engine/results/nano_taste_dataset.pt'
    )
