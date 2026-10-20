#!/bin/bash
# One consolidated run: iOS deps (png/jpeg/freetype), host Panda3D build (verbose), replay for iOS arm64,
# GLES1 + iPhone display, then an unsigned IPA with Python 3.10 that tests importing panda3d on the device.
set -u
W="$GITHUB_WORKSPACE"
DEPS="$W/ios-deps"
cd "$W/panda3d"

echo "::group::patches"
# iOS SDK has <malloc/malloc.h>, not <sys/malloc.h>
sed -i '' 's|#include <sys/malloc.h>|#include <malloc/malloc.h>|' dtool/src/dtoolbase/dtoolbase.h
# iOS has no _NSGetEnviron (crt_externs); use environ
sed -i '' 's/\*_NSGetEnviron()/environ/' dtool/src/dtoolutil/executionEnvironment.cxx
printf 'extern "C" { extern char **environ; }\n' | cat - dtool/src/dtoolutil/executionEnvironment.cxx > /tmp/ee.cxx && mv /tmp/ee.cxx dtool/src/dtoolutil/executionEnvironment.cxx
# IOKit (macOS HID) does not exist on iOS
for f in panda/src/device/ioKitInputDevice.h panda/src/device/ioKitInputDevice.cxx panda/src/device/ioKitInputDeviceManager.h panda/src/device/ioKitInputDeviceManager.cxx panda/src/device/inputDeviceManager.cxx; do
  sed -i '' 's/defined(__APPLE__)/(defined(__APPLE__) \&\& !defined(BUILD_IPHONE))/g' $f
done
python "$W/panda_ios/patch_sources.py" . 
echo "::endgroup::"

echo "::group::host tools needed by makepanda (brew)"
brew install pkg-config freetype libpng jpeg-turbo openssl@3 libogg libvorbis > "$W/brew.log" 2>&1; tail -2 "$W/brew.log"
OSSL_HOST=$(brew --prefix openssl@3)
echo "host openssl: $OSSL_HOST"
echo "::endgroup::"

echo "::group::iOS dependencies"
mkdir -p "$DEPS" "$W/depsrc"
cd "$W/depsrc"
build_dep() {  # name url extra-cmake-args...
  local name="$1" url="$2"; shift 2
  if [ -f "$DEPS/.done-$name" ]; then echo "$name cached"; return; fi
  mkdir -p "$name" && cd "$name"
  curl -sL "$url" | tar xz --strip-components=1
  cmake -S . -B build -G "Unix Makefiles" -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_ARCHITECTURES=arm64 \
    -DCMAKE_OSX_DEPLOYMENT_TARGET=15.0 -DCMAKE_INSTALL_PREFIX="$DEPS" -DBUILD_SHARED_LIBS=OFF \
    -DCMAKE_POSITION_INDEPENDENT_CODE=ON "$@" > "$W/dep_$name.log" 2>&1 \
    && cmake --build build --config Release -j4 >> "$W/dep_$name.log" 2>&1 \
    && cmake --install build >> "$W/dep_$name.log" 2>&1 \
    && touch "$DEPS/.done-$name"
  echo "$name rc=$?"; tail -3 "$W/dep_$name.log"
  cd ..
}
build_dep libpng https://github.com/pnggroup/libpng/archive/refs/tags/v1.6.44.tar.gz -DPNG_SHARED=OFF -DPNG_STATIC=ON -DPNG_TESTS=OFF -DPNG_TOOLS=OFF -DPNG_FRAMEWORK=OFF
# OpenSSL for iOS (Panda: HTTPClient, VirtualFileMountHTTP, SSL sockets)
if [ ! -f "$DEPS/.done-openssl" ]; then
  mkdir -p openssl && cd openssl && curl -sL https://github.com/openssl/openssl/releases/download/openssl-3.3.2/openssl-3.3.2.tar.gz | tar xz --strip-components=1
  ./Configure ios64-xcrun no-shared no-tests no-apps no-ui-console no-dso no-engine no-async -miphoneos-version-min=15.0 --prefix="$DEPS" --openssldir="$DEPS/ssl" > "$W/dep_openssl.log" 2>&1 \
    && make -j4 build_libs >> "$W/dep_openssl.log" 2>&1 && make install_dev >> "$W/dep_openssl.log" 2>&1 && touch "$DEPS/.done-openssl"
  echo "openssl rc=$?"; tail -3 "$W/dep_openssl.log"
  cd ..
