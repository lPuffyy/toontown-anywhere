# Releasing the native apps through GitHub

Every installer and every update is published as a **GitHub release** of this repository (`lPuffyy/toontown-anywhere`). One tag, `vX.Y.Z`,
is one release, and every platform's files for that version are attached to it. Nothing is hosted anywhere else, and the apps find their
updates on GitHub too.

## How a player gets and updates the app

| Platform | First install | Updates |
|---|---|---|
| **Windows** | `https://github.com/lPuffyy/toontown-anywhere/releases/latest/download/TTAnywhere-Setup.exe` | The app reads `windows.json` and `windows.json.sig` from the newest release (`.../releases/latest/download/`), checks the signature, downloads the zip named in the list and swaps it in. |
| **Steam Deck / Linux** (planned) | `TTAnywhere-linux.tar.gz` (or AppImage) from the release | Same signed list, `linux.json`. |
| **Android** (planned) | `TTAnywhere.apk` from the release, or add the repo to Obtainium (it follows GitHub releases by itself) | The F-Droid style repo (below) or Obtainium. The APK is signed with one Android key that must never change. |
| **iOS** (planned) | Add the AltStore / SideStore source `https://github.com/lPuffyy/toontown-anywhere/releases/latest/download/altstore.json` | The source file lists the newest `.ipa` (a release asset), so AltStore offers each update. |

The game's own code and files (the packs) are **not** part of these releases: they update from the game server's `packs.json`, so most
updates never need a new release of the app.

## Making a release (Windows today)

1. Raise `__version__` in `native/tta_native/__init__.py`, commit and push.
2. Tag the same number and push the tag: `git tag v0.3.0` then `git push origin v0.3.0`.
3. `.github/workflows/native-release.yml` builds the app and the setup program on a Windows runner, checks that the tag matches the version,
   checks that the signing key matches the public key built into the app, signs `windows.json`, and creates the release with
   `TTAnywhere-Setup-<version>.exe`, `TTAnywhere-Setup.exe` (a name that never changes, for the download button),
   `TTAnywhere-<version>-windows.zip`, `windows.json` and `windows.json.sig`.
4. Installed apps pick it up the next time they start.

"Run workflow" in the Actions tab builds without releasing and keeps the files for 7 days, for a trial.

### One-time setup

- Make the real signing key: `python native/tools/sign_tool.py keygen KEYFILE` (KEYFILE outside the repo). Put the printed public key in
  `native/tta_native/updatekey.py`, commit, and add the **private** key's contents as the repository secret `TTA_UPDATE_KEY`
  (Settings, Secrets and variables, Actions). **Back the private key up in two places.** If it is lost, installed apps can only be
  moved to a new key by installing a new setup program by hand; if it leaks, anyone can push an update.
- The key in the repo today is a test key.

## The other installers (same release, same rules)

Each platform adds a job to the same workflow that attaches its files to the same release and writes a signed list for its platform
(`linux.json`, ...) with `sign_tool.py`.

- **Android:** the APK is built by the Panda3D Android build (a separate repository's workflow today); its job downloads that APK and attaches it as
  `TTAnywhere.apk`. For the F-Droid style repo, a job runs `fdroid update` over the newest APKs and publishes the `repo/` folder with GitHub
  Pages (APKs are about 50 MB, so keep only the last few versions). Obtainium needs nothing but the release.
- **iOS:** the IPA is built on a macOS runner (the expensive minutes; build only for tagged releases). A job then writes `altstore.json`
  (name, bundle id, version, date, size, `downloadURL` = the IPA's release asset) and attaches it. Players re-sign through AltStore or SideStore.
- **Steam Deck / Linux:** a Linux runner builds the same PyInstaller app and attaches the tarball and `linux.json`.

## Known problem: antivirus false alarms

Windows Defender flagged a build of `TTAnywhere.exe` as `Trojan:Win32/Bearfoos.A!ml` (a generic machine-learning guess, common for
PyInstaller programs that are not code-signed). Before a public release:

1. Sign the executable and setup program with a code-signing certificate (SignPath Foundation signs open-source projects for free and works from
   GitHub Actions; otherwise a paid certificate).
2. Submit each release to Microsoft as a false positive (<https://www.microsoft.com/wdsi/filesubmission>).
3. Optionally build PyInstaller's launcher from source in the workflow (`pip install --no-binary pyinstaller pyinstaller`), which most
   often stops the generic detections.
