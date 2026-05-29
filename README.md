# daggr-pipelines

**Ready-to-run AI pipeline templates built on [daggr](https://github.com/gradio-app/daggr)** — chain Gradio apps, Hugging Face models, and custom Python functions into visual DAG workflows with state persistence and one-command deployment.

## What's in here

```
pipelines/            Ready-to-run pipeline templates
  batch_character_sprites.py   Generate N game character sprites (concept → art → bg removal → folder)
  image_to_3d.py               Image → background removal → 3D model (with fallback services)
  viral_content.py             Topic → social media content package (strategy + parallel images)

scripts/              Utility scripts
  check_spaces.py              Liveness checker — pings all registered Spaces, reports status
  discover_spaces.py           Discovery — search HF Hub for new/trending Spaces by category

references/           Data files
  sota_registry.json           Machine-readable Space registry (exported from check_spaces.py)
  compute_guide.md             Compute requirements by category and use case
```

## Quick Start

```bash
git clone https://github.com/Jpalmer95/daggr-pipelines.git
cd daggr-pipelines
pip install -r requirements.txt

# Run a pipeline (interactive visual canvas)
python pipelines/batch_character_sprites.py

# Or with hot reloading
daggr pipelines/batch_character_sprites.py

# Check which Spaces are alive
python scripts/check_spaces.py

# Discover new Spaces by category
python scripts/discover_spaces.py 3d
```

## Pipelines

### Batch Character Sprites
**Compute:** Cloud free tier (no local GPU)  
**Duration:** ~2-3 min per character  
**License note:** Output is commercial-OK (FLUX.1-schnell = Apache 2.0)  

Generates a batch of game character sprites:
1. **Concept Generation** (FnNode) — creates elemental themes, sizes, shapes
2. **Image Generation** (gradio_client → Z-Image-Turbo) — concept art per character
3. **Background Removal** (gradio_client) — clean transparent sprites
4. **Asset Organization** (FnNode) — saves to `output/characters/batch_<timestamp>/` with manifest.json

### Image to 3D Asset
**Compute:** Cloud paid tier (GPU Space for 3D gen)  
**Duration:** ~1-2 min per image  

Pipeline with automatic fallback:
1. **Background Removal** (GradioNode) — clean subject
2. **3D Generation** (FnNode) — tries TripoSG → Hunyuan3D → reports result
3. **Asset Packaging** (FnNode) — copies model + sprite + metadata to game folder

### Viral Content Generator
**Compute:** Cloud free tier  
**Duration:** ~3-5 min  

Social media content from a topic:
1. **Content Strategy** (FnNode) — platform-specific prompts, captions, hashtags
2. **Primary + Alt Images** (GradioNode × 2, parallel) — A/B test variants
3. **Content Package** (FnNode) — JSON + readiness check

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

## Adding a New Pipeline

1. Create `pipelines/your_pipeline.py`
2. Use `InputNode` for parameters, `GradioNode` for Spaces, `FnNode` for logic
3. Follow the file-path convention (all media between nodes = path strings)
4. Always use `postprocess` for multi-return Spaces
5. Loop inside `FnNode` instead of scatter/gather (buggy in v0.8.0)
6. Add your Space to the registry in `check_spaces.py`
7. Document compute requirements in the file docstring

## Pairing with Hermes Agent

This repo is designed to be used with [Hermes Agent](https://github.com/NousResearch/hermes-agent). The accompanying skill (`daggr-pipelines`) provides:

- Prompt-to-pipeline translation (describe what you want, get a script)
- Automatic Space selection based on task + compute + license requirements
- Compute-aware routing (prefer local GPU over cloud when available)
- Game asset folder conventions that integrate with Godot/Unity project structures

## Contributing

PRs welcome! Especially:

- New pipeline templates with real-world use cases
- Tested Space additions to the registry
- Local ComfyUI variants of cloud-only pipelines
- Rigging/animation nodes (when the Spaces become available)

## License

MIT — use freely. Note that individual HF Spaces have their own licenses; check `commercial_ok` tags in the registry before using outputs commercially.
