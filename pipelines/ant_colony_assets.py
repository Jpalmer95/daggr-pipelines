"""
Ant Colony Game Assets Pipeline
================================
The flagship daggr-pipelines example: generate a colony of ant game assets
with varying elemental status, size, and shape.

Each ant produces:
    - A concept.json (element, size, role, stats, personality)
    - A sprite.png (512x512 bg-removed character art)
    - A raw.png (full background for splash screens / menus)
    - A manifest.json linking everything
    - Optional: a 3D .glb model (when 3d=True)

Pipeline:
    1. Colony Concept (FnNode) — generate N ant archetypes
    2. Character Art (GradioNode / batch in FnNode) — one image per ant
    3. Background Removal — clean sprites
    4. Asset Package (FnNode) — structured Godot-ready folder

Compute: cloud-free (image gen + bg removal are free HF Spaces)
Duration: ~15 min for 10 ants at free-tier rates
License: Apache 2.0 (commercial-OK) via FLUX.1-schnell
Tags: game-dev, character-assets, batch, ants, colony, elemental

Usage:
    python pipelines/ant_colony_assets.py              # Default 5 ants, image-only
    python pipelines/ant_colony_assets.py --count 10   # 10 ants
    python pipelines/ant_colony_assets.py --with-3d    # Also generate 3D models (adds ~$1)
    daggr pipelines/ant_colony_assets.py               # Hot reloading
    OUTPUT_DIR=~/my_game/assets python pipelines/ant_colony_assets.py
"""

import argparse
import json
import os
import random
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import gradio as gr
from daggr import FnNode, GradioNode, InputNode, Graph


# ─── Colony Configuration ─────────────────────────────────────────────────────

DEFAULT_OUTPUT_DIR = os.environ.get(
    "DAGGR_OUTPUT_DIR",
    "./output/ant_colony",
)

ELEMENTS = [
    {
        "name": "fire",
        "palette": "fiery reds and oranges, glowing embers, smoke trails",
        "traits": ["aggressive", "fast", "burns on contact"],
        "stat_bonus": {"attack": 2, "speed": 1, "hp": -1},
    },
    {
        "name": "water",
        "palette": "aqua blues and seafoam, droplets, flowing water patterns",
        "traits": ["healer", "amphibious", "splash damage"],
        "stat_bonus": {"heal": 3, "hp": 1, "attack": -1},
    },
    {
        "name": "earth",
        "palette": "moss greens and browns, rocky textures, leaf details",
        "traits": ["tank", "slow", "burrows"],
        "stat_bonus": {"hp": 3, "defense": 2, "speed": -2},
    },
    {
        "name": "lightning",
        "palette": "electric yellow and violet, sparking mandibles, ozone",
        "traits": ["ranged", "stun", "chain attack"],
        "stat_bonus": {"attack": 2, "range": 2, "hp": -1},
    },
    {
        "name": "shadow",
        "palette": "deep purples and blacks, glowing eyes, smoke",
        "traits": ["stealth", "critical", "ambush"],
        "stat_bonus": {"crit": 3, "stealth": 2, "hp": -1},
    },
    {
        "name": "crystal",
        "palette": "translucent pinks and cyans, prismatic facets, shimmering",
        "traits": ["magic", "reflect", "fragile"],
        "stat_bonus": {"magic": 3, "defense": -1, "regen": 1},
    },
]

ANT_ROLES = [
    {"name": "worker",   "size_bucket": "small",  "base_hp": 4, "base_atk": 2},
    {"name": "soldier",  "size_bucket": "medium", "base_hp": 7, "base_atk": 4},
    {"name": "guardian", "size_bucket": "large",  "base_hp": 10, "base_atk": 6},
    {"name": "royal",    "size_bucket": "huge",   "base_hp": 15, "base_atk": 8},
]

SIZE_MODIFIERS = {
    "small":  {"scale": 0.7, "agility": 1.3, "desc": "tiny, nimble"},
    "medium": {"scale": 1.0, "agility": 1.0, "desc": "average-sized"},
    "large":  {"scale": 1.4, "agility": 0.7, "desc": "imposing, armored"},
    "huge":   {"scale": 1.8, "agility": 0.5, "desc": "colossal, heavy-plated"},
}


# ─── Input Parameters ─────────────────────────────────────────────────────────

