#!/usr/bin/env python3
"""
Faithful re-implementation of the parts of Jellyfin that decide WHICH manifest
entry gets installed, so a manifest layout can be tested without a server:

  Emby.Server.Implementations/Updates/InstallationManager.cs (release-10.11.z and master/12 are identical here)
    GetPackages()             - drops entries whose targetAbi > ApplicationVersion (lower bound ONLY)
    GetAvailablePackages()    - repos in configured order, same-GUID packages merged with MergeSortedList (source wins ties)
    GetCompatibleVersions()   - abi filter, optional specific/min version, OrderByDescending (STABLE sort)
    GetAvailablePluginUpdates - GetCompatibleVersions(minVersion=installed).First(v > installed)
  Jellyfin.Api/Controllers/PackageController.cs
    POST /Packages/Installed/{name}?version=&repositoryUrl=  -> GetCompatibleVersions(specificVersion).FirstOrDefault()
  jellyfin-web (10.11 and 12 ship the same page): "Install" uses packageInfo.versions[0]; a revision row posts its version string.

ApplicationVersion is the *assembly* version: 12.0.0-rc1 and 12.0.0 are both 12.0.0.0 (SharedVersion.cs).

Exit status is 0 only if (1) every FIX layout resolves every host to the right zip for install-latest,
install-by-version AND the 12.6 auto-update of a mis-installed server, and (2) every TODAY layout still
reproduces the failure it is listed for (the premise of the proposal; if Jellyfin changes, this trips).

The TODAY layouts read the pre-rollout snapshots in fixtures/, not the live URLs, so the script keeps
working after the rollout overwrites those URLs. `--live` instead fetches every URL and checks that
each one now serves the unified manifest (run it after publishing).
"""
import json, copy, os, sys, urllib.request
from jfversion import V

JE_GUID = "f69e946a-4b3c-4e9a-8f0a-8d7c1b2c4d9b"
URL_LEGACY = "https://raw.githubusercontent.com/n00bcodr/Jellyfin-Enhanced/main/manifest.json"
URL_10 = "https://raw.githubusercontent.com/n00bcodr/jellyfin-plugins/main/10.11/manifest.json"
URL_12 = "https://raw.githubusercontent.com/n00bcodr/jellyfin-plugins/main/12/manifest.json"
URL_1010 = "https://raw.githubusercontent.com/n00bcodr/jellyfin-plugins/main/10.10/manifest.json"
URL_NEW = "https://raw.githubusercontent.com/n00bcodr/jellyfin-plugins/main/manifest.json"
ABI12_SUFFIX = "_12.0.0.zip"
ZIP = {"12.0.0.0": "Jellyfin.Plugin.JellyfinEnhanced_12.0.0.zip",
       "10.11.0.0": "Jellyfin.Plugin.JellyfinEnhanced_10.11.0.zip",
       "10.10.7.0": "Jellyfin.Plugin.JellyfinEnhanced_10.10.7.zip"}
HERE = os.path.dirname(os.path.abspath(__file__))

FIXTURES = {URL_LEGACY: "legacy", URL_10: "10.11", URL_12: "12", URL_1010: "10.10"}

def fetch(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)

def fixture(url):
    with open(os.path.join(HERE, "fixtures", FIXTURES[url] + ".manifest.json"), encoding="utf-8") as f:
        return json.load(f)

def check_live(unified):
    """After rollout: every URL (old and new) must serve the unified manifest: same packages, same
    rows, in the SAME ORDER (order is the invariant the whole scheme rests on). Timestamps and
    changelogs are ignored; checksum + sourceUrl are what Jellyfin installs."""
    def shape(manifest):
        # a LIST of (guid, rows), not a dict: a duplicated package object must not collapse into the other
        return [(p["guid"], [(v["version"], v["targetAbi"], v["checksum"].upper(), v["sourceUrl"]) for v in p["versions"]]) for p in manifest]
    names = {p["guid"]: p["name"] for p in unified}
    def label(guid):
        return f"{names.get(guid, '?')} ({guid[:8]})"
    want = shape(unified)
    ok = True
    for url in [URL_LEGACY, URL_10, URL_12, URL_1010, URL_NEW]:
        try:
            got = shape(fetch(url))
        except Exception as ex:  # noqa: BLE001
            hint = "  (expected until the canonical file is first published)" if url == URL_NEW and "404" in str(ex) else ""
            print(f"  {url}: FETCH FAILED ({ex}){hint}"); ok = False
            getattr(ex, "close", lambda: None)()
            continue
        if got == want:
            print(f"  {url}: OK  serves the unified manifest")
            continue
        ok = False
        got_guids = [g for g, _ in got]
        if len(got_guids) != len(set(got_guids)):
            print(f"  {url}: BAD duplicated package object(s): {[label(g) for g in set(got_guids) if got_guids.count(g) > 1]}")
        gd = dict(got)
        for guid, rows in want:
            g = gd.get(guid)
            if g is None:
                print(f"  {url}: BAD package {label(guid)} missing"); continue
            if set(g) != set(rows):
                print(f"  {url}: BAD package {label(guid)}: missing {len(set(rows) - set(g))} / extra {len(set(g) - set(rows))} rows")
            elif g != rows:
                print(f"  {url}: BAD package {label(guid)}: same rows, different ORDER")
        for guid in set(got_guids) - {g for g, _ in want}:
            print(f"  {url}: BAD unexpected package {label(guid)}")
        if [g for g, _ in got] != [g for g, _ in want] and set(got_guids) == {g for g, _ in want} and len(got_guids) == len(want):
            print(f"  {url}: BAD packages in a different order")
    return ok

