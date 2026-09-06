import re
from pathlib import Path

list_content = Path("../list.md").read_text()
scraper_path = Path("scripts/scraper.py")
scraper_content = scraper_path.read_text()

urls = []
for line in list_content.splitlines():
    line = line.strip()
    if not line: continue
    # Extract url
    match = re.search(r'https?://[^\s]+', line)
    if match:
        url = match.group(0).strip('/') # remove trailing slashes for uniformity if you want, but actually URLs can have slashes
        url = match.group(0)
        urls.append(url)

# Remove duplicates while preserving order
seen = set()
unique_urls = []
for u in urls:
    if u not in seen:
        seen.add(u)
        unique_urls.append(u)

# Limit to 100
unique_urls = unique_urls[:100]

sites_block = "SITES = [\n"
for i, url in enumerate(unique_urls, 1):
    site_id = f"site-{i:03d}"
    sites_block += f'    {{"url": "{url}", "id": "{site_id}"}},\n'
sites_block += "]\n"

# Replace in scraper.py
start_idx = scraper_content.find("SITES = [")
end_idx = scraper_content.find("]", start_idx) + 1

if start_idx != -1 and end_idx != 0:
    new_content = scraper_content[:start_idx] + sites_block + scraper_content[end_idx:]
    scraper_path.write_text(new_content)
    print(f"Updated scraper.py with {len(unique_urls)} sites.")
else:
    print("Could not find SITES block in scraper.py")
