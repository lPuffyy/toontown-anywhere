# DRAFT ONLY — DO NOT MERGE / NO PULL REQUEST

This is a local draft snapshot of the browser client work. It has **not** been
opened as a pull request. Resources/packs are built locally and are not part of
this repository.

## Client / code pack

- Restored the shared localizer fix for `QuestScriptTutorialMickey_4` and removed
  the stale compiled `TTLocalizerEnglish` bytecode that was masking it. This
  fixes the tutorial movie aborting and the toon staying frozen.
- Kept browser input recovery on tab/window return, reconnect, and trusted game
  pointer presses.
- Added quiet-log FPS samples (one every 30 s, with scene context), one-shot
  task-cost profiling, and the active texture-mode line so ordinary devices can
  be diagnosed without `?log=1`.
- Cut-out shader: smooth fractional alpha, with an A/B `?cut=hard`. Street signs
  now skip depth write so their face cannot be depth-rejected by its backing
  when transparent-bin sort order flips with camera distance (`?signdw=1`
  restores the old behavior).
- Web Settings gained an Original / Remastered texture picker.

## Resources / packs (built locally, not committed here)

- Remastered textures were rebuilt with Upscayl Standard and capped at 512 px on
  the long side; SGI alpha masks kept the verified RLE pipeline.
- Fixed 33 Upscayl outputs that came out black/flat on tiny sources, including
  the sky textures.
- Restored the upstream Toontown Anywhere repainted art for Disney-character
  playgrounds, street signs, statues and matching DNA/audio (330 files) under
  the original filenames, so no code or DNA links break. Other Remastered art
  was left in place.
- Original packs ~357 MB, Remastered ~437 MB; pack version bumped and deployed
  with script key `tta-ui.js?v=1795000056`.

## Tab-return connection recovery (draft v59)

- Hiding the PC tab closed its WebSocket; the server then booted the session with code 345 ("timed out while waiting for heartbeat"), leaving the game in a lost-connection state where keyboard movement was ignored.
- Returning to the tab or window now forces a clean reload when `webnet.state` is `closed`, instead of leaving a dead session. The event is logged as `JS| auto reload after connection loss (...)`.
- `webui.py` documents that boot code 345 is transient (not a deliberate logout) and remains retryable. New client bundle: `game_ot_reconnect.apk`; script key `tta-ui.js?v=1795000059`.
- Verified the earlier fixes are still present after the upstream merge: tutorial localizer + removed stale `.pyc`, quiet FPS sampling, sign depth-write handling, focus/key recovery, and restored TTA pack art.

## Reworked couch/rug textures (draft v60)

- Replaced seven Remastered textures with the user's reworked 512px versions (`couch.jpg`, `couch2.jpg`, `couch3.jpg`, `carpet.jpg`, `rug_string.jpg`, `phase_3.5_palette_3cmla_1.jpg`, `toon_interior_palette_3cmla_1.jpg`), written back as JPEG q93 4:4:4.
- Kept the existing `rug_string_a.rgb` mask and created verified opaque SGI RLE `_a.rgb` masks for the other six targets that had none. Original packs untouched.
- Remastered packs rebuilt at 449.6 MB; `HD_PACK_V=10`, script key `tta-ui.js?v=1795000060`.
- Follow-up: `carpet.jpg`, `couch3.jpg` and `rug_string.jpg` were switched from the `_remastered` versions to the user's `_clean` versions (same 512px JPEG format); `HD_PACK_V=11`, script key `tta-ui.js?v=1795000061`.
- Follow-up: all seven `_a.rgb` masks were regenerated from the replacement PNGs' alpha channels (the sources are RGB, so every mask is fully opaque, including `rug_string_a.rgb` which previously had a cut-out). `HD_PACK_V=12`, script key `tta-ui.js?v=1795000062`.

## Pack parity, per-device picker, input diagnostics (draft v63)

