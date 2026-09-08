"""
preprocess_video.py — Phase 3 Prep: Video Preprocessor

Uses PyTorch and TorchCodec to ingest Playwright .webm recordings,
perform mathematical scene detection (MSE on structural layout shifts),
and save keyframes for LLM multi-modal ingestion.

Optimizations:
- Batched extraction via C++ backend
- Hardware acceleration (CUDA/MPS)
- Downsampled MSE (128x128) to ignore tiny artifacts and speed up math
"""
import sys
import os
import json
from pathlib import Path
import torch
import torch.nn.functional as F
import torchvision.transforms.functional as TF
try:
    from torchcodec.decoders import VideoDecoder
except ImportError:
    print("torchcodec not installed. Install via pip install torchcodec torchvision")
    sys.exit(1)

from rich.console import Console
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATA_DIR

console = Console()

MSE_THRESHOLD = 0.012  # Structural layout change threshold (lowered to catch subtle scroll shifts)
BATCH_SIZE = 32        # Process frames in batches for C++ throughput
MAX_KEYFRAMES = 37     # Cap per site to avoid RAM overload on long videos
SAMPLE_FPS = 1.0       # Sample at 1fps (was 2fps but with idle-time recordings, quality > quantity)


def is_content_frame(tensor) -> bool:
    """
    Returns True only if the frame contains real rendered website content.
    Filters out:
      - Loading screens / splash screens (near-uniform colour, minimal edges)
      - Blank white / near-white pages
      - Frozen / idle frames (handled separately via MSE)

    Three checks:
      1. Avg brightness < 0.92  (near-white blank = loading screen)
      2. Pixel variance > 0.002 (flat uniform colour = splash gradient)
      3. Edge density > 0.005   (Sobel-approx: text + UI elements have edges)
    """
    avg_brightness = tensor.mean().item()
    if avg_brightness > 0.92:
        return False  # near-white blank

    variance = tensor.var().item()
    if variance < 0.002:
        return False  # too uniform — loading screen gradient

    # Approximate edge density using pixel-difference in X and Y
    gray = tensor.mean(dim=0, keepdim=True)  # (1, H, W)
    dx = (gray[:, :, 1:] - gray[:, :, :-1]).abs().mean().item()
    dy = (gray[:, 1:, :] - gray[:-1, :, :]).abs().mean().item()
    edge_density = (dx + dy) / 2
    if edge_density < 0.005:
        return False  # no edges = no text/UI visible

    return True

def process_video(site_id):
    site_dir = DATA_DIR / site_id
    video_files = list(site_dir.glob("*.webm"))
    
    if not video_files:
        return False
        
    video_path = video_files[0]
    frames_dir = site_dir / "frames"
    frames_dir.mkdir(exist_ok=True)
    
    console.print(f"[cyan]→[/cyan] Processing video for {site_id} using Batched TorchCodec...")
    
    # 1. Hardware Acceleration (CUDA for NVIDIA, MPS for Apple Silicon)
    if torch.cuda.is_available():
        device = "cuda"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"
        
    try:
        decoder = VideoDecoder(str(video_path), device=device)
        fps = decoder.metadata.average_fps if decoder.metadata.average_fps else 30.0
        total_frames = len(decoder)
        
    # Sample at SAMPLE_FPS
    frame_interval = max(1, int(fps / SAMPLE_FPS))
    sample_indices = list(range(0, total_frames, frame_interval))
        
        extracted_frames = []
        prev_downsampled = None
        
        # 2. Batched Iteration
        for batch_start in range(0, len(sample_indices), BATCH_SIZE):
            batch_indices = sample_indices[batch_start : batch_start + BATCH_SIZE]
            
            # Fetch entire batch via C++ backend [Batch, Channels, Height, Width]
            batch = decoder.get_frames_at(indices=batch_indices)
            tensors = batch.data.float() / 255.0
            
            # 3. Downsample for structural comparison (Massive speedup + noise filtering)
            # 128x128 ignores playing videos/cursors but catches modal opens and page scrolls
            downsampled = F.interpolate(tensors, size=(128, 128), mode="bilinear", align_corners=False)
            
            for i in range(len(batch_indices)):
                current_ds = downsampled[i]
                is_keyframe = False
                
                if prev_downsampled is None:
                    # First frame — only accept if it's real content
                    if is_content_frame(tensors[i]):
                        is_keyframe = True
                else:
                    mse = F.mse_loss(current_ds, prev_downsampled).item()
                    if mse > MSE_THRESHOLD and is_content_frame(tensors[i]):
                        is_keyframe = True
                        
                if is_keyframe and len(extracted_frames) < MAX_KEYFRAMES:
                    frame_idx = batch_indices[i]
                    timestamp = frame_idx / fps
                    frame_name = f"frame_{len(extracted_frames):03d}.jpg"
                    
                    # Save the ORIGINAL high-res frame (moved back to CPU)
                    img = TF.to_pil_image(batch.data[i].cpu())
                    img.save(frames_dir / frame_name, quality=80)
                    
                    extracted_frames.append({
                        "filename": frame_name,
                        "timestamp_sec": round(timestamp, 2),
                        "frame_index": frame_idx
                    })
                    
                    prev_downsampled = current_ds
                    
        # Write manifest
        manifest_path = site_dir / "motion_storyboard.json"
        manifest_path.write_text(json.dumps({
            "total_extracted": len(extracted_frames),
            "mse_threshold": MSE_THRESHOLD,
            "device": device,
            "frames": extracted_frames
        }, indent=2))
        
        console.print(f"[green]✓[/green] Extracted {len(extracted_frames)} structural keyframes for {site_id}")
        return True
        
    except Exception as e:
        console.print(f"[red]✗ Failed to process {site_id}: {e}[/red]")
        return False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", help="Process specific site ID")
    args = parser.parse_args()
    
    if args.site:
        process_video(args.site)
    else:
        for site_dir in sorted(DATA_DIR.iterdir()):
            if site_dir.is_dir():
                process_video(site_dir.name)
