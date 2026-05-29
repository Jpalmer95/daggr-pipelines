#!/usr/bin/env python3
"""
Space Discovery Script — Searches HF Hub for trending/new Spaces by category.

Usage:
    python discover_spaces.py image-gen        # Search for image gen Spaces
    python discover_spaces.py 3d               # Search for 3D Spaces
    python discover_spaces.py tts              # Search for TTS Spaces
    python discover_spaces.py --all            # Search all categories
    python discover_spaces.py --trending       # Show top trending Spaces overall
"""

import argparse
import json
from typing import Optional

from huggingface_hub import HfApi


# Search queries per category
CATEGORY_QUERIES = {
    "image-gen": [
        "text to image", "image generation", "FLUX", "stable diffusion",
        "image gen", "text2img",
    ],
    "image-edit": [
        "background removal", "inpainting", "image editing",
        "upscale", "image to image",
    ],
    "video": [
        "text to video", "image to video", "video generation",
        "video gen", "text2video",
    ],
    "audio": [
        "music generation", "sound generation", "audio generation",
        "music gen", "audiogen",
    ],
    "tts": [
        "text to speech", "TTS", "voice", "speech synthesis",
    ],
    "3d": [
        "image to 3d", "3d generation", "3d model", "point cloud",
        "mesh generation", "text to 3d",
    ],
    "vision": [
        "vision language", "image description", "VLM",
        "image captioning", "visual QA",
    ],
}


def search_spaces(category: str, limit: int = 10) -> list[dict]:
    """Search for Spaces matching a category."""
    api = HfApi()
    results = []
    seen = set()
    
    queries = CATEGORY_QUERIES.get(category, [category])
    
    for query in queries:
        try:
            spaces = api.list_spaces(
                search=query,
                sort="likes",
                direction=-1,
                limit=limit,
            )
            for space in spaces:
                if space.id in seen:
                    continue
                seen.add(space.id)
                
                results.append({
                    "id": space.id,
                    "name": space.id.split("/")[1] if "/" in space.id else space.id,
                    "likes": space.likes or 0,
                    "sdk": space.sdk or "unknown",
                    "tags": [t for t in (space.tags or [])[:5]],
                })
        except Exception as e:
            print(f"  Warning: search for '{query}' failed: {e}")
    
    # Sort by likes
    results.sort(key=lambda x: x["likes"], reverse=True)
    return results[:limit]


def get_trending(limit: int = 20) -> list[dict]:
    """Get top trending Spaces overall."""
    api = HfApi()
    try:
        spaces = api.list_spaces(
            sort="likes",
            direction=-1,
            limit=limit,
        )
        return [
            {
                "id": s.id,
                "likes": s.likes or 0,
                "sdk": s.sdk or "unknown",
                "tags": [t for t in (s.tags or [])[:5]],
            }
            for s in spaces
        ]
    except Exception as e:
        print(f"Error: {e}")
        return []


def print_results(category: str, results: list[dict]):
    """Pretty-print search results."""
    print(f"\n{'='*60}")
    print(f"  {category.upper()} SPACES (Top {len(results)})")
    print(f"{'='*60}\n")
    
    for r in results:
        likes = r.get("likes", 0)
        sdk = r.get("sdk", "?")
        tags = ", ".join(r.get("tags", [])[:3])
        print(f"  ♥ {likes:>5}  {r['id']}")
        print(f"           SDK: {sdk}  |  Tags: {tags}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Discover HF Spaces for daggr pipelines")
    parser.add_argument("category", nargs="?", help="Category to search (image-gen, 3d, tts, etc.)")
    parser.add_argument("--all", "-a", action="store_true", help="Search all categories")
    parser.add_argument("--trending", "-t", action="store_true", help="Show top trending Spaces")
    parser.add_argument("--limit", "-n", type=int, default=10, help="Max results per category")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    args = parser.parse_args()
    
    if args.trending:
        results = get_trending(limit=args.limit)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print_results("Trending (All Categories)", results)
        return
    
    if args.all:
        categories = list(CATEGORY_QUERIES.keys())
    elif args.category:
        categories = [args.category]
        if args.category not in CATEGORY_QUERIES:
            print(f"Unknown category: {args.category}")
            print(f"Available: {', '.join(CATEGORY_QUERIES.keys())}")
            return
    else:
        parser.print_help()
        return
    
    all_results = {}
    for cat in categories:
        all_results[cat] = search_spaces(cat, limit=args.limit)
    
    if args.json:
        print(json.dumps(all_results, indent=2))
    else:
        for cat, results in all_results.items():
            print_results(cat, results)


if __name__ == "__main__":
    main()
