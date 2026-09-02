#!/usr/bin/env python3
"""
CI-grade validation of a published manifest file (run on every push to jellyfin-plugins and on
the JE repo's manifest.json):

  1. the invariants Jellyfin's resolver depends on (build_unified_manifest.check)
  2. the anti-jprm tripwire: for each plugin, every version >= its first jf12 release has a
     12.0.0.0 row AND that row precedes the 10.11.0.0 row. jprm collapses pairs to one row; this
     is what catches it.
  3. optional --checksums N: download the N newest assets per plugin and verify MD5.

    python3 validate_manifest.py <manifest.json> [--checksums 2]
"""
import argparse, hashlib, sys, urllib.request, json
from jfversion import V
from plugins import PLUGINS
from build_unified_manifest import check

def md5_of(url):
    h = hashlib.md5()
    with urllib.request.urlopen(url, timeout=120) as r:
        for chunk in iter(lambda: r.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()

def tripwire(manifest):
    bad = []
    by_guid = {p["guid"]: p for p in manifest}
    for key, plugin in PLUGINS.items():
        pkg = by_guid.get(plugin["guid"])
        if pkg is None:
            bad.append(f"{plugin['name']}: package missing from manifest"); continue
        if not pkg["versions"]:
            bad.append(f"{plugin['name']}: package has no versions"); continue
        rows = {}
        for i, v in enumerate(pkg["versions"]):
            rows.setdefault(v["version"], {})[v["targetAbi"]] = i
        for version, abis in rows.items():
            if V(version) < V(plugin["first_jf12"]):
                continue
            # jprm collapses a pair to ONE row; either survivor is wrong
            for abi in ("12.0.0.0", "10.11.0.0"):
                if abi not in abis:
                    bad.append(f"{plugin['name']} {version}: no {abi} row (jprm collapsed it?)")
            if "12.0.0.0" in abis and "10.11.0.0" in abis and abis["12.0.0.0"] > abis["10.11.0.0"]:
                bad.append(f"{plugin['name']} {version}: 12.0.0.0 row listed AFTER the 10.11.0.0 row")
    return bad

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--checksums", type=int, default=0, metavar="N", help="verify MD5 of the N newest assets per plugin")
    a = ap.parse_args()
    with open(a.manifest, encoding="utf-8") as f:
        manifest = json.load(f)
    check(manifest)                      # exits 1 with a message on failure
    bad = tripwire(manifest)
    if a.checksums:
        by_guid = {p["guid"]: p for p in manifest}
        for plugin in PLUGINS.values():
            pkg = by_guid.get(plugin["guid"])
            if pkg is None:
                continue                      # already reported by the tripwire
            for v in pkg["versions"][: a.checksums]:
                actual = md5_of(v["sourceUrl"])
                if actual != v["checksum"].upper():
                    bad.append(f"{plugin['name']} {v['version']}/{v['targetAbi']}: checksum {v['checksum']} but asset is {actual}")
                else:
                    print(f"  md5 ok  {plugin['name']} {v['version']}/{v['targetAbi']}")
    if bad:
        sys.exit("validation failed:\n  " + "\n  ".join(bad))
    print(f"{a.manifest}: invariants ok, every post-jf12 version is paired and ordered")

if __name__ == "__main__":
    main()
