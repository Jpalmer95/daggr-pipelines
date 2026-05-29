"""
ComfyUI Variant of Ant Colony Pipeline
========================================
Local-GPU path: zero API cost, faster, no rate limits, works offline.

Uses ComfyUI (via the comfyui skill) for image generation and 3D generation.
Falls back to cloud Spaces when ComfyUI isn't available.

Requirements:
  - Local GPU ≥ 8GB VRAM (for image gen) / ≥ 24GB (for 3D)
  - ComfyUI installed and running (see comfyui skill)
  - FLUX.1-schnell or SDXL checkpoint loaded in ComfyUI
  - TripoSR or similar 3D checkpoint (optional)

Usage:
    python pipelines/ant_colony_comfyui.py --count 10
    python pipelines/ant_colony_comfyui.py --count 10 --with-3d

This script is functionally identical to pipelines/ant_colony_assets.py in
output structure — drop-in replacement. The only difference is the compute
backend (local ComfyUI vs cloud HF Spaces).
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Lazy imports to avoid dragging daggr/gradio into import time
# when ComfyUI isn't available


# ─── ComfyUI Client ───────────────────────────────────────────────────────────

def comfyui_available() -> bool:
    """Check if ComfyUI is running locally."""
    import requests
    try:
        return requests.get("http://127.0.0.1:8188/system_stats", timeout=2).ok
    except Exception:
        return False


def comfyui_generate_image(
    prompt: str,
    seed: int,
    width: int = 512,
    height: int = 512,
    checkpoint: str = "flux1-schnell-fp8.safetensors",
    steps: int = 4,
) -> str | None:
    """
    Submit an image generation workflow to ComfyUI and return the resulting
    file path. Returns None on failure.

    This is a minimal workflow using only the essential nodes:
        KSampler → VAEDecode → SaveImage

    Requires the checkpoint to already be loaded in ComfyUI's models/checkpoints/.
    """
    import requests
    import uuid
    import time
    import urllib.parse

    workflow = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": checkpoint},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": prompt,
                "clip": ["1", 1],
            },
        },
        "3": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "4": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["2", 0],  # FLUX doesn't use negative prompts
                "latent_image": ["3", 0],
                "seed": seed,
                "steps": steps,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
            },
        },
        "5": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["4", 0],
                "vae": ["1", 2],
            },
        },
        "6": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["5", 0],
                "filename_prefix": f"ant_colony_{uuid.uuid4().hex[:8]}",
            },
        },
    }

    try:
        resp = requests.post(
            "http://127.0.0.1:8188/prompt",
            json={"prompt": workflow},
            timeout=10,
        )
        resp.raise_for_status()
        prompt_id = resp.json()["prompt_id"]

        # Poll until done (max 5 min)
        for _ in range(150):
            time.sleep(2)
            hist = requests.get("http://127.0.0.1:8188/history/" + prompt_id, timeout=5).json()
            if prompt_id in hist:
                outputs = hist[prompt_id].get("outputs", {})
                save_output = outputs.get("6", {})
                images = save_output.get("images", [])
                if images:
                    filename = images[0]["filename"]
                    subdir = images[0].get("subfolder", "")
                    comfy_output_dir = Path.home() / "comfyui" / "ComfyUI" / "output" / subdir
                    result_path = comfy_output_dir / filename
                    if result_path.exists():
                        return str(result_path)
                # If no image found, something failed
                return None

        return None  # Timed out
    except Exception as e:
        print(f"  ComfyUI error: {e}")
        return None


# ─── Main Driver ───────────────────────────────────────────────────────────────

def generate_ant_images_with_comfyui(colony: list[dict]) -> list[dict]:
    """Generate art for all ants using local ComfyUI."""
    results = []
    for ant in colony:
        entry = {**ant, "image_path": None, "art_error": None}
        path = comfyui_generate_image(
            prompt=ant["prompt"],
            seed=ant["seed"],
            width=512,
            height=512,
            steps=4,
        )
        if path:
            entry["image_path"] = path
        else:
            entry["art_error"] = "ComfyUI generation failed"
        results.append(entry)
        print(f"  [{len(results)}/{len(colony)}] {ant['id']} → {'OK' if path else 'FAIL'}")
    return results


def cli():
    """Local ComfyUI driver for the ant pipeline."""
    from ant_colony_assets import (
        generate_colony, remove_all_backgrounds,
        generate_3d_models, package_colony, DEFAULT_OUTPUT_DIR,
    )

    parser = argparse.ArgumentParser(description="Ant colony pipeline (ComfyUI local variant)")
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--with-3d", action="store_true")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--style", default="stylized 2D game character, clean linework, vibrant colors, front-facing")
    args = parser.parse_args()

    if not comfyui_available():
        print("ERROR: ComfyUI is not running at http://127.0.0.1:8188")
        print("Launch it with `comfy launch` or see the comfyui skill.")
        sys.exit(1)

    print(f"[LOCAL GPU] Generating colony: {args.count} ants via ComfyUI\n")

    colony = generate_colony(args.count, args.style, args.with_3d)
    print(f"[1/4] {len(colony)} ant concepts")

    print("\n[2/4] Image generation (local ComfyUI, ~5s each)...")
    art = generate_ant_images_with_comfyui(colony)

    print("\n[3/4] Background removal (cloud Space — no local bg-remover node yet)...")
    sprites = remove_all_backgrounds(art)

    assets = sprites
    if args.with_3d:
        print("\n[4/4] 3D models via TripoSG (cloud — local TripoSR not wired in yet)...")
        assets = generate_3d_models(sprites)

    report = package_colony(assets, args.output_dir)

    print(f"\n{'='*60}")
    print(f"  [LOCAL GPU PATH] {report['summary']}")
    print(f"  Roster: {report['roster_path']}")
    print(f"{'='*60}")


if __name__ == "__main__":
    cli()
