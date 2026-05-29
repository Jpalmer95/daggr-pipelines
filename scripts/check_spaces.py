#!/usr/bin/env python3
"""
Space Liveness Checker — pings HF Spaces and reports their STATUS.

Usage:
    python check_spaces.py                    # Check all spaces in the registry
    python check_spaces.py --category image   # Check only image gen spaces
    python check_spaces.py --json             # Output as JSON for cron consumption
"""

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional

from huggingface_hub import HfApi


# ─── Space Registry ───────────────────────────────────────────────────────────

class Category(str, Enum):
    IMAGE_GEN = "image-gen"
    IMAGE_EDIT = "image-edit"
    VIDEO = "video"
    AUDIO = "audio"
    TTS = "tts"
    THREE_D = "3d"
    VISION = "vision"
    TEXT = "text"
    TRANSLATION = "translation"


class License(str, Enum):
    APACHE2 = "apache-2.0"       # Commercial OK
    MIT = "mit"                  # Commercial OK
    CREATIVEML = "creativeml-openrail-m"  # Commercial OK (Stable Diffusion family)
    FLUX_DEV = "flux-dev"        # Non-commercial
    FLUX_SCHNELL = "apache-2.0"  # Commercial OK
    GPL = "gpl-3.0"              # Copyleft — careful for commercial
    PROPRIETARY = "proprietary"  # Check terms
    UNKNOWN = "unknown"


class ComputeTier(str, Enum):
    CPU = "cpu"          # No GPU needed
    CLOUD_FREE = "cloud-free"  # HF free tier (ZeroGPU, rate limited)
    CLOUD_PAID = "cloud-paid"  # Dedicated GPU Space
    LOCAL_8GB = "local-8gb"    # Can run locally with 8GB VRAM
    LOCAL_24GB = "local-24gb"  # Needs 24GB VRAM


@dataclass
class SpaceEntry:
    space_id: str          # HF Space ID (owner/name)
    api_name: str          # Main API endpoint
    category: str          # Category enum value
    task: str              # Short description
    license: str           # License enum value
    commercial_ok: bool    # Can use outputs commercially
    compute: str           # ComputeTier enum value
    speed: str             # "fast" / "medium" / "slow"
    inputs: str            # Key input parameter names
    outputs: str           # What you get back
    notes: str = ""        # Gotchas, postprocess hints


