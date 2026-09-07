"""
extract_taste.py — Phase 2: The Taste Extractor

Queries Supabase for the RLHF Ground Truth. 
Extracts visual math, metadata, and motion physics for the Top 15 (Winners) and Bottom 15 (Losers).
Uses Gemini to synthesize the underlying system differences (physics, spacing, type).
"""
import sys
import os
import json
import requests
from pathlib import Path
from supabase import create_client, Client
import statistics

# Allow running from scripts/ or from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from config import DATA_DIR, OLLAMA_URL

console = Console()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def load_site_data(site_id):
    site_dir = DATA_DIR / site_id
    if not site_dir.exists():
        return None
        
    data = {}
    
    # 1. Visual Math
    visual_path = site_dir / "visual_analysis.json"
    if visual_path.exists():
        data["visual"] = json.loads(visual_path.read_text())
        
    # 2. Metadata (DOM, Typo)
    meta_path = site_dir / "metadata.json"
    if meta_path.exists():
        data["meta"] = json.loads(meta_path.read_text())
        
    # 3. Motion Physics
    motion_path = site_dir / "motion_code.json"
    if motion_path.exists():
        motion = json.loads(motion_path.read_text())
        data["motion"] = {
            "gsap_detected": motion.get("gsap_detected", False),
            "gsap_calls": len(motion.get("gsap_calls", [])),
            "css_transitions": len(motion.get("css_transitions", [])),
            "scroll_driven": motion.get("scroll_patterns", {}).get("scroll_driven_count", 0)
        }
        
    # 4. Rationale
    rationale_path = site_dir / "taste_rationale.md"
    if rationale_path.exists():
        data["rationale"] = rationale_path.read_text()
        
    return data

def aggregate_cohort(sites):
    aggregated = {
        "avg_whitespace": [],
        "avg_asymmetry": [],
        "avg_brightness": [],
        "avg_max_font_size": [],
        "avg_dom_nodes": [],
        "motion_profiles": [],
        "rationales": []
    }
    
    for site in sites:
        site_id = site["site_id"]
        data = load_site_data(site_id)
        if not data:
            continue
            
        if "visual" in data:
            aggregated["avg_whitespace"].append(data["visual"].get("whitespace_ratio", 0))
            aggregated["avg_asymmetry"].append(data["visual"].get("asymmetry_score", 0))
            aggregated["avg_brightness"].append(data["visual"].get("avg_brightness", 0))
            
        if "meta" in data:
            dom = data["meta"].get("dom_structure", {})
            aggregated["avg_dom_nodes"].append(dom.get("tags", {}).get("total_nodes", 0))
            aggregated["avg_max_font_size"].append(dom.get("typography", {}).get("max_font_size_px", 0))
            
        if "motion" in data:
            aggregated["motion_profiles"].append(data["motion"])
            
        if "rationale" in data:
            # We just take a snippet of the rationale to save token space
            lines = data["rationale"].split("\n")
            snippet = "\n".join([line for line in lines if line.startswith("* `")])
            aggregated["rationales"].append(snippet)
            
    # Calculate means
    def mean(lst):
        return sum(lst) / len(lst) if lst else 0
        
    return {
        "whitespace_ratio": mean(aggregated["avg_whitespace"]),
        "asymmetry_score": mean(aggregated["avg_asymmetry"]),
        "brightness": mean(aggregated["avg_brightness"]),
        "max_font_size_px": mean(aggregated["avg_max_font_size"]),
        "dom_nodes": mean(aggregated["avg_dom_nodes"]),
        "motion_summary": f"{sum(1 for m in aggregated['motion_profiles'] if m.get('gsap_detected'))} sites used GSAP. Avg scroll triggers: {mean([m.get('scroll_driven', 0) for m in aggregated['motion_profiles']])}",
        "design_principles_extracted": "\n".join(aggregated["rationales"])
    }

def main():
    console.print("[cyan]Fetching RLHF Ground Truth from Supabase...[/cyan]")
    res = supabase.table("ratings").select("site_id, mu, sigma").execute()
    data = res.data
    
    if len(data) < 30:
        console.print("[red]Not enough data to extract top/bottom 15.[/red]")
        sys.exit(1)
        
    for d in data:
        d["score"] = d["mu"] - 3 * d["sigma"]
        
    data.sort(key=lambda x: x["score"], reverse=True)
    
    top_15 = data[:15]
    bottom_15 = data[-15:]
    
    console.print("[cyan]Aggregating Math & Physics for Top 15 (Winners)...[/cyan]")
    top_15_agg = aggregate_cohort(top_15)
    
    console.print("[cyan]Aggregating Math & Physics for Bottom 15 (Losers)...[/cyan]")
    bottom_15_agg = aggregate_cohort(bottom_15)
    
    prompt = f"""
You are the world's leading expert in digital design, motion physics, and aesthetic mathematics.
I am providing you with the aggregated structural data, mathematical layouts, and motion physics (GSAP/CSS) for the Top 15 Highest Rated websites (The Winners) and the Bottom 15 Lowest Rated websites (The Losers). 

IMPORTANT CONTEXT: All 30 of these websites are premium Awwwards/Landbook winners. The "Losers" are not bad 1990s websites; they are simply the *least preferred* among an elite group based on 700+ human RLHF votes.

Your task is to analyze the subtle differences in the underlying system: typography scaling, whitespace ratios, layout asymmetry, and motion choreography/physics.

Extract the definitive "Rules of Taste" from this dataset. Focus on the systems, physics, and execution.

TOP 15 (THE WINNERS) DATA:
{json.dumps(top_15_agg, indent=2)}

BOTTOM 15 (THE LOSERS) DATA:
{json.dumps(bottom_15_agg, indent=2)}

Output a comprehensive, highly-detailed Markdown report that covers:
1. The Core Differences (Visual & Mathematical)
2. Typography & Layout Systems (Density, Grids, Asymmetry)
3. Motion & Physics (GSAP vs CSS, easing, interaction)
4. The Definitive "Taste Tokens" (Actionable rules to achieve top-tier aesthetic)
"""

    console.print(f"[cyan]Synthesizing structural differences with local Ollama model...[/cyan]")
    
    payload = {
        "model": "llama3.1", # Or whichever model you are running locally (e.g. qwen2, llava)
        "prompt": prompt,
        "stream": False
    }
    
    try:
        req = requests.post(OLLAMA_URL, json=payload)
        req.raise_for_status()
        response_text = req.json().get("response", "")
    except Exception as e:
        console.print(f"[red]Error connecting to Ollama at {OLLAMA_URL}: {e}[/red]")
        sys.exit(1)
    
    out_dir = Path(__file__).parent.parent / "results"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / "taste_extraction_report.md"
    
    out_file.write_text(response_text)
    console.print(f"[green]✓ Analysis complete! Saved to {out_file}[/green]")

if __name__ == "__main__":
    main()