fi
# libjpeg: IJG 9f with configure (libjpeg-turbo's CMake fails on the runner's CMake)
if [ ! -f "$DEPS/.done-libjpeg" ]; then
  mkdir -p jpeg && cd jpeg && curl -sL https://www.ijg.org/files/jpegsrc.v9f.tar.gz | tar xz --strip-components=1
  SDKP=$(xcrun --sdk iphoneos --show-sdk-path)
  ./configure --host=aarch64-apple-darwin --prefix="$DEPS" --disable-shared --enable-static     CC="$(xcrun --sdk iphoneos -f clang)" CFLAGS="-arch arm64 -isysroot $SDKP -miphoneos-version-min=15.0 -fPIC -O2" > "$W/dep_libjpeg.log" 2>&1     && make -j4 >> "$W/dep_libjpeg.log" 2>&1 && make install >> "$W/dep_libjpeg.log" 2>&1 && touch "$DEPS/.done-libjpeg"
  echo "libjpeg rc=$?"; tail -3 "$W/dep_libjpeg.log"
  cd ..
fi
build_dep freetype https://github.com/freetype/freetype/archive/refs/tags/VER-2-13-3.tar.gz -DFT_DISABLE_BZIP2=ON -DFT_DISABLE_BROTLI=ON -DFT_DISABLE_HARFBUZZ=ON -DFT_DISABLE_PNG=ON
# Ogg Vorbis decoding (every sound in the game is .ogg)
build_dep libogg https://github.com/xiph/ogg/releases/download/v1.3.5/libogg-1.3.5.tar.gz -DINSTALL_DOCS=OFF -DCMAKE_POLICY_VERSION_MINIMUM=3.5
build_dep libvorbis https://github.com/xiph/vorbis/releases/download/v1.3.7/libvorbis-1.3.7.tar.gz -DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DCMAKE_PREFIX_PATH="$DEPS" -DOGG_ROOT="$DEPS" -DCMAKE_FIND_ROOT_PATH_MODE_LIBRARY=BOTH -DCMAKE_FIND_ROOT_PATH_MODE_INCLUDE=BOTH
ls "$DEPS/lib" "$DEPS/include" | head -40
echo "::endgroup::"

echo "::group::host Panda3D build (verbose)"
cd "$W/panda3d"
python makepanda/makepanda.py --nothing --use-python --use-zlib --use-png --use-jpeg --use-freetype --use-direct --use-openal --use-vorbis --use-openssl --openssl-incdir="$OSSL_HOST/include" --openssl-libdir="$OSSL_HOST/lib" \
  --use-pandaphysics --use-pandafx --use-pandaparticlesystem --threads 4 --verbose --outputdir built-host > ../host_verbose.log 2>&1
echo "host exit=$?"; tail -3 ../host_verbose.log; ls built-host/lib | tr '\n' ' '; echo
echo "::endgroup::"

echo "::group::Python for iOS (BeeWare)"
cd "$W"
if [ ! -d pysup/Python.xcframework ]; then
  URL="${PYTHON_IOS_SUPPORT_URL:-https://github.com/beeware/Python-Apple-support/releases/download/3.10-b14/Python-3.10-iOS-support.b14.tar.gz}"
  echo "python support: $URL"
  mkdir -p pysup && curl -sL "$URL" | tar xz -C pysup
fi
ls pysup
PYXC="$W/pysup/Python.xcframework/ios-arm64"
PYINC=$(dirname "$(find "$PYXC" -name Python.h | head -1)")
echo "PYINC=$PYINC"
find pysup -maxdepth 2 | head -20
echo "::endgroup::"

echo "::group::replay for iOS"
cd "$W/panda3d"
python "$W/panda_ios/replay.py" ../host_verbose.log . "$PYINC" "$DEPS" 2>&1 | tee ../replay.log | tail -250
echo "::endgroup::"

echo "::group::app shell + IPA"
bash "$W/panda_ios/assemble_app.sh" "$W" "$PYXC" "$PYINC" 2>&1 | tee "$W/assemble.log" | tail -60
[ -f "$W/out/TTRPanda.ipa" ] || { echo "FATAL: no IPA produced"; exit 1; }
echo "::endgroup::"
