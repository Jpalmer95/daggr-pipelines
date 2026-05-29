"""
Tests for pipeline logic (non-network)
========================================

Run from the repo root:
    pytest tests/ -v

Or directly:
    python tests/test_pipeline_logic.py

These tests do NOT call any HF Spaces or network APIs.
They exercise pure-Python functions used inside pipelines:
    - Concept generation (elemental themes, shapes, sizes)
    - Asset organization (folder layout, manifest.json)
    - PipelineBuilder describe() logic
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Make repo importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipelines.batch_character_sprites import (
    generate_concepts,
    organize_assets,
    ELEMENTAL_THEMES,
    SIZE_TIERS,
)
from pipelines.helpers import PipelineBuilder


def test_generate_concepts_counts():
    """Concept generator should produce exactly N concepts."""
    concepts = generate_concepts("fantasy game", "pixel art", 5)
    assert len(concepts) == 5
    # Each concept has required fields
    for c in concepts:
        assert "id" in c
        assert "prompt" in c
        assert "element" in c
        assert "size" in c
        assert "shape" in c
        assert "seed" in c
    print("✓ test_generate_concepts_counts")


def test_generate_concepts_unique_elements():
    """With count <= num themes, each character should get a unique element."""
    concepts = generate_concepts("sci-fi", "cel-shaded", len(ELEMENTAL_THEMES))
    elements = [c["element"] for c in concepts]
    assert len(set(elements)) == len(ELEMENTAL_THEMES)
    print("✓ test_generate_concepts_unique_elements")


def test_generate_concepts_prompts_contain_style():
    """Each prompt should incorporate the art style."""
    concepts = generate_concepts("medieval", "hand-painted", 3)
    for c in concepts:
        assert "hand-painted" in c["prompt"]
    print("✓ test_generate_concepts_prompts_contain_style")


def test_organize_assets_creates_structure():
    """Organize step should create batch dir + per-character subdirs + manifest."""
    concepts = generate_concepts("test", "pixel art", 2)
    # Simulate the image and bg removal steps by creating dummy files
    tmpdir = tempfile.mkdtemp()
    try:
        output_dir = os.path.join(tmpdir, "output")
        # Build fake sprite results
        sprites = []
        for c in concepts:
            raw_path = os.path.join(tmpdir, f"{c['id']}_raw.png")
            sprite_path = os.path.join(tmpdir, f"{c['id']}_sprite.png")
            Path(raw_path).write_text("fake png raw")
            Path(sprite_path).write_text("fake png sprite")
            sprites.append({
                "id": c["id"],
                "element": c["element"],
                "size": c["size"],
                "shape": c["shape"],
                "image_path": raw_path,
                "sprite_path": sprite_path,
            })

        report = organize_assets(sprites, output_dir)

        # Verify batch dir exists
        batch_dir = Path(report["batch_dir"])
        assert batch_dir.exists()

        # Verify manifest
        manifest_path = Path(report["manifest_path"])
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["count"] == 2

        # Verify per-character subdirs
        for c in concepts:
            char_dir = batch_dir / c["id"]
            assert char_dir.exists()
            assert (char_dir / "concept.json").exists()
            assert (char_dir / "raw.png").exists()
            assert (char_dir / "sprite.png").exists()

        print("✓ test_organize_assets_creates_structure")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_pipeline_builder_describe():
    """PipelineBuilder should produce a clean step description list."""
    builder = PipelineBuilder("Test Pipeline")
    builder.add_prompt_input("Test prompt", default="hello world")
    # Can't add Space-dependent steps without live Spaces in test,
    # so just verify the InputNode was added
    desc = builder.describe()
    assert len(desc) == 1
    assert "hello world" in desc[0]
    print("✓ test_pipeline_builder_describe")


def test_pipeline_builder_build():
    """PipelineBuilder.build() should return a daggr Graph."""
    from daggr import Graph
    builder = PipelineBuilder("Empty Test")
    builder.add_prompt_input("Prompt", default="test")
    graph = builder.build()
    assert isinstance(graph, Graph)
    assert graph.name == "Empty Test"
    assert len(graph.nodes) == 1
    print("✓ test_pipeline_builder_build")


def test_pipeline_builder_choice_input():
    """add_choice_input should create a named InputNode."""
    builder = PipelineBuilder("Choice Test")
    builder.add_choice_input(
        label="Art Style",
        choices=["pixel", "realistic", "cel"],
        default="pixel",
        port_name="style",
        group_name="Art",
    )
    desc = builder.describe()
    assert len(desc) == 1
    assert "Art Style" in desc[0]
    print("✓ test_pipeline_builder_choice_input")


# ─── Run-all harness ───────────────────────────────────────────────────────────

def main():
    tests = [
        test_generate_concepts_counts,
        test_generate_concepts_unique_elements,
        test_generate_concepts_prompts_contain_style,
        test_organize_assets_creates_structure,
        test_pipeline_builder_describe,
        test_pipeline_builder_build,
        test_pipeline_builder_choice_input,
    ]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} FAILED: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"  {passed} passed, {failed} failed, {len(tests)} total")
    print(f"{'='*50}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
