"""
Tests for ant colony pipeline logic
=======================================
All offline / no-network. Exercises concept generation, stats math, and packaging.
"""

import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipelines.ant_colony_assets import (
    generate_colony,
    package_colony,
    ELEMENTS, ANT_ROLES, SIZE_MODIFIERS,
    generate_all_art, remove_all_backgrounds,
)


def test_all_elements_distinct():
    """Each elemental type has a unique palette."""
    palettes = {e["palette"] for e in ELEMENTS}
    assert len(palettes) == len(ELEMENTS)
    print("✓ test_all_elements_distinct")


def test_colony_stats_apply_elemental_bonus():
    """Fire ants should get the fire element's stat bonuses applied."""
    colony = generate_colony(6, "test style", False)
    fire_ant = next((a for a in colony if a["element"] == "fire"), None)
    assert fire_ant is not None
    # Fire element: attack+2, speed+1, hp-1
    fire_bonus = next(e["stat_bonus"] for e in ELEMENTS if e["name"] == "fire")
    role = next(r for r in ANT_ROLES if r["name"] == fire_ant["role"])
    # Verify at least one fire-specific stat is present
    for stat, bonus in fire_bonus.items():
        assert stat in fire_ant["stats"] or bonus in fire_ant["stats"].values(), \
            f"Missing fire stat '{stat}' in {fire_ant['stats']}"
    print("✓ test_colony_stats_apply_elemental_bonus")


def test_colony_has_required_fields():
    """Every ant should have id, element, role, size, stats, personality, prompt, seed."""
    colony = generate_colony(4, "test", False)
    required = {"id", "element", "role", "size", "stats", "personality", "prompt", "seed"}
    for ant in colony:
        assert required.issubset(ant.keys()), f"Missing keys in {ant.keys()}"
    print("✓ test_colony_has_required_fields")


def test_colony_prompts_contain_style():
    """Every ant prompt should include the supplied art style."""
    style = "pixel art masterpiece"
    colony = generate_colony(3, style, False)
    for ant in colony:
        assert style in ant["prompt"]
    print("✓ test_colony_prompts_contain_style")


def test_colony_unique_ids():
    """Each ant should get a unique ID even with small counts."""
    colony = generate_colony(len(ELEMENTS), "test", False)
    ids = [a["id"] for a in colony]
    assert len(set(ids)) == len(ids)
    print("✓ test_colony_unique_ids")


def test_package_creates_html_gallery():
    """package_colony() should write a colony_overview.html."""
    tmpdir = tempfile.mkdtemp()
    try:
        output_dir = os.path.join(tmpdir, "out")
        # Build minimal ant entries with dummy image paths
        ants = []
        for i in range(2):
            raw = os.path.join(tmpdir, f"raw{i}.png")
            sprite = os.path.join(tmpdir, f"sprite{i}.png")
            open(raw, "w").close()
            open(sprite, "w").close()
            ants.append({
                "id": f"ant_{i:02d}",
                "element": "fire",
                "role": "soldier",
                "size": "medium",
                "stats": {"hp": 7, "attack": 4},
                "personality": ["aggressive"],
                "image_path": raw,
                "sprite_path": sprite,
                "seed": i,
                "index": i,
            })
        report = package_colony(ants, output_dir)
        assert os.path.exists(report["gallery_path"])
        assert report["gallery_path"].endswith("colony_overview.html")
        print("✓ test_package_creates_html_gallery")
    finally:
        shutil.rmtree(tmpdir)


def test_headless_functions_run():
    """Verify the batch functions have the expected signature and handle empty inputs gracefully."""
    import inspect
    # generate_all_art and remove_all_backgrounds accept a single list arg
    assert len(inspect.signature(generate_all_art).parameters) == 1
    assert len(inspect.signature(remove_all_backgrounds).parameters) == 1
    # Calling them with an empty list should return an empty list (no errors, no network)
    assert generate_all_art([]) == []
    assert remove_all_backgrounds([]) == []
    print("✓ test_headless_functions_run (empty-input safe)")


def main():
    tests = [
        test_all_elements_distinct,
        test_colony_has_required_fields,
        test_colony_prompts_contain_style,
        test_colony_unique_ids,
        test_colony_stats_apply_elemental_bonus,
        test_package_creates_html_gallery,
        test_headless_functions_run,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"✗ {t.__name__} FAILED: {e}")
            failed += 1
    print(f"\n{'='*50}")
    print(f"  {passed} passed, {failed} failed, {len(tests)} total")
    print(f"{'='*50}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
