# daggr-pipelines

**Ready-to-run AI pipeline templates built on [daggr](https://github.com/gradio-app/daggr)** — chain Gradio apps, Hugging Face models, and custom Python functions into visual DAG workflows with state persistence and one-command deployment.

## What's in here

```
pipelines/                      Ready-to-run pipeline templates
  ant_colony_assets.py           [NEW] Generate N elemental ant game characters (sprite + optional 3D)
  ant_colony_comfyui.py          [NEW] Local-GPU variant of ant_colony via ComfyUI (zero cost)
  batch_character_sprites.py     Batch character sprites from a theme
  image_to_3d.py                 Image → bg removal → 3D model (with fallback)
  viral_content.py               Topic → social media content package
  helpers/
    __init__.py                  Exposes PipelineBuilder and helpers
    builder.py                   Programmatic pipeline construction API
    godot.py                     [NEW] Import batches into Godot 4.x projects (.tscn, .gd autoload)

scripts/                        Utility scripts
  check_spaces.py                Liveness checker for all registered Spaces
  discover_spaces.py             Search HF Hub for new Spaces by category
  export_registry.py             Export Space registry to JSON (for agents / cron)
  prompt_to_pipeline.py          [NEW] Agent-facing: describe → rank → run or script
  weekly_liveness.sh             Cron wrapper for weekly Space health reports

references/                     Data files
  registry.json                  Machine-readable Space registry (generated from REGISTRY)
  compute_guide.md               Decision matrix for CPU/GPU/cloud routing
  tested_spaces.md               Manually tested Space endpoint table
```

## Quick Start

```bash
git clone https://github.com/Jpalmer95/daggr-pipelines.git
cd daggr-pipelines
pip install -r requirements.txt

# Run the flagship pipeline (ant colony asset generator)
python pipelines/ant_colony_assets.py --count 10
python pipelines/ant_colony_assets.py --count 10 --with-3d
python pipelines/ant_colony_assets.py --ui              # interactive canvas

# Agent-facing tools
python scripts/prompt_to_pipeline.py --describe "generate 10 fire ant game sprites"
python scripts/prompt_to_pipeline.py --script "narrate an article with TTS" --output narrate.py
python scripts/prompt_to_pipeline.py --list
python scripts/prompt_to_pipeline.py --spaces-healthy

# Check which Spaces are alive
python scripts/check_spaces.py

# Discover new Spaces by category
python scripts/discover_spaces.py 3d

# Run tests
python tests/test_pipeline_logic.py
python tests/test_ant_colony.py

# Generate machine-readable registry JSON
python scripts/export_registry.py > references/registry.json
```

## Pipelines

### Ant Colony Assets ⭐ (flagship example)
**Compute:** Cloud free (image + bg) + cloud paid (optional 3D)  
**Duration:** ~15 min per 10 ants  
**License note:** Output is commercial-OK (FLUX.1-schnell = Apache 2.0)

The motivating example. Generates N ants with:
* Varying **elemental status** (fire/water/earth/lightning/shadow/crystal)
* Varying **size** (small worker → huge royal)
* Varying **role** (worker, soldier, guardian, royal)
* Unique **stats** per ant (HP, attack, elemental bonuses)
* **Personality traits** from the element's trait pool

Each ant produces: concept.json, raw.png, sprite.png, optional model.glb.
The batch produces: colony_roster.json, colony_overview.html (visual gallery).

```bash
# Headless CLI
python pipelines/ant_colony_assets.py --count 10 --output-dir ~/my_game/assets
python pipelines/ant_colony_assets.py --count 10 --with-3d

# Gradio UI canvas
python pipelines/ant_colony_assets.py --ui
```

### Ant Colony (ComfyUI local variant)
**Compute:** Local GPU (8GB+) — zero API cost, no rate limits  
**Prerequisite:** Local GPU + ComfyUI running on :8188 with FLUX.1-schnell checkpoint

Drop-in replacement for the cloud version. Identical output structure.
```bash
python pipelines/ant_colony_comfyui.py --count 10
```

### Batch Character Sprites
**Compute:** Cloud free tier  
**Duration:** ~2-3 min per character  
Generates N character sprites from a game theme and art style.

### Image to 3D Asset
**Compute:** Cloud paid tier (GPU Space for 3D gen)  
**Duration:** ~1-2 min per image  
Pipeline with automatic fallback: TripoSG → Hunyuan3D.

### Viral Content Generator
**Compute:** Cloud free tier  
**Duration:** ~3-5 min  
Topic → content strategy + parallel A/B images.

## Space Registry

The `check_spaces.py` script maintains a registry of tested Spaces with metadata:

| Field | Purpose |
|-------|---------|
| `category` | Task type (image-gen, 3d, tts, video, vision, etc.) |
| `api_name` | Exact daggr/gradio_client endpoint name |
| `license` | License type |
| `commercial_ok` | Can you use outputs commercially? |
| `compute` | CPU / cloud-free / cloud-paid / local-8gb / local-24gb |
| `speed` | fast / medium / slow |
| `notes` | Postprocess tips, gotchas |

```bash
# Check all registered Spaces
python scripts/check_spaces.py

# Check one category
python scripts/check_spaces.py --category image-gen

# JSON output (for cron jobs / automated tooling)
python scripts/check_spaces.py --json
```

## Compute Requirements

| Use Case | Compute | Cost | Notes |
|----------|---------|------|-------|
| Concept art, bg removal, TTS | Cloud free (ZeroGPU) | Free | Rate limited, cold starts |
| 3D generation, video | Cloud paid (A10G+) | ~$1/hr | Required for heavy models |
| Everything offline | Local 8GB+ VRAM | Free | Use ComfyUI for image/3D |
| Maximum quality | Local 24GB VRAM | Free | Full model weights locally |

## Agent-Facing Tooling: `prompt_to_pipeline.py`

Give a natural-language description of a workflow, get:
* Ranked matches against all registered pipeline templates
* A ready-to-run Python script that imports the matched pipeline
* Direct pipeline execution via `--run`

```bash
# Rank matches for a description
python scripts/prompt_to_pipeline.py --describe "generate 10 fire ant game sprites"
# → ant_colony  (score: 8)

# Generate a standalone script you can save and ship
python scripts/prompt_to_pipeline.py --script "narrate an article with TTS" --output narrate.py

# Run the best match headlessly with output dir override
python scripts/prompt_to_pipeline.py --run "generate ant characters" --output ~/out

# Check which Spaces are currently live
python scripts/prompt_to_pipeline.py --spaces-healthy
```

This tool is designed so Hermes Agent (or any LLM agent) can:
1. Ask "what pipeline does X?" and get a ranked list
2. Emit the matched script as a deliverable to the user
3. Run the pipeline headlessly and stream results back

## Hermes Agent Workflow Demo

A typical end-to-end agent session using this repo:

```
User: "I'm building an indie game, generate 10 elemental ant characters"

Agent workflow:
  1. Load daggr-pipelines skill → check for existing pipeline templates
  2. Run: python scripts/prompt_to_pipeline.py --describe "10 ant characters"
     → Top match: ant_colony (score 8)
  3. Check compute: no local GPU → use cloud-free path
  4. Check Space health: python scripts/prompt_to_pipeline.py --spaces-healthy
     → FLUX.1-schnell ✓  |  hf-applications/background-removal ✓
  5. Run headless:
     python pipelines/ant_colony_assets.py --count 10 --output-dir ~/game/assets
  6. Stream progress:
     [1/4] Generated 10 ant concepts
     [2/4] Generating character art (FLUX.1-schnell)...
           ant_fire_worker_01 ✓  ant_water_soldier_02 ✓  ...  (10/10)
     [3/4] Removing backgrounds...  done
     [4/4] Packaging assets...
     Summary: 10 sprites → ~/game/assets/colony_20260528_231500/
  7. (If Godot project detected) Run Godot helper:
     python pipelines/helpers/godot.py \
         --project ~/game --batch-dir ~/game/assets/colony_20260528_231500 \
         --subfolder characters/ants
     → Generates 10 .tscn scenes + colony_data.gd autoload
  8. Report to user:
     "10 elemental ant characters generated. Roster at
      ~/game/assets/colony_20260528_231500/colony_roster.json.
      Gallery at colony_overview.html. Godot autoload at
      characters/ants/colony_data.gd."
```

## PipelineBuilder API (programmatic construction)

For agents or users who need a custom pipeline not covered by the templates:

```python
from pipelines.helpers import PipelineBuilder

builder = PipelineBuilder("My Custom Pipeline")
builder.add_prompt_input("Describe a scene", default="medieval tavern interior")
builder.add_image_gen_step("FLUX.1-schnell")
builder.add_bg_removal_step()
builder.add_3d_gen_step(fallback=True)
builder.add_organize_step("output/scenes")

graph = builder.build()
graph.launch()

# Or describe without launching:
print(builder.describe())
# → ["Prompt: 'medieval tavern interior'", "Image (FLUX.1-schnell)",
#    "Clean Sprite (no bg)", "3D Model", "Asset Report"]
```

## Pairing with Hermes Agent

This repo is designed to be used with [Hermes Agent](https://github.com/NousResearch/hermes-agent). The accompanying skill (`daggr-pipelines`) provides:

- Prompt-to-pipeline translation (describe what you want, get a script)
- Automatic Space selection based on task + compute + license requirements
- Compute-aware routing (prefer local GPU over cloud when available)
- Game asset folder conventions that integrate with Godot/Unity project structures

## Adding a New Pipeline

1. Create `pipelines/your_pipeline.py`
2. Use `InputNode` for parameters, `GradioNode` for Spaces, `FnNode` for logic
3. Follow the file-path convention (all media between nodes = path strings)
4. Always use `postprocess` for multi-return Spaces
5. Loop inside `FnNode` instead of scatter/gather (buggy in v0.8.0)
6. Add your Space to the `REGISTRY` list in `scripts/check_spaces.py`
7. Register the pipeline in `PIPELINE_REGISTRY` inside `scripts/prompt_to_pipeline.py`
8. Document compute requirements in the file docstring
9. Add offline-friendly tests to `tests/` (no network calls, mock as needed)
10. Run `python scripts/export_registry.py > references/registry.json` to refresh the JSON

## Tests

```bash
python tests/test_pipeline_logic.py    # 7 tests (PipelineBuilder + generic)
python tests/test_ant_colony.py        # 7 tests (ant colony generation + packaging)
# Total: 14 tests, ~1 second, no network required
```

## Contributing

PRs welcome! Especially:

- New pipeline templates with real-world use cases (register them in `prompt_to_pipeline.py`)
- Tested Space additions to the `REGISTRY` in `check_spaces.py`
- Local ComfyUI variants of more cloud-only pipelines
- Rigging/animation nodes (when the HF Spaces become available)
- Test coverage for the Space-fallback paths in the ant pipeline

## Hermes Agent Integration

This repo pairs with the [Hermes Agent](https://github.com/NousResearch/hermes-agent) ecosystem:

* **Skill** `daggr-pipelines` — compute routing guide, registry, pairing instructions
* **Skill** `daggr` — core daggr patterns, node types, pitfalls
* **Companion** `comfyui` skill — local GPU image/3D gen for zero-cost variants
* **Companion** `gradio-app-development` — deploy pipelines to HF Spaces
* **Cron job** `daggr-space-liveness` — weekly Space health report (Mon 9am)
* **Agent-facing** `scripts/prompt_to_pipeline.py` — natural-language → pipeline ranking

Once the pipeline registry and ComfyUI variants stabilize, we'll contribute
the skills back to the Hermes Agent skill bundle.

## License

MIT — use freely. Note that individual HF Spaces have their own licenses; check `commercial_ok` tags in the registry before using outputs commercially.
