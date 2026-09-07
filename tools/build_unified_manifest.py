#!/usr/bin/env python3
"""
Build ONE Jellyfin plugin manifest that serves every Jellyfin line the project
has ever shipped for (10.9/10.10, 10.11.x, 12.x).

Inputs : the four manifests that are live today (or local copies), most curated first:
           12      jellyfin-plugins/main/12/manifest.json
           10.11   jellyfin-plugins/main/10.11/manifest.json
           legacy  Jellyfin-Enhanced/main/manifest.json        (10.10.7.0 + 10.11.0.0 entries)
           10.10   jellyfin-plugins/main/10.10/manifest.json   (10.10.7.0 + older 10.9 entries for the other plugins)
Output : manifest.unified.json

Rule: keep every distinct (guid, version, targetAbi) entry once; within a
package sort by version DESC, then targetAbi DESC. Jellyfin's ABI filter
(`appVersion >= targetAbi`, lower bound only) then does the "dynamic" part on
the server:
  * a 10.10.7 host drops the 10.11.0.0 and 12.0.0.0 entries  -> 10.10.7 zips
  * a 10.11.x host drops the 12.0.0.0 entries                 -> jf10 zips
  * a 12.x host keeps everything; every resolver path is a stable descending
    sort that returns the first entry among equal versions   -> jf12 zips
Same file at every URL. No domain, no server-side logic.

Known residual (inherent to the lower-bound-only filter): versions that only
ever had a jf10 build stay listed, so an admin on Jellyfin 12 who deliberately
picks an old revision from the catalog gets the jf10 zip. The default Install
button and auto-update never do. Those entries get a changelog banner saying so
(disable with --no-annotate); simulate_jellyfin_resolver.py counts them.

Conflicts: when two sources list the same (version, targetAbi) with different
checksums (happens: 10.3.0.0 in the 10.10 file is stale), the asset is
downloaded and the entry whose MD5 matches wins. Neither matching is fatal.

NOTE: do not regenerate this file with jprm; jprm dedupes on version string and
would collapse each pair to one entry.
"""
import hashlib, json, os, re, sys, tempfile, urllib.request
from collections import OrderedDict
from jfversion import V, FOUR, with_banner

SOURCES = [
    ("12",     "https://raw.githubusercontent.com/n00bcodr/jellyfin-plugins/main/12/manifest.json"),
    ("10.11",  "https://raw.githubusercontent.com/n00bcodr/jellyfin-plugins/main/10.11/manifest.json"),
    ("legacy", "https://raw.githubusercontent.com/n00bcodr/Jellyfin-Enhanced/main/manifest.json"),
    ("10.10",  "https://raw.githubusercontent.com/n00bcodr/jellyfin-plugins/main/10.10/manifest.json"),
]
# targetAbi -> zip filename suffix the entry must point at. Anything else is a typo.
ABI_SUFFIX = {"12.0.0.0": "_12.0.0.zip", "10.11.0.0": "_10.11.0.zip", "10.10.7.0": "_10.10.7.zip",
              "10.9.9.0": "_10.9.9.zip", "10.9.4.0": "_10.9.4.zip"}
LINE_NAME = {"12.0.0.0": "Jellyfin 12", "10.11.0.0": "Jellyfin 10.11", "10.10.7.0": "Jellyfin 10.10",
             "10.9.9.0": "Jellyfin 10.9", "10.9.4.0": "Jellyfin 10.9"}

def load(src):
    if src.startswith("http"):
        with urllib.request.urlopen(src, timeout=30) as r:
            return json.load(r)
    with open(src, encoding="utf-8") as f:
        return json.load(f)

