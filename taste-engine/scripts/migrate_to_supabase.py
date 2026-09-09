"""
migrate_to_supabase.py

Uploads local `ratings.json` and embeddings to Supabase.
Run this once after setting up your Supabase database.
"""
import sys
import json
import os
from pathlib import Path
from supabase import create_client, Client

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATA_DIR, EMBED_FILE
from rich.console import Console

console = Console()

def get_env_var(key):
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    return os.environ.get(key)

SUPABASE_URL = get_env_var("SUPABASE_URL")
SUPABASE_KEY = get_env_var("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    console.print("[red]✗ SUPABASE_URL or SUPABASE_KEY not found in .env[/red]")
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def migrate():
    # 1. Upload Ratings
    ratings_path = DATA_DIR / "ratings.json"
    if ratings_path.exists():
        ratings_data = json.loads(ratings_path.read_text())
    else:
        console.print("[yellow]No ratings.json found. Initializing defaults from data directory.[/yellow]")
        ratings_data = {}
        for site_dir in DATA_DIR.glob("site-*"):
            if site_dir.is_dir() and (site_dir / "embedding.json").exists():
                ratings_data[site_dir.name] = {}

    for site_id, data in ratings_data.items():
        rating = data.get("rating", {})
        mu = rating.get("mu", 25.0)
        sigma = rating.get("sigma", 8.333)
        wins = data.get("wins", 0)
        losses = data.get("losses", 0)
        comparisons = data.get("comparisons", 0)
        
        # Load embedding
        emb_path = DATA_DIR / site_id / EMBED_FILE
        vector = None
        if emb_path.exists():
            vector = json.loads(emb_path.read_text()).get("vector")
            
        row = {
            "site_id": site_id,
            "mu": mu,
            "sigma": sigma,
            "wins": wins,
            "losses": losses,
            "comparisons": comparisons,
            "vector": vector
        }
        
        # Upsert
        res = supabase.table("ratings").upsert(row).execute()
        console.print(f"[green]✓ Upserted[/green] {site_id}")
        
    console.print("[bold green]Migration complete![/bold green]")

if __name__ == "__main__":
    migrate()
