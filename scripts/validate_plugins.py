#!/usr/bin/env python3
"""Fail-loud checks for plugin manifests and skill frontmatter.

No CI in this repo, so this is the test harness. Exit 0 with "PLUGINS OK",
or exit 1 printing one "PLUGINS INVALID: <reason>" per line.
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
REQUIRED_PLUGINS = {"onyx", "pl-tools", "pl-knowledge"}

# Only pl-knowledge is required to omit `version`. onyx already ships
# "version": "0.2.3" and stripping it would change release behaviour for
# colleagues who already installed it — that's out of scope here, so the
# no-version rule is scoped to the plugin this task actually introduces.
NO_VERSION_PLUGINS = {"pl-knowledge"}

errors = []


def load_json(path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        errors.append(f"missing file {path.relative_to(ROOT)}")
    except json.JSONDecodeError as exc:
        errors.append(f"invalid JSON in {path.relative_to(ROOT)}: {exc}")
    return None


def check_marketplace():
    data = load_json(ROOT / ".claude-plugin" / "marketplace.json")
    if data is None:
        return
    listed = {p.get("name") for p in data.get("plugins", [])}
    for name in sorted(REQUIRED_PLUGINS - listed):
        errors.append(f"marketplace.json does not list plugin '{name}'")
    if "Onyx knowledge search" in data.get("description", ""):
        errors.append(
            "marketplace.json description still advertises 'Onyx knowledge search'"
        )


def check_plugin(name):
    data = load_json(ROOT / "plugins" / name / ".claude-plugin" / "plugin.json")
    if data is None:
        return
    if data.get("name") != name:
        errors.append(f"{name}/plugin.json name is {data.get('name')!r}, expected {name!r}")
    if not data.get("description"):
        errors.append(f"{name}/plugin.json has no description")
    if name in NO_VERSION_PLUGINS and "version" in data:
        errors.append(f"{name}/plugin.json must not have a version field (SHA-versioned repo)")


def check_skill_frontmatter(path):
    text = path.read_text()
    rel = path.relative_to(ROOT)
    if not text.startswith("---\n"):
        errors.append(f"{rel} does not open with YAML frontmatter")
        return
    end = text.find("\n---\n", 4)
    if end == -1:
        errors.append(f"{rel} frontmatter is not terminated")
        return
    block = text[4:end]
    for key in ("name:", "description:"):
        if key not in block:
            errors.append(f"{rel} frontmatter missing {key}")


def main():
    check_marketplace()
    for name in sorted(REQUIRED_PLUGINS):
        check_plugin(name)
    for path in sorted((ROOT / "plugins").glob("*/skills/*/SKILL.md")):
        check_skill_frontmatter(path)
    if errors:
        for err in errors:
            print(f"PLUGINS INVALID: {err}")
        return 1
    print("PLUGINS OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
