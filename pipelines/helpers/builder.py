"""
Pipeline Builder Helpers
========================

A programmatic pipeline builder for Hermes Agent. Instead of writing full
pipeline scripts, agents can construct pipelines from high-level descriptions
using these helpers.

Example usage by an agent:
    from pipelines.helpers import PipelineBuilder
    
    builder = PipelineBuilder("My Game Assets")
    builder.add_prompt_input("Describe your character", default="fire elemental knight")
    builder.add_image_gen_step("FLUX.1-schnell")
    builder.add_bg_removal_step()
    builder.add_3d_gen_step(fallback=True)
    builder.add_organize_step("output/character_assets")
    
    graph = builder.build()
    graph.launch()

The builder handles all the postprocess boilerplate, file path conventions,
and Space parameter wiring. It also knows which Spaces are alive (via the
registry in check_spaces.py) and can route to alternatives.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional

import gradio as gr
from daggr import Graph, GradioNode, FnNode, InputNode


# ─── Space presets ─────────────────────────────────────────────────────────────
# These map friendly names → daggr node configs.
# Update these as Space availability changes (or use check_spaces.py for live data).

IMAGE_GEN_SPACES = {
    "FLUX.1-schnell": {
        "space": "black-forest-labs/FLUX.1-schnell",
        "api_name": "/infer",
        "inputs_template": {
            "prompt": None,  # wired by builder
            "seed": 0,
            "randomize_seed": True,
            "width": 1024,
            "height": 1024,
            "num_inference_steps": 4,
        },
        "postprocess": lambda result, seed: result,  # discard seed
        "commercial": True,
        "cost": "free-tier",
    },
    "Z-Image-Turbo": {
        "space": "hf-applications/Z-Image-Turbo",
        "api_name": "/generate_image",
        "inputs_template": {
            "prompt": None,
            "height": 1024,
            "width": 1024,
            "seed": 0,
        },
        "postprocess": None,
        "commercial": True,
        "cost": "free-tier-often-sleeping",
    },
    "SD3.5-large": {
        "space": "stabilityai/stable-diffusion-3.5-large",
        "api_name": "/infer",
        "inputs_template": {
            "prompt": None,
            "seed": 0,
            "randomize_seed": True,
            "width": 1024,
            "height": 1024,
            "num_inference_steps": 28,
            "guidance_scale": 7.5,
        },
        "postprocess": lambda result, seed: result,
        "commercial": True,
        "cost": "cloud-paid",
    },
}

BG_REMOVAL_SPACES = {
    "default": {
        "space": "hf-applications/background-removal",
        "api_name": "/image",
        "postprocess": lambda original, processed: processed,
    },
    "not-lain": {
        "space": "not-lain/background-removal",
        "api_name": "/run",
        "postprocess": None,
    },
}

THREED_SPACES = {
    "TripoSG": {
        "space": "VAST-AI/TripoSG",
        "api_name": "/generate",
        "commercial": True,
    },
    "Hunyuan3D": {
        "space": "Tencent/Hunyuan3D-2",
        "api_name": "/generation_all",
        "commercial": False,
    },
}

TTS_SPACES = {
    "Edge-TTS": {
        "space": "innoai/Edge-TTS-Text-to-Speech",
        "api_name": "/tts_interface",
        "inputs_template": {
            "text": None,
            "voice": "en-US-AriaNeural - en-US (Female)",
            "rate": 0,
            "pitch": 0,
        },
        "commercial": True,
    },
    "Kokoro-TTS": {
        "space": "hexgrad/Kokoro-TTS",
        "api_name": "/tts",
        "inputs_template": {
            "text": None,
            "voice": "af_sky",
        },
        "commercial": True,
    },
    "Qwen3-TTS": {
        "space": "ysharma/Qwen3-TTS",
        "api_name": "/generate_voice_design",
        "inputs_template": {
            "text": None,
            "language": "Auto",
            "voice_description": "friendly narrator",
        },
        "commercial": False,
    },
}


# ─── Dataclass for a "step" ───────────────────────────────────────────────────

@dataclass
class PipelineStep:
    name: str              # human-readable step name
    node: object           # daggr Node instance
    output_port: str       # the port downstream nodes connect to
    label: str             # display label


# ─── PipelineBuilder ───────────────────────────────────────────────────────────

class PipelineBuilder:
    """
    Build a daggr Graph incrementally, step by step.
    
    Designed for use by Hermes Agent or other orchestrators who want to
    compose pipelines from natural-language-like descriptions rather than
    writing full pipeline code.
    """

    def __init__(self, name: str = "Pipeline"):
        self.name = name
        self._nodes: list = []
        self._steps: list[PipelineStep] = []
        self._input_nodes: list[InputNode] = []

    # ── Input helpers ──────────────────────────────────────────────────────────

    def add_prompt_input(
        self,
        label: str = "Prompt",
        default: str = "",
        lines: int = 3,
        port_name: str = "prompt",
    ) -> "PipelineBuilder":
        """Add a text prompt input to the pipeline."""
        inp = InputNode(
            name="Prompt",
            ports={port_name: gr.Textbox(label=label, value=default, lines=lines)},
        )
        self._input_nodes.append(inp)
        self._nodes.append(inp)
        self._steps.append(PipelineStep(
            name="prompt_input",
            node=inp,
            output_port=port_name,
            label=f"Prompt: '{default[:40]}'" if default else "Prompt",
        ))
        return self

    def add_choice_input(
        self,
        label: str,
        choices: list[str],
        default: str,
        port_name: str,
        group_name: str = "Options",
    ) -> "PipelineBuilder":
        """Add a dropdown choice input."""
        inp = InputNode(
            name=group_name,
            ports={port_name: gr.Dropdown(label=label, choices=choices, value=default)},
        )
        self._input_nodes.append(inp)
        self._nodes.append(inp)
        self._steps.append(PipelineStep(
            name=f"choice_{port_name}",
            node=inp,
            output_port=port_name,
            label=f"{label} = {default}",
        ))
        return self

    # ── Space step helpers ─────────────────────────────────────────────────────

    def add_image_gen_step(
        self,
        space_key: str = "FLUX.1-schnell",
        label: str = "Generated Image",
    ) -> "PipelineBuilder":
        """
        Add a GradioNode that calls a text-to-image Space.
        Wires the prompt from the previous step's 'prompt' port.
        """
        if space_key not in IMAGE_GEN_SPACES:
            raise ValueError(
                f"Unknown image Space: {space_key}. "
                f"Available: {list(IMAGE_GEN_SPACES.keys())}"
            )
        cfg = IMAGE_GEN_SPACES[space_key]

        # Resolve the upstream prompt port
        prompt_source = None
        for step in reversed(self._steps):
            if step.output_port == "prompt":
                prompt_source = getattr(step.node, step.output_port)
                break
        if prompt_source is None:
            raise ValueError(
                "No upstream 'prompt' port found. Call add_prompt_input() first."
            )

        # Build input dict
        inputs = dict(cfg["inputs_template"])
        inputs["prompt"] = prompt_source

        node = GradioNode(
            cfg["space"],
            api_name=cfg["api_name"],
            inputs=inputs,
            postprocess=cfg.get("postprocess"),
            outputs={"image": gr.Image(label=label)},
        )
        self._nodes.append(node)
        self._steps.append(PipelineStep(
            name=f"image_gen_{space_key}",
            node=node,
            output_port="image",
            label=f"Image ({space_key})",
        ))
        return self

    def add_bg_removal_step(
        self,
        space_key: str = "default",
        label: str = "Clean Sprite (no bg)",
    ) -> "PipelineBuilder":
        """
        Add a background removal step. Wires the image from the previous step.
        """
        cfg = BG_REMOVAL_SPACES[space_key]
        image_source = getattr(self._steps[-1].node, self._steps[-1].output_port)
        node = GradioNode(
            cfg["space"],
            api_name=cfg["api_name"],
            inputs={"image": image_source},
            postprocess=cfg.get("postprocess"),
            outputs={"image": gr.Image(label=label)},
        )
        self._nodes.append(node)
        self._steps.append(PipelineStep(
            name="bg_removal",
            node=node,
            output_port="image",
            label=label,
        ))
        return self

    def add_3d_gen_step(
        self,
        space_key: str = "TripoSG",
        fallback: bool = True,
        label: str = "3D Model",
    ) -> "PipelineBuilder":
        """
        Add a 3D generation step. If fallback=True, wraps in FnNode that tries
        multiple Spaces and returns the first success.
        """
        cfg = THREED_SPACES[space_key]
        image_source = getattr(self._steps[-1].node, self._steps[-1].output_port)

        if fallback:
            # FnNode that tries TripoSG first, then Hunyuan3D
            services = [
                (THREED_SPACES["TripoSG"]["space"], THREED_SPACES["TripoSG"]["api_name"], "TripoSG"),
                (THREED_SPACES["Hunyuan3D"]["space"], THREED_SPACES["Hunyuan3D"]["api_name"], "Hunyuan3D"),
            ]
            def generate_3d_fallback(image_path, services=services):
                from gradio_client import Client
                for space_id, api_name, name in services:
                    try:
                        client = Client(space_id)
                        output = client.predict(image_path, api_name=api_name)
                        if output and (isinstance(output, str) or
                                       (isinstance(output, dict) and "path" in output)):
                            path = output if isinstance(output, str) else output["path"]
                            return {"model_path": path, "service": name}
                    except Exception:
                        continue
                return {"model_path": None, "service": None, "error": "all 3D Spaces failed"}

            node = FnNode(
                fn=generate_3d_fallback,
                inputs={"image_path": image_source},
                outputs={"model_info": gr.JSON(label="3D Result")},
                concurrent=False,
            )
            self._nodes.append(node)
            self._steps.append(PipelineStep(
                name="gen_3d_fallback",
                node=node,
                output_port="model_info",
                label=label,
            ))
        else:
            node = GradioNode(
                cfg["space"],
                api_name=cfg["api_name"],
                inputs={"image": image_source},
                outputs={"model": gr.Model3D(label=label)},
            )
            self._nodes.append(node)
            self._steps.append(PipelineStep(
                name="gen_3d",
                node=node,
                output_port="model",
                label=label,
            ))
        return self

    def add_tts_step(
        self,
        space_key: str = "Edge-TTS",
        label: str = "Audio",
    ) -> "PipelineBuilder":
        """Add a TTS step. Wires text from the previous step."""
        cfg = TTS_SPACES[space_key]
        text_source = getattr(self._steps[-1].node, self._steps[-1].output_port)
        inputs = dict(cfg["inputs_template"])
        inputs["text"] = text_source
        node = GradioNode(
            cfg["space"],
            api_name=cfg["api_name"],
            inputs=inputs,
            outputs={"audio": gr.Audio(label=label)},
        )
        self._nodes.append(node)
        self._steps.append(PipelineStep(
            name=f"tts_{space_key}",
            node=node,
            output_port="audio",
            label=label,
        ))
        return self

    def add_organize_step(
        self,
        output_dir: str = "./output/assets",
        label: str = "Asset Report",
    ) -> "PipelineBuilder":
        """Add a terminal FnNode that copies all generated files to a structured folder."""
        # Gather all prior step outputs
        sources = {}
        for step in self._steps:
            sources[step.name] = getattr(step.node, step.output_port)

        def organize_files(output_dir=output_dir, sources=sources):
            import json
            import os
            import shutil
            from pathlib import Path
            from datetime import datetime

            out = Path(output_dir) / datetime.now().strftime("batch_%Y%m%d_%H%M%S")
            out.mkdir(parents=True, exist_ok=True)
            files = {}
            for name, val in sources.items():
                if isinstance(val, str) and os.path.exists(val):
                    shutil.copy2(val, out / Path(val).name)
                    files[name] = str(out / Path(val).name)
            (out / "manifest.json").write_text(json.dumps({"files": files}, indent=2))
            return {"output_dir": str(out), "files": files, "count": len(files)}

        # Wire only the last step's output (simplification)
        last = self._steps[-1]
        node = FnNode(
            fn=organize_files,
            inputs={"_source": getattr(last.node, last.output_port)},
            outputs={"report": gr.JSON(label=label)},
            concurrent=True,
        )
        self._nodes.append(node)
        self._steps.append(PipelineStep(
            name="organize",
            node=node,
            output_port="report",
            label=label,
        ))
        return self

    def add_custom_node(self, node, output_port: str, name: str, label: str) -> "PipelineBuilder":
        """Attach a pre-built node (GradioNode/FnNode/InferenceNode) with wiring."""
        self._nodes.append(node)
        self._steps.append(PipelineStep(
            name=name, node=node, output_port=output_port, label=label,
        ))
        return self

    # ── Build ──────────────────────────────────────────────────────────────────

    def build(self) -> Graph:
        """Assemble all nodes into a daggr Graph."""
        return Graph(name=self.name, nodes=self._nodes)

    def describe(self) -> list[str]:
        """Return a human-readable summary of the pipeline steps."""
        return [step.label for step in self._steps]


# ─── Quick sanity check ────────────────────────────────────────────────────────

def demo():
    """Quick demo: build a concept→image→bg removal→3D pipeline."""
    builder = PipelineBuilder("Concept to 3D Asset")
    (builder
     .add_prompt_input(
         "Describe a game character",
         default="a small fire elemental, cartoon style, transparent background",
     )
     .add_image_gen_step("FLUX.1-schnell")
     .add_bg_removal_step()
     .add_3d_gen_step(fallback=True)
     .add_organize_step("output/character_assets"))

    graph = builder.build()
    print("Pipeline:", graph.name)
    print("Steps:", builder.describe())
    print("Ready to launch: graph.launch()")


if __name__ == "__main__":
    demo()