- Original packs now carry TTA's repainted art at **TTA's original resolutions** (rebuilt directly from the live TTA packs); Remastered remains the 512px upscaled set (449.3 MB). Original packs are 317.6 MB.
- Texture picker is gated by a versioned per-device flag (`tta_textures_chosen_v2`), so this release offers the Original/Remaster choice once on first login and once on each new device, then never again until the version is bumped.
- Added unconditional canvas/window re-focus on tab/window return plus quiet-log diagnostics (`JS| return state ...`, `JS| restored keyboard input observed`) to chase the remaining PC keybind issue after clicking away.

## Eye rendering (draft v65)

- Toon/cog eyes and pupils are layered decals; fractional-alpha depth writes made them sort incorrectly with the head surface. The signage depth-write exemption now also covers nodes whose names contain `eye`, `pupil`, `lash` or `eyelid`. `?signdw=1` still restores the old behaviour.
- New client bundle `game_ot_eyes.apk`; script key `tta-ui.js?v=1795000065`.
- Follow-up: eyes/pupils/lashes now use the opaque alpha-test shader path (hard discard, no blending) while signs stay smooth with depth write off. New bundle `game_ot_eyehard.apk`; script key `tta-ui.js?v=1795000066`. Client-side fix applies to both Original and Remastered packs.

## Combined rendering/return/plack fixes (draft v68)

- Remastered uses TTA's original eye/pupil/lash textures again (64px) while the rest of Remastered stays 512px; Original already used the same files.
- All picture-over-model decals (signs, windows, trolley, billboards, banners, labels, eyes/pupils/lashes) now get a small negative polygon offset (`?decaloff=0` disables) so they stay visible at distance.
- Return-to-game recovery is universal: desktop refocus, touch devices get a "Tap to resume" gesture, WebSocket-closed still forces a clean reload.
- Added `?hoodcache=1` iOS A/B switch for hood model caching.
- Device tab restyled to match the Options / Enter Code tabs.
- Cleanup: removed all superseded APKs; only `game_ot_final.apk` remains. Backups kept.
- `HD_PACK_V=15`, script `tta-ui.js?v=1795000068`.
- Follow-up: reverted the two reworked palettes (`phase_3.5_palette_3cmla_1.jpg`, `toon_interior_palette_3cmla_1.jpg`) to their pre-rework versions, and re-applied Upscayl Standard to all 12 eye/pupil/lash colour textures plus the verified RLE path for their 12 masks (512px, zero fallbacks). Device tab label centred to match Options / Enter Code. `HD_PACK_V=16`, script `tta-ui.js?v=1795000069`.
- Removed our local sign/eye/decal workaround (`_SIGN_NO_DEPTH`, `DECAL_OFFSET`, `_is_sign`, depth-write exceptions and polygon offsets) so the upstream main-build fix is the only one active. New bundle `game_ot_upstream.apk`, script `tta-ui.js?v=1795000070`.

## Tab centering, restart warning, staff account (draft v71)

- Centered the Enter Code and Device tab labels to the tab artwork (`text_align=ACenter`, `text_pos=(0.033, 0, 0)`).
- Moved the Device page restart warning below the settings rows and made it brighter; added `JS| device restart pressed` logging so a non-working restart can be diagnosed.
- Promoted the existing `gremzy_dev` account to `DEVELOPER` access (developer badge + staff powers) and set its local password. Server restarted to apply.
- `HD_PACK_V=17`, script `tta-ui.js?v=1795000071`.

## Tab centering pass 2 and mod panel access (draft v72)

- Adjusted Enter Code and Device tab label offsets from screenshot measurements (`0.07` and `0.115` respectively) so the text centres on the tab artwork.
- `gremzy_dev` now has `admin: true` in `users.json`, which is what the `/mod/` panel checks; the in-game `DEVELOPER` access level remains for the name badge and staff magic words.
- `HD_PACK_V=18`, script `tta-ui.js?v=1795000072`.

## Cog HQ fixes (draft v73)

- Remastered packs were missing `phase_12/dna/cog_hq_bossbot_sz.dna` (Bossbot HQ safe-zone DNA), causing `IndexError` in `getCogHQViszones` and a forced return to a street. Copied it and seven missing Clarabelle voice files from Original into Remastered; both packs now match.
- `QuestMap.py` now loads HQ quest-map models with `okMissing=True` and returns quietly when TTA didn't ship them, stopping repeated `cog_hq_*_maps.bam not found` errors.
- `HD_PACK_V=19`, script `tta-ui.js?v=1795000073`.

