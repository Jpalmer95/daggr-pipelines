"""
Batch Character Sprites Pipeline
=================================
Generates a batch of character concept art from descriptions:
  1. Concept Generation (LLM) → character descriptions with prompts
  2. Image Generation (FLUX.1-schnell) → character art
  3. Background Removal → clean sprite with transparent bg
  4. Asset Organization (FnNode) → saves to game folder

Compute: cloud-free (all remote HF Spaces, no local GPU needed)
Duration: ~2-3 min per character
License: FLUX.1-schnell = Apache 2.0 (commercial OK)
Tags: game-dev, 2d, sprites, character-art, batch

Usage:
    python batch_character_sprites.py
    daggr batch_character_sprites.py    # hot reload
"""

import os
import json
import random
import shutil
from pathlib import Path
from datetime import datetime

import gradio as gr
from daggr import GradioNode, FnNode, InferenceNode, InputNode, Graph


# ─── Configuration ─────────────────────────────────────────────────────────────

# Where generated assets end up. Game projects can set this to their assets dir.
OUTPUT_DIR = os.environ.get("DAGGR_OUTPUT_DIR", "./output/characters")
IMAGE_WIDTH = 1024
IMAGE_HEIGHT = 1024

ELEMENTAL_THEMES = [
    "fire", "water", "earth", "air", "lightning",
    "ice", "shadow", "light", "nature", "arcane",
]

SIZE_TIERS = ["small", "medium", "large", "huge"]

SHAPE_DESCRIPTORS = [
    "slender and agile", "stocky and armored", "tall and ethereal",
    "compact and mechanical", "bulky and crystalline",
]


# ─── Input Node: Batch Parameters ─────────────────────────────────────────────

batch_params = InputNode(
    name="Batch Settings",
    ports={
        "game_theme": gr.Textbox(
            label="Game Theme / Setting",
            value="elemental fantasy creatures",
            info="What kind of game? e.g., 'sci-fi robots', 'medieval knights'"
        ),
        "art_style": gr.Dropdown(
            label="Art Style",
            choices=["pixel art", "hand-painted", "cel-shaded", "realistic", "low-poly 3D render"],
            value="hand-painted",
        ),
        "count": gr.Slider(
            label="Number of Characters",
            minimum=1, maximum=10, step=1, value=3,
        ),
        "output_dir": gr.Textbox(
            label="Output Directory",
            value=OUTPUT_DIR,
            info="Where to save generated assets",
        ),
    },
)


# ─── Step 1: Generate Character Concepts ──────────────────────────────────────

def generate_concepts(game_theme: str, art_style: str, count: int) -> list[dict]:
    """Generate character concept descriptions locally (no LLM needed for demo).
    
    For production, swap this with an InferenceNode calling Llama-3.1 or similar.
    """
    count = int(count)  # Gradio slider returns float
    random.seed(42)  # Reproducible demos; comment out for random results
    
    concepts = []
    used_elements = set()
    used_shapes = set()
    
    for i in range(count):
        # Cycle through elements, avoiding repeats
        element = ELEMENTAL_THEMES[i % len(ELEMENTAL_THEMES)]
        while element in used_elements and len(used_elements) < len(ELEMENTAL_THEMES):
            element = random.choice(ELEMENTAL_THEMES)
        used_elements.add(element)
        
        # Pick shape (try to avoid repeats)
        available_shapes = [s for s in SHAPE_DESCRIPTORS if s not in used_shapes]
        if not available_shapes:
            available_shapes = SHAPE_DESCRIPTORS
        shape = random.choice(available_shapes)
        used_shapes.add(shape)
        
        # Pick size
        size = SIZE_TIERS[i % len(SIZE_TIERS)]
        
        name = f"{element}_{size}_v{i+1:02d}"
        
        concept = {
            "id": name,
            "element": element,
            "size": size,
            "shape": shape,
            "prompt": (
                f"A {size} {element}-themed game character, {shape}, "
                f"{game_theme}, {art_style} style, "
                f"full body, centered on solid white background, "
                f"game art, high detail, clean edges"
            ),
            "seed": random.randint(0, 999999),
        }
        concepts.append(concept)
    
    return concepts


concept_gen = FnNode(
    fn=generate_concepts,
    inputs={
        "game_theme": batch_params.game_theme,
        "art_style": batch_params.art_style,
        "count": batch_params.count,
    },
    outputs={
        "concepts": gr.JSON(label="Character Concepts"),
    },
    concurrent=True,
)


# ─── Step 2: Generate Character Art (loop inside FnNode) ──────────────────────
# Note: We loop inside one FnNode because daggr's scatter/gather is buggy in v0.8.0.
# This is the documented workaround. See the skill's "Scatter/Gather" section.

