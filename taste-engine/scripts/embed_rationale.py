"""
embed_rationale.py — Step 5b: Vector Embedding for Matchmaking

Generates numerical embeddings from the taste rationale using Gemini's text-embedding API.
This allows elo_validator.py to cluster similar sites together for fair matchmaking.
"""
import sys
import json
import time
import os
from pathlib import Path
from google import genai

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from config import DATA_DIR

console = Console()

def get_api_key():
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("GEMINI_API_KEY")

API_KEY = get_api_key()
if not API_KEY or API_KEY == "your_key_here":
    console.print("[red]✗ GEMINI_API_KEY not found.[/red]")
    sys.exit(1)

client = genai.Client(api_key=API_KEY)

def generate_embedding(site_id: str):
    site_dir = DATA_DIR / site_id
    rationale_path = site_dir / "taste_rationale.md"
    embed_path = site_dir / "embedding.json"

    if not rationale_path.exists():
        return False
        
    try:
        text = rationale_path.read_text()
        console.print(f"[cyan]→[/cyan] Embedding {site_id}...")
        
        response = client.models.embed_content(
            model='gemini-embedding-2',
            contents=text,
        )
        
        vector = response.embeddings[0].values
        
        embed_path.write_text(json.dumps({"vector": vector}))
        console.print(f"[green]✓[/green] Embedding saved for {site_id}")
        return True
        
    except Exception as e:
        console.print(f"[red]✗ Failed to embed {site_id}: {e}[/red]")
        return False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", help="Process a single site ID")
    args = parser.parse_args()

    if args.site:
        generate_embedding(args.site)
    else:
        for site_dir in sorted(DATA_DIR.iterdir()):
            if site_dir.is_dir() and (site_dir / "taste_rationale.md").exists():
                generate_embedding(site_dir.name)
                time.sleep(1)  # respect rate limits
