#!/usr/bin/env python3
"""
Prompt-to-Pipeline Tool
========================
Given a natural-language description of a desired workflow, this tool:
    1. Resolves the description to a known pipeline template (exact or closest)
    2. Optionally instantiates it with parameter overrides
    3. Optionally runs it headlessly and emits a report
    4. Emits a ready-to-run Python script the agent can save to disk

Usage (Hermes Agent-facing):
    python scripts/prompt_to_pipeline.py --describe "generate 10 fire ant game sprites"
    python scripts/prompt_to_pipeline.py --run "generate 10 fire ant game sprites" --output ~/game_assets
    python scripts/prompt_to_pipeline.py --script "translate 3 articles to French and narrate"
    python scripts/prompt_to_pipeline.py --list         # Show all known pipeline templates
    python scripts/prompt_to_pipeline.py --spaces-healthy   # Which Spaces are currently live
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


# ─── Known Pipeline Templates ─────────────────────────────────────────────────

PIPELINE_REGISTRY = {
    "ant_colony": {
        "module": "pipelines.ant_colony_assets",
        "file": "pipelines/ant_colony_assets.py",
        "description": "Generate N elemental ant game characters (art → sprites → optional 3D)",
        "keywords": ["game", "ant", "character", "asset", "elemental", "colony", "sprite"],
        "compute": "cloud-free",  # 3D portion is cloud-paid, disabled by default
        "duration": "~15 min per 10 ants",
        "tags": ["game-dev", "batch", "2d", "3d"],
        "cli_args": ["--count", "--with-3d", "--output-dir", "--style"],
    },
    "ant_colony_comfyui": {
        "module": "pipelines.ant_colony_comfyui",
        "file": "pipelines/ant_colony_comfyui.py",
        "description": "Local-GPU variant of ant_colony via ComfyUI (requires 8GB+ VRAM)",
        "keywords": ["local", "gpu", "comfyui", "ant"],
        "compute": "local-8gb",
        "duration": "~3 min per 10 ants (local GPU)",
        "tags": ["game-dev", "batch", "2d", "local"],
        "cli_args": ["--count", "--with-3d", "--output-dir"],
    },
    "image_to_3d": {
        "module": "pipelines.image_to_3d",
        "file": "pipelines/image_to_3d.py",
        "description": "Image → bg removal → 3D model (TripoSG with Hunyuan3D fallback)",
        "keywords": ["3d", "model", "image", "glb", "asset"],
        "compute": "cloud-paid",
        "duration": "~1-2 min per image",
        "tags": ["game-dev", "3d", "assets"],
        "cli_args": [],
    },
    "batch_characters": {
        "module": "pipelines.batch_character_sprites",
        "file": "pipelines/batch_character_sprites.py",
        "description": "Batch generate character sprites from a theme",
        "keywords": ["character", "art", "sprite", "batch"],
        "compute": "cloud-free",
        "duration": "~2-3 min per character",
        "tags": ["game-dev", "2d", "sprites"],
        "cli_args": [],
    },
    "viral_content": {
        "module": "pipelines.viral_content",
        "file": "pipelines/viral_content.py",
        "description": "Topic → social media content package (strategy + parallel images)",
        "keywords": ["social", "content", "instagram", "tiktok", "twitter", "marketing"],
        "compute": "cloud-free",
        "duration": "~3-5 min",
        "tags": ["social-media", "content", "marketing"],
        "cli_args": [],
    },
}


def score_match(description: str, entry: dict) -> int:
    """Score a pipeline entry against a natural-language description."""
    description = description.lower()
    score = 0
    for kw in entry["keywords"]:
        if kw in description:
            score += 2
    # Description substring matching
    for word in entry["description"].lower().split():
        if len(word) > 4 and word in description:
            score += 1
    return score


def resolve(description: str) -> list[tuple[str, dict, int]]:
    """Rank all pipeline templates by relevance to the description."""
    ranked = []
    for name, entry in PIPELINE_REGISTRY.items():
        ranked.append((name, entry, score_match(description, entry)))
    ranked.sort(key=lambda x: -x[2])
    return ranked


def print_list():
    """Print all registered pipeline templates."""
    print("\nRegistered pipeline templates:\n")
    for name, entry in PIPELINE_REGISTRY.items():
        print(f"  {name:<24} [{entry['compute']:<12}] {entry['duration']}")
        print(f"  {'':24} {entry['description']}")
        print(f"  {'':24} tags: {', '.join(entry['tags'])}")
        print()


def describe(description: str):
    """Show which pipeline matches the description and why."""
    ranked = resolve(description)
    print(f"\nQuery: \"{description}\"\n")
    print("Top matches:\n")
    for name, entry, score in ranked[:5]:
        marker = "→" if score > 0 else " "
        print(f"  {marker} {name:<24} (score: {score})")
        print(f"      {entry['description']}")
        print(f"      compute: {entry['compute']}   duration: {entry['duration']}")
        print()

    best_name, best_entry, best_score = ranked[0]
    if best_score == 0:
        print("  No strong matches. Use --list to see all available pipelines.")
        return

    print(f"Recommended: {best_name}")
    print(f"Run: python {best_entry['file']}")
    print(f"Source: {best_entry['file']}")


def generate_script(description: str, output_path: str | None = None) -> str:
    """
    Generate a standalone pipeline script that uses PipelineBuilder.

    Returns the script as a string. If output_path is given, also writes it.
    """
    ranked = resolve(description)
    best_name, best_entry, best_score = ranked[0]

    if best_score == 0:
        # Fallback: produce a minimal builder template for the agent to fill in
        script = f"""# Generated by scripts/prompt_to_pipeline.py
