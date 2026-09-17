import json
import re

def process_dataset(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        data = [json.loads(line) for line in f]

    processed_data = []

    for idx, item in enumerate(data):
        prompt_msgs = item.get("prompt", [])
        chosen_msgs = item.get("chosen", [])
        rejected_msgs = item.get("rejected", [])
        
        if len(prompt_msgs) < 2:
            continue
            
        system_msg = prompt_msgs[0]
        user_content = prompt_msgs[1]["content"]
        
        # 1. Isolate the Metric Blocks
        split_b = re.split(r'VARIANT\s+B\s+METRICS:', user_content, flags=re.IGNORECASE)
        if len(split_b) < 2: continue
        split_a = re.split(r'VARIANT\s+A\s+METRICS:', split_b[0], flags=re.IGNORECASE)
        if len(split_a) < 2: continue
            
        header = split_a[0].strip()
        original_metrics_a = split_a[1].strip()
        original_metrics_b = split_b[1].strip()
        
        # 2. Enforce 50/50 Positional Parity BEFORE Math
        original_winner = "A" if re.search(r'\bVariant A\b', chosen_msgs[0]["content"], re.IGNORECASE) else "B"
        target_winner = "A" if idx % 2 == 0 else "B"
        
        if original_winner != target_winner:
            # Execute Swap
            final_metrics_a = original_metrics_b
            final_metrics_b = original_metrics_a
            
            # Robust label flip using regex to avoid case/substring collision
            def flip_labels(text):
                text = re.sub(r'\bVariant A\b', '[TEMP_A]', text, flags=re.IGNORECASE)
                text = re.sub(r'\bVariant B\b', 'Variant A', text, flags=re.IGNORECASE)
                text = re.sub(r'\[TEMP_A\]', 'Variant B', text, flags=re.IGNORECASE)
                return text
                
            new_chosen = flip_labels(chosen_msgs[0]["content"])
            new_rejected = flip_labels(rejected_msgs[0]["content"])
        else:
            # Maintain Order
            final_metrics_a = original_metrics_a
            final_metrics_b = original_metrics_b
            new_chosen = chosen_msgs[0]["content"]
            new_rejected = rejected_msgs[0]["content"]

        # 3. Arithmetic Extraction Engine (Operating on the Final Positions)
        def get_val(text, pattern):
            match = re.search(pattern, text)
            return float(match.group(1)) if match else 0.0
            
        dom_a = get_val(final_metrics_a, r'Total DOM depth:\s*(\d+)')
        dom_b = get_val(final_metrics_b, r'Total DOM depth:\s*(\d+)')
        ws_a = get_val(final_metrics_a, r'Whitespace Ratio:\s*([\d\.]+)')
        ws_b = get_val(final_metrics_b, r'Whitespace Ratio:\s*([\d\.]+)')
        cv_a = get_val(final_metrics_a, r'Color Variance:\s*([\d\.]+)')
        cv_b = get_val(final_metrics_b, r'Color Variance:\s*([\d\.]+)')
        asym_a = get_val(final_metrics_a, r'Asymmetry Score:\s*([\d\.]+)')
        asym_b = get_val(final_metrics_b, r'Asymmetry Score:\s*([\d\.]+)')
        
        # 4. Compute the Semantic Deltas
        dom_diff = dom_b - dom_a
        dom_pct = (dom_diff / dom_a * 100) if dom_a else 0
        ws_diff = ws_b - ws_a
        cv_diff = cv_b - cv_a
        asym_diff = asym_b - asym_a
        
        delta_block = (
            f"\n\n[COMPUTED METRIC DELTAS]:\n"
            f"- DOM Depth: Variant B has {abs(dom_diff):.0f} {'more' if dom_diff > 0 else 'fewer'} nodes "
            f"({abs(dom_pct):.1f}% {'heavier' if dom_pct > 0 else 'lighter'} than A).\n"
            f"- Whitespace: Variant B ratio is {'higher' if ws_diff > 0 else 'lower'} by {abs(ws_diff):.3f}.\n"
            f"- Color Variance: Variant B is {'higher' if cv_diff > 0 else 'lower'} by {abs(cv_diff):.3f}.\n"
            f"- Asymmetry Score: Variant B is {'higher' if asym_diff > 0 else 'lower'} by {abs(asym_diff):.3f}.\n"
        )
        
        # 5. Reconstruct and Append
        new_user_content = f"{header}\n\nVARIANT A METRICS:\n{final_metrics_a}\n\nVARIANT B METRICS:\n{final_metrics_b}{delta_block}"

        processed_data.append({
            "prompt": [system_msg, {"role": "user", "content": new_user_content}],
            "chosen": [{"role": "assistant", "content": new_chosen}],
            "rejected": [{"role": "assistant", "content": new_rejected}],
            "margin": item.get("margin", 1.0)
        })

    with open(output_file, 'w', encoding='utf-8') as f:
        for row in processed_data:
            f.write(json.dumps(row) + '\n')
            
    print(f"Compilation successful. Processed {len(processed_data)} pairs with perfect 50/50 parity.")

if __name__ == "__main__":
    process_dataset(
        '/Users/obafemi/Documents/dev/dziner/taste-engine/results/master_dpo_dataset_v3.jsonl', 
        '/Users/obafemi/Documents/dev/dziner/taste-engine/results/master_dataset_v4_delta.jsonl'
    )
