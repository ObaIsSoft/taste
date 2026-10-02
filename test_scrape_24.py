"""
test_scrape_24.py — Test the fixed scraper on 24 random sites from the 1k list.
Run: python3 test_scrape_24.py
"""
import random
import sys
import time
from pathlib import Path

# Add taste-engine to path
sys.path.insert(0, str(Path(__file__).parent / "taste-engine"))
sys.path.insert(0, str(Path(__file__).parent / "taste-engine" / "scripts"))

from scripts.scraper import scrape_site

# Read the 1k URL list
list_path = Path(__file__).parent / "list.md"
urls = []
for line in list_path.read_text().splitlines():
    line = line.strip()
    if not line:
        continue
    # Extract URL from numbered list
    if ". " in line:
        url = line.split(". ", 1)[1].strip()
        if url.startswith("http"):
            urls.append(url)

print(f"Found {len(urls)} URLs in list.md")

# Pick 24 random sites (seeded for reproducibility)
random.seed(42)
selected = random.sample(urls, 24)

print(f"Selected {len(selected)} random sites for testing:\n")
for i, url in enumerate(selected, 1):
    print(f"  {i:2d}. {url}")

print(f"\n{'='*60}")
print("Starting scrape test...")
print(f"{'='*60}\n")

results = {"ok": 0, "failed": 0, "errors": []}

for i, url in enumerate(selected, 1):
    site_id = f"test-{i:03d}"
    print(f"\n[{i}/24] Scraping {url} → {site_id}")
    try:
        result = scrape_site(url, site_id)
        if result.get("status") == "ok":
            results["ok"] += 1
            print(f"  ✓ Success — {result.get('title', 'no title')}")
        else:
            results["failed"] += 1
            results["errors"].append((site_id, url, result.get("error", "unknown")))
            print(f"  ✗ Failed — {result.get('error', 'unknown error')}")
    except Exception as e:
        results["failed"] += 1
        results["errors"].append((site_id, url, str(e)))
        print(f"  ✗ Exception — {e}")
    time.sleep(1)  # be polite

print(f"\n{'='*60}")
print(f"RESULTS: {results['ok']}/24 succeeded, {results['failed']}/24 failed")
print(f"{'='*60}")

if results["errors"]:
    print("\nFailed sites:")
    for site_id, url, error in results["errors"]:
        print(f"  {site_id}: {url}")
        print(f"    Error: {error}")

print(f"\nData saved to: taste-engine/data/")