REGISTRY: list[SpaceEntry] = [
    # ── Image Generation ──────────────────────────────────────────────────────
    SpaceEntry(
        space_id="black-forest-labs/FLUX.1-schnell",
        api_name="/infer",
        category=Category.IMAGE_GEN,
        task="Fast text-to-image (4-8 steps, good quality)",
        license=License.FLUX_SCHNELL,
        commercial_ok=True,
        compute=ComputeTier.CLOUD_FREE,
        speed="fast",
        inputs="prompt, seed, randomize_seed, width, height, num_inference_steps",
        outputs="(image_result_dict, seed)",
        notes="Postprocess: normalize result dict. Often overloaded during peak hours.",
    ),
    SpaceEntry(
        space_id="black-forest-labs/FLUX.1-dev",
        api_name="/infer",
        category=Category.IMAGE_GEN,
        task="Higher-quality text-to-image (dev weights, slower)",
        license=License.FLUX_DEV,
        commercial_ok=False,
        compute=ComputeTier.CLOUD_FREE,
        speed="medium",
        inputs="prompt, seed, randomize_seed, width, height, num_inference_steps, guidance_scale",
        outputs="(image_result_dict, seed)",
        notes="Non-commercial license. Use schnell for commercial work.",
    ),
    SpaceEntry(
        space_id="stabilityai/stable-diffusion-3.5-large",
        api_name="/infer",
        category=Category.IMAGE_GEN,
        task="Stable Diffusion 3.5 Large (good quality, slower)",
        license=License.CREATIVEML,
        commercial_ok=True,
        compute=ComputeTier.CLOUD_PAID,
        speed="medium",
        inputs="prompt, seed, randomize_seed, width, height, num_inference_steps, guidance_scale",
        outputs="(image_result_dict, seed)",
        notes="May need paid hardware Space. Reliable quality.",
    ),
    SpaceEntry(
        space_id="hf-applications/Z-Image-Turbo",
        api_name="/generate_image",
        category=Category.IMAGE_GEN,
        task="Fast text-to-image (good for prototyping)",
        license=License.UNKNOWN,
        commercial_ok=True,
        compute=ComputeTier.CLOUD_FREE,
        speed="fast",
        inputs="prompt, height, width, seed",
        outputs="image_dict",
        notes="Very fast, lower quality than FLUX. Good for rapid iteration.",
    ),

    # ── Image Editing ─────────────────────────────────────────────────────────
    SpaceEntry(
        space_id="hf-applications/background-removal",
        api_name="/image",
        category=Category.IMAGE_EDIT,
        task="Background removal (clean subjects)",
        license=License.UNKNOWN,
        commercial_ok=True,
        compute=ComputeTier.CLOUD_FREE,
        speed="fast",
        inputs="image",
        outputs="(original, processed)",
        notes="Postprocess: lambda _, final: final. Returns tuple.",
    ),
    SpaceEntry(
        space_id="not-lain/background-removal",
        api_name="/run",
        category=Category.IMAGE_EDIT,
        task="Alternative background removal",
        license=License.UNKNOWN,
        commercial_ok=True,
        compute=ComputeTier.CLOUD_FREE,
        speed="fast",
        inputs="image",
        outputs="image",
        notes="Simpler API — single image in/out.",
    ),

    # ── 3D Generation ─────────────────────────────────────────────────────────
    SpaceEntry(
        space_id="VAST-AI/TripoSG",
        api_name="/generate",
        category=Category.THREE_D,
        task="Image-to-3D model (good quality, ~30-60s)",
        license=License.UNKNOWN,
        commercial_ok=True,
        compute=ComputeTier.CLOUD_PAID,
        speed="medium",
        inputs="image",
        outputs="glb_file",
        notes="Reliable for game assets. Returns .glb file path.",
    ),
    SpaceEntry(
        space_id="Tencent/Hunyuan3D-2",
        api_name="/generation_all",
        category=Category.THREE_D,
        task="Image-to-3D (Tencent, higher detail)",
        license=License.UNKNOWN,
        commercial_ok=False,
        compute=ComputeTier.CLOUD_PAID,
        speed="slow",
        inputs="image",
        outputs="glb_file",
        notes="Higher detail but slower. Check license for commercial use.",
    ),
    SpaceEntry(
        space_id="JeffreyXiang/TRELLIS",
        api_name="/generate",
        category=Category.THREE_D,
        task="Image-to-3D (structurally clean)",
        license=License.UNKNOWN,
        commercial_ok=True,
        compute=ComputeTier.CLOUD_PAID,
        speed="slow",
        inputs="image",
        outputs="glb_file",
        notes="Good topology. May need 24GB VRAM Space.",
    ),

    # ── Video ─────────────────────────────────────────────────────────────────
    SpaceEntry(
        space_id="Lightricks/ltx-2-distilled",
        api_name="/generate_video",
        category=Category.VIDEO,
        task="Image-to-video (3-sec clips)",
        license=License.UNKNOWN,
        commercial_ok=False,
        compute=ComputeTier.CLOUD_PAID,
        speed="slow",
        inputs="prompt, image",
        outputs="video_file",
        notes="Good for short animations of still concept art.",
    ),
    SpaceEntry(
        space_id="multimodalart/HunyuanVideo",
        api_name="/generate",
        category=Category.VIDEO,
        task="Text/image-to-video (high quality)",
        license=License.UNKNOWN,
        commercial_ok=False,
        compute=ComputeTier.CLOUD_PAID,
        speed="slow",
        inputs="prompt, image, num_frames",
        outputs="video_file",
        notes="High quality but heavy. Often queued.",
    ),

    # ── Vision / VLM ──────────────────────────────────────────────────────────
    SpaceEntry(
        space_id="vikhyatk/moondream2",
        api_name="/answer_question",
        category=Category.VISION,
        task="Vision-language model (image Q&A)",
        license=License.UNKNOWN,
        commercial_ok=True,
        compute=ComputeTier.CLOUD_FREE,
        speed="fast",
        inputs="img (filepath!), prompt",
        outputs="text",
        notes="Needs preprocess to convert image dict to filepath string.",
    ),
    SpaceEntry(
        space_id="nvidia/NVLM",
        api_name="/img_chat",
        category=Category.VISION,
        task="NVIDIA vision-language model",
        license=License.UNKNOWN,
        commercial_ok=True,
        compute=ComputeTier.CLOUD_FREE,
        speed="medium",
        inputs="img, prompt, max_tokens",
        outputs="text",
        notes="Often overloaded. Use moondream2 as fallback.",
    ),

    # ── TTS ───────────────────────────────────────────────────────────────────
    SpaceEntry(
        space_id="ysharma/Qwen3-TTS",
        api_name="/generate_voice_design",
        category=Category.TTS,
        task="Voice design TTS (specify voice style)",
        license=License.UNKNOWN,
        commercial_ok=False,
        compute=ComputeTier.CLOUD_FREE,
        speed="medium",
        inputs="text, language, voice_description",
        outputs="audio_file",
        notes="Good voice quality. Check Qwen license for commercial use.",
    ),
    SpaceEntry(
        space_id="innoai/Edge-TTS-Text-to-Speech",
        api_name="/tts_interface",
        category=Category.TTS,
        task="Edge TTS (Microsoft voices, free, reliable)",
        license=License.UNKNOWN,
        commercial_ok=True,
        compute=ComputeTier.CLOUD_FREE,
        speed="fast",
        inputs="text, voice, rate, pitch",
        outputs="(audio_file, warning)",
        notes="Free Microsoft TTS. Very reliable. Use for rapid prototyping.",
    ),
    SpaceEntry(
        space_id="hexgrad/Kokoro-TTS",
        api_name="/tts",
        category=Category.TTS,
        task="Kokoro TTS (natural-sounding, open)",
        license=License.APACHE2,
        commercial_ok=True,
        compute=ComputeTier.CLOUD_FREE,
        speed="medium",
        inputs="text, voice",
        outputs="audio_file",
        notes="Apache 2.0 — safe for commercial use.",
    ),

    # ── Text / LLM ────────────────────────────────────────────────────────────
    # (InferenceNode uses HF Inference Providers, not Spaces — see skill)

    # ── Translation ───────────────────────────────────────────────────────────
    SpaceEntry(
        space_id="abidlabs/en2fr",
        api_name="/predict",
        category=Category.TRANSLATION,
        task="English-to-French (small model)",
        license=License.UNKNOWN,
        commercial_ok=True,
        compute=ComputeTier.CPU,
        speed="fast",
        inputs="text",
        outputs="text",
        notes="Use run_locally=True for local dev. Very lightweight.",
    ),
]


