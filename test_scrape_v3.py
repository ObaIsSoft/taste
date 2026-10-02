"""
test_scrape_v3.py — Test scraper with in-process retry and memory management.
Each site gets a fresh browser instance. Failed sites are retried once.
Explicit garbage collection prevents memory buildup.

Run: python3 test_scrape_v3.py [seed] [count]
"""
import gc
import random
import sys
import time
import traceback
from pathlib import Path

# Add taste-engine to path
sys.path.insert(0, str(Path(__file__).parent / "taste-engine"))
sys.path.insert(0, str(Path(__file__).parent / "taste-engine" / "scripts"))


def scrape_with_retry(url: str, site_id: str, max_attempts: int = 2) -> dict:
    """Scrape a single site with retry logic and memory cleanup."""
    from scripts.scraper import scrape_site

    for attempt in range(1, max_attempts + 1):
        try:
            result = scrape_site(url, site_id)
            if result.get("status") == "ok":
                return result
            # If failed but not last attempt, retry
            if attempt < max_attempts:
                print(f"    Retrying (attempt {attempt + 1})...", flush=True)
                time.sleep(3)
        except Exception as e:
            if attempt < max_attempts:
                print(f"    Exception: {str(e)[:60]}, retrying...", flush=True)
                time.sleep(3)
            else:
                return {"status": "error", "error": str(e)}

    return result if 'result' in dir() else {"status": "failed", "error": "all attempts failed"}


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 456
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 25

    list_path = Path(__file__).parent / "list.md"
    urls = []
    for line in list_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        if ". " in line:
            url = line.split(". ", 1)[1].strip()
            if url.startswith("http"):
                urls.append(url)

    random.seed(seed)
    selected = random.sample(urls, count)

    # Pre-filter: skip URLs with DNS resolution failures
    import socket
    valid_urls = []
    dns_failures = []
    for url in selected:
        hostname = url.split("/")[2]
        try:
            socket.gethostbyname(hostname)
            valid_urls.append(url)
        except socket.gaierror:
            dns_failures.append(url)

    if dns_failures:
        print(f"Skipping {len(dns_failures)} URLs with DNS failures:")
        for url in dns_failures:
            print(f"  {url}")
        print()

    selected = valid_urls
    count = len(selected)

    print(f"Seed: {seed}, Count: {count} (after DNS filter)")
    print(f"Selected {len(selected)} random sites\n")

    results = {"ok": 0, "failed": 0, "retried": 0, "errors": []}

    for i, url in enumerate(selected, 1):
        site_id = f"test3-{i:03d}"
        print(f"[{i}/{count}] {url} -> {site_id}", flush=True)

        result = scrape_with_retry(url, site_id)

        if result.get("status") == "ok":
            results["ok"] += 1
            print(f"  OK — {result.get('title', 'no title')[:60]}", flush=True)
        else:
            results["failed"] += 1
            error = result.get("error", result.get("status", "unknown"))
            results["errors"].append((site_id, url, error))
            print(f"  FAIL — {error[:80]}", flush=True)

        # Explicit garbage collection after each site
        gc.collect()
        time.sleep(0.5)

    print(f"\n{'='*60}")
    print(f"RESULTS: {results['ok']}/{count} succeeded ({results['ok']/count*100:.1f}%)")
    print(f"  Failed: {results['failed']}")
    print(f"{'='*60}")

    if results["errors"]:
        print("\nFailed sites:")
        for site_id, url, error in results["errors"]:
            print(f"  {site_id}: {url}")
            print(f"    Error: {error[:100]}")


if __name__ == "__main__":
    main()
