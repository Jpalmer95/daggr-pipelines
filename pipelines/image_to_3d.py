"""
Image-to-3D Asset Pipeline
============================
Takes a single image (or a batch) and produces 3D game-ready models:
  1. Input: image upload or text prompt (image gen)
  2. Background removal (clean subject)
  3. 3D model generation (TripoSG or fallback)
  4. Asset packaging (copy to game folder with metadata)

Compute: cloud-paid (HF Space with GPU for 3D gen)
Duration: ~1-2 min per image
License: See Space licenses in registry
Tags: game-dev, 3d, models, assets

Usage:
    python image_to_3d.py
    daggr image_to_3d.py
"""

import os
import json
import shutil
from pathlib import Path
from datetime import datetime

import gradio as gr
from daggr import GradioNode, FnNode, InputNode, Graph


OUTPUT_DIR = os.environ.get("DAGGR_OUTPUT_DIR", "./output/3d_assets")


# ─── Input Node ───────────────────────────────────────────────────────────────

inputs = InputNode(
    name="Input",
    ports={
        "image": gr.Image(label="Input Image", type="filepath"),
        "name": gr.Textbox(label="Asset Name", value="hero_character"),
        "output_dir": gr.Textbox(label="Output Directory", value=OUTPUT_DIR),
    },
)


# ─── Step 1: Background Removal ───────────────────────────────────────────────

bg_removal = GradioNode(
    "hf-applications/background-removal",
    api_name="/image",
    inputs={"image": inputs.image},
    postprocess=lambda original, processed: processed,
    outputs={"sprite": gr.Image(label="Clean Sprite")},
)


# ─── Step 2: 3D Generation (with fallback) ────────────────────────────────────

def generate_3d_with_fallback(image_path: str) -> dict:
    """Try TripoSG first, fall back to Hunyuan3D if it fails."""
    from gradio_client import Client
    
    result: dict = {"model_path": None, "service": None, "error": None}
    
    # Primary: TripoSG
    services = [
        ("VAST-AI/TripoSG", "/generate", "TripoSG"),
        ("Tencent/Hunyuan3D-2", "/generation_all", "Hunyuan3D"),
    ]
    
    for space_id, api_name, name in services:
        try:
            client = Client(space_id)
            output = client.predict(image_path, api_name=api_name)
            if output and (isinstance(output, str) or 
                          (isinstance(output, dict) and "path" in output)):
                result["model_path"] = output if isinstance(output, str) else output["path"]
                result["service"] = name
                return result
        except Exception as e:
            result["error"] = f"{name} failed: {str(e)[:100]}"
            continue
    
    return result


gen_3d = FnNode(
    fn=generate_3d_with_fallback,
    inputs={"image_path": bg_removal.sprite},
    outputs={"model_info": gr.JSON(label="3D Generation Result")},
    concurrent=False,
)


# ─── Step 3: Package assets ───────────────────────────────────────────────────

def package_assets(image, sprite, model_info: dict, name: str, output_dir: str) -> dict:
    """Copy all generated files into a game-ready folder."""
    out = Path(output_dir) / name
    out.mkdir(parents=True, exist_ok=True)
    
    report = {
        "name": name,
        "output_dir": str(out),
        "files": {},
        "generated_at": datetime.now().isoformat(),
    }
    
    # Copy source image
    if image and os.path.exists(image):
        shutil.copy2(image, out / f"{name}_original.png")
        report["files"]["original"] = str(out / f"{name}_original.png")
    
    # Copy sprite (sprite is an image object, save it)
    # The sprite comes through as a filepath in daggr
    if isinstance(sprite, str) and os.path.exists(sprite):
        shutil.copy2(sprite, out / f"{name}_sprite.png")
        report["files"]["sprite"] = str(out / f"{name}_sprite.png")
    
    # Copy 3D model
    if model_info and model_info.get("model_path") and os.path.exists(model_info["model_path"]):
        ext = Path(model_info["model_path"]).suffix or ".glb"
        shutil.copy2(model_info["model_path"], out / f"{name}{ext}")
        report["files"]["model"] = str(out / f"{name}{ext}")
        report["service_used"] = model_info.get("service")
    
    # Save manifest
    (out / "manifest.json").write_text(json.dumps(report, indent=2))
    report["files"]["manifest"] = str(out / "manifest.json")
    
    return report


package = FnNode(
    fn=package_assets,
    inputs={
        "image": inputs.image,
        "sprite": bg_removal.sprite,
        "model_info": gen_3d.model_info,
        "name": inputs.name,
        "output_dir": inputs.output_dir,
    },
    outputs={"report": gr.JSON(label="Asset Report")},
    concurrent=True,
)


graph = Graph(
    name="🧊 Image to 3D Asset",
    nodes=[inputs, bg_removal, gen_3d, package],
)

if __name__ == "__main__":
    graph.launch()
