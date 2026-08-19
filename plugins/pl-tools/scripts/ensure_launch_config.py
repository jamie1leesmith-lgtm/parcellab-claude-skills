#!/usr/bin/env python3
"""Idempotently upsert one configuration entry into a Claude Code launch.json.

Reads the existing file if present and merges by "name" instead of
overwriting the whole file -- a prior overwrite here destroyed an unrelated
entry a different skill had already placed in the same file, with no backup
and no way to recover it (see branded-template Step 8).
"""
import json
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 3:
        print("usage: ensure_launch_config.py <path-to-launch.json> <entry-json>", file=sys.stderr)
        sys.exit(1)

    path = Path(sys.argv[1])
    entry = json.loads(sys.argv[2])
    if "name" not in entry:
        print("entry JSON must include a \"name\" key to merge by", file=sys.stderr)
        sys.exit(1)

    if path.exists():
        config = json.loads(path.read_text())
    else:
        config = {"version": "0.0.1", "configurations": []}

    config.setdefault("configurations", [])
    for i, existing in enumerate(config["configurations"]):
        if existing.get("name") == entry["name"]:
            config["configurations"][i] = entry
            break
    else:
        config["configurations"].append(entry)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + "\n")
    print(f"ok: '{entry['name']}' entry present in {path} ({len(config['configurations'])} total configurations)")


if __name__ == "__main__":
    main()
