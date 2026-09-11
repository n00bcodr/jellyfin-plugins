"""The three plugins that share the n00bcodr manifest, and what a release of each looks like."""
PLUGINS = {
    "je": {
        "name": "Jellyfin Enhanced",
        "guid": "f69e946a-4b3c-4e9a-8f0a-8d7c1b2c4d9b",
        "repo": "n00bcodr/Jellyfin-Enhanced",
        # (targetAbi, asset name) -- ORDER MATTERS: higher targetAbi first for the same version.
        "targets": [("12.0.0.0", "Jellyfin.Plugin.JellyfinEnhanced_12.0.0.zip"),
                    ("10.11.0.0", "Jellyfin.Plugin.JellyfinEnhanced_10.11.0.zip")],
        "first_jf12": "12.0.0.0",   # every version from here on MUST have a 12.0.0.0 row (anti-jprm tripwire)
    },
    "jsinjector": {
        "name": "JavaScript Injector",
        "guid": "f5a34f7b-2e8a-4e6a-a722-3a216a81b374",
        "repo": "n00bcodr/Jellyfin-JavaScript-Injector",
        "targets": [("12.0.0.0", "Jellyfin.Plugin.JavaScriptInjector_12.0.0.zip"),
                    ("10.11.0.0", "Jellyfin.Plugin.JavaScriptInjector_10.11.0.zip")],
        "first_jf12": "4.0.0.0",
    },
    "tweaks": {
        "name": "Jellyfin Tweaks",
        "guid": "dfee3828-01df-49df-85b1-5c2b75e5ea1a",
        "repo": "n00bcodr/JellyfinTweaks",
        "targets": [("12.0.0.0", "Jellyfin.Plugin.JellyTweaks_12.0.0.zip"),
                    ("10.11.0.0", "Jellyfin.Plugin.JellyTweaks_10.11.0.zip")],
        "first_jf12": "4.0.0.0",
    },
}

# Every URL that must serve the unified manifest, as (checkout, relative path). Every plugin's
# own repo serves the full 3-plugin catalog, not just its own package -- so all four checkouts
# end up byte-identical everywhere.
PUBLISH_TARGETS = [
    ("je",         "manifest.json"),       # n00bcodr/Jellyfin-Enhanced
    ("jsinjector", "manifest.json"),       # n00bcodr/Jellyfin-JavaScript-Injector
    ("tweaks",     "manifest.json"),       # n00bcodr/JellyfinTweaks
    ("plugins",    "manifest.json"),       # canonical URL, n00bcodr/jellyfin-plugins
    ("plugins",    "12/manifest.json"),
    ("plugins",    "10.11/manifest.json"),
    ("plugins",    "10.10/manifest.json"),
]
