"""
motion_capture.py - DEPRECATED legacy Step 2 (ffmpeg-based, writes legacy frames manifest).
Canonical is preprocess_video.py -> frames/ + motion_storyboard.json.
Kept for compat only, do not use in pipeline.

THE PROBLEM WE SOLVE HERE:
  Playwright starts recording the instant the browser opens — before the page
  has rendered. This means the first 3-8 seconds of video is typically:
    - White blank (page loading)
    - Loading spinner
    - Partial render
  Sampling at t=0, 0.5, 1s etc. captures LOADING STATE, not DESIGN STATE.

THE FIX:
  1. Probe the video to get total duration
  2. Extract a dense grid of candidate frames (every 0.5s)
  3. Score each frame for "blankness" — skip frames that are near-white or near-black
     with no meaningful content (high std dev = content present)
  4. Find the first non-blank frame = content_start
  5. Sample 6 frames evenly between content_start and video end
  6. Save only content-bearing frames
"""
import sys
import os
import json
import glob
import subprocess
import shutil
from pathlib import Path
from PIL import Image, ImageStat
import io

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from config import DATA_DIR, LOGS_DIR, METADATA_FILE, LEGACY_FRAMES

console = Console()

# How many final frames to keep per site
TARGET_FRAME_COUNT = 6

# Blankness thresholds
# A frame is "blank" if its pixel std dev is below this — means near-uniform color
BLANK_STD_THRESHOLD = 8.0
# Also blank if >95% of pixels are very close to white or very close to black
BLANK_EXTREME_RATIO = 0.92