def abi_of(v):
    """GetPackages: TryParse failure -> 0.0.0.1. GetAvailablePackages: TryParse failure -> entry kept. Same outcome: compatible."""
    try:
        return V(v.get("targetAbi") or "")
    except ValueError:
        return (0, 0, 0, 1)

# ---- InstallationManager --------------------------------------------------
def get_packages(app_ver, repo_name, repo_url, manifest, filter_incompatible=True):
    packages = copy.deepcopy(manifest)
    for entry in packages:
        for a in range(len(entry["versions"]) - 1, -1, -1):
            ver = entry["versions"][a]
            ver["repositoryName"], ver["repositoryUrl"] = repo_name, repo_url
            if filter_incompatible and app_ver < abi_of(ver):
                del entry["versions"][a]
    return packages

def merge_sorted_list(source, dest):
    # verbatim port of InstallationManager.MergeSortedList
    s_len = len(source) - 1
    d_len = len(dest)
    s = d = 0
    src_v = V(source[0]["version"]); dst_v = V(dest[0]["version"])
    while d < d_len:
        if src_v >= dst_v:
            if s < s_len:
                s += 1; src_v = V(source[s]["version"])
            else:
                while d < d_len:
                    source.append(dest[d]); d += 1
                break
        else:
            source.insert(s, dest[d]); s += 1; d += 1
            if d >= d_len:
                break
            s_len += 1
            dst_v = V(dest[d]["version"])

def get_available_packages(app_ver, repos):
    result = []
    for name, url, manifest in repos:
        for package in get_packages(app_ver, name, url, manifest, True):
            existing = next((p for p in result if p["guid"] == package["guid"]), None)
            for i in range(len(package["versions"]) - 1, -1, -1):
                if app_ver < abi_of(package["versions"][i]):
                    del package["versions"][i]
            if not package["versions"]:
                continue
            if existing is not None:
                merge_sorted_list(existing["versions"], package["versions"])
            else:
                result.append(package)
    return result

def get_compatible_versions(app_ver, packages, guid, min_version=None, specific_version=None):
    pkgs = [p for p in packages if p["guid"] == guid]
    if specific_version is not None:
        pkgs = [p for p in pkgs if any(V(v["version"]) == specific_version for v in p["versions"])]
    package = pkgs[0] if pkgs else None
    if package is None:
        return []
    # GetCompatibleVersions: IsNullOrEmpty(targetAbi) -> compatible; otherwise Version.Parse (throws on garbage, so do we)
    avail = [v for v in package["versions"] if not v.get("targetAbi") or V(v["targetAbi"]) <= app_ver]
    if specific_version is not None:
        avail = [v for v in avail if V(v["version"]) == specific_version]
    elif min_version is not None:
        avail = [v for v in avail if V(v["version"]) >= min_version]
    return sorted(avail, key=lambda v: V(v["version"]), reverse=True)   # Python sort is stable, like LINQ

# ---- PackageController / web ------------------------------------------------
def web_install_latest(app_ver, repos, guid=JE_GUID):
    packages = get_available_packages(app_ver, repos)
    pkg = next((p for p in packages if p["guid"] == guid), None)
    if not pkg:
        return None
    chosen = pkg["versions"][0]
    return api_install(app_ver, repos, chosen["version"], chosen["repositoryUrl"], guid)

def api_install(app_ver, repos, version, repository_url=None, guid=JE_GUID):
    packages = get_available_packages(app_ver, repos)
    if repository_url:
        packages = [p for p in packages if any(v["repositoryUrl"].lower() == repository_url.lower() for v in p["versions"])]
    res = get_compatible_versions(app_ver, packages, guid, specific_version=V(version) if version else None)
    return res[0] if res else None

