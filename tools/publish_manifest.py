#!/usr/bin/env python3
"""
Copy the unified manifest to every path that a live URL is served from, after validating ABI
ordering and paired builds. Invalid input writes nothing. Every plugin's own repo gets the full
3-plugin catalog, not just its own package -- every checkout passed ends up byte-identical.

--plugins-repo (n00bcodr/jellyfin-plugins) is always required; --je-repo, --jsinjector-repo and
--tweaks-repo are each optional -- pass whichever local checkouts you actually have. build.sh only
passes --plugins-repo, to mirror this repo's own root/12/10.11/10.10 copies; a full manual release
(or .github/workflows/sync-downstream.yml, which checks out all four) passes every flag to reach
every repo in one run:

    python3 publish_manifest.py --je-repo /path/to/Jellyfin-Enhanced \
        --jsinjector-repo /path/to/Jellyfin-JavaScript-Injector \
        --tweaks-repo /path/to/JellyfinTweaks \
        --plugins-repo /path/to/jellyfin-plugins [manifest.unified.json] [--check]

It only writes files. Committing and pushing is yours to do (every repo passed, back to back), and
`simulate_jellyfin_resolver.py --live` is the check that the URLs actually serve it afterwards.
--check writes nothing and exits 1 if any target differs from the unified file (use it in CI).
"""
import argparse, json, os, sys, tempfile
from plugins import PUBLISH_TARGETS
from validate_manifest import validate

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", nargs="?", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "manifest.unified.json"))
    ap.add_argument("--je-repo", help="local checkout of n00bcodr/Jellyfin-Enhanced")
    ap.add_argument("--jsinjector-repo", help="local checkout of n00bcodr/Jellyfin-JavaScript-Injector")
    ap.add_argument("--tweaks-repo", help="local checkout of n00bcodr/JellyfinTweaks")
    ap.add_argument("--plugins-repo", required=True, help="local checkout of n00bcodr/jellyfin-plugins")
    ap.add_argument("--check", action="store_true", help="only report which targets differ; write nothing")
    a = ap.parse_args()
    roots = {"je": a.je_repo, "jsinjector": a.jsinjector_repo, "tweaks": a.tweaks_repo, "plugins": a.plugins_repo}
    roots = {k: v for k, v in roots.items() if v}    # only the repos actually passed
    for r in roots.values():
        if not os.path.exists(os.path.join(r, ".git")):      # a file in a worktree, a dir otherwise
            sys.exit(f"{r} is not a git checkout")
    # Read once: validation and every copy use the same bytes, even if the source
    # is edited concurrently. Validate in --check mode as well as write mode.
    with open(a.manifest, "rb") as f:
        payload = f.read()
    validate(json.loads(payload))
    stale = []
    for which, rel in PUBLISH_TARGETS:
        if which not in roots:
            continue
        dest = os.path.join(roots[which], rel)
        same = False
        if os.path.exists(dest):
            with open(dest, "rb") as f:
                same = f.read() == payload
        if same:
            print(f"  same    {dest}")
            continue
        if a.check:
            print(f"  DIFFERS {dest}" if os.path.exists(dest) else f"  MISSING {dest}")
            stale.append(dest)
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".manifest-", dir=os.path.dirname(dest))
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(payload)
            os.chmod(temporary, 0o644)
            os.replace(temporary, dest)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        print(f"  wrote   {dest}")
    if a.check and stale:
        sys.exit(f"{len(stale)} target(s) do not match the unified manifest")
    if not a.check:
        print("now: commit every repo passed above, push back to back, then run simulate_jellyfin_resolver.py --live")

if __name__ == "__main__":
    main()