# Query: {description!r}
# No exact match found — scaffolded template using PipelineBuilder.

import sys
sys.path.insert(0, ".")

from pipelines.helpers import PipelineBuilder

builder = PipelineBuilder("Generated Pipeline")
# TODO: wire up inputs + nodes for: {description!r}
# See PIPELINE_REGISTRY keys: {list(PIPELINE_REGISTRY.keys())}
builder.add_prompt_input("Input", default="{description!r}")

# Build and launch
graph = builder.build()
if __name__ == "__main__":
    graph.launch()
"""
    else:
        # Emit a script that imports and runs the matched pipeline with overrides
        script = f"""# Generated by scripts/prompt_to_pipeline.py
# Query: {description!r}
# Matched template: {best_name}  (score: {best_score})

import sys
from pathlib import Path

# Add repo to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from {best_entry['module']} import graph

# Description:
#   {best_entry['description']}
#
# CLI: python {best_entry['file']}
# Compute: {best_entry['compute']}   Duration: {best_entry['duration']}

if __name__ == "__main__":
    graph.launch()
"""

    if output_path:
        Path(output_path).write_text(script)
        print(f"\nWrote generated script: {output_path}")
    return script


def run_pipeline(description: str, output_dir: str | None = None):
    """
    Resolve the best-matching pipeline and run its CLI entry point in the
    project's venv. Streams output to stdout.
    """
    ranked = resolve(description)
    best_name, best_entry, best_score = ranked[0]

    if best_score == 0:
        print(f"No pipeline matches: {description!r}")
        print("Available:", list(PIPELINE_REGISTRY.keys()))
        sys.exit(1)

    print(f"\nMatched: {best_name}")
    print(f"Running: python {best_entry['file']}")
    print(f"Compute: {best_entry['compute']}   Duration: {best_entry['duration']}\n")

    # Build CLI command
    cmd = [sys.executable, best_entry["file"]]
    if output_dir and "--output-dir" in best_entry["cli_args"]:
        cmd.extend(["--output-dir", output_dir])

    # Activate venv if present
    venv_python = Path(__file__).parent.parent / ".venv" / "bin" / "python"
    if venv_python.exists():
        cmd[0] = str(venv_python)

    proc = subprocess.run(cmd, cwd=str(Path(__file__).parent.parent))
    sys.exit(proc.returncode)


def show_healthy_spaces():
    """Print which registry Spaces are currently alive."""
    venv_python = Path(__file__).parent.parent / ".venv" / "bin" / "python"
    python = str(venv_python) if venv_python.exists() else sys.executable
    check_script = Path(__file__).parent / "check_spaces.py"
    result = subprocess.run(
        [python, str(check_script), "--json"],
        capture_output=True, text=True, cwd=str(Path(__file__).parent.parent),
        timeout=120,
    )
    if result.returncode not in (0, 1):  # 1 means "some spaces down" — not a fatal error
        print("Failed to query Spaces:", result.stderr[:200])
        return
    spaces = json.loads(result.stdout)
    running = [s for s in spaces if s["ok"]]
    down = [s for s in spaces if not s["ok"]]
    print(f"\nSpaces: {len(running)} running / {len(spaces)} total\n")
    print("RUNNING:")
    for s in running:
        print(f"  ✓ {s['space']:<42} [{s['category']}]  commercial_ok={s['commercial_ok']}")
    if down:
        print("\nDOWN:")
        for s in down:
            print(f"  ✗ {s['space']:<42} ({s['stage']})")


def main():
    parser = argparse.ArgumentParser(description="Prompt-to-pipeline tool for Hermes Agent")
    parser.add_argument("--describe", help="Describe what you want (rank matches)")
    parser.add_argument("--run", help="Describe and run the matching pipeline")
    parser.add_argument("--script", help="Describe and write a standalone script to stdout")
    parser.add_argument("--output", help="Output directory (for --run) or file path (for --script)")
    parser.add_argument("--list", action="store_true", help="List all pipeline templates")
    parser.add_argument("--spaces-healthy", action="store_true", help="Show current Space health")
    args = parser.parse_args()

    if args.list:
        print_list()
        return
    if args.spaces_healthy:
        show_healthy_spaces()
        return
    if args.describe:
        describe(args.describe)
        return
    if args.run:
        run_pipeline(args.run, args.output)
        return
    if args.script:
        out = args.output or "./generated_pipeline.py"
        generate_script(args.script, out)
        return
    parser.print_help()


if __name__ == "__main__":
    # Allow invocation from anywhere by changing to repo root
    repo_root = Path(__file__).parent.parent
    os.chdir(repo_root)
    main()
