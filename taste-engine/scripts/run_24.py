import os
import shutil
import sys
from playwright.sync_api import sync_playwright

sys.path.append('/Users/obafemi/Documents/dev/dziner/taste-engine/scripts')
from batch_scraper_v2 import process_site, VIEWPORT, DATA_DIR, parse_urls

target_sites = ['004', '024', '026', '042', '053', '060', '071', '074', '078', '102', '108', '268', '269', '273', '276', '341', '345', '353', '360', '361', '365', '374', '394', '396', '406']

all_urls = parse_urls()

for site in target_sites:
    path = DATA_DIR / f'site-{site}'
    if path.exists():
        shutil.rmtree(path)
        print(f"Deleted old folder for site-{site}")

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        executable_path='/Applications/Brave Browser.app/Contents/MacOS/Brave Browser',
        args=[
            '--ignore-gpu-blocklist',
            '--use-gl=angle',
            '--use-angle=gl',
            '--enable-webgl',
            '--enable-gpu-rasterization'
        ]
    )
    context = browser.new_context(
        viewport={'width': VIEWPORT['width'], 'height': VIEWPORT['height']},
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36'
    )
    context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    for site in target_sites:
        try:
            url = all_urls[int(site) - 1]
        except IndexError:
            print(f"Skipping site-{site}, URL not found")
            continue
        print(f"--- Processing target site-{site}: {url} ---")
        process_site(context, url, f'site-{site}')
        
    browser.close()
