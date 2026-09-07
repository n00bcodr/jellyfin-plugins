# Manifest tooling

This repository serves ONE manifest (`manifest.json`, mirrored byte-for-byte at `12/`, `10.11/` and
`10.10/`, and at the legacy path in the Jellyfin-Enhanced repo). Every plugin version appears once per
build, higher `targetAbi` first; Jellyfin's own ABI filter and first-wins tie-break route each server
to its build. **Never run jprm on this file**: it dedupes on version string and collapses every pair.
The release and publishing helpers refuse an invalid manifest before replacing files.

## Release day

All three plugins share the manifest files, so every one of them follows this. Needs `gh auth login`.
Once the tooling lives under `tools/` in the `jellyfin-plugins` checkout, the working file is that
repo's root `manifest.json`; pass it positionally (the scripts' default `manifest.unified.json` is
only for this proposal directory). Tags are bare (`12.6.0.0`, no `v`).

1. Tag and publish the GitHub release with **both** zips attached (`_12.0.0.zip` and `_10.11.0.zip`).
2. `python3 tools/add_release.py <tag> manifest.json --plugin je|jsinjector|tweaks` (default `je`;
   optionally `--changelog-file`. The GitHub release body is used otherwise, so drop the old "if you are
   on 12 use this other manifest" block and the ko-fi footer from the release template first, or pass
   `--changelog-file`, or they end up in the changelog).
3. `python3 tools/simulate_jellyfin_resolver.py manifest.json` and
   `python3 tools/validate_manifest.py manifest.json --checksums 2`.
4. `python3 tools/publish_manifest.py manifest.json --je-repo <JE checkout> --plugins-repo .`, then
   commit to release branches and open PRs in both repositories. Merge both after validation
   passes.
5. `python3 tools/simulate_jellyfin_resolver.py manifest.json --live` until all five URLs report OK.
6. Watch the analytics mismatch row (`jf10` target on a 12.x server).

Never run jprm against these files. `.github/workflows/validate-manifest.yml` validates all four
copies on PRs, merge queues and pushes. It rejects missing build pairs, reversed order, duplicate
packages, checksum mismatches and upstream source drift. The legacy Enhanced manifest has its own
check using an immutable revision of the same validator. The `--live` check confirms that
all five URLs match after the two merges and GitHub's raw-content caches refresh.

## Verified on real servers

Beyond the source reading and the ported resolver, the whole scheme was exercised on 2 Sep 2026 against
real `jellyfin/jellyfin` containers (12.0.0, 10.11.11, 10.10.7) driven through the REST API, with the
three manifests served from a branch on a fork. Every claim above held: the stale 10.11 manifest gives a
12 server the jf10 DLL; the unified manifest gives 12 the jf12 DLL (by default Install and by explicit
version string), gives 10.11 the jf10 DLL, gives 10.10 its frozen line; the auto-update task on a server
stuck with jf10 12.5.0.0 installed the jf12 zip of the next version; an explicitly chosen old version
gives its only (jf10) build; and the runtime guard logs and reports the mismatch for a sideloaded jf10
DLL on 12 and stays silent for the right DLL on either line.

The publishing safety check was rerun on 7 Sep 2026 with reversed rows, missing jf12 or jf10 rows,
duplicate package GUIDs and invalid JSON. Write mode and `--check` both rejected every invalid
input without changing any of the five destination files. A valid manifest produced five identical
copies. The release helper generated a correctly ordered pair and preserved its input on missing
assets or an invalid resulting catalog. Additional verification scripts remain local.

## Files

| File | Purpose |
|---|---|
| `build_unified_manifest.py` | One-time migration: merge the four live manifests. Run once; re-running after the rollout is idempotent, but do not re-run between `add_release.py` and `publish_manifest.py` (it rebuilds from the live URLs and would drop the unpublished rows). `--only-paired`, `--no-annotate`. |
| `add_release.py` | Per-release helper for any of the three plugins. Refuses to overwrite an existing version without `--force`. |
| `publish_manifest.py` | Writes the five served copies into two local checkouts; `--check` for CI. |
| `validate_manifest.py` | Invariants, the anti-jprm tripwire, optional checksum verification. |
| `simulate_jellyfin_resolver.py` | Port of the Jellyfin resolver paths above; `--live` post-rollout check. |
| `check_upstream.py` | Pinned SHA-256 of the upstream source files the port was written from; `--pin` after re-verifying. |
| `jfversion.py`, `plugins.py` | Shared `System.Version` semantics and banner helpers; the plugin table (guid, repo, assets, first jf12 release) and the five served paths (`PUBLISH_TARGETS`). |
| `test_tooling.py` | `python3 -m unittest test_tooling`: version ordering, banner idempotence, merge conflict resolution, tripwire, fixture hashes. No network. |
| `fixtures/` | Historical manifests for provenance and resolver checks. Do not publish these obsolete per-line catalogs through the unified-manifest release process. |

## Why two rows per version

Jellyfin only enforces a lower bound on `targetAbi` (`InstallationManager.GetPackages`), sorts
compatible rows with a stable descending sort and takes the first (`GetCompatibleVersions`,
`GetAvailablePluginUpdates`, `PackageController.InstallPackage`), and the web client posts a version
*string*, never a row index. So a 10.11 server drops the `12.0.0.0` rows and gets jf10; a 12 server
keeps both and gets the jf12 row listed first. `check_upstream.py` pins the upstream source this
depends on and the weekly CI run fails if it changes.
