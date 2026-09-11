Snapshots of the four manifests that were live on 2 Sep 2026, before the unified manifest was
published to their URLs. `simulate_jellyfin_resolver.py` uses these for its "TODAY" layouts so the
script keeps working (and keeps proving the original failure) after the rollout overwrites the
live URLs. `simulate_jellyfin_resolver.py --live` fetches the URLs instead and checks that each
one now serves the unified manifest. To roll the rollout back, publish these files back.

| file | fetched from |
|---|---|
| `legacy.manifest.json` | https://raw.githubusercontent.com/n00bcodr/Jellyfin-Enhanced/main/manifest.json |
| `10.11.manifest.json` | https://raw.githubusercontent.com/n00bcodr/jellyfin-plugins/main/10.11/manifest.json |
| `12.manifest.json` | https://raw.githubusercontent.com/n00bcodr/jellyfin-plugins/main/12/manifest.json |
| `10.10.manifest.json` | https://raw.githubusercontent.com/n00bcodr/jellyfin-plugins/main/10.10/manifest.json |

`unified.manifest.json` is different: it's the unified manifest as it stood right after the
rollout PR merged (latest Jellyfin Enhanced release 12.5.0.0), frozen on purpose. The "BAD
transition" and "FIX ..." layouts in `simulate_jellyfin_resolver.py` use it (not the live
manifest.json passed on the command line) to demonstrate the migration's before/after at the
exact moment it happened -- if they used the live file instead, every real release after 12.5.0.0
would shift what "latest" resolves to and make those layouts drift out from under their own
documented expectations (this is what broke CI in the 12.6.0.0 and 12.7.0.0 releases).

`SHA256SUMS` records their hashes; `test_tooling.py` fails if a fixture is edited.
