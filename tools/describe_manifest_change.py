#!/usr/bin/env python3
"""
Describe what changed between two manifest.json snapshots, for a sync commit message. For each
package present in both, finds its highest version whose entry is new or changed, and prints one
comma-joined line, e.g. "v4.1.0.0 - Jellyfin Tweaks, v12.7.0.0 - Jellyfin Enhanced" -- a package
whose entries are unchanged (or only reordered) contributes nothing. Prints an empty line if
nothing actually changed.

    python3 describe_manifest_change.py old.json new.json
"""
import json, sys
from jfversion import V


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    old_path, new_path = sys.argv[1], sys.argv[2]
    old = {p["guid"]: p for p in load(old_path)}
    new = {p["guid"]: p for p in load(new_path)}
    lines = []
    for guid, pkg in new.items():
        old_versions = {(v["version"], v["targetAbi"]): v for v in old.get(guid, {}).get("versions", [])}
        new_versions = {(v["version"], v["targetAbi"]): v for v in pkg["versions"]}
        changed = [k for k, v in new_versions.items() if old_versions.get(k) != v]
        if not changed:
            continue
        highest = max(changed, key=lambda k: V(k[0]))
        lines.append(f"v{highest[0]} - {pkg['name']}")
    print(", ".join(lines))


if __name__ == "__main__":
    main()
