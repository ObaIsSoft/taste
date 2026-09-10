Create a `Modelfile` in the directory containing your `.gguf` file to configure the context window, prompt template, and stop tokens:

```dockerfile
FROM ./taste_critic.Q4_K_M.gguf

TEMPLATE """<|im_start|>user
{{ .Prompt }}<|im_end|>
<|im_start|>assistant
"""

PARAMETER stop "<|im_start|>"
PARAMETER stop "<|im_end|>"
PARAMETER temperature 0.7
PARAMETER num_ctx 4096

```

Register and verify the model locally:

```bash
# 1. Register the model with Ollama
ollama create taste-critic -f ./Modelfile

# 2. Test interactive execution
ollama run taste-critic "Evaluate Variant A (DOM: 120, Whitespace: 0.85) vs Variant B (DOM: 4000, Whitespace: 0.10)."

```

---

### Automated Metric Evaluator (`evaluate_pair.py`)

This zero-dependency Python script sends structured UI metric payloads directly to the Ollama HTTP API endpoint (`localhost:11434`), enforcing exact ChatML parsing and streaming the critic's verdict:

```python
import json
import urllib.request

def evaluate_variants(variant_a: dict, variant_b: dict) -> str:
    prompt = f"""Evaluate Variant A and Variant B for aesthetic equilibrium and structural tension.

VARIANT A METRICS:
- DOM Nodes: {variant_a.get('dom_nodes')}
- Whitespace Ratio: {variant_a.get('whitespace_ratio')}
- Color Variance: {variant_a.get('color_variance')}
- Palette Mood: {variant_a.get('palette_mood')}
- Asymmetry Score: {variant_a.get('asymmetry_score')}
- Motion Easing: {variant_a.get('motion_easing')}
- Motion Duration (avg ms): {variant_a.get('motion_duration_ms')}

VARIANT B METRICS:
- DOM Nodes: {variant_b.get('dom_nodes')}
- Whitespace Ratio: {variant_b.get('whitespace_ratio')}
- Color Variance: {variant_b.get('color_variance')}
- Palette Mood: {variant_b.get('palette_mood')}
- Asymmetry Score: {variant_b.get('asymmetry_score')}
- Motion Easing: {variant_b.get('motion_easing')}
- Motion Duration (avg ms): {variant_b.get('motion_duration_ms')}"""

    payload = {
        "model": "taste-critic",
        "prompt": prompt,
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

    with urllib.request.urlopen(req) as res:
        response_data = json.loads(res.read().decode("utf-8"))
        return response_data.get("response", "")

if __name__ == "__main__":
    v_a = {
        "dom_nodes": 140,
        "whitespace_ratio": 0.84,
        "color_variance": 0.12,
        "palette_mood": "monochromatic-neutral",
        "asymmetry_score": 0.08,
        "motion_easing": "cubic-bezier(0.16, 1, 0.3, 1)",
        "motion_duration_ms": 280
    }
    v_b = {
        "dom_nodes": 6200,
        "whitespace_ratio": 0.08,
        "color_variance": 0.78,
        "palette_mood": "high-saturation",
        "asymmetry_score": 0.62,
        "motion_easing": "linear",
        "motion_duration_ms": 120
    }

    print(evaluate_variants(v_a, v_b))

```

---

### TrueSkill Rating Engine Integration

To use the critic to rank designs programmatically, wrap its pairwise decisions in an automated TrueSkill scoring pipeline:

```python
import trueskill
import re

# Initialize TrueSkill environment
env = trueskill.TrueSkill(draw_probability=0.0)

class DesignVariant:
    def __init__(self, name: str, metrics: dict):
        self.name = name
        self.metrics = metrics
        self.rating = env.create_rating()

def run_pairwise_matchup(v1: DesignVariant, v2: DesignVariant):
    verdict = evaluate_variants(v1.metrics, v2.metrics)

    # Deterministic parser for winning variant
    match_a = re.search(r"Variant A demonstrates elite", verdict)
    match_b = re.search(r"Variant B demonstrates elite", verdict)

    if match_a and not match_b:
        v1.rating, v2.rating = trueskill.rate_1vs1(v1.rating, v2.rating)
    elif match_b and not match_a:
        v2.rating, v1.rating = trueskill.rate_1vs1(v2.rating, v1.rating)
    else:
        # Penalize ambiguous responses with no rating delta update
        pass

    return verdict

```

Do you plan to ingest UI metrics directly from headless browser snapshots (e.g., Playwright/Puppeteer AST extraction), or are you manually compiling these design metric dictionaries?