## Decal diagnostics (draft v74)

- Enabled a modest default `?decal=2` extra depth offset for Panda `DecalEffect` children (windows/doors); `?decal=0` disables it for A/B.
- Added quiet-log diagnostics for cut-out/decal nodes: `web: decal node ...` with name, transparency mode, depth-write, depth-offset and DecalEffect state (capped at 40 lines).
- New bundle `game_ot_diag.apk`; script `tta-ui.js?v=1795000074`.

## Hard cut-outs default, eye offset A/B (draft v75)

- User confirmed `?cut=hard` fixes signs/windows/decals and prefers it to `?dmul=1`. Hard alpha-test is now the default; `?cut=smooth` restores the blended shader; `dmul` is back to its original 6.
- Fixed a `hasEffect()` type bug in the decal debug code.
- Added an eye-specific depth offset (`?eyeoff=N`, default 2, `?eyeoff=0` disables) applied to eye/pupil/lash cut-out geometry, plus `web: decal node ... eye` diagnostics. Panda inspection showed those geoms are `MDual` with no depth offset, supporting the offset theory.
- New bundle `game_ot_hard.apk`; script `tta-ui.js?v=1795000075`.

## Decal effect reference fix (draft v76)

- Fixed a name collision: `DecalEffect` was aliased `_DE`, then later overwritten by `DirectEntry` as `_DE`, so `boost_decals` called `DirectEntry.getClassType()` and failed on every model, raising hundreds of `decal boost failed` errors. Renamed to `_DECALFX`.
- New bundle `game_ot_decalfix.apk`; script `tta-ui.js?v=1795000076`.

## Eye shader separation (draft v77)

- Mask analysis: `eyes_a.rgb` is transparent across ~67% of the eye (the sclera is the white head geometry behind it), so a hard alpha test makes the opaque eye outline cover that white. Eyes now get their own smooth alpha-blend shader while signs/windows stay hard. `?eyehard` restores the old global path for eyes.
- New bundle `game_ot_eyesmooth.apk`; script `tta-ui.js?v=1795000077`.

## Actor eye path fix (draft v78)

- Diagnostics showed no `eye` decal logs at all: toon eyes load through the Actor path (`shader=False`), which never ran our eye shader/offset logic, so `?eyeoff` was a no-op.
- Applied the eye-specific smooth shader + depth offset in the Actor (`not shader`) path for eye/pupil/lash geoms, with `eye-actor` diagnostics. Signs/windows remain hard.
- New bundle `game_ot_eyefix.apk`; script `tta-ui.js?v=1795000078`.

## Eye material revert + offset-only A/B (draft v79)

- Reverted the custom eye shader/transparency handling: it corrupted eyelash meshes (names containing 'eye') and eye materials. Eyes now keep their original material again.
- `?eyeoff=N` still applies a depth offset to eye/pupil geometry, now only in the Actor path where eyes actually load; default returned to 0 (off) so eyes render as before. `?eyeoff=8` and `?eyeoff=-8` are the A/B.
- New bundle `game_ot_eyeo2.apk`; script `tta-ui.js?v=1795000079`.

## Baked RGBA eye textures (draft v82)

- Baked each eye color texture together with its SGI alpha mask into a single RGBA PNG (`eyes_rgba.png`, etc.) in both texture trees, verified masks with the Panda RLE reader first.
- `ToonHead.py` now loads those RGBA PNGs directly instead of `eyes.jpg` + `eyes_a.rgb`, removing the browser's dependence on the separate SGI alpha file (which historically failed to load).
- Eye depth offset returned to 0 (off); no custom eye shader. Signs/windows remain on hard cut-outs.
- New bundle `game_ot_eyergba.apk`; script `tta-ui.js?v=1795000082`.

## Known items

- PC/iPad/PC rendering and FPS still need a final cross-device pass; the latest
  logs show no texture-load or shader errors.
- No pull request was opened.
