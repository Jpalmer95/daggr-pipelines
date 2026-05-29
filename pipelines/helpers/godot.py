"""
Godot Project Helper
====================
Integrates generated daggr-pipelines assets directly into a Godot 4.x project.

Handles:
    1. Copying sprites/models into the project's asset folder structure
    2. Generating Godot .import hints (e.g. .import.png for textures)
    3. Creating a scene tree .tscn per character with the sprite already applied
    4. Producing a colony_data.gd autoload singleton that maps IDs → scenes

Godot 4.x is assumed. For Godot 3.x, the .tscn format is similar but
Resource types differ (e.g. Sprite2D vs Sprite).

Usage (from within a pipeline):
    from pipelines.helpers.godot import GodotProjectHelper
    helper = GodotProjectHelper("/home/jonathan/mygame")
    helper.import_colony(batch_report, subfolder="characters/ants")

Usage (CLI):
    python pipelines/helpers/godot.py \\
        --project /home/jonathan/mygame \\
        --batch-dir output/ant_colony/colony_20260528_230000 \\
        --subfolder characters/ants
"""

import argparse
import json
import os
import shutil
import sys
import textwrap
from pathlib import Path


class GodotProjectHelper:
    """Helper for integrating daggr-pipelines output into a Godot 4.x project."""

    def __init__(self, project_root: str | Path):
        self.root = Path(project_root)
        if not (self.root / "project.godot").exists():
            raise FileNotFoundError(
                f"{self.root} is not a Godot project (no project.godot found)"
            )

    # ── Asset copying ─────────────────────────────────────────────────────────

    def import_colony(
        self,
        batch_report: dict | Path,
        subfolder: str = "characters",
    ) -> dict:
        """Import a full colony batch into the Godot project.

        batch_report: either the dict returned by package_colony() or a path
                      to its colony_roster.json file.
        subfolder: target folder inside the project (under res://)

        Returns: summary dict with paths and counts.
        """
        if isinstance(batch_report, (str, Path)):
            report_data = json.loads(Path(batch_report).read_text())
        else:
            report_data = batch_report

        target_dir = self.root / subfolder
        target_dir.mkdir(parents=True, exist_ok=True)

        imported = {"count": 0, "scenes": [], "autoload_path": None}

        for ant in report_data.get("ants", []):
            ant_dir = target_dir / ant["id"]
            ant_dir.mkdir(parents=True, exist_ok=True)

            # Copy sprite + raw
            source_dir = Path(ant["dir"])
            for fname in ("sprite.png", "raw.png", "model.glb"):
                src = source_dir / fname
                if src.exists():
                    shutil.copy2(src, ant_dir / fname)

            # Copy concept metadata
            src_concept = source_dir / "concept.json"
            if src_concept.exists():
                shutil.copy2(src_concept, ant_dir / "concept.json")

            # Generate Godot scene (.tscn) wrapping the sprite
            scene_path = self._write_character_scene(ant_dir, ant)
            imported["scenes"].append(str(scene_path.relative_to(self.root)))

            imported["count"] += 1

        # Generate autoload singleton for colony data access
        autoload_path = self._write_colony_singleton(report_data, target_dir)
        imported["autoload_path"] = str(autoload_path.relative_to(self.root))

        return imported

    # ── Scene generation ──────────────────────────────────────────────────────

    def _write_character_scene(self, ant_dir: Path, ant: dict) -> Path:
        """Write a minimal .tscn for a single character."""
        scene_path = ant_dir / f"{ant['id']}.tscn"

        has_sprite = (ant_dir / "sprite.png").exists()
        has_model = (ant_dir / "model.glb").exists()

        ext_resources = []
        nodes = []

        # Load sprite texture if present
        if has_sprite:
            ext_resources.append(
                f'[ext_resource type="Texture2D" path="sprite.png" id="1"]'
            )
            nodes.append(textwrap.dedent("""\
                [node name="Sprite2D" type="Sprite2D"]
                texture = ExtResource("1")
                pixel_per_unit = 100
                """).strip())

        # Load 3D model if present
        if has_model:
            ext_resources.append(
                f'[ext_resource type="PackedScene" path="model.glb" id="2"]'
            )
            nodes.append(textwrap.dedent("""\
                [node name="Model3D" type="Node3D"]
                """).strip())
            nodes.append(textwrap.dedent("""\
                [node name="ModelInstance" parent="Model3D" instance=ExtResource("2")]
                """).strip())

        # Stats metadata as a child node (so code can query at runtime)
        stats_text = ", ".join(f"{k}={v}" for k, v in ant.get("stats", {}).items())
        nodes.append(textwrap.dedent(f"""\
            [node name="AntData" type="Node"]
            metadata/ant_id = "{ant['id']}"
            metadata/element = "{ant['element']}"
            metadata/role = "{ant['role']}"
            metadata/size = "{ant['size']}"
            metadata/stats = "{stats_text}"
            metadata/personality = [{', '.join(f'"{t}"' for t in ant.get('personality', []))}]
            """).strip())

        root_node_type = "Node2D" if has_sprite else ("Node3D" if has_model else "Node")
        content = f"[gd_scene format=3]\n\n" + "\n".join(ext_resources) + "\n\n"
        content += f'[node name="{ant["id"]}" type="{root_node_type}"]\n\n'
        content += "\n\n".join(nodes) + "\n"

        scene_path.write_text(content)
        return scene_path

    # ── Colony singleton ──────────────────────────────────────────────────────

    def _write_colony_singleton(self, batch_report: dict, target_dir: Path) -> Path:
        """Generate a colony_data.gd singleton that maps ID → path/scene/stats."""

        roster = {}
        for ant in batch_report.get("ants", []):
            ant_dir_str = ant.get("dir", "")
            scene_rel = ant_dir_str.split(self.root.name + "/")[-1] if ant_dir_str else ""
            scene_path_str = f"res://{scene_rel}/{ant['id']}.tscn" if ant_dir_str else ""
            roster[ant["id"]] = {
                "element": ant["element"],
                "role": ant["role"],
                "size": ant["size"],
                "stats": ant["stats"],
                "personality": ant["personality"],
                "scene_path": scene_path_str,
            }

        gd_path = target_dir / "colony_data.gd"
        gd_path.write_text(textwrap.dedent(f"""\
            # Generated by daggr-pipelines godot helper
            # Add as Autoload: Project > AutoLoad > Add > "res://{target_dir.name}/colony_data.gd"
            extends Node

            var colony: Dictionary = {json.dumps(roster, indent=2)}

            func get_ant(id: String) -> Dictionary:
                return colony.get(id, {{}})

            func get_scene(id: String) -> PackedScene:
                var path = colony.get(id, {{}}).get("scene_path", "")
                if path and ResourceLoader.exists(path):
                    return load(path)
                return null

            func get_ants_by_element(element: String) -> Array:
                return colony.keys().filter(func(id): return colony[id].element == element)

            func get_ants_by_role(role: String) -> Array:
                return colony.keys().filter(func(id): return colony[id].role == role)
            """))

        return gd_path


# ── CLI ────────────────────────────────────────────────────────────────────────

def cli():
    parser = argparse.ArgumentParser(description="Import daggr-pipelines batch into Godot")
    parser.add_argument("--project", required=True, help="Godot project root")
    parser.add_argument("--batch-dir", required=True, help="Path to generated batch dir")
    parser.add_argument("--subfolder", default="characters", help="Target folder inside project")
    args = parser.parse_args()

    roster_path = Path(args.batch_dir) / "colony_roster.json"
    if not roster_path.exists():
        print(f"Could not find {roster_path}")
        sys.exit(1)

    helper = GodotProjectHelper(args.project)
    result = helper.import_colony(roster_path, subfolder=args.subfolder)

    print(f"\nImported {result['count']} characters into {args.project}")
    print(f"  Scenes: {len(result['scenes'])}")
    print(f"  Autoload: {result['autoload_path']}")
    print(f"\nNext step: In Godot, Project > AutoLoad > add {result['autoload_path']}")


if __name__ == "__main__":
    cli()
