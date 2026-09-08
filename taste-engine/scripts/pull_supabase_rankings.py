import os
import json
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

response = supabase.table("ratings").select("*").execute()
data = response.data

# Sort by conservative_score (mu - 3*sigma) descending
data.sort(key=lambda x: x.get('conservative_score', 0), reverse=True)

winners = data[:15]
losers = data[-15:]

results_dir = Path(__file__).parent.parent / "results"
results_dir.mkdir(exist_ok=True)

with open(results_dir / "winners_summaries.json", "w") as f:
    json.dump([{"site_id": r["site_id"]} for r in winners], f, indent=2)

with open(results_dir / "losers_summaries.json", "w") as f:
    json.dump([{"site_id": r["site_id"]} for r in losers], f, indent=2)

print(f"Pulled {len(data)} ratings from Supabase.")
print("Saved winners and losers to results directory.")
