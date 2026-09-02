#!/usr/bin/env python3
"""
The whole scheme rests on how four Jellyfin server source files and one jellyfin-web page resolve
manifest entries (stable sort, first-wins ties, lower-bound ABI filter). simulate_jellyfin_resolver.py is a port of those files
as they were on 2 Sep 2026. This script re-downloads them from both maintained branches and
fails if any has changed since, so that drift is noticed instead of silently breaking the fix.
On failure: re-read the file, update the port if the resolver semantics changed, then re-pin.

    python3 check_upstream.py [--pin]     (--pin rewrites the hashes below from what is live now)
"""
import hashlib, re, sys, urllib.request

FILES = [
    "Emby.Server.Implementations/Updates/InstallationManager.cs",
    "Emby.Server.Implementations/Plugins/PluginManager.cs",
    "Jellyfin.Api/Controllers/PackageController.cs",
    "MediaBrowser.Model/Updates/VersionInfo.cs",
]
BRANCHES = ["master", "release-10.11.z"]
WEB = "src/apps/dashboard/routes/plugins/plugin.tsx"

PINNED = {
    "jellyfin/jellyfin/master/Emby.Server.Implementations/Updates/InstallationManager.cs": "0e9ddc12969763af4a16c5c390666b69ca58adbb3852b89bd43b3fd88cc13bb8",
    "jellyfin/jellyfin/master/Emby.Server.Implementations/Plugins/PluginManager.cs": "bc3974c99fac3576cc26107789c287f62c12e947c6d8cab5e39d5e103ea80c4a",
    "jellyfin/jellyfin/master/Jellyfin.Api/Controllers/PackageController.cs": "c3d199a05a59f78373b1f911ba3da1e200b4f10b840cd5e670c074265ba23b54",
    "jellyfin/jellyfin/master/MediaBrowser.Model/Updates/VersionInfo.cs": "86edb673ce08ec9c893153663fb9a5199a6e5c3ee4d60ed0827efac2a5809eca",
    "jellyfin/jellyfin-web/master/src/apps/dashboard/routes/plugins/plugin.tsx": "c207e1a3448840f604520665ee035b374e7ea5151ca1a998b42315674dbc0c53",
    "jellyfin/jellyfin/release-10.11.z/Emby.Server.Implementations/Updates/InstallationManager.cs": "1433450b91ed4c73d8437392f14055ea20178c7b4d99378af2cef4de995a3c0a",
    "jellyfin/jellyfin/release-10.11.z/Emby.Server.Implementations/Plugins/PluginManager.cs": "ce6659d2326b92a784dfb7ab51398e5357f3aa5238e0f021881a808d3f42937b",
    "jellyfin/jellyfin/release-10.11.z/Jellyfin.Api/Controllers/PackageController.cs": "96b5ca5190b97699a083f967584c134f650e6afadbbee56fc0cb6e216303b99d",
    "jellyfin/jellyfin/release-10.11.z/MediaBrowser.Model/Updates/VersionInfo.cs": "86edb673ce08ec9c893153663fb9a5199a6e5c3ee4d60ed0827efac2a5809eca",
    "jellyfin/jellyfin-web/release-10.11.z/src/apps/dashboard/routes/plugins/plugin.tsx": "c207e1a3448840f604520665ee035b374e7ea5151ca1a998b42315674dbc0c53",
}

def sha(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return hashlib.sha256(r.read()).hexdigest()

def targets():
    for b in BRANCHES:
        for f in FILES:
            yield f"jellyfin/jellyfin/{b}/{f}"
        yield f"jellyfin/jellyfin-web/{b}/{WEB}"

def main():
    if set(sys.argv[1:]) & {"-h", "--help"}:
        print("usage: check_upstream.py [--pin]"); print(__doc__); return 0
    if set(sys.argv[1:]) - {"--pin"}:
        sys.exit("usage: check_upstream.py [--pin]")
    live = {t: sha("https://raw.githubusercontent.com/" + t) for t in targets()}
    if "--pin" in sys.argv[1:]:
        with open(__file__, encoding="utf-8") as f:
            src = f.read()
        body = "PINNED = {\n" + "".join(f'    "{k}": "{v}",\n' for k, v in live.items()) + "}\n"
        src, n = re.subn(r"PINNED = \{.*?\n\}\n", body, src, count=1, flags=re.S)
        if n != 1:
            sys.exit("PINNED block not found in this file; restore it to the `PINNED = {\\n...\\n}` shape")
        with open(__file__, "w", encoding="utf-8") as f:
            f.write(src)
        print(f"pinned {len(live)} files"); return 0
    drift = [t for t, h in live.items() if PINNED.get(t) != h]
    for t in live:
        print(f"  {'DRIFT ' if t in drift else 'same  '} {t}")
    if drift:
        sys.exit("upstream resolver source changed; re-verify simulate_jellyfin_resolver.py against it, then `check_upstream.py --pin`")
    print("upstream resolver source unchanged since pin")

if __name__ == "__main__":
    sys.exit(main())
