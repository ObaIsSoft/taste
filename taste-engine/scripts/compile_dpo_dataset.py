import os
import json
import random
import sys
import math
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    METADATA_FILE, VISUAL_FILE, MOTION_CODE_FILE,
    RATIONALE_FILE, VLM_RAW_FILE, ELO_FILE
)

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase = create_client(url, key)

DATA_DIR = Path(__file__).parent.parent / "data"
RESULTS_DIR = Path(__file__).parent.parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)
OUTPUT_FILE = RESULTS_DIR / "master_dpo_dataset.jsonl"

def load_site_data(site_id):
    """Loads metadata, visual_analysis, motion_code, and taste_rationale for a site."""
    site_dir = DATA_DIR / site_id
    if not site_dir.exists():
        return None
        
    try:
        with open(site_dir / METADATA_FILE) as f:
            meta = json.load(f)
        with open(site_dir / VISUAL_FILE) as f:
            visual = json.load(f)
            
        motion_path = site_dir / MOTION_CODE_FILE
        motion = json.load(open(motion_path)) if motion_path.exists() else {}
        
        rationale_path = site_dir / RATIONALE_FILE
        rationale = json.load(open(rationale_path)) if rationale_path.exists() else {}
        
        vlm_path = site_dir / VLM_RAW_FILE
        vlm_data = vlm_path.read_text().strip() if vlm_path.exists() else "No visual data"
        # Distill Motion
        libs = motion.get("libraries_detected", {})
        has_gsap = libs.get("gsap", False)
        has_scrolltrigger = libs.get("scrollTrigger", False)
        kf_count = len(motion.get("css_keyframes", {}))
        tr_count = len(motion.get("css_transitions", []))
        
        if has_gsap or has_scrolltrigger:
            motion_str = "Motion Engine: GSAP / ScrollTrigger Physics detected."
        elif kf_count > 0 or tr_count > 0:
            motion_str = f"Motion Engine: Native CSS Keyframes ({kf_count} keyframes, {tr_count} transitions), No physics engines detected."
        else:
            motion_str = "Motion Engine: None detected."
            
        # Distill Typography
        computed = meta.get("dom_structure", {}).get("computed_styles", [])
        total_nodes = meta.get("dom_structure", {}).get("tags", {}).get("total_nodes", "N/A")
        max_font_size = 0
        best_line_height = "normal"
        best_tracking = "normal"
        for style in computed:
            fs_str = style.get("fontSize", "0px")
            try:
                fs = float(fs_str.replace("px", ""))
                if fs > max_font_size:
                    max_font_size = fs
                    best_line_height = style.get("lineHeight", "normal")
                    best_tracking = style.get("letterSpacing", "normal")
            except:
                pass
                
        ratio_str = ""
        if best_line_height != "normal" and max_font_size > 0:
            try:
                lh = float(best_line_height.replace("px", ""))
                ratio = round(lh / max_font_size, 2)
                ratio_str = f"({ratio} ratio)"
            except:
                pass
                
        typo_str = f"Display Typography: {max_font_size}px, line-height: {best_line_height} {ratio_str}, tracking: {best_tracking}. Total DOM depth: {total_nodes} nodes."

        # Build the math/metrics payload
        metrics = {
            "whitespace_ratio": visual.get("whitespace_ratio", "N/A"),
            "color_variance": visual.get("color_variance", "N/A"),
            "palette_mood": visual.get("palette_mood", "N/A"),
            "asymmetry_score": visual.get("asymmetry_score", "N/A"),
            "motion_engine": motion_str,
            "typography": typo_str,
            "vlm_raw_description": vlm_data
        }
        
        return {
            "metrics": metrics,
            "rationale": rationale
        }
    except Exception as e:
        print(f"Error loading {site_id}: {e}")
        return None

