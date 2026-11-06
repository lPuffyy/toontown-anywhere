#!/usr/bin/env bash
# Toontown: Anywhere for Steam on Linux (Steam Deck included)
#
# Adds "Toontown: Anywhere" to your Steam library as a non-Steam game. It opens the game full screen in its own browser
# window (with its own profile, so it remembers your sign-in), and works in Game Mode on the Steam Deck with the controls.
#
#   bash steam-linux.sh              install (or update)
#   bash steam-linux.sh --uninstall  remove it again
#
# Run it in Desktop Mode on a Steam Deck. Steam has to be closed while the library list is changed: the script offers to
# close it for you. Nothing here needs sudo.
set -euo pipefail

NAME="Toontown: Anywhere"
URL="https://toontown.puffsco.com/play/"
SITE="https://toontown.puffsco.com"
DIR="$HOME/.local/share/toontown-anywhere"
LAUNCHER="$DIR/launch.sh"
DESKTOP_FILE="$HOME/.local/share/applications/toontown-anywhere.desktop"

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31mxx\033[0m %s\n' "$*" >&2; exit 1; }
ask() {   # ask "question" -> 0 for yes; works when the script is piped into bash too
    local reply=""
    if [ -r /dev/tty ]; then read -r -p "$1 [Y/n] " reply < /dev/tty || true; fi
    case "$reply" in [nN]*) return 1 ;; *) return 0 ;; esac
}

command -v python3 >/dev/null || die "python3 is needed (it comes with SteamOS and most Linux systems)."

# ---- Steam's folders: every account that has signed in on this computer -------------------------------------------
steam_roots() {
    local d
    for d in "$HOME/.steam/steam" "$HOME/.local/share/Steam" "$HOME/.var/app/com.valvesoftware.Steam/.local/share/Steam"; do
        if [ -d "$d/userdata" ]; then readlink -f "$d"; fi
    done | sort -u
}

close_steam() {
    if pgrep -x steam >/dev/null 2>&1 || pgrep -f "com.valvesoftware.Steam" >/dev/null 2>&1; then
        ask "Steam is running and has to be closed to change its library. Close Steam now?" || die "Close Steam and run this again."
        say "Closing Steam..."
        (steam -shutdown >/dev/null 2>&1 || flatpak run com.valvesoftware.Steam -shutdown >/dev/null 2>&1 || true) &
        for _ in $(seq 1 30); do
            pgrep -x steam >/dev/null 2>&1 || pgrep -f "com.valvesoftware.Steam" >/dev/null 2>&1 || return 0
            sleep 1
        done
        die "Steam did not close. Close it yourself (Steam menu > Exit) and run this again."
    fi
}

