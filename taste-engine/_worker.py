
import sys
from pathlib import Path
# Use __file__ to find the taste-engine directory (same approach as scraper.py)
script_dir = Path(__file__).parent
taste_engine_dir = script_dir.parent
sys.path.insert(0, str(taste_engine_dir))
sys.path.insert(0, str(taste_engine_dir / 'scripts'))
from scripts.scraper import scrape_site
try:
    result = scrape_site('https://gchf.kr/index.html/', 'test4-020')
    print(result.get('status', 'unknown'))
except Exception as e:
    print(f'error: {str(e)[:100]}')