# ─── Liveness Checker ─────────────────────────────────────────────────────────

@dataclass
class SpaceStatus:
    space_id: str
    stage: str           # RUNNING, BUILDING, RUNTIME_ERROR, CONFIG_ERROR, PAUSED, SLEEPING
    hardware: str
    sdk: str
    ok: bool
    error: Optional[str] = None


def check_space(api: HfApi, space_id: str) -> SpaceStatus:
    """Check a single Space's status via the HF API."""
    try:
        info = api.space_info(space_id)
        runtime = info.runtime if hasattr(info, 'runtime') and info.runtime else None
        stage = "UNKNOWN"
        hardware = "unknown"
        sdk = "unknown"
        error = None

        if runtime:
            raw = runtime.raw if hasattr(runtime, 'raw') else {}
            stage = raw.get("stage", "UNKNOWN")
            hardware_info = raw.get("hardware", {})
            if isinstance(hardware_info, dict):
                current = hardware_info.get("current")
                if current:
                    hardware = current if isinstance(current, str) else str(current)
            sdk_info = raw.get("sdk", {})
            if isinstance(sdk_info, dict):
                sdk = sdk_info.get("stage", "unknown")
            elif isinstance(raw.get("sdk"), str):
                sdk = raw["sdk"]
            error = raw.get("errorMessage")
        else:
            # Fallback: just check if we got a response
            stage = getattr(info, 'stage', 'UNKNOWN') or "UNKNOWN"

        ok = stage == "RUNNING"

        return SpaceStatus(
            space_id=space_id, stage=stage, hardware=hardware,
            sdk=sdk, ok=ok, error=error,
        )
    except Exception as e:
        return SpaceStatus(
            space_id=space_id, stage="ERROR", hardware="n/a",
            sdk="n/a", ok=False, error=str(e)[:200],
        )


def check_all(category: Optional[str] = None) -> tuple[list[SpaceStatus], list[SpaceEntry]]:
    """Check all spaces (or just one category) and return statuses."""
    api = HfApi()
    entries = REGISTRY
    if category:
        entries = [e for e in REGISTRY if e.category == category]

    statuses = []
    for entry in entries:
        status = check_space(api, entry.space_id)
        statuses.append(status)
    return statuses, entries


def print_report(statuses: list[SpaceStatus], entries: list[SpaceEntry], as_json: bool = False):
    """Print a human-readable or JSON report."""
    if as_json:
        output = []
        for status, entry in zip(statuses, entries):
            output.append({
                "space": status.space_id,
                "ok": status.ok,
                "stage": status.stage,
                "category": entry.category,
                "license": entry.license,
                "commercial_ok": entry.commercial_ok,
                "compute": entry.compute,
                "error": status.error,
            })
        print(json.dumps(output, indent=2))
        return

    # Human-readable report
    total = len(statuses)
    running = sum(1 for s in statuses if s.ok)
    print(f"\n{'='*60}")
    print(f"  DAGGR SPACE LIVENESS REPORT")
    print(f"  {running}/{total} spaces running")
    print(f"{'='*60}\n")

    for status, entry in zip(statuses, entries):
        icon = "✓" if status.ok else "✗"
        lic_icon = "🟢" if entry.commercial_ok else "🔴"
        print(f"  {icon} {status.space_id}")
        print(f"    Stage: {status.stage}  |  Category: {entry.category}  |  License: {lic_icon} {entry.license}")
        if status.error:
            print(f"    Error: {status.error[:80]}")
        print()

    print(f"{'─'*60}")
    print(f"  Legend: ✓ = RUNNING, ✗ = DOWN  |  🟢 = commercial OK, 🔴 = non-commercial")
    print()


def main():
    parser = argparse.ArgumentParser(description="Check HF Space liveness for daggr pipelines")
    parser.add_argument("--category", "-c", help="Filter by category (image-gen, 3d, tts, etc.)")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    statuses, entries = check_all(category=args.category)
    print_report(statuses, entries, as_json=args.json)

    # Exit with non-zero if any space is down (useful for cron alerting)
    if any(not s.ok for s in statuses):
        sys.exit(1)


if __name__ == "__main__":
    main()