def auto_update(app_ver, repos, installed):
    packages = get_available_packages(app_ver, repos)
    res = get_compatible_versions(app_ver, packages, JE_GUID, min_version=installed)
    return next((v for v in res if V(v["version"]) > installed), None)

def zipname(v):
    return "-" if v is None else f"{v['version']} -> {v['sourceUrl'].rsplit('/', 1)[-1]}"

# ---- scenarios ---------------------------------------------------------------
def with_next_release(manifest, kind, version="12.6.0.0"):
    """Prepend a fake next release in the shape that manifest would carry (same zips)."""
    abis = {"legacy": ["10.11.0.0"], "10.11": ["10.11.0.0"], "12": ["12.0.0.0"], "10.10": [], "unified": ["12.0.0.0", "10.11.0.0"]}[kind]
    m = copy.deepcopy(manifest)
    for p in m:
        if p["guid"] != JE_GUID:
            continue
        new = []
        for abi in abis:
            e = copy.deepcopy(p["versions"][0])
            e.update(version=version, targetAbi=abi, checksum="fake-" + abi,
                     sourceUrl=e["sourceUrl"].rsplit("/", 1)[0] + "/" + ZIP[abi])
            new.append(e)
        p["versions"] = new + p["versions"]
    return m

def expected_zip(app_ver):
    if app_ver >= V("12.0.0.0"):
        return ZIP["12.0.0.0"]
    if app_ver >= V("10.11.0.0"):
        return ZIP["10.11.0.0"]
    return ZIP["10.10.7.0"]