def md5_of(url):
    h = hashlib.md5()
    with urllib.request.urlopen(url, timeout=120) as r:
        for chunk in iter(lambda: r.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()

def write_atomic(path, obj):
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", dir=os.path.dirname(os.path.abspath(path)))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.chmod(tmp, 0o644)          # mkstemp creates 0600; the manifest is a public file
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise

def same_payload(a, b):
    return a["checksum"].upper() == b["checksum"].upper() and a["sourceUrl"] == b["sourceUrl"]

def resolve_conflict(name, key, first, second, first_label, second_label):
    """Two sources disagree on checksum/sourceUrl for one (version, abi). Ask the asset."""
    for label, e in ((first_label, first), (second_label, second)):
        try:
            actual = md5_of(e["sourceUrl"])
        except Exception as ex:  # noqa: BLE001
            print(f"WARN {name} {key}: cannot download {e['sourceUrl']}: {ex}", file=sys.stderr)
            continue
        if actual == e["checksum"].upper():
            print(f"INFO {name} {key}: sources disagree; {label} entry matches the asset (md5 {actual}), keeping it", file=sys.stderr)
            return e
    sys.exit(f"{name} {key}: no source's checksum matches the actual asset; fix the manifests first")

def merge(manifests, annotate=True, only_paired=False):
    by_guid = OrderedDict()
    for label, m in manifests:
        for pkg in m:
            e = by_guid.setdefault(pkg["guid"], {"meta": pkg, "entries": OrderedDict(), "labels": {}})
            for v in pkg["versions"]:
                for field in ("version", "targetAbi"):
                    try:
                        V(v.get(field) or "")
                    except ValueError as ex:
                        sys.exit(f"{label} manifest, {pkg['name']} {v.get('version')!r}: bad {field}: {ex}")
                key = (v["version"], v["targetAbi"])
                if key in e["entries"]:
                    if not same_payload(e["entries"][key], v):
                        e["entries"][key] = resolve_conflict(pkg["name"], key, e["entries"][key], v, e["labels"][key], label)
                        e["labels"][key] = label
                    continue                    # first-seen wins on identical payloads
                e["entries"][key] = dict(v)
                e["labels"][key] = label

    unified = []
    for guid, e in by_guid.items():
        entries = sorted(e["entries"].values(), key=lambda v: (V(v["version"]), V(v["targetAbi"])), reverse=True)
        abis_per_version = {}
        for v in entries:
            abis_per_version.setdefault(v["version"], []).append(v["targetAbi"])
        if only_paired:
            # Drop every version that has no Jellyfin 12 build. 12 hosts can then never pick a
            # jf10-only build; 10.11 hosts lose catalog rollback to anything older than the
            # plugin's first jf12 release (JE 12.0.0.0, JS Injector / Tweaks 4.0.0.0).
            entries = [v for v in entries if any(V(a) >= V("12.0.0.0") for a in abis_per_version[v["version"]])]
        if annotate:
            for v in entries:
                line = LINE_NAME.get(v["targetAbi"], f"targetAbi {v['targetAbi']}")
                paired_with_12 = any(V(a) >= V("12.0.0.0") for a in abis_per_version[v["version"]])
                if V(v["targetAbi"]) >= V("12.0.0.0"):
                    head = f"**Build for {line}.**"
                elif paired_with_12:
                    head = f"**Build for {line}.** On Jellyfin 12 the catalog installs the Jellyfin 12 build of this version automatically."
                else:
                    head = f"**Build for {line} only. Not for Jellyfin 12.**"
                v["changelog"] = with_banner(head, v.get("changelog"))
        pkg = OrderedDict((k, val) for k, val in e["meta"].items() if k != "versions")
        pkg["versions"] = entries
        unified.append(pkg)
    return unified

# The per-line naming used since the 10.x releases (_12.0.0.zip, _10.11.0.zip, _10.10.7.zip).
# Deliberately 3-component: the 5.x releases used 4-component *plugin*-version suffixes (_5.0.0.0.zip)
# that must not be read as an ABI.
SUFFIXED = re.compile(r"_[0-9]+\.[0-9]+\.[0-9]+\.zip$")

def check(unified):
    """Invariants Jellyfin's resolver depends on. Exit 1 instead of assert so -O can't strip it.
    Pre-existing oddities in old history (3-component versions, unsuffixed zip names) are warnings;
    add_release.py enforces the strict form for everything new."""
    bad, warn = [], []
    for pkg in unified:
        vs = pkg["versions"]
        for v in vs:
            for field in ("version", "targetAbi"):
                if not FOUR.match(v[field]):
                    warn.append(f"{pkg['name']} {v['version']}: {field} {v[field]!r} is not 4-component (PopulateManifest compares strings)")
            suffix = ABI_SUFFIX.get(v["targetAbi"])
            zipn = v["sourceUrl"].rsplit("/", 1)[-1]
            if suffix is None:
                bad.append(f"{pkg['name']} {v['version']}: unknown targetAbi {v['targetAbi']}")
            elif SUFFIXED.search(zipn) and not zipn.endswith(suffix):
                bad.append(f"{pkg['name']} {v['version']}: targetAbi {v['targetAbi']} but sourceUrl {zipn}")
        for a, b in zip(vs, vs[1:]):
            ka, kb = (V(a["version"]), V(a["targetAbi"])), (V(b["version"]), V(b["targetAbi"]))
            if ka < kb:
                bad.append(f"{pkg['name']}: {a['version']}/{a['targetAbi']} listed before {b['version']}/{b['targetAbi']}")
            if ka == kb:
                bad.append(f"{pkg['name']}: duplicate entry {a['version']}/{a['targetAbi']}")
    unsuffixed = sum(1 for pkg in unified for v in pkg["versions"] if not SUFFIXED.search(v["sourceUrl"].rsplit("/", 1)[-1]))
    if unsuffixed:
        warn.append(f"{unsuffixed} entries use pre-10.x zip names without an ABI suffix; their targetAbi cannot be cross-checked against the file name")
    for w in warn:
        print("WARN " + w, file=sys.stderr)
    if bad:
        sys.exit("manifest invariant violated:\n  " + "\n  ".join(bad))

def report(unified):
    for pkg in unified:
        by_abi, versions = {}, {}
        for v in pkg["versions"]:
            by_abi[v["targetAbi"]] = by_abi.get(v["targetAbi"], 0) + 1
            versions.setdefault(v["version"], set()).add(v["targetAbi"])
        unpaired = sum(1 for abis in versions.values() if not any(V(a) >= V("12.0.0.0") for a in abis))
        print(f"{pkg['name']:<22} {len(pkg['versions']):>3} entries  "
              + ", ".join(f"{n} @ {abi}" for abi, n in sorted(by_abi.items(), key=lambda kv: V(kv[0]), reverse=True))
              + f"  | {len(versions)} versions, {unpaired} with no Jellyfin 12 build (still installable on 12 by explicit choice)")

def main(argv):
    usage = "usage: build_unified_manifest.py [--no-annotate] [--only-paired] [out.json] [12 10.11 legacy 10.10]  (paths or URLs, all four or none)"
    flags = {a for a in argv[1:] if a.startswith("-")}
    args = [a for a in argv[1:] if not a.startswith("-")]
    if flags & {"-h", "--help"}:
        print(usage); print(__doc__); return
    unknown = flags - {"--no-annotate", "--only-paired"}
    if unknown or len(args) not in (0, 1, 5):
        sys.exit(usage)
    annotate = "--no-annotate" not in flags
    out = args[0] if args else os.path.join(os.path.dirname(os.path.abspath(__file__)), "manifest.unified.json")
    srcs = args[1:5] if len(args) == 5 else [u for _, u in SOURCES]
    manifests = [(label, load(src)) for (label, _), src in zip(SOURCES, srcs)]
    unified = merge(manifests, annotate=annotate, only_paired="--only-paired" in flags)
    check(unified)
    write_atomic(out, unified)
    report(unified)
    print("wrote", out)

if __name__ == "__main__":
    main(sys.argv)
