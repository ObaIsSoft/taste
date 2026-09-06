import numpy as np
from PIL import Image
from pathlib import Path
import warnings

warnings.simplefilter('ignore', Image.DecompressionBombWarning)

data_dir = Path("data")
busted_sites = []
fine_sites = []

for site in sorted(data_dir.glob("site-*")):
    hero_path = site / "screenshot_hero.png"
    full_path = site / "screenshot_full.png"
    if not (hero_path.exists() and full_path.exists()):
        continue
        
    try:
        hero = np.array(Image.open(hero_path).convert("RGB"))
        full = np.array(Image.open(full_path).convert("RGB"))
        
        h_h, h_w, _ = hero.shape
        f_h, f_w, _ = full.shape
        
        if f_h <= h_h:
            # It's a short page, impossible to be "stuck at footer" vs "hero" really
            fine_sites.append(site.name)
            continue
            
        top_slice = full[0:h_h, :, :]
        
        # Calculate mean absolute difference
        diff = np.mean(np.abs(hero.astype(float) - top_slice.astype(float)))
        
        # If the difference is large, the hero screenshot is NOT of the top of the page.
        if diff > 15.0:
            busted_sites.append((site.name, diff))
        else:
            fine_sites.append(site.name)
    except Exception as e:
        print(f"Error on {site.name}: {e}")

print(f"Total Busted (Footer/Scrolled): {len(busted_sites)}")
print(f"Total Fine (Hero matched top): {len(fine_sites)}")
if busted_sites:
    print("\nBusted sites:")
    print(", ".join([s[0] for s in busted_sites]))
