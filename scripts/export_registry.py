#!/usr/bin/env python3
"""
Export the Space registry to JSON.

Usage:
    python export_registry.py                     # Print to stdout
    python export_registry.py > references/registry.json
    python export_registry.py --file out.json     # Save to file
    python export_registry.py --category image-gen --file filtered.json

This produces a machine-readable JSON snapshot of the registry defined inline
in check_spaces.py. Hermes Agent sessions, cron jobs, or other tooling can
consume this without having to run the full check_spaces.py liveness check.

Fields match SpaceEntry dataclass in check_spaces.py.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_spaces import REGISTRY, Category


def export(registry, category_filter: str | None = None) -> list[dict]:
    output = []
    for entry in registry:
        if category_filter and entry.category != category_filter:
            continue
        output.append({
            "space_id": entry.space_id,
            "api_name": entry.api_name,
            "category": entry.category.value if hasattr(entry.category, "value") else str(entry.category),
            "task": entry.task,
            "license": entry.license.value if hasattr(entry.license, "value") else str(entry.license),
            "commercial_ok": entry.commercial_ok,
            "compute": entry.compute.value if hasattr(entry.compute, "value") else str(entry.compute),
            "speed": entry.speed,
            "inputs": entry.inputs,
            "outputs": entry.outputs,
            "notes": entry.notes,
        })
    return output


def main():
    parser = argparse.ArgumentParser(description="Export Space registry to JSON")
    parser.add_argument("--file", "-f", help="Output file path (default: stdout)")
    parser.add_argument("--category", "-c", help="Filter by category")
    parser.add_argument("--indent", type=int, default=2, help="JSON indent level")
    args = parser.parse_args()

    data = export(REGISTRY, args.category)

    payload = {
        "schema": "daggr-pipelines/space-registry/v1",
        "generated_from": "scripts/check_spaces.py",
        "count": len(data),
        "spaces": data,
    }

    text = json.dumps(payload, indent=args.indent)

    if args.file:
        with open(args.file, "w") as f:
            f.write(text + "\n")
        print(f"Wrote {len(data)} entries to {args.file}")
    else:
        print(text)


if __name__ == "__main__":
    main()