def format_metrics(metrics):
    return (
        f"- {metrics['typography']}\n"
        f"- Whitespace Ratio: {metrics.get('whitespace_ratio', 'N/A')}\n"
        f"- Color Variance: {metrics['color_variance']}\n"
        f"- Palette Mood: {metrics['palette_mood']}\n"
        f"- Asymmetry Score: {metrics['asymmetry_score']}\n"
        f"- {metrics['motion_engine']}\n"
        f"- Visual Forensic Description: {metrics['vlm_raw_description']}"
    )

def format_rationale(letter, rationale, metrics):
    taste_rule = rationale.get("taste_rule", "N/A")
    premium = " ".join(rationale.get("premium_signals", []))
    return f"Variant {letter} demonstrates elite aesthetic execution.\nTaste Rule: {taste_rule}\nPremium Signals: {premium}"

def main():
    print("Fetching match history from Supabase...")
    # Using postgrest limit/pagination if > 1000, but 620 fits in one fetch
    response = supabase.table("match_history").select("*").limit(2000).execute()
    matches = response.data
    
    print(f"Found {len(matches)} matches in Supabase.")
    
    elo_scores = {}
    if ELO_FILE.exists():
        elo_scores = json.loads(ELO_FILE.read_text())
    
    valid_pairs = []
    seen_pairs = set()
    
    for match in matches:
        if match.get("is_draw"):
            continue
            
        winner_id = match["winner_id"]
        loser_id = match["loser_id"]
        
        # Calculate TrueSkill Margin for MADPO
        mu_w = elo_scores.get(winner_id, {}).get("mu", 25.0)
        sigma_w = elo_scores.get(winner_id, {}).get("sigma", 8.333)
        mu_l = elo_scores.get(loser_id, {}).get("mu", 25.0)
        sigma_l = elo_scores.get(loser_id, {}).get("sigma", 8.333)
        
        margin = (mu_w - mu_l) / math.sqrt(sigma_w**2 + sigma_l**2)
        
        # Deduplicate A vs B matches
        pair_sig = tuple(sorted([winner_id, loser_id]))
        if pair_sig in seen_pairs:
            continue
        seen_pairs.add(pair_sig)
        
        # Load local data
        winner_data = load_site_data(winner_id)
        loser_data = load_site_data(loser_id)
        
        if not winner_data or not loser_data:
            continue
            
        if not winner_data["rationale"] or not loser_data["rationale"]:
            continue
        # Create both permutations to prevent positional bias in DPO (A vs B, B vs A)
        permutations = [
            (winner_id, winner_data, True, loser_id, loser_data, False),
            (loser_id, loser_data, False, winner_id, winner_data, True)
        ]
        
        for p in permutations:
            var_A_id, var_A_data, var_A_is_winner, var_B_id, var_B_data, var_B_is_winner = p
            
            prompt = (
                "Evaluate Variant A and Variant B for aesthetic equilibrium and structural tension.\n\n"
                "VARIANT A METRICS:\n" + format_metrics(var_A_data["metrics"]) + "\n\n"
                "VARIANT B METRICS:\n" + format_metrics(var_B_data["metrics"])
            )
            
            winner_letter = "A" if var_A_is_winner else "B"
            loser_letter = "B" if var_A_is_winner else "A"
            
            winner_d = var_A_data if var_A_is_winner else var_B_data
            loser_d = var_B_data if var_A_is_winner else var_A_data
            
            chosen_text = format_rationale(winner_letter, winner_d["rationale"], winner_d["metrics"])
            rejected_text = format_rationale(loser_letter, loser_d["rationale"], loser_d["metrics"])
            
            valid_pairs.append({
                "prompt": prompt,
                "chosen": chosen_text,
                "rejected": rejected_text,
                "margin": round(margin, 4)
            })
        
    print(f"Generated {len(valid_pairs)} valid DPO tuples.")
    
    with open(OUTPUT_FILE, "w") as f:
        for obj in valid_pairs:
            f.write(json.dumps(obj) + "\n")
            
    print(f"Saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
