# Compute Guide

Decision matrix for routing pipeline nodes to the right backend, balancing
cost, speed, reliability, and license compliance.

## Tier Summary

| Tier | VRAM / Hardware | Cost | Best for |
|------|-----------------|------|----------|
| `cpu` | No GPU | Free | Translation, image bg removal, TTS |
| `cloud-free` | HF ZeroGPU (rate limited) | Free | Concept art, image gen (rate-limited) |
| `cloud-paid` | HF A10G / A100 | ~$0.60-3.00/hr | 3D gen, video generation |
| `local-8gb` | RTX 3060 / 4060 | Free (hardware cost) | Image gen via ComfyUI, TripoSR |
| `local-24gb` | RTX 4090 / A5000 | Free (hardware cost) | Full models, Wan2.1 video, large 3D |

## Decision Flowchart

```
User request arrives
    │
    ├─ Task is pure-Python (reorg, format conversion, JSON generation)
    │    → FnNode with concurrent=True
    │
    ├─ Task is image generation
    │    ├─ Local GPU ≥8GB available?
    │    │        YES → ComfyUI (comfyui skill), free, fast, reliable
    │    │        NO  → FLUX.1-schnell via GradioNode (cloud-free tier)
    │    └─ Need commercial outputs?
    │         NO  → FLUX.1-dev (higher quality, non-commercial)
    │         YES → FLUX.1-schnell or SD3.5 (Apache 2.0 / CreativeML)
    │
    ├─ Task is background removal
    │    → Always hf-applications/background-removal (free, fast, reliable)
    │
    ├─ Task is 3D model generation
    │    ├─ Local GPU ≥24GB?
    │    │        YES → ComfyUI + TripoSR (fast, offline)
    │    │        NO  → VAST-AI/TripoSG (cloud-paid, best current quality)
    │    └─ Fallback → Tencent/Hunyuan3D-2 (non-commercial but works when TripoSG overloaded)
    │
    ├─ Task is video generation
    │    ├─ Local GPU ≥24GB?
    │    │        YES → ComfyUI + Wan2.1 (best quality, offline)
    │    │        NO  → Wan-AI/Wan2.1 Space (cloud-paid, Apache 2.0)
    │
    ├─ Task is TTS
    │    → Edge-TTS (free, commercial OK, fast)
    │    OR Kokoro-TTS (Apache 2.0, commercial OK)
    │    OR Qwen3-TTS (voice design, non-commercial)
    │
    └─ Task is text generation (LLM)
         → InferenceNode (HF Inference Providers, free tier generous)
         Model: meta-llama/Llama-3.1-8B-Instruct (safe commercial-OK choice)
```

## Cost Estimation by Pipeline

| Pipeline | Cloud-free | Cloud-paid | Local (8GB) | Local (24GB) |
|----------|-----------|-----------|-------------|--------------|
| batch_character_sprites | ~$0 | — | — | — |
| image_to_3d | — | ~$1/10 models | — | $0 with TripoSR |
| viral_content | ~$0 | — | — | — |
| ant_game_assets | ~$0 | ~$5/10 ants | $0 | $0 |
| full game production batch | ~$0 | ~$20/50 assets | $0 | $0 |

*Cloud-free = HF ZeroGPU rate-limited. Real rate: ~50 requests/hour for free Spaces.*
*Cloud-paid = HF dedicated A10G. $0.60/hr. 10 models @ ~1min each ≈ $0.10.*
*Local = electricity cost only. GPU amortization is separate.*

## Cold Start Times

| Space Tier | Cold Start | Notes |
|------------|------------|-------|
| CPU | ~10-30s | Always warm if popular |
| ZeroGPU (free) | ~2-5 min | Sleeps after ~5 min idle |
| Dedicated GPU | ~5-10 min | Stays warm for hours |
| Local ComfyUI | ~10s | Already running |

**Hot-path pattern:** for batch pipelines, warm the Space with a single throwaway
request before starting the real loop. Add a 30s `time.sleep` between warm-up
and first real request for ZeroGPU Spaces.

## Rate Limits & Staggering

- **HF free tier:** ~10 requests/min/Space is safe. Above that you'll see 429s.
- **HF paid Spaces:** essentially unlimited (you're renting the hardware).
- **Batch work around:** sleep 6s between requests to stay under free tier.
  ```python
  for item in batch:
      result = client.predict(...)
      time.sleep(6)
  ```

## License Quick Reference

| License | Commercial | Use where |
|---------|-----------|-----------|
| Apache 2.0 | ✅ Yes | FLUX.1-schnell, Wan2.1, Kokoro-TTS |
| MIT | ✅ Yes | most utility Spaces |
| CreativeML OpenRAIL-M | ✅ Yes | Stable Diffusion family |
| FLUX.1-dev | ❌ Non-commercial | Higher-quality image gen for research |
| GPL-3.0 | ⚠️ Copyleft | Avoid for commercial closed-source |
| Unknown | ❓ Verify | Check Space's LICENSE.md before use |

**Rule of thumb:** if `commercial_ok=True` in the registry, use it. If not, verify
the Space's LICENSE.md before using outputs in a shipped game.

## Hardware Detection (for agents)

```python
import torch
import shutil

def available_compute():
    """Returns the best compute tier available on this machine."""
    if torch.cuda.is_available():
        vram_gb = torch.cuda.get_device_properties(0).total_mem / 1e9
        if vram_gb >= 20:
            return "local-24gb"
        elif vram_gb >= 7:
            return "local-8gb"
    return "cpu"

def has_comfyui():
    return shutil.which("comfy-cli") is not None or Path("~/comfyui").expanduser().exists()
```

Use this in pipeline builders to auto-route:
- ComfyUI present + local GPU → local ComfyUI pipeline
- Otherwise → cloud Spaces
