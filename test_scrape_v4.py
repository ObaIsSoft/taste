"""
test_scrape_v4.py — Test scraper with per-site process isolation.
Each site runs in a separate Python process, so a crash (EPIPE) in one site
doesn't affect the others. Failed sites are retried once.

Run: python3 test_scrape_v4.py [seed] [count]
"""
import gc
import random
import subprocess
import sys
import time
from pathlib import Path

# Worker script that runs in a subprocess (written to temp file so __file__ works)
WORKER_SCRIPT = """
import sys
from pathlib import Path
# Use __file__ to find the taste-engine directory (same approach as scraper.py)
script_dir = Path(__file__).parent
taste_engine_dir = script_dir.parent
sys.path.insert(0, str(taste_engine_dir))
sys.path.insert(0, str(taste_engine_dir / 'scripts'))
from scripts.scraper import scrape_site
try:
    result = scrape_site('{url}', '{site_id}')
    print(result.get('status', 'unknown'))
except Exception as e:
    print(f'error: {{str(e)[:100]}}')
"""


def scrape_single(url: str, site_id: str, taste_engine_dir: str, timeout: int = 180) -> str:
    """Scrape a single site in a subprocess (isolated memory)."""
    # Write worker script to a temp file inside taste-engine so __file__ resolves correctly
    worker_path = Path(taste_engine_dir) / "_worker.py"
    code = WORKER_SCRIPT.format(url=url, site_id=site_id)
    worker_path.write_text(code)

    try:
        result = subprocess.run(
            [sys.executable, str(worker_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(Path(__file__).parent)
        )
        # Get the last line of stdout (the status)
        lines = result.stdout.strip().split('\n')
        return lines[-1] if lines else 'unknown'
    except subprocess.TimeoutExpired:
        return 'timeout'
    except Exception as e:
        return f'error: {str(e)[:50]}'
    finally:
        # Clean up temp worker file
        try:
            worker_path.unlink()
        except Exception:
            pass


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 789
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 25

    taste_engine_dir = str(Path(__file__).parent / "taste-engine")

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
    print(f"Per-site process isolation: ON")
    print(f"Retry failed sites: ON\n")

    results = {"ok": 0, "failed": 0, "retried": 0, "errors": []}

    for i, url in enumerate(selected, 1):
        site_id = f"test4-{i:03d}"
        print(f"[{i}/{count}] {url} -> {site_id}", flush=True)

        # First attempt
        status = scrape_single(url, site_id, taste_engine_dir)

        if status == "ok":
            results["ok"] += 1
            print(f"  OK (attempt 1)", flush=True)
        else:
            # Retry once with fresh process
            results["retried"] += 1
            print(f"  Attempt 1 failed ({status}), retrying...", flush=True)
            time.sleep(2)

            status = scrape_single(url, site_id, taste_engine_dir, timeout=240)

            if status == "ok":
                results["ok"] += 1
                print(f"  OK (attempt 2)", flush=True)
            else:
                results["failed"] += 1
                results["errors"].append((site_id, url, status))
                print(f"  FAIL — {status}", flush=True)

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
