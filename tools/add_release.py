#!/usr/bin/env python3
"""
Append one release of one plugin to the unified manifest: two entries per
release (jf12 first, then jf10), checksums computed from the real GitHub assets.

    python3 add_release.py <tag> [manifest.unified.json] [--plugin je|jsinjector|tweaks] [--changelog-file FILE] [--force]

All three plugins share the manifest files, so every one of them must use this
(never jprm, which collapses the pairs) when it releases. Needs `gh auth login`.

<tag> must be the 4-component release tag (12.6.0.0). Refuses to touch a
version that is already in the manifest unless --force (the CI-written entries
carry per-target build timestamps and a commit-derived changelog you would
otherwise overwrite). Fails loudly if either asset is missing, so a
half-published release can never produce a half manifest.
"""
import argparse, hashlib, json, os, subprocess, sys, tempfile, urllib.request
from datetime import datetime, timezone
from jfversion import V, require_four, with_banner

from plugins import PLUGINS
from validate_manifest import validate

def md5_of(url):
    h = hashlib.md5()
    with urllib.request.urlopen(url, timeout=120) as r:
        for chunk in iter(lambda: r.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("manifest", nargs="?", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "manifest.unified.json"))
    ap.add_argument("--plugin", choices=sorted(PLUGINS), default="je", help="which plugin's release (default: je)")
    ap.add_argument("--changelog-file", help="markdown to use instead of the GitHub release body")
    ap.add_argument("--force", action="store_true", help="replace entries that already exist for this tag")
    a = ap.parse_args()
    tag = require_four(a.tag, "tag")
    plugin = PLUGINS[a.plugin]
    REPO, GUID, TARGETS = plugin["repo"], plugin["guid"], plugin["targets"]

    with open(a.manifest, encoding="utf-8") as f:
        manifest = json.load(f)
    pkg = next((p for p in manifest if p["guid"] == GUID), None)
    if pkg is None:
        sys.exit(f"{a.manifest} has no package with guid {GUID}")
    existing = [v for v in pkg["versions"] if v["version"] == tag]
    if existing and not a.force:
        sys.exit(f"{tag} already has {len(existing)} entries in {a.manifest}; re-run with --force to replace them")

    try:
        rel = json.loads(subprocess.check_output(
            ["gh", "release", "view", tag, "-R", REPO, "--json", "body,publishedAt,isDraft,assets"], stderr=subprocess.STDOUT))
    except FileNotFoundError:
        sys.exit("the GitHub CLI (gh) is not installed or not on PATH")
    except subprocess.CalledProcessError as e:
        sys.exit(f"gh release view {tag} failed: {e.output.decode(errors='replace').strip()}")
    if rel.get("isDraft") or not rel.get("publishedAt"):
        sys.exit(f"release {tag} is still a draft; publish it first")
    assets = {x["name"] for x in rel["assets"]}
    missing = [n for _, n in TARGETS if n not in assets]
    if missing:
        sys.exit(f"release {tag} is missing assets: {missing}")
    ts = datetime.fromisoformat(rel["publishedAt"].replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    if a.changelog_file:
        with open(a.changelog_file, encoding="utf-8") as f:
            raw = f.read()
    else:
        raw = rel.get("body") or ""
    changelog = raw.replace("\r\n", "\n").strip() or f"Release {tag}"   # with_banner strips any banner already in it

    pkg["versions"] = [v for v in pkg["versions"] if v["version"] != tag]

    new = []
    for abi, asset in TARGETS:
        url = f"https://github.com/{REPO}/releases/download/{tag}/{asset}"
        head = "**Build for Jellyfin 12.**" if abi == "12.0.0.0" else \
               "**Build for Jellyfin 10.11.** On Jellyfin 12 the catalog installs the Jellyfin 12 build of this version automatically."
        new.append({"version": tag, "changelog": with_banner(head, changelog), "targetAbi": abi,
                    "sourceUrl": url, "checksum": md5_of(url), "timestamp": ts})
        print(f"  {tag} abi={abi} {asset} md5={new[-1]['checksum']}")
    pkg["versions"] = sorted(new + pkg["versions"], key=lambda v: (V(v["version"]), V(v["targetAbi"])), reverse=True)
    validate(manifest)  # No replacement if any release is unpaired or incorrectly ordered.

    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(a.manifest) + ".", dir=os.path.dirname(os.path.abspath(a.manifest)))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.chmod(tmp, 0o644)
        os.replace(tmp, a.manifest)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    print("updated", a.manifest)

if __name__ == "__main__":
    main()
