"""
config.py — Central config for TASTE pipeline.
Edit this file to change paths, models, and thresholds.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT         = Path(__file__).parent
DATA_DIR     = ROOT / "data"
LOGS_DIR     = ROOT / "logs"
MASTER_FILE  = DATA_DIR / "master_dataset.jsonl"
ELO_FILE     = DATA_DIR / "elo_scores.json"

# ── Canonical per-site filenames (Plan A freeze) ─────────────────────────
# Single source of truth. All scripts must import these, never hardcode.
METADATA_FILE     = "metadata.json"
VISUAL_FILE       = "visual_analysis.json"
MOTION_CODE_FILE  = "motion_code.json"
STORYBOARD_FILE   = "motion_storyboard.json"
FRAMES_DIRNAME    = "frames"
RATIONALE_FILE    = "taste_rationale.json"
VLM_RAW_FILE      = "stage2_vlm_raw.json"
EMBED_FILE        = "embedding.json"
# Legacy files (deprecated, read-only fallback, do not write new):
LEGACY_LLAVA      = "llava_analysis.json"
LEGACY_FRAMES     = "frames_manifest.json"
LEGACY_CLAUDE     = "claude_rationale.json"
LEGACY_RATIONALE_MD = "taste_rationale.md"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# ── API Keys (Automatically picked up by litellm) ────────────────────────────
# GEMINI_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY should be set in .env
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# ── Unified Models (LiteLLM) ───────────────────────────────────────────────
# The local stack
VISION_MODEL = os.environ.get("VISION_MODEL", "ollama/minicpm-v")
REASONING_MODEL = os.environ.get("REASONING_MODEL", "ollama/gemma4")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "ollama/nomic-embed-text")

# ── Scraper ────────────────────────────────────────────────────────────────
VIEWPORT     = {"width": 1440, "height": 900}
SCROLL_SPEED = 250         # px per step when recording video (faster = more page covered)
SCROLL_PAUSE = 0.08        # seconds between steps (slightly slower tick = smoother recording)
SCROLL_DURATION = 90       # seconds to scroll (was 30 — gives full coverage of tall pages)
VIDEO_FPS    = 25

# Frame extraction timestamps — these are now IGNORED by preprocess_video.py
# which uses MSE-based keyframe detection instead. Kept for legacy reference only.
FRAME_TIMESTAMPS = [0.0, 0.5, 1.0, 2.0, 4.0, 6.0]

# ── Quality thresholds ─────────────────────────────────────────────────────
MIN_ELO_FOR_CORPUS = 1500   # Elo rating to qualify for training corpus
MIN_COMPARISONS    = 5      # Minimum pairwise comparisons before trusting Elo
HIGH_CONSENSUS     = 0.70   # Fraction of annotators agreeing = "consensus taste"
