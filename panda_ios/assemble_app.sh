#!/bin/bash
# Build the M2 test app: UIKit shell + embedded Python 3.10 + the iOS Panda3D libraries. Unsigned IPA.
set -u
W="$1"; PYXC="$2"; PYINC="$3"
SDK=$(xcrun --sdk iphoneos --show-sdk-path)
APP="$W/out/TTRPanda.app"
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
cp "$W/panda_ios/ios_bootstrap.py" "$APP/app/ios_bootstrap.py"
cp "$W"/panda3d/built-host/panda3d/__init__.py "$APP/app/panda3d/" 2>/dev/null
[ -d "$W/panda3d/built-host/direct" ] && cp -R "$W/panda3d/built-host/direct" "$APP/app/direct"
cp "$W/panda_ios/m2_test.py" "$APP/app/m2_test.py"
cp "$W/panda_ios/m3_test.py" "$APP/app/m3_test.py"
cp "$W/panda_ios/ios_game.py" "$APP/app/ios_game.py"
cp "$W/panda_ios/cacert.pem" "$APP/app/cacert.pem"

# The game's Python code and resources are NOT bundled: the app downloads them from the server on first launch.
# Server addresses come from the build (env TTR_RESOURCE_SERVER / TTR_GAME_SERVER) into a header the app compiles in.
mkdir -p "$W/out/gen"
cat > "$W/out/gen/ttr_config.h" <<CFG
#define RESOURCE_SERVER @"${TTR_RESOURCE_SERVER:-http://127.0.0.1:7380}"
#define GAME_SERVER @"${TTR_GAME_SERVER:-127.0.0.1:7298}"
CFG
cat "$W/out/gen/ttr_config.h"

cat > "$APP/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>TTRPanda</string>
<key>CFBundleIdentifier</key><string>com.ttr.pandatest</string>
<key>CFBundleName</key><string>TTR: Mobile</string>
<key>CFBundleDisplayName</key><string>TTR: Mobile</string>
<key>CFBundleIcons</key><dict><key>CFBundlePrimaryIcon</key><dict><key>CFBundleIconFiles</key><array><string>AppIcon60x60</string></array><key>CFBundleIconName</key><string>AppIcon</string></dict></dict>
<key>CFBundleShortVersionString</key><string>0.1</string>
<key>CFBundleVersion</key><string>1</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>MinimumOSVersion</key><string>15.0</string>
<key>UIDeviceFamily</key><array><integer>1</integer><integer>2</integer></array>
<key>UIRequiredDeviceCapabilities</key><array><string>arm64</string></array>
<key>UILaunchScreen</key><dict/>
<key>NSLocalNetworkUsageDescription</key><string>Connects to your Toontown server and downloads game files from it.</string>
<key>UIFileSharingEnabled</key><true/>
<key>LSSupportsOpeningDocumentsInPlace</key><true/>
<key>UIStatusBarHidden</key><true/>
<key>UIRequiresFullScreen</key><true/>
<key>UISupportedInterfaceOrientations</key><array><string>UIInterfaceOrientationLandscapeRight</string><string>UIInterfaceOrientationLandscapeLeft</string></array>
<key>UISupportedInterfaceOrientations~ipad</key><array><string>UIInterfaceOrientationLandscapeRight</string><string>UIInterfaceOrientationLandscapeLeft</string></array>
</dict></plist>
PLIST

# app icon (drawn with Pillow on the runner)
python3 -m pip install --quiet pillow > /dev/null 2>&1 || pip3 install --quiet pillow > /dev/null 2>&1
python3 "$W/panda_ios/make_icon.py" "$APP" || echo "icon generation failed (app will use the default icon)"

xcrun --sdk iphoneos clang -arch arm64 -isysroot "$SDK" -miphoneos-version-min=15.0 -fobjc-arc \
  -I "$PYINC" -I "$W/out/gen" "$W/panda_ios/main.m" -F "$PYXC" -framework Python -framework UIKit -framework Foundation -framework QuartzCore -framework CoreGraphics -framework Security -framework AVFoundation -framework OpenAL \
  -Wl,-rpath,@executable_path/Frameworks -o "$APP/TTRPanda" 2>&1 | head -30
[ -x "$APP/TTRPanda" ] || { echo "FATAL: main executable was not built"; exit 1; }
ls -la "$APP" | head -20
du -sh "$APP"
mkdir -p "$W/out/Payload" && cp -R "$APP" "$W/out/Payload/" && (cd "$W/out" && zip -qr TTRPanda.ipa Payload) && ls -la "$W/out/TTRPanda.ipa"
