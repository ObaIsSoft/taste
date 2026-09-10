import json
import urllib.request
import random
from pathlib import Path
from rich.console import Console

console = Console()
DATA_FILE = Path(__file__).parent.parent / "results" / "master_dpo_dataset.jsonl"
OUT_FILE = Path(__file__).parent.parent / "model_evaluation.md"

def query_ollama(prompt: str) -> str:
    payload = {
        "model": "taste-critic",
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 128
        }
    }
    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as res:
            response_data = json.loads(res.read().decode("utf-8"))
            return response_data.get("response", "")
    except Exception as e:
        return ""

def extract_winner(text: str) -> str:
    # Look for "Variant A" or "Variant B" at the start
    text = text.strip()
    if text.startswith("Variant A"):
        return "A"
    if text.startswith("Variant B"):
        return "B"
    return "UNKNOWN"

def main():
    if not DATA_FILE.exists():
        console.print(f"[red]Could not find {DATA_FILE}[/red]")
        return
        
    lines = DATA_FILE.read_text().strip().split("\n")
    dpo_data = [json.loads(l) for l in lines]
    
    # We want 50 unique physical matchups. 
    # Because our dataset already has A vs B and B vs A duplicated, 
    # we need to group them.
    # Actually, we can just pick 50 random lines, and for each line, manually flip the prompt to create the B vs A version.
    
    sample_lines = random.sample(dpo_data, min(50, len(dpo_data)))
    
    correct_picks = 0
    total_queries = 0
    picked_a = 0
    picked_b = 0
    stable_content = 0
    
    results_md = "# Taste Engine Evaluation (100 Queries)\n\n"
    
    console.print(f"[bold cyan]Running evaluation on {len(sample_lines)} pairs (100 total queries)...[/bold cyan]")
    
    for idx, pair in enumerate(sample_lines):
        # Forward prompt (as it is in the dataset)
        prompt_fwd = pair["prompt"]
        chosen_fwd = pair["chosen"]
        expected_winner_fwd = extract_winner(chosen_fwd)
        
        # Backward prompt (swap A and B metrics in the text)
        # We split the prompt to find "VARIANT A METRICS:" and "VARIANT B METRICS:"
        parts = prompt_fwd.split("VARIANT A METRICS:\n")
        intro = parts[0]
        metrics_parts = parts[1].split("\n\nVARIANT B METRICS:\n")
        metric_a = metrics_parts[0]
        metric_b = metrics_parts[1]
        
        prompt_bwd = f"{intro}VARIANT A METRICS:\n{metric_b}\n\nVARIANT B METRICS:\n{metric_a}"
        expected_winner_bwd = "B" if expected_winner_fwd == "A" else "A"
        
        # Test Forward
        resp_fwd = query_ollama(prompt_fwd)
        actual_fwd = extract_winner(resp_fwd)
        
        if actual_fwd == expected_winner_fwd:
            correct_picks += 1
        if actual_fwd == "A":
            picked_a += 1
        elif actual_fwd == "B":
            picked_b += 1
            
        total_queries += 1
        console.print(f"[{total_queries}/100] Forward: Expected {expected_winner_fwd}, Got {actual_fwd}")
        
        # Test Backward
        resp_bwd = query_ollama(prompt_bwd)
        actual_bwd = extract_winner(resp_bwd)
        
        if actual_bwd == expected_winner_bwd:
            correct_picks += 1
        if actual_bwd == "A":
            picked_a += 1
        elif actual_bwd == "B":
            picked_b += 1
            
        total_queries += 1
        console.print(f"[{total_queries}/100] Backward: Expected {expected_winner_bwd}, Got {actual_bwd}")
        
        # Content Stability: Did it pick the same underlying design?
        # If it picked A in forward, the same design is B in backward.
        if (actual_fwd == "A" and actual_bwd == "B") or (actual_fwd == "B" and actual_bwd == "A"):
            stable_content += 1
            
    accuracy = correct_picks / total_queries
    p_a = picked_a / total_queries
    p_b = picked_b / total_queries
    stability = stable_content / len(sample_lines)
    
    md_content = f"""# Taste Engine Alpha - Positional Bias Evaluation

**Test Configuration:** 50 distinct matchups evaluated forward (A vs B) and reversed (B vs A) for a total of 100 queries.

## Results
- **Total Queries:** {total_queries}
- **Accuracy:** {correct_picks}/{total_queries} = {accuracy:.2f}
- **P(pick A):** {picked_a}/{total_queries} = {p_a:.2f}
- **P(pick B):** {picked_b}/{total_queries} = {p_b:.2f}
- **Content Stability:** {stable_content}/{len(sample_lines)} = {stability:.2f}

## Conclusion
If Content Stability is low and P(pick B) is extremely high, the model is suffering from severe positional bias (it favors the letter B rather than the design metrics). This mathematically confirms the necessity of transitioning from SFT to Margin-Adaptive DPO (MADPO) with balanced tuple placements and true contrastive preference gradients.
"""
    OUT_FILE.write_text(md_content)
    console.print(f"\n[bold green]Evaluation complete! Saved to {OUT_FILE}[/bold green]")
    console.print(md_content)

if __name__ == "__main__":
    main()