def run():
    args = sys.argv[1:]
    flags = {a for a in args if a.startswith("-")}
    paths = [a for a in args if not a.startswith("-")]
    usage = ("usage: simulate_jellyfin_resolver.py [manifest.json] [--live]\n"
             "  default: prove the layouts against fixtures/ and the given (or ./manifest.unified.json) unified file\n"
             "  --live : fetch the five URLs and check each serves that unified file, in order")
    if flags & {"-h", "--help"}:
        print(usage); return 0
    if flags - {"--live"} or len(paths) > 1:
        sys.exit(usage)
    with open(paths[0] if paths else os.path.join(HERE, "manifest.unified.json"), encoding="utf-8") as f:
        unified = json.load(f)
    if "--live" in flags:
        print("=== live: what each URL serves right now")
        ok = check_live(unified)
        print("\nevery URL serves the unified manifest:", ok)
        return 0 if ok else 1
    mlegacy, m10, m12, m1010 = fixture(URL_LEGACY), fixture(URL_10), fixture(URL_12), fixture(URL_1010)
    # Row ids: "<host>:latest", "<host>:12.5.0.0", "victim:@12.6". Each layout lists exactly the rows
    # that are EXPECTED to resolve to the wrong zip (or nothing). A layout passes only if the set of
    # actually-bad rows equals that set, so a regression inside a TODAY layout cannot hide behind
    # "it was supposed to fail anyway".
    H107, H1011, H12, H13 = "10.10.7", "10.11.11", "12.0.0", "13.0.0"
    jf12_rows = {f"{H12}:latest", f"{H12}:12.5.0.0", f"{H13}:latest", f"{H13}:12.5.0.0", "victim:@12.6"}
    layouts = [
        ("TODAY  legacy JE-repo manifest.json only",
            jf12_rows,
            [("JE legacy", URL_LEGACY, mlegacy, "legacy")]),
        ("TODAY  10.11 manifest only (the common mistake)",
            jf12_rows | {f"{H107}:latest"},
            [("JE 10.11", URL_10, m10, "10.11")]),
        ("TODAY  12 manifest only",
            {f"{H107}:latest", f"{H1011}:latest", f"{H1011}:12.5.0.0"},
            [("JE 12", URL_12, m12, "12")]),
        ("TODAY  10.10 manifest only (frozen line)",
            {f"{H1011}:latest", f"{H1011}:12.5.0.0"} | jf12_rows,
            [("JE 10.10", URL_1010, m1010, "10.10")]),
        ("TODAY  both 10.11 + 12 manifests, 10.11 added first",
            jf12_rows | {f"{H107}:latest"},
            [("JE 10.11", URL_10, m10, "10.11"), ("JE 12", URL_12, m12, "12")]),
        ("TODAY  both 10.11 + 12 manifests, 12 added first",
            {f"{H107}:latest"},
            [("JE 12", URL_12, m12, "12"), ("JE 10.11", URL_10, m10, "10.11")]),
        ("BAD    transition: stale legacy first + new unified URL",
            jf12_rows,
            [("JE legacy", URL_LEGACY, mlegacy, "legacy"), ("JE", URL_NEW, unified, "unified")]),
        ("FIX    unified manifest at ONE url",
            set(),
            [("JE", URL_NEW, unified, "unified")]),
        ("FIX    unified served at legacy url + new url",
            set(),
            [("JE legacy", URL_LEGACY, unified, "unified"), ("JE", URL_NEW, unified, "unified")]),
        ("FIX    unified served at both old jellyfin-plugins urls",
            set(),
            [("JE 10.11", URL_10, unified, "unified"), ("JE 12", URL_12, unified, "unified")]),
    ]
    hosts = [(H107, V("10.10.7.0")), (H1011, V("10.11.11.0")), (H12, V("12.0.0.0")), (H13, V("13.0.0.0"))]
    all_ok = True
    for label, expected_bad, repos3 in layouts:
        repos = [(n, u, m) for n, u, m, _ in repos3]
        print(f"\n=== {label}")
        actual_bad = set()
        def judge(row, v, want, version=None):
            ok = v is not None and v["sourceUrl"].endswith(want) and (version is None or v["version"] == version)
            if not ok:
                actual_bad.add(row)
            return "OK " if ok else "BAD"
        for hname, hv in hosts:
            want = expected_zip(hv)
            latest = web_install_latest(hv, repos)
            # the 10.10.7 line stopped at plugin 10.11.1.0; assert the exact version there
            m_latest = judge(f"{hname}:latest", latest, want, "10.11.1.0" if hv < V("10.11.0.0") else None)
            print(f"  Jellyfin {hname:<24} Install(latest):   {m_latest} {zipname(latest)}")
            if hv >= V("10.11.0.0"):
                by_ver = api_install(hv, repos, "12.5.0.0")
                m_by = judge(f"{hname}:12.5.0.0", by_ver, want)
                print(f"  {'':<32} Install(12.5.0.0): {m_by} {zipname(by_ver)}")
        # the 3 victims: jf10 build 12.5.0.0 running on Jellyfin 12; what does the daily PluginUpdateTask do?
        hv = V("12.0.0.0")
        upd_now = auto_update(hv, repos, V("12.5.0.0"))
        nxt = [(n, u, with_next_release(m, kind)) for n, u, m, kind in repos3]
        upd_next = auto_update(hv, nxt, V("12.5.0.0"))
        m_heal = judge("victim:@12.6", upd_next, ZIP["12.0.0.0"], "12.6.0.0")
        print(f"  {'victim: jf10 12.5.0.0 on JF12':<32} auto-update today:  {zipname(upd_now)}")
        print(f"  {'':<32} auto-update @12.6:  {m_heal} {zipname(upd_next)}")
        if actual_bad == expected_bad:
            print(f"  => {'PASS' if not actual_bad else 'FAILS'} exactly as documented")
        else:
            all_ok = False
            print(f"  => UNEXPECTED: bad rows {sorted(actual_bad)} != documented {sorted(expected_bad)}")
    # ---- exhaustive: on a 12 host, click every revision row of the unified catalog ----------------
    # Versions that only ever had a jf10/10.10.7 build resolve to that build on 12 by construction
    # (lower-bound ABI filter). This is the documented residual; the count must match the manifest.
    hv = V("12.0.0.0")
    repos = [("JE", URL_NEW, unified)]
    for pkg in get_available_packages(hv, repos):
        guid = pkg["guid"]
        paired = {v["version"] for v in pkg["versions"] if V(v["targetAbi"]) >= V("12.0.0.0")}
        seen, right, wrong, mismatched = set(), 0, 0, []
        for row in pkg["versions"]:
            if row["version"] in seen:
                continue
            seen.add(row["version"])
            got = api_install(hv, repos, row["version"], row["repositoryUrl"], guid)
            got_jf12 = got is not None and got["targetAbi"] == "12.0.0.0" and got["sourceUrl"].endswith(ABI12_SUFFIX)
            # per version: a version WITH a jf12 row must resolve to it, one WITHOUT must not claim to
            if got_jf12 != (row["version"] in paired):
                mismatched.append(row["version"])
            right += got_jf12
            wrong += not got_jf12
        unpaired = len(seen) - len(paired)
        print(f"\n=== exhaustive: Jellyfin 12 host installing each of the {len(seen)} distinct versions of {pkg['name']} "
              f"({len(pkg['versions'])} catalog rows)")
        print(f"  {right} resolve to the Jellyfin 12 build (every version that has one), "
              f"{wrong} resolve to an older build (versions with no Jellyfin 12 build: {unpaired})")
        if mismatched:
            print(f"  => UNEXPECTED: {mismatched} resolved against their pairing")
        all_ok &= not mismatched
    print("\nall layouts behave as documented:", all_ok)
    return 0 if all_ok else 1

if __name__ == "__main__":
    sys.exit(run())