# ---- the library list (shortcuts.vdf, Steam's binary format) -------------------------------------------------------
# edit_shortcuts add|remove <vdf file> [exe startdir icon]: prints the shortcut's app id (for the artwork file names)
edit_shortcuts() {
    python3 - "$@" <<'PY'
import os, struct, sys, zlib
mode, path = sys.argv[1], sys.argv[2]
NAME = "Toontown: Anywhere"

def read_vdf(data, i=0):
    out = {}
    while True:
        t = data[i]; i += 1
        if t == 8:
            return out, i
        end = data.index(b"\0", i); key = data[i:end].decode("utf-8", "replace"); i = end + 1
        if t == 0:
            out[key], i = read_vdf(data, i)
        elif t == 1:
            end = data.index(b"\0", i); out[key] = data[i:end].decode("utf-8", "replace"); i = end + 1
        elif t == 2:
            out[key] = ("int", struct.unpack_from("<i", data, i)[0]); i += 4
        elif t == 7:
            out[key] = ("u64", struct.unpack_from("<Q", data, i)[0]); i += 8
        else:
            raise ValueError("unknown field type %d in %s" % (t, path))

def write_vdf(d):
    b = b""
    for k, v in d.items():
        key = k.encode() + b"\0"
        if isinstance(v, dict):
            b += b"\0" + key + write_vdf(v)
        elif isinstance(v, tuple) and v[0] == "int":
            b += b"\2" + key + struct.pack("<i", v[1])
        elif isinstance(v, tuple) and v[0] == "u64":
            b += b"\7" + key + struct.pack("<Q", v[1])
        else:
            b += b"\1" + key + str(v).encode() + b"\0"
    return b + b"\x08"

shortcuts = {}
if os.path.exists(path) and os.path.getsize(path) > 0:
    data = open(path, "rb").read()
    if data[0] != 0:
        raise SystemExit("unexpected format in " + path)
    end = data.index(b"\0", 1)
    shortcuts, _ = read_vdf(data, end + 1)
entries = [v for v in shortcuts.values() if isinstance(v, dict) and v.get("AppName", v.get("appname")) != NAME]

if mode == "add":
    exe, startdir, icon = sys.argv[3], sys.argv[4], sys.argv[5]
    quoted = '"%s"' % exe
    appid = (zlib.crc32((quoted + NAME).encode()) & 0xFFFFFFFF) | 0x80000000      # the id Steam itself gives such a shortcut
    entries.append({
        "appid": ("int", appid - (1 << 32)), "AppName": NAME, "Exe": quoted, "StartDir": '"%s"' % startdir,
        "icon": icon, "ShortcutPath": "", "LaunchOptions": "", "IsHidden": ("int", 0), "AllowDesktopConfig": ("int", 1),
        "AllowOverlay": ("int", 1), "OpenVR": ("int", 0), "Devkit": ("int", 0), "DevkitGameID": "",
        "DevkitOverrideAppID": ("int", 0), "LastPlayTime": ("int", 0), "FlatpakAppID": "", "tags": {},
    })
    print(appid)
out = b"\0shortcuts\0" + write_vdf({str(n): e for n, e in enumerate(entries)}) + b"\x08"
os.makedirs(os.path.dirname(path), exist_ok=True)
tmp = path + ".tmp"
open(tmp, "wb").write(out)
os.replace(tmp, path)
PY
}

