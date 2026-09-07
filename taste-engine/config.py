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

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# ── API Keys (Automatically picked up by litellm) ────────────────────────────
# GEMINI_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY should be set in .env

# ── Unified Models (LiteLLM) ───────────────────────────────────────────────
# Change this to "ollama/llama3.1", "claude-3-5-sonnet-20241022", "gpt-4o", etc.
TASTE_MODEL = os.environ.get("TASTE_MODEL", "gemini/gemini-1.5-pro")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "gemini/text-embedding-004")

# ── Scraper ────────────────────────────────────────────────────────────────
VIEWPORT     = {"width": 1440, "height": 900}
SCROLL_SPEED = 80          # px per step when recording video
SCROLL_PAUSE = 0.04        # seconds between steps
VIDEO_FPS    = 25

# Frame extraction timestamps (seconds into the recording)
FRAME_TIMESTAMPS = [0.0, 0.5, 1.0, 2.0, 4.0, 6.0]

# ── Quality thresholds ─────────────────────────────────────────────────────
MIN_ELO_FOR_CORPUS = 1500   # Elo rating to qualify for training corpus
MIN_COMPARISONS    = 5      # Minimum pairwise comparisons before trusting Elo
HIGH_CONSENSUS     = 0.70   # Fraction of annotators agreeing = "consensus taste"
