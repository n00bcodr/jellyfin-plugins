#!/usr/bin/env python3
"""
Copy the unified manifest to every path that a live URL is served from, in two local checkouts,
after validating ABI ordering and paired builds. Invalid input writes nothing.

    python3 publish_manifest.py --je-repo /path/to/Jellyfin-Enhanced --plugins-repo /path/to/jellyfin-plugins [manifest.unified.json] [--check]

It only writes files. Committing and pushing is yours to do (both repos, back to back), and
`simulate_jellyfin_resolver.py --live` is the check that the URLs actually serve it afterwards.
--check writes nothing and exits 1 if any target differs from the unified file (use it in CI).
"""
import argparse, json, os, sys, tempfile
from plugins import PUBLISH_TARGETS
from validate_manifest import validate

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", nargs="?", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "manifest.unified.json"))
    ap.add_argument("--je-repo", required=True, help="local checkout of n00bcodr/Jellyfin-Enhanced")
    ap.add_argument("--plugins-repo", required=True, help="local checkout of n00bcodr/jellyfin-plugins")
    ap.add_argument("--check", action="store_true", help="only report which targets differ; write nothing")
    a = ap.parse_args()
    roots = {"je": a.je_repo, "plugins": a.plugins_repo}
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
        print("now: commit BOTH repos, push back to back, then run simulate_jellyfin_resolver.py --live")

if __name__ == "__main__":
    main()