# ---- uninstall -----------------------------------------------------------------------------------------------------
if [ "${1:-}" = "--uninstall" ]; then
    close_steam
    for root in $(steam_roots); do
        for vdf in "$root"/userdata/*/config/shortcuts.vdf; do
            [ -f "$vdf" ] || continue
            cp -p "$vdf" "$vdf.before-toontown-uninstall"
            edit_shortcuts remove "$vdf"
            say "Removed from Steam ($(basename "$(dirname "$(dirname "$vdf")")"))"
        done
    done
    rm -f "$DESKTOP_FILE"
    rm -rf "$DIR"
    say "Toontown: Anywhere is uninstalled. (Your toons are safe: they live on the server.)"
    exit 0
fi

# ---- a browser that can run the game as its own full-screen app ----------------------------------------------------
# Chromium-based browsers are preferred: they open a page as an app window and pass controllers to the game.
BROWSER_KIND="" BROWSER_CMD="" FLATPAK_ID=""
if command -v flatpak >/dev/null; then
    for id in com.google.Chrome org.chromium.Chromium com.microsoft.Edge com.brave.Browser; do
        if flatpak info "$id" >/dev/null 2>&1; then FLATPAK_ID="$id"; BROWSER_KIND=chromium; BROWSER_CMD="flatpak run $id"; break; fi
    done
fi
if [ -z "$BROWSER_KIND" ]; then
    for b in google-chrome google-chrome-stable chromium chromium-browser microsoft-edge brave-browser; do
        if command -v "$b" >/dev/null; then BROWSER_KIND=chromium; BROWSER_CMD="$(command -v "$b")"; break; fi
    done
fi
if [ -z "$BROWSER_KIND" ] && command -v flatpak >/dev/null; then
    if ask "No Chrome or Chromium found. Install Google Chrome from Flathub now? (recommended)"; then
        say "Installing Google Chrome (Flathub)..."
        flatpak install --user -y flathub com.google.Chrome || flatpak install -y flathub com.google.Chrome || true
        if flatpak info com.google.Chrome >/dev/null 2>&1; then
            FLATPAK_ID=com.google.Chrome; BROWSER_KIND=chromium; BROWSER_CMD="flatpak run com.google.Chrome"
        fi
    fi
fi
if [ -z "$BROWSER_KIND" ]; then
    if command -v flatpak >/dev/null && flatpak info org.mozilla.firefox >/dev/null 2>&1; then
        FLATPAK_ID=org.mozilla.firefox; BROWSER_KIND=firefox; BROWSER_CMD="flatpak run org.mozilla.firefox"
    elif command -v firefox >/dev/null; then
        BROWSER_KIND=firefox; BROWSER_CMD="$(command -v firefox)"
    fi
fi
[ -n "$BROWSER_KIND" ] || die "No supported browser found. Install Google Chrome or Chromium (Discover / Flathub) and run this again."
say "Using browser: $BROWSER_CMD"

# Flatpak browsers cannot see controllers unless they may read /run/udev (the usual Steam Deck fix)
if [ -n "$FLATPAK_ID" ] && [ "$BROWSER_KIND" = chromium ]; then
    flatpak override --user --filesystem=/run/udev:ro "$FLATPAK_ID" && say "Controllers enabled for $FLATPAK_ID"
fi

# ---- the launcher ----------------------------------------------------------------------------------------------------
mkdir -p "$DIR" "$(dirname "$DESKTOP_FILE")"
if [ -n "$FLATPAK_ID" ]; then
    PROFILE="$HOME/.var/app/$FLATPAK_ID/data/toontown-anywhere"       # inside the browser's sandbox, so it can write there
else
    PROFILE="$DIR/profile"
fi
mkdir -p "$PROFILE"
if [ "$BROWSER_KIND" = chromium ]; then
    RUN="$BROWSER_CMD --user-data-dir=\"$PROFILE\" --app=\"$URL\" --start-fullscreen --no-first-run --no-default-browser-check --autoplay-policy=no-user-gesture-required"
else
    RUN="$BROWSER_CMD --profile \"$PROFILE\" --no-remote --kiosk \"$URL\""
fi
cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
# Starts Toontown: Anywhere full screen (made by steam-linux.sh; run that again to update it)
exec $RUN "\$@"
EOF
chmod +x "$LAUNCHER"
say "Launcher: $LAUNCHER"

# ---- artwork -------------------------------------------------------------------------------------------------------
fetch() { curl -fsSL "$1" -o "$2" 2>/dev/null || wget -q "$1" -O "$2" 2>/dev/null; }
ICON="$DIR/icon.png"; ART="$DIR/background.jpg"
fetch "$SITE/play/icon-512.png" "$ICON" || warn "Could not download the icon (no internet?); Steam will use its default."
fetch "$SITE/_ui/background.jpg" "$ART" || warn "Could not download the artwork; Steam will use its default."

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=$NAME
Comment=Play Toontown in your browser
Exec=$LAUNCHER
Icon=$ICON
Terminal=false
Categories=Game;
EOF

# ---- add it to Steam -------------------------------------------------------------------------------------------------
ROOTS="$(steam_roots)"
[ -n "$ROOTS" ] || die "Steam's folder was not found. Start Steam once and sign in, then run this again."
close_steam
added=0
for root in $ROOTS; do
    for user in "$root"/userdata/*/; do
        user="${user%/}"; id="$(basename "$user")"
        case "$id" in ''|*[!0-9]*|0) continue ;; esac
        vdf="$user/config/shortcuts.vdf"
        [ -f "$vdf" ] && cp -p "$vdf" "$vdf.before-toontown"
        appid="$(edit_shortcuts add "$vdf" "$LAUNCHER" "$DIR/" "$ICON")"
        grid="$user/config/grid"; mkdir -p "$grid"
        if [ -f "$ART" ]; then
            cp "$ART" "$grid/${appid}_hero.jpg"         # the big banner on the game's page
            cp "$ART" "$grid/${appid}.jpg"              # the wide picture (recent games)
        fi
        if [ -f "$ICON" ]; then
            cp "$ICON" "$grid/${appid}p.png"            # the library tile (Steam fits the square icon in it)
            cp "$ICON" "$grid/${appid}_icon.png"
        fi
        say "Added to Steam for account $id"
        added=$((added + 1))
    done
done
[ "$added" -gt 0 ] || die "No Steam account found. Start Steam once and sign in, then run this again."

say "Done! Start Steam: \"$NAME\" is in your library (under Non-Steam)."
say "On a Steam Deck, switch back to Game Mode and find it in Library > Non-Steam."
say "Tip: in the game's Steam controller settings, the 'Gamepad' layout works best (the game has controller support)."
