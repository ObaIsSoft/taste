"""
test_scrape_v2.py — Test scraper with per-site process isolation and retry.
Each site runs in a separate Python process to prevent memory buildup.
Failed sites are retried once with a fresh browser.

Run: python3 test_scrape_v2.py [seed] [count]
"""
import random
import subprocess
import sys
import time
from pathlib import Path

def scrape_single(url: str, site_id: str, timeout: int = 180) -> dict:
    """Scrape a single site in a subprocess (isolated memory)."""
    code = f"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path('{Path(__file__).parent}' / 'taste-engine'))
sys.path.insert(0, str(Path('{Path(__file__).parent}' / 'taste-engine' / 'scripts'))
from scripts.scraper import scrape_site
result = scrape_site('{url}', '{site_id}')
print(result.get('status', 'unknown'))
"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(Path(__file__).parent)
        )
        status = result.stdout.strip().split('\n')[-1] if result.stdout.strip() else 'unknown'
        return {"status": status, "stdout": result.stdout, "stderr": result.stderr}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "stdout": "", "stderr": "timeout"}
    except Exception as e:
        return {"status": "error", "stdout": "", "stderr": str(e)}


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

    print(f"Seed: {seed}, Count: {count}")
    print(f"Selected {len(selected)} random sites\n")

    results = {"ok": 0, "failed": 0, "retried": 0, "errors": []}

    for i, url in enumerate(selected, 1):
        site_id = f"test3-{i:03d}"
        print(f"[{i}/{count}] {url} -> {site_id}", flush=True)

        # First attempt
        result = scrape_single(url, site_id)

        if result["status"] == "ok":
            results["ok"] += 1
            print(f"  OK (attempt 1)", flush=True)
        else:
            # Retry once with fresh process
            results["retried"] += 1
            print(f"  Attempt 1 failed ({result['status']}), retrying...", flush=True)
            time.sleep(2)

            result = scrape_single(url, site_id, timeout=240)

            if result["status"] == "ok":
                results["ok"] += 1
                print(f"  OK (attempt 2)", flush=True)
            else:
                results["failed"] += 1
                results["errors"].append((site_id, url, result["status"]))
                print(f"  FAIL — {result['status']}", flush=True)

        time.sleep(0.5)

    print(f"\n{'='*60}")
    print(f"RESULTS: {results['ok']}/{count} succeeded ({results['ok']/count*100:.1f}%)")
    print(f"  Retried: {results['retried']}")
    print(f"  Failed: {results['failed']}")
    print(f"{'='*60}")

    if results["errors"]:
        print("\nFailed sites:")
        for site_id, url, status in results["errors"]:
            print(f"  {site_id}: {url} — {status}")


if __name__ == "__main__":
    main()
