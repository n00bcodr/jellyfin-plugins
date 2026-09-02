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

`SHA256SUMS` records their hashes; `test_tooling.py` fails if a fixture is edited.
