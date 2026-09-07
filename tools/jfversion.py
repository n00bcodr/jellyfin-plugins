"""System.Version semantics shared by the manifest tooling.

System.Version accepts 2-4 dot-separated components and compares a MISSING
component as -1 (so "10.11" < "10.11.0" < "10.11.0.0"). Jellyfin compares
manifest versions with System.Version and, in PluginManager.PopulateManifest,
by exact string, so every value we write must be the full 4-component form.
"""
import re

FOUR = re.compile(r"^[0-9]+(\.[0-9]+){3}\Z")

# Bold first line the tooling prepends to every changelog; stripped before re-adding so that
# rebuilding from an already-annotated manifest (the deployed URLs) never stacks banners.
BANNER = re.compile(r"^(?:\*\*Build for Jellyfin [^\n]*\*\*[^\n]*\n*)+")   # a whole run, so stacked banners collapse

def strip_banner(changelog):
    return BANNER.sub("", (changelog or "").replace("\r\n", "\n").strip(), count=1).strip()

def with_banner(head, changelog):
    body = strip_banner(changelog)
    return head + ("\n\n" + body if body else "")

def V(s):
    parts = s.split(".")
    if not 2 <= len(parts) <= 4 or not all(re.fullmatch(r"[0-9]+", p) for p in parts):
        raise ValueError(f"not a System.Version: {s!r}")
    nums = [int(p) for p in parts]
    if any(n > 0x7FFFFFFF for n in nums):            # System.Version components are Int32
        raise ValueError(f"component out of range: {s!r}")
    return tuple(nums + [-1] * (4 - len(parts)))

def require_four(s, what):
    if not FOUR.match(s):
        raise SystemExit(f"{what} must be a 4-component version like 12.6.0.0, got {s!r}")
    try:
        V(s)
    except ValueError as ex:
        raise SystemExit(f"{what}: {ex}")
    return s