def generate_all_images(concepts: list[dict]) -> list[dict]:
    """Generate character images via HF Space (gradio_client).
    
    Uses the same Space as a GradioNode would, but calls it directly
    so we can loop over the concept list in a single node.
    """
    from gradio_client import Client
    
    results = []
    client = None
    
    for concept in concepts:
        image_path = None
        error = None
        
        try:
            if client is None:
                client = Client("hf-applications/Z-Image-Turbo")
            
            result = client.predict(
                prompt=concept["prompt"],
                height=IMAGE_HEIGHT,
                width=IMAGE_WIDTH,
                seed=concept["seed"],
                api_name="/generate_image",
            )
            
            # Result can be a dict {"path": "..."} or a string path
            if isinstance(result, dict) and "path" in result:
                image_path = result["path"]
            elif isinstance(result, str):
                image_path = result
            elif hasattr(result, "path"):  # pyright: ignore
                image_path = result.path    # pyright: ignore
                
        except Exception as e:
            error = str(e)
        
        results.append({
            "id": concept["id"],
            "element": concept["element"],
            "size": concept["size"],
            "shape": concept["shape"],
            "prompt": concept["prompt"],
            "seed": concept["seed"],
            "image_path": image_path,
            "error": error,
        })
    
    return results


image_gen = FnNode(
    fn=generate_all_images,
    inputs={
        "concepts": concept_gen.concepts,
    },
    outputs={
        "images": gr.JSON(label="Generated Images (with paths)"),
    },
    # Keep sequential — these are network I/O but we want to respect rate limits
    concurrent=False,
)


# ─── Step 3: Remove Backgrounds ───────────────────────────────────────────────

def remove_backgrounds(images: list[dict]) -> list[dict]:
    """Remove backgrounds from all generated images."""
    from gradio_client import Client
    
    results = []
    client = None
    
    for img in images:
        if not img.get("image_path"):
            img["sprite_path"] = None
            img["bg_error"] = "No image to process"
            results.append(img)
            continue
        
        try:
            if client is None:
                client = Client("hf-applications/background-removal")
            
            original, processed = client.predict(
                img["image_path"],
                api_name="/image",
            )
            
            # processed is a file path
            img["sprite_path"] = processed
            
        except Exception as e:
            img["sprite_path"] = None
            img["bg_error"] = str(e)
        
        results.append(img)
    
    return results


bg_removal = FnNode(
    fn=remove_backgrounds,
    inputs={
        "images": image_gen.images,
    },
    outputs={
        "sprites": gr.JSON(label="Sprites (bg removed)"),
    },
    concurrent=False,
)


# ─── Step 4: Organize into Game Folder ────────────────────────────────────────

def organize_assets(sprites: list[dict], output_dir: str) -> dict:
    """Copy sprites to game asset folder with organized structure.
    
    Creates:
        output_dir/
        ├── manifest.json          # metadata for all characters
        ├── fire_medium_v01/
        │   ├── concept.json       # original concept data
        │   ├── raw.png            # pre-bg-removal image
        │   └── sprite.png         # bg-removed sprite
        └── ...
    """
    output_path = Path(output_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_dir = output_path / f"batch_{timestamp}"
    batch_dir.mkdir(parents=True, exist_ok=True)
    
    manifest = {
        "generated_at": timestamp,
        "count": len(sprites),
        "characters": [],
    }
    
    for sprite in sprites:
        char_dir = batch_dir / sprite["id"]
        char_dir.mkdir(exist_ok=True)
        
        # Save concept metadata
        concept_data = {k: v for k, v in sprite.items() 
                       if k not in ("image_path", "sprite_path")}
        (char_dir / "concept.json").write_text(json.dumps(concept_data, indent=2))
        
        # Copy raw image
        if sprite.get("image_path") and os.path.exists(sprite["image_path"]):
            shutil.copy2(sprite["image_path"], char_dir / "raw.png")
        
        # Copy sprite
        if sprite.get("sprite_path") and os.path.exists(sprite["sprite_path"]):
            shutil.copy2(sprite["sprite_path"], char_dir / "sprite.png")
            manifest["characters"].append({
                "id": sprite["id"],
                "element": sprite["element"],
                "size": sprite["size"],
                "shape": sprite["shape"],
                "sprite_path": str(char_dir / "sprite.png"),
                "raw_path": str(char_dir / "raw.png"),
                "concept_path": str(char_dir / "concept.json"),
            })
    
    (batch_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    
    return {
        "batch_dir": str(batch_dir),
        "manifest_path": str(batch_dir / "manifest.json"),
        "total_characters": len(manifest["characters"]),
        "summary": f"Generated {len(manifest['characters'])} characters → {batch_dir}",
    }


organize = FnNode(
    fn=organize_assets,
    inputs={
        "sprites": bg_removal.sprites,
        "output_dir": batch_params.output_dir,
    },
    outputs={
        "report": gr.JSON(label="Generation Report"),
    },
    concurrent=True,
)


# ─── Assemble & Launch ────────────────────────────────────────────────────────

graph = Graph(
    name="🎮 Batch Character Sprites",
    nodes=[concept_gen, image_gen, bg_removal, organize],
)

if __name__ == "__main__":
    graph.launch()