def get_video_duration(video_path: Path) -> float:
    """Get video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def extract_single_frame(video_path: Path, timestamp: float, out_path: Path) -> bool:
    """Extract one frame at timestamp. Returns True on success."""
    cmd = [
        "ffmpeg",
        "-ss", f"{timestamp:.3f}",
        "-i", str(video_path),
        "-vframes", "1",
        "-q:v", "2",
        str(out_path),
        "-y",
        "-loglevel", "error",
    ]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0 and out_path.exists() and out_path.stat().st_size > 1000


def is_blank_frame(img_path: Path) -> tuple[bool, float]:
    """
    Returns (is_blank, content_score).
    content_score: 0 = totally blank, 100 = rich content.
    """
    try:
        img = Image.open(img_path).convert("RGB").resize((160, 90))  # fast downsample
        stat = ImageStat.Stat(img)

        # Standard deviation across all channels — low = uniform = blank
        avg_std = sum(stat.stddev[:3]) / 3

        # Count pixels that are near-white (>245) or near-black (<10)
        pixels = list(img.getdata())
        extreme = sum(
            1 for r, g, b in pixels
            if (r > 245 and g > 245 and b > 245) or (r < 10 and g < 10 and b < 10)
        )
        extreme_ratio = extreme / len(pixels)

        is_blank = avg_std < BLANK_STD_THRESHOLD or extreme_ratio > BLANK_EXTREME_RATIO
        content_score = min(100, avg_std * 2)

        return is_blank, round(content_score, 1)

    except Exception:
        return True, 0.0


def find_video(site_dir: Path) -> Path | None:
    """Find the .webm video file in a site directory."""
    videos = list(site_dir.glob("*.webm"))
    if not videos:
        return None
    return max(videos, key=lambda v: v.stat().st_size)


def extract_frames(site_id: str) -> list[str]:
    """
    Extract meaningful frames from the site's interaction video.
    Skips blank/loading frames. Returns list of saved frame paths.
    """
    site_dir = DATA_DIR / site_id
    video_path = find_video(site_dir)

    if not video_path:
        console.print(f"[yellow]⚠ No video for[/yellow] {site_id}")
        return []

    # Check ffmpeg
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        console.print("[red]✗ ffmpeg/ffprobe not found. Install with: brew install ffmpeg[/red]")
        return []

    frames_dir = site_dir / "frames"
    # Clear old frames if they exist (we're regenerating)
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir()

    duration = get_video_duration(video_path)
    if duration < 1.0:
        console.print(f"[yellow]⚠ Video too short ({duration:.1f}s) for[/yellow] {site_id}")
        return []

    console.print(f"[cyan]→[/cyan] {site_id}: video={duration:.1f}s ({video_path.stat().st_size/1_048_576:.1f}MB)")

    # ── Phase 1: Dense probe to find content start ─────────────────────────
    # Sample every 0.5s across the first 15s (or full video if shorter)
    probe_end   = min(duration, 15.0)
    probe_step  = 0.5
    probe_times = [round(t, 2) for t in _frange(0.0, probe_end, probe_step)]

    probe_dir = frames_dir / "_probe"
    probe_dir.mkdir()

    content_start = None
    probe_results = []

    for ts in probe_times:
        probe_path = probe_dir / f"probe_{ts:.2f}.png"
        ok = extract_single_frame(video_path, ts, probe_path)
        if ok:
            blank, score = is_blank_frame(probe_path)
            probe_results.append((ts, blank, score))
            if not blank and content_start is None:
                content_start = ts

    if content_start is None:
        # All probed frames were blank — content loads late, try from 5s
        console.print(f"[yellow]  ⚠ All probe frames blank, assuming content starts at 5s[/yellow]")
        content_start = min(5.0, duration * 0.3)

    # Clean up probe frames
    shutil.rmtree(probe_dir)

    # Log what we found
    blank_count = sum(1 for _, b, _ in probe_results if b)
    console.print(
        f"[dim]  Content start: t={content_start:.1f}s "
        f"({blank_count}/{len(probe_results)} probe frames were blank)[/dim]"
    )

    # ── Phase 2: Sample TARGET_FRAME_COUNT frames from content window ──────
    # Give a small buffer after content start so entrance animation has begun
    sample_start = content_start + 0.3
    sample_end   = duration - 0.5  # avoid last 0.5s (sometimes cuts off)

    if sample_end <= sample_start:
        sample_end = duration

    # Distribute evenly across the content window
    sample_times = _distribute(sample_start, sample_end, TARGET_FRAME_COUNT)

    saved_frames = []
    frame_metadata = []

    for i, ts in enumerate(sample_times):
        label = f"frame_{i:02d}_t{ts:.1f}s"
        out_path = frames_dir / f"{label}.png"
        ok = extract_single_frame(video_path, ts, out_path)

        if ok:
            blank, score = is_blank_frame(out_path)
            if blank:
                console.print(f"[yellow]  ⚠ Frame {i} at t={ts:.1f}s is blank (score={score}) — keeping anyway[/yellow]")
            saved_frames.append(str(out_path))
            frame_metadata.append({
                "index":         i,
                "timestamp":     round(ts, 2),
                "path":          str(out_path),
                "content_score": score,
                "is_blank":      blank,
            })
        else:
            console.print(f"[yellow]  ⚠ Frame {i} at t={ts:.1f}s failed[/yellow]")

    # ── Save manifest ──────────────────────────────────────────────────────
    manifest = {
        "site_id":       site_id,
        "video_path":    str(video_path),
        "video_size_mb": round(video_path.stat().st_size / 1_048_576, 2),
        "video_duration_s": round(duration, 2),
        "content_start_s":  round(content_start, 2),
        "frames":        saved_frames,
        "frame_metadata": frame_metadata,
        "blank_probe_count": blank_count,
        "total_probe_count": len(probe_results),
    }
    (site_dir / LEGACY_FRAMES).write_text(json.dumps(manifest, indent=2))

    avg_score = (
        sum(f["content_score"] for f in frame_metadata) / len(frame_metadata)
        if frame_metadata else 0
    )
    console.print(
        f"[green]✓[/green] {site_id}: {len(saved_frames)} frames saved, "
        f"avg content score={avg_score:.0f}/100, "
        f"sampling t={sample_start:.1f}s → t={sample_end:.1f}s"
    )
    return saved_frames


def _frange(start: float, stop: float, step: float):
    """Float range generator."""
    t = start
    while t < stop:
        yield t
        t += step


def _distribute(start: float, end: float, count: int) -> list[float]:
    """Distribute `count` timestamps evenly between start and end."""
    if count <= 1:
        return [start]
    step = (end - start) / (count - 1)
    return [round(start + i * step, 2) for i in range(count)]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Extract motion frames (blank-aware)")
    parser.add_argument("--site", help="Process a single site ID")
    args = parser.parse_args()

    if args.site:
        extract_frames(args.site)
    else:
        for site_dir in sorted(DATA_DIR.iterdir()):
            if not site_dir.is_dir() or not (site_dir / METADATA_FILE).exists():
                continue
            extract_frames(site_dir.name)
