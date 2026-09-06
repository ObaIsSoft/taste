import numpy as np
from PIL import Image
from pathlib import Path

def is_footer(site_dir):
    try:
        hero = np.array(Image.open(site_dir / "screenshot_hero.png").convert("RGB"))
        full = np.array(Image.open(site_dir / "screenshot_full.png").convert("RGB"))
        
        h_h, h_w, _ = hero.shape
        f_h, f_w, _ = full.shape
        
        if f_h <= h_h:
            return False # Page is too short to tell
            
        # Compare with top
        top_slice = full[0:h_h, :, :]
        # Compare with bottom
        bottom_slice = full[f_h-h_h:f_h, :, :]
        
        diff_top = np.mean(np.abs(hero - top_slice))
        diff_bottom = np.mean(np.abs(hero - bottom_slice))
        
        # If it matches the bottom better than the top, and the bottom match is very close (<10 pixel diff average)
        if diff_bottom < diff_top and diff_bottom < 15.0:
            return True
    except Exception as e:
        pass
    return False

data_dir = Path("data")
footer_sites = []
for site in sorted(data_dir.glob("site-*")):
    if site.is_dir() and (site / "screenshot_hero.png").exists():
        if is_footer(site):
            footer_sites.append(site.name)

print(f"Found {len(footer_sites)} sites with footer screenshots:")
print(", ".join(footer_sites))
