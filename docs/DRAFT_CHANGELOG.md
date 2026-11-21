# Remaster Update

Upscaled art rendering and cross-platform client fixes for the browser client.
Supersedes the earlier (closed) PRs #3 and #4.

Resource packs are built locally and are not part of this repository.

## New features

- **Original / Remastered texture picker**
  - Shown automatically on first login/startup, before packs download
    (`beginDownload()`), so the choice sets the manifest from the start.
  - Per-device and versioned (`tta_textures_chosen_v2`): offered once on
    first login and once on each new device.
  - Also available afterward in Settings. Same fixes in both packs.
- **"Tap to resume" overlay** on touch devices after returning from
  another app.
- **Restyled Device tab** in Shticker Book Options, matching the
  Options / Enter Code tabs.
- **Daily upstream auto-sync** — local TTA_Dev tooling (outside this repo)
  that merges upstream, keeps local fixes, and rebuilds packs.

## Fixed

- **Tutorial movie freeze** — added the `QuestScriptTutorialMickey_4`
  localizer and removed the stale `.pyc` that masked it.
- **Input recovery** on tab/window return, reconnect, and pointer presses.
- **Signs/windows/decals** — hard alpha-test (`?cut=hard`) is now the
  default and has been stable since release. Local depth/offset
  workarounds removed.
- **Cog HQs** — restored missing Bossbot DNA + Clarabelle audio to
  Remastered; `QuestMap.py` now handles absent HQ maps.

## In progress

- **Eyes** - latest approach bakes eye alpha into RGBA PNGs (resource side).
  The earlier depth offset is opt-in via `?eyeoff=N` and now off by default.
  Needs visual confirmation; not a shipped fix.

## Packs

- The two packs run **separately, one at a time** — only the selected mode
  is downloaded and used per session, never both loaded together. Both
  are kept in cache so switching modes doesn't force a re-download.
- Repaired 33 black Upscayl outputs, SGI RLE masks, ~330 restored TTA
  art files, couch/rug reworks, and 512px eye textures.
- Total resource sizes (per mode, not simultaneous):
  - Original ≈ 317.6 MB
  - Remastered ≈ 449.3 MB
  - Combined on disk ≈ 767 MB
- `HD_PACK_V=19`, script `tta-ui.js?v=1795000075`
  (verify against active page before release).
