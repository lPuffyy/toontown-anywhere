# Toontown: Anywhere for iPhone and iPad

The native iOS app: a UIKit shell (`panda_ios/main.m`: start screen, sign-in, touch controls, settings) around Python 3.10 and Panda3D built
for iOS. It runs the same game as the website and the Windows app. The game's own code, models and sounds are **not** in the app: it downloads
them from the Toontown: Anywhere server on first launch. It shares `native/tta_native` (sign-in, packs, chat helpers, control code, HUD
layout, WebSocket connection) with the Windows app, and the website's `web/game` code, so a fix there is a fix here.

## Build (GitHub Actions, macOS runner)

1. **`ios-panda-stage`** (about 10 minutes, rarely needed): builds Panda3D for iOS and publishes it as a release (`stage-<run id>`,
   `panda-ios-stage.zip`). Re-run it only when `panda_ios/patch_sources.py` (the Panda display patches) changes.
2. **`ios-app`** (a few minutes): give it the stage release name in `stage_release` and the server in `resource_server`; it builds an unsigned
   IPA, kept as the release `ipa-<run id>`. `sync_tta.py` runs first and gathers `native/tta_native` and the websocket package.
3. Publish the IPA to SideStore (icon, bundle id and version are set in a copy of the IPA; the source files live on the server).

`panda_ios/` holds: `main.m` (the shell), `ios_game.py` (the Python side the shell calls), `ios_bootstrap.py`, `patch_sources.py` (Panda iOS
display patches), `build_ios.sh` / `assemble_app.sh` / `replay.py` (the build), `sync_tta.py`, `ui_bundled/` (the cloud sky and the Toon
Display font), `cacert.pem`, `THIRD_PARTY_NOTICES.md` (inherited from the shell's origin; keep it).

## Screen size and safe area ("display appropriately on every device")

`main.m` reports the screen to the game (`pushScreenMetrics:`, about three times a second): width and height in pixels, and UIKit's
`safeAreaInsets` (camera cut-out, rounded corners, home bar). `ios_game.set_screen()` stores them, asks the game's window to take the new
size, and `hud.py` keeps the game's buttons (chat, laff, book, friends) inside the safe area and hangs the side ones from the screen's
edges, at any shape. When the size or insets change while playing (rotation, a foldable opening or closing, Stage Manager) the touch
controls are laid out again. The layout code itself was checked on this PC at nine screen shapes (SE to iPad Pro, 4:3 foldable, an
extreme wide phone); see the display test in `native/README.md`.

## NOT verified yet (needs a device build)

Nothing in this flavour has run on an iPhone or iPad. Check first:

- The app starts, shows the start screen, downloads the packs, signs in and enters the game (`ios_game_tta.launch`).
- WebSocket over TLS works with the bundled `cacert.pem`.
- The game's window really follows the UIKit view when the size changes (fold / unfold, Stage Manager, rotation): `_resize_game_window`
  asks Panda for the new size, but the iOS display code may ignore it. If the picture stays the old size, the Panda iOS window class
  (`iPhoneGraphicsWindow`) needs a layout hook that resizes its drawable.
- The touch controls rebuild (`showControls` called again) without leaking the old window.
- Memory on small iPhones (the area model cache is off for iOS; see the PWA's memory-kill notes).
