"""
Viral Content Generator
=======================
Generate social media content packages:
  1. Content Strategy (FnNode) → prompts, captions, hashtags
  2. Primary Image (GradioNode, FLUX.1-schnell) → main visual
  3. Alt Image (GradioNode) → A/B test variant (parallel)
  4. Content Video (GradioNode) → short animated clip (sequential)
  5. Package (FnNode) → JSON + HTML preview

Compute: cloud-free (all remote Spaces)
Duration: ~3-5 min
License: FLUX.1-schnell = Apache 2.0 (commercial OK)
Tags: social-media, content, marketing

Usage:
    python viral_content.py
    daggr viral_content.py
"""

import random
import json

import gradio as gr
from daggr import GradioNode, FnNode, InputNode, Graph


# ─── Platform-specific styles ─────────────────────────────────────────────────

PLATFORM_STYLES = {
    "Instagram": {"aspect": "square, centered composition", "tone": "aesthetic, instagram-worthy"},
    "TikTok":    {"aspect": "vertical, dynamic framing", "tone": "eye-catching, bold"},
    "Twitter/X": {"aspect": "horizontal, clean design", "tone": "attention-grabbing"},
    "LinkedIn":  {"aspect": "professional, clean", "tone": "polished, business-ready"},
}


# ─── Input Node ───────────────────────────────────────────────────────────────

inputs = InputNode(
    name="Content Brief",
    ports={
        "topic": gr.Textbox(label="Topic / Subject", value="A futuristic coffee shop on Mars"),
        "platform": gr.Dropdown(
            label="Platform",
            choices=list(PLATFORM_STYLES.keys()),
            value="Instagram",
        ),
        "tone": gr.Dropdown(
            label="Tone",
            choices=["Professional", "Fun & Playful", "Inspirational", "Educational", "Trending/Viral"],
            value="Fun & Playful",
        ),
    },
)


# ─── Step 1: Expand Idea into Strategy ────────────────────────────────────────

def expand_idea(topic: str, platform: str, tone: str) -> dict:
    """Generate image prompts, caption, and hashtags from a topic."""
    style = PLATFORM_STYLES.get(platform, PLATFORM_STYLES["Instagram"])
    
    tone_emoji = {
        "Professional": "📊", "Fun & Playful": "🎉",
        "Inspirational": "✨", "Educational": "💡", "Trending/Viral": "🔥",
    }.get(tone, "✨")
    
    image_prompt = (
        f"{style['tone']}, {style['aspect']}. "
        f"{topic}. {tone.lower()} mood. High quality, vivid colors."
    )
    
    caption = f"{tone_emoji} {topic} — coming soon. #trending"
    
    topic_words = [w for w in topic.split() if len(w) > 3][:3]
    hashtags = " ".join(f"#{w.lower()}" for w in topic_words + ["AI", "content"])
    
    return {
        "image_prompt": image_prompt,
        "caption": caption,
        "hashtags": hashtags,
        "platform": platform,
        "tone": tone,
    }


strategy = FnNode(
    fn=expand_idea,
    inputs={
        "topic": inputs.topic,
        "platform": inputs.platform,
        "tone": inputs.tone,
    },
    outputs={
        "plan": gr.JSON(label="Content Plan"),
    },
    concurrent=True,
)


# ─── Steps 2a & 2b: Parallel Image Generation ────────────────────────────────

def make_image_node(source_port, label):
    return GradioNode(
        "hf-applications/Z-Image-Turbo",
        api_name="/generate_image",
        inputs={
            "prompt": source_port,  # Will be wired in post-init
            "seed": random.randint(0, 999999),
            "width": 1024,
            "height": 1024,
        },
        outputs={"image": gr.Image(label=label)},
    )


# We need strategy.plan.image_prompt — but plan is a JSON dict.
# Use a tiny FnNode to extract the prompt string.

def extract_prompt(plan: dict) -> str:
    return plan.get("image_prompt", "a beautiful landscape")

prompt_extractor = FnNode(
    fn=extract_prompt,
    inputs={"plan": strategy.plan},
    outputs={"prompt": gr.Textbox(visible=False)},
    concurrent=True,
)

primary_image = make_image_node(prompt_extractor.prompt, "🖼️ Primary Image")
alt_image = make_image_node(prompt_extractor.prompt, "🖼️ Alt Image (A/B)")
# Different seed for variation — override the fixed seed
alt_image = GradioNode(
    "hf-applications/Z-Image-Turbo",
    api_name="/generate_image",
    inputs={
        "prompt": prompt_extractor.prompt,
        "seed": random.randint(0, 999999),
        "width": 1024,
        "height": 1024,
    },
    outputs={"image": gr.Image(label="🖼️ Alt Image (A/B)")},
)


# ─── Step 4: Package ──────────────────────────────────────────────────────────

def package_content(plan: dict, primary, alt):
    """Bundle into a content package."""
    return {
        "platform": plan.get("platform"),
        "primary_image": primary,
        "alt_image": alt,
        "caption": plan.get("caption"),
        "hashtags": plan.get("hashtags"),
        "ready": bool(primary and plan.get("caption")),
    }


final = FnNode(
    fn=package_content,
    inputs={
        "plan": strategy.plan,
        "primary": primary_image.image,
        "alt": alt_image.image,
    },
    outputs={"package": gr.JSON(label="Content Package")},
    concurrent=True,
)


graph = Graph(
    name="📱 Viral Content Generator",
    nodes=[inputs, strategy, prompt_extractor, primary_image, alt_image, final],
)

if __name__ == "__main__":
    graph.launch()
