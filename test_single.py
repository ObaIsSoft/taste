import json
import urllib.request

prompt_text = """Evaluate Variant A and Variant B for aesthetic equilibrium and structural tension.

VARIANT A METRICS:
Display Typography: 120px, line-height: 114px (0.95 ratio), tracking: -4.0px. Total DOM depth: 850 nodes.
- Whitespace Ratio: 0.68
- Color Variance: 0.42
- Palette Mood: deep-charcoal-and-bone
- Asymmetry Score: 0.18
- Motion Engine: GSAP / ScrollTrigger Physics detected.
- Visual Forensic Description: {"focal_subject": {"type": "photographic", "description": "High-fashion editorial crop"}, "background_style": {"type": "textured", "has_grain_or_noise": true}}

VARIANT B METRICS:
Display Typography: 42px, line-height: 60px (1.42 ratio), tracking: 1.0px. Total DOM depth: 4200 nodes.
- Whitespace Ratio: 0.30
- Color Variance: 0.65
- Palette Mood: standard-corporate-blue
- Asymmetry Score: 0.02
- Motion Engine: Native CSS Keyframes (2 transitions)
- Visual Forensic Description: {"focal_subject": {"type": "product_mockup", "description": "Standard SaaS dashboard"}, "background_style": {"type": "flat_color", "has_grain_or_noise": false}}"""

payload = {
    "model": "taste-critic-bare",
    "prompt": prompt_text,
    "stream": False,
    "options": {
        "temperature": 0.7,
        "num_predict": 256
    }
}

req = urllib.request.Request(
    "http://localhost:11434/api/generate",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)

try:
    with urllib.request.urlopen(req) as res:
        response_data = json.loads(res.read().decode("utf-8"))
        print(response_data.get("response", ""))
except Exception as e:
    print(f"Error: {e}")
