from pathlib import Path
import json

data_dir = Path("data")
missing_files = {}

required = [
    "metadata.json",
    "motion_code.json",
    "screenshot_hero.png",
    "screenshot_full.png"
]

for i in range(1, 101):
    site_id = f"site-{i:03d}"
    site_dir = data_dir / site_id
    
    if not site_dir.exists():
        missing_files[site_id] = ["ENTIRE DIRECTORY MISSING"]
        continue
        
    missing = []
    for req in required:
        if not (site_dir / req).exists():
            missing.append(req)
            
    if missing:
        missing_files[site_id] = missing

for site, files in missing_files.items():
    print(f"{site} is missing: {', '.join(files)}")
    
print(f"\nTotal incomplete sites: {len(missing_files)}")
