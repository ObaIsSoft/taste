import shutil
from pathlib import Path

# Paths
ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
PUBLIC_DATA_DIR = ROOT / "web" / "public" / "data"

PUBLIC_DATA_DIR.mkdir(parents=True, exist_ok=True)

print("Copying images to public directory for Vercel deployment...")

copied = 0
for site_dir in DATA_DIR.glob("site-*"):
    if not site_dir.is_dir(): continue
    
    site_id = site_dir.name
    dest_dir = PUBLIC_DATA_DIR / site_id
    dest_dir.mkdir(exist_ok=True)
    
    # Copy screenshots
    for img in ["screenshot_hero.png", "screenshot_full.png"]:
        src = site_dir / img
        if src.exists():
            shutil.copy2(src, dest_dir / img)
            copied += 1

print(f"Copied {copied} images to {PUBLIC_DATA_DIR}")
