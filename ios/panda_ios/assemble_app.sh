#!/bin/bash
# Build the M2 test app: UIKit shell + embedded Python 3.10 + the iOS Panda3D libraries. Unsigned IPA.
set -u
W="$1"; PYXC="$2"; PYINC="$3"
SDK=$(xcrun --sdk iphoneos --show-sdk-path)
APP="$W/out/TTAnywhere.app"
rm -rf "$W/out"; mkdir -p "$APP/Frameworks" "$APP/python/lib/python3.10" "$APP/app/panda3d"

cp -R "$PYXC/Python.framework" "$APP/Frameworks/"
# stdlib shipped by BeeWare
STD=$(find "$W/pysup" -maxdepth 3 -type d \( -name "python3.10" -o -name "python-stdlib" \) | head -1)
echo "stdlib: $STD"
if [ -d "$W/pysup/python-stdlib" ]; then cp -R "$W/pysup/python-stdlib/." "$APP/python/lib/python3.10/"; else cp -R "$STD/." "$APP/python/lib/python3.10/"; fi
LD=$(find "$W/pysup" -type d -name "lib-dynload" | grep -i "ios.*arm64\|iphoneos" | grep -vi simulator | head -1)
echo "lib-dynload: $LD"
# stdlib extension modules must live in Frameworks (as .dylib) to be signed; ios_bootstrap maps them
if [ -n "$LD" ]; then
  for f in "$LD"/*.so; do b=$(basename "$f"); cp "$f" "$APP/Frameworks/ext_${b%%.cpython*}.dylib"; done
  echo "stdlib extension modules: $(ls "$APP"/Frameworks/ext_*.dylib | wc -l)"
fi

# Panda3D iOS libraries and python modules
cp "$W"/panda3d/built-ios/lib/*.1.10.dylib "$APP/Frameworks/" 2>/dev/null
cp "$W"/panda3d/built-ios/lib/libpandagles.dylib "$APP/Frameworks/" 2>/dev/null
cp "$W"/panda3d/built-ios/lib/libp3openal_audio.dylib "$APP/Frameworks/" 2>/dev/null || echo "no openal audio plugin built"
for f in "$W"/panda3d/built-ios/panda3d/*.so; do b=$(basename "$f"); cp "$f" "$APP/Frameworks/pymod_${b%%.*}.dylib"; done
cp "$W/ios/panda_ios/ios_bootstrap.py" "$APP/app/ios_bootstrap.py"
cp "$W"/panda3d/built-host/panda3d/__init__.py "$APP/app/panda3d/" 2>/dev/null
[ -d "$W/panda3d/built-host/direct" ] && cp -R "$W/panda3d/built-host/direct" "$APP/app/direct"
cp "$W/ios/panda_ios/m2_test.py" "$APP/app/m2_test.py"
cp "$W/ios/panda_ios/m3_test.py" "$APP/app/m3_test.py"
# the game's own Python side, the shared client code (copied from native/ by sync_tta.py) and the pure-Python websocket package
cp "$W/ios/panda_ios/ios_game.py" "$APP/app/ios_game.py"
cp -R "$W/ios/panda_ios/tta_native" "$APP/app/tta_native"
cp -R "$W/ios/panda_ios/vendor" "$APP/app/vendor"
cp "$W/ios/panda_ios/tta_native/settings-spec.json" "$APP/settings-spec.json"      # the settings cog's fallback copy
cp -R "$W/ios/panda_ios/ui_bundled" "$APP/ui_bundled"                                # the cloud sky and the Toon Display font (the web app's)
cp "$W/ios/panda_ios/cacert.pem" "$APP/app/cacert.pem"
cp "$W/LICENSE" "$APP/LICENSE.txt"
cp "$W/ios/panda_ios/THIRD_PARTY_NOTICES.md" "$APP/THIRD_PARTY_NOTICES.md"

# The game's Python code and resources are NOT bundled: the app downloads them from the server on first launch.
# Server addresses come from the build (env APP_RESOURCE_SERVER, APP_GAME_SERVER) into a header the app compiles in.
mkdir -p "$W/out/gen"
cat > "$W/out/gen/app_config.h" <<CFG
#define RESOURCE_SERVER @"${APP_RESOURCE_SERVER:-http://127.0.0.1:7380}"
#define GAME_SERVER @"${APP_GAME_SERVER:-127.0.0.1:7298}"
CFG
echo '#define APP_FLAVOR_TTA 1' >> "$W/out/gen/app_config.h"
cat "$W/out/gen/app_config.h"

cat > "$APP/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>TTAnywhere</string>
<key>CFBundleIdentifier</key><string>com.puffsco.toontownanywhere</string>
<key>CFBundleName</key><string>Toontown: Anywhere</string>
<key>CFBundleDisplayName</key><string>TT: Anywhere</string>
<key>CFBundleIcons</key><dict><key>CFBundlePrimaryIcon</key><dict><key>CFBundleIconFiles</key><array><string>AppIcon60x60</string></array><key>CFBundleIconName</key><string>AppIcon</string></dict></dict>
<key>CFBundleShortVersionString</key><string>0.1</string>
<key>CFBundleVersion</key><string>1</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>MinimumOSVersion</key><string>15.0</string>
<key>UIDeviceFamily</key><array><integer>1</integer><integer>2</integer></array>
<key>UIRequiredDeviceCapabilities</key><array><string>arm64</string></array>
<key>UILaunchScreen</key><dict/>
<key>UIApplicationSceneManifest</key><dict><key>UIApplicationSupportsMultipleScenes</key><false/><key>UISceneConfigurations</key><dict><key>UIWindowSceneSessionRoleApplication</key><array><dict><key>UISceneConfigurationName</key><string>Default Configuration</string><key>UISceneDelegateClassName</key><string>SceneDelegate</string></dict></array></dict></dict>
<key>NSLocalNetworkUsageDescription</key><string>Connects to your Toontown server and downloads game files from it.</string>
<key>UIFileSharingEnabled</key><true/>
<key>LSSupportsOpeningDocumentsInPlace</key><true/>
<key>UIStatusBarHidden</key><true/>
<key>UIRequiresFullScreen</key><true/>
<key>CADisableMinimumFrameDurationOnPhone</key><true/>
<key>UISupportedInterfaceOrientations</key><array><string>UIInterfaceOrientationLandscapeRight</string><string>UIInterfaceOrientationLandscapeLeft</string></array>
<key>UISupportedInterfaceOrientations~ipad</key><array><string>UIInterfaceOrientationLandscapeRight</string><string>UIInterfaceOrientationLandscapeLeft</string></array>
</dict></plist>
PLIST

# version and build number come from the release (APP_VERSION, APP_BUILD); a trial build keeps the defaults
if [ -n "${APP_VERSION:-}" ]; then
  /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $APP_VERSION" "$APP/Info.plist"
  /usr/libexec/PlistBuddy -c "Set :CFBundleVersion ${APP_BUILD:-1}" "$APP/Info.plist"
fi

# app icon (drawn with Pillow on the runner)
python3 -m pip install --quiet pillow > /dev/null 2>&1 || pip3 install --quiet pillow > /dev/null 2>&1
python3 "$W/ios/panda_ios/make_icon.py" "$APP" || echo "icon generation failed (app will use the default icon)"

xcrun --sdk iphoneos clang -arch arm64 -isysroot "$SDK" -miphoneos-version-min=15.0 -fobjc-arc -Wno-deprecated-declarations \
  -I "$PYINC" -I "$W/out/gen" "$W/ios/panda_ios/main.m" -F "$PYXC" -framework Python -framework UIKit -framework Foundation -framework QuartzCore -framework CoreGraphics -framework CoreText -framework Security -framework AVFoundation -framework OpenAL \
  -Wl,-rpath,@executable_path/Frameworks -o "$APP/TTAnywhere" 2>&1 | head -30
# iPhone Duo decides between its letterboxed compatibility mode and the full display by the SDK version
# the app was built with (27.1 or later = full display). The xcode-27 runner has the real SDK (27.1), and the full display left the game's buttons at
# the right edge of the Duo without taps, so the app is marked as built with an older SDK (APP_SDK_MARK, default 26.0) to get the compatibility window
# every earlier build had. Set APP_SDK_MARK=27.1, or to an empty value, to get the full display (or the real SDK) back.
SDK_MARK="${APP_SDK_MARK-26.0}"
if [ -n "$SDK_MARK" ] && [ -x "$APP/TTAnywhere" ]; then
  xcrun vtool -set-build-version ios 15.0 "$SDK_MARK" -replace -output "$APP/TTAnywhere.marked" "$APP/TTAnywhere" \
    && mv "$APP/TTAnywhere.marked" "$APP/TTAnywhere" && chmod +x "$APP/TTAnywhere" || echo "WARNING: could not mark the SDK version"
fi
echo "--- build version of the app binary and the frameworks:"
for f in "$APP/TTAnywhere" "$APP"/Frameworks/*.framework/*; do [ -f "$f" ] && echo "$f" && xcrun vtool -show-build "$f" 2>&1 | grep -E "platform|minos|sdk" | tr '\n' ' ' && echo; done | head -60
[ -x "$APP/TTAnywhere" ] || { echo "FATAL: main executable was not built"; exit 1; }
ls -la "$APP" | head -20
du -sh "$APP"
mkdir -p "$W/out/Payload" && cp -R "$APP" "$W/out/Payload/" && (cd "$W/out" && zip -qr TTAnywhere.ipa Payload) && ls -la "$W/out/TTAnywhere.ipa"