batch_params = InputNode(
    name="Colony Settings",
    ports={
        "count": gr.Slider(1, 10, value=5, step=1, label="Number of Ants"),
        "game_style": gr.Textbox(
            label="Game Art Style",
            value="stylized 2D game character, clean linework, vibrant colors, front-facing",
            lines=2,
        ),
        "with_3d": gr.Checkbox(label="Also generate 3D models (costs ~$1)", value=False),
        "output_dir": gr.Textbox(label="Output Directory", value=DEFAULT_OUTPUT_DIR),
    },
)


# ─── Step 1: Generate Colony Concepts ─────────────────────────────────────────

def generate_colony(count: int, game_style: str, with_3d: bool) -> list[dict]:
    """Produce N unique ant archetypes with stats and image prompts."""
    count = int(count)
    colony = []

    # Deterministic enough for demos, random enough for variety
    rng = random.Random(hash((count, game_style, datetime.now().toordinal() // 7)))

    for i in range(count):
        element = ELEMENTS[i % len(ELEMENTS)]
        role = ANT_ROLES[i % len(ANT_ROLES)]
        size = SIZE_MODIFIERS[role["size_bucket"]]

        # Build stats dict (base + elemental bonus)
        stats = {"hp": role["base_hp"], "attack": role["base_atk"]}
        for stat, bonus in element["stat_bonus"].items():
            stats[stat] = stats.get(stat, 0) + bonus

        # Unique personality seed
        personality_traits = rng.sample(element["traits"], k=min(2, len(element["traits"])))
        size_desc = size["desc"]

        ant_id = f"ant_{element['name']}_{role['name']}_{i+1:02d}"

        prompt = (
            f"A {size_desc} {element['name'].upper()} elemental ant, a {role['name']} class, "
            f"{element['palette']}, {', '.join(personality_traits)}, "
            f"{game_style}, full body character art, centered on solid white background, "
            f"game-ready, high detail, consistent proportions, anthropomorphic ant hero"
        )

        colony.append({
            "id": ant_id,
            "element": element["name"],
            "role": role["name"],
            "size": role["size_bucket"],
            "stats": stats,
            "personality": personality_traits,
            "prompt": prompt,
            "seed": rng.randint(0, 999_999_999),
            "index": i,
        })

    return colony


colony_concept = FnNode(
    fn=generate_colony,
    inputs={
        "count": batch_params.count,
        "game_style": batch_params.game_style,
        "with_3d": batch_params.with_3d,
    },
    outputs={"colony": gr.JSON(label="Colony Roster")},
    concurrent=True,
)


# ─── Step 2: Batch Image Generation ───────────────────────────────────────────
# Loops inside a single FnNode calling gradio_client to avoid the daggr
# scatter/gather bug in v0.8.0. Stagger requests to stay under free-tier rate.

def generate_all_art(colony: list[dict]) -> list[dict]:
    """Generate character art for every ant in the colony."""
    from gradio_client import Client

    results = []
    client = None
    space = "black-forest-labs/FLUX.1-schnell"

    for ant in colony:
        entry = {**ant, "image_path": None, "art_error": None}

        try:
            if client is None:
                client = Client(space)
            # FLUX.1-schnell /infer returns (image_result_dict, seed)
            image_result, _seed = client.predict(
                prompt=ant["prompt"],
                seed=ant["seed"],
                randomize_seed=True,
                width=512,
                height=512,
                num_inference_steps=4,
                api_name="/infer",
            )
            entry["image_path"] = image_result["path"] if isinstance(image_result, dict) else str(image_result)
        except Exception as e:
            entry["art_error"] = str(e)[:200]

        results.append(entry)
        # Stay under HF free-tier rate limit
        time.sleep(6)

    return results


art_generator = FnNode(
    fn=generate_all_art,
    inputs={"colony": colony_concept.colony},
    outputs={"art": gr.JSON(label="Character Art")},
    concurrent=False,  # sequential to respect rate limits
)


# ─── Step 3: Background Removal ───────────────────────────────────────────────

def remove_all_backgrounds(art: list[dict]) -> list[dict]:
    """Strip backgrounds from every ant image, producing sprite paths."""
    from gradio_client import Client

    results = []
    client = None
    space = "hf-applications/background-removal"

    for entry in art:
        new_entry = {**entry, "sprite_path": None, "bg_error": None}

        if not entry.get("image_path"):
            new_entry["bg_error"] = "No source image (art step failed)"
            results.append(new_entry)
            continue

        try:
            if client is None:
                client = Client(space)
            _original, processed = client.predict(
                entry["image_path"],
                api_name="/image",
            )
            new_entry["sprite_path"] = processed
        except Exception as e:
            new_entry["bg_error"] = str(e)[:200]

        results.append(new_entry)
        time.sleep(4)

    return results


bg_remover = FnNode(
    fn=remove_all_backgrounds,
    inputs={"art": art_generator.art},
    outputs={"sprites": gr.JSON(label="Clean Sprites")},
    concurrent=False,
)


# ─── Step 4 (optional): 3D Model Generation ───────────────────────────────────

def generate_3d_models(sprites: list[dict]) -> list[dict]:
    """Optional 3D model generation. Tries TripoSG, falls back to Hunyuan3D."""
    from gradio_client import Client

    results = []
    for entry in sprites:
        new_entry = {**entry, "model_path": None, "model_service": None, "model_error": None}

        if not entry.get("sprite_path"):
            results.append(new_entry)
            continue

        services = [
            ("VAST-AI/TripoSG", "/generate", "TripoSG"),
            ("Tencent/Hunyuan3D-2", "/generation_all", "Hunyuan3D"),
        ]

        for space_id, api_name, name in services:
            try:
                client = Client(space_id)
                output = client.predict(entry["sprite_path"], api_name=api_name)
                if output and (isinstance(output, str) or
                               (isinstance(output, dict) and "path" in output)):
                    new_entry["model_path"] = output if isinstance(output, str) else output["path"]
                    new_entry["model_service"] = name
                    break
            except Exception as e:
                new_entry["model_error"] = f"{name}: {str(e)[:100]}"

        results.append(new_entry)
        time.sleep(8)  # 3D services are heavy

    return results


gen_3d = FnNode(
    fn=generate_3d_models,
    inputs={"sprites": bg_remover.sprites},
    outputs={"assets_3d": gr.JSON(label="3D Models (optional)")},
    concurrent=False,
)


# ─── Step 5: Package into Godot-ready Folder ──────────────────────────────────

def package_colony(assets_3d: list[dict], output_dir: str) -> dict:
    """Organize generated assets into a structured game-ready directory.

    Structure:
        output_dir/
        ├── colony_<timestamp>/
        │   ├── colony_roster.json     # Full colony metadata
        │   ├── colony_overview.html  # Visual gallery
        │   ├── ant_fire_soldier_01/
        │   │   ├── concept.json
        │   │   ├── raw.png            # With background (menus, splash)
        │   │   ├── sprite.png         # Transparent bg (in-game)
        │   │   └── model.glb          # If 3D enabled
        │   └── ...
    """
    out_root = Path(output_dir)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_dir = out_root / f"colony_{stamp}"
    batch_dir.mkdir(parents=True, exist_ok=True)

    roster = {"generated_at": stamp, "count": len(assets_3d), "ants": []}

    for ant in assets_3d:
        ant_dir = batch_dir / ant["id"]
        ant_dir.mkdir(exist_ok=True)

        # Save concept metadata
        concept = {k: v for k, v in ant.items()
                   if k not in ("image_path", "sprite_path", "model_path",
                                "art_error", "bg_error", "model_error", "model_service")}
        concept["files"] = {}
        (ant_dir / "concept.json").write_text(json.dumps(concept, indent=2))

        if ant.get("image_path") and Path(ant["image_path"]).exists():
            shutil.copy2(ant["image_path"], ant_dir / "raw.png")
            concept["files"]["raw"] = "raw.png"
            (ant_dir / "concept.json").write_text(json.dumps(concept, indent=2))

        if ant.get("sprite_path") and Path(ant["sprite_path"]).exists():
            shutil.copy2(ant["sprite_path"], ant_dir / "sprite.png")
            concept["files"]["sprite"] = "sprite.png"
            (ant_dir / "concept.json").write_text(json.dumps(concept, indent=2))

        if ant.get("model_path") and Path(ant["model_path"]).exists():
            ext = Path(ant["model_path"]).suffix or ".glb"
            shutil.copy2(ant["model_path"], ant_dir / f"model{ext}")
            concept["files"]["model"] = f"model{ext}"
            (ant_dir / "concept.json").write_text(json.dumps(concept, indent=2))

        roster["ants"].append({
            "id": ant["id"],
            "element": ant["element"],
            "role": ant["role"],
            "size": ant["size"],
            "stats": ant["stats"],
            "personality": ant["personality"],
            "dir": str(ant_dir),
            "files": concept["files"],
            "art_error": ant.get("art_error"),
            "bg_error": ant.get("bg_error"),
            "model_error": ant.get("model_error"),
        })

    (batch_dir / "colony_roster.json").write_text(json.dumps(roster, indent=2))

    # Generate a simple HTML gallery for previewing
    html_rows = []
    for ant in roster["ants"]:
        ant_dir_name = ant["id"]
        sprite_rel = f"./{ant_dir_name}/sprite.png" if "sprite" in ant["files"] else ""
        raw_rel = f"./{ant_dir_name}/raw.png" if "raw" in ant["files"] else ""
        stats_html = ", ".join(f"{k}:{v}" for k, v in ant["stats"].items())
        html_rows.append(f"""
        <div style="display:inline-block; margin:10px; vertical-align:top; width:200px;">
          <h3>{ant["id"]}</h3>
          <p>{ant["element"]} {ant["role"]} ({ant["size"]})</p>
          {'<img src="{}" style="max-width:160px">'.format(sprite_rel) if sprite_rel else "<em>no sprite</em>"}
          <p style="font-size:11px">{stats_html}</p>
          <p style="font-size:11px;color:#666">{", ".join(ant["personality"])}</p>
        </div>
        """.strip())
    gallery_html = "<html><body style='font-family:sans-serif'>" + "".join(html_rows) + "</body></html>"
    (batch_dir / "colony_overview.html").write_text(gallery_html)

    success_count = sum(1 for a in roster["ants"] if "sprite" in a["files"])
    model_count = sum(1 for a in roster["ants"] if "model" in a["files"])

    return {
        "batch_dir": str(batch_dir),
        "roster_path": str(batch_dir / "colony_roster.json"),
        "gallery_path": str(batch_dir / "colony_overview.html"),
        "total_ants": len(roster["ants"]),
        "successful_sprites": success_count,
        "successful_3d": model_count,
        "summary": (
            f"Colony generated: {success_count}/{len(roster['ants'])} sprites, "
            f"{model_count} 3D models → {batch_dir}"
        ),
    }


package = FnNode(
    fn=package_colony,
    inputs={
        "assets_3d": gen_3d.assets_3d,
        "output_dir": batch_params.output_dir,
    },
    outputs={"report": gr.JSON(label="Colony Report")},
    concurrent=True,
)


# ─── Graph Assembly ───────────────────────────────────────────────────────────

graph = Graph(
    name="🐜 Ant Colony Game Assets",
    nodes=[batch_params, colony_concept, art_generator, bg_remover, gen_3d, package],
)


# ─── CLI Entry Point ──────────────────────────────────────────────────────────

def cli():
    """Headless CLI mode for agents: generate colony without launching UI."""
    parser = argparse.ArgumentParser(description="Ant colony game asset generator")
    parser.add_argument("--count", type=int, default=5, help="Number of ants (1-10)")
    parser.add_argument("--with-3d", action="store_true", help="Also generate 3D models")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory")
    parser.add_argument("--style", default="stylized 2D game character, clean linework, vibrant colors, front-facing")
    parser.add_argument("--ui", action="store_true", help="Launch interactive Gradio canvas instead of headless run")
    args = parser.parse_args()

    if args.ui:
        graph.launch()
        return

    # Headless: drive the pipeline directly via the concept generator + gradio_client
    print(f"Generating colony: {args.count} ants, 3d={args.with_3d}")
    print(f"Output: {args.output_dir}")
    print(f"Style: {args.style}\n")

    colony = generate_colony(args.count, args.style, args.with_3d)
    print(f"[1/4] Generated {len(colony)} ant concepts:")
    for ant in colony:
        print(f"  - {ant['id']}  (stats: {ant['stats']})")

    print("\n[2/4] Generating character art (FLUX.1-schnell)...")
    art = generate_all_art(colony)
    print("  done")

    print("\n[3/4] Removing backgrounds...")
    sprites = remove_all_backgrounds(art)
    print("  done")

    assets = sprites
    if args.with_3d:
        print("\n[4/4] Generating 3D models (TripoSG / Hunyuan3D)...")
        assets = generate_3d_models(sprites)
        print("  done")
    else:
        print("\n[SKIP] 3D models (--with-3d not specified)")

    print("\n[PKG] Packaging assets...")
    report = package_colony(assets, args.output_dir)

    print(f"\n{'='*60}")
    print(f"  {report['summary']}")
    print(f"  Roster:    {report['roster_path']}")
    print(f"  Gallery:   {report['gallery_path']}")
    print(f"{'='*60}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cli()
    else:
        graph.launch()
