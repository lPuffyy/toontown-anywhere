"""Replay the commands of a verbose host (macOS) makepanda build for the iPhone SDK, then build the
GLES1 + iPhone display module by hand.

  python replay.py <host_verbose.log> <panda3d dir> <ios python include dir> <ios deps prefix>

Compiles every object needed by the Panda3D libraries with `-arch arm64 -isysroot iPhoneOS`, links them again
for iOS (dylibs + python extension modules), reports errors per file (does not stop at the first failure).
"""
import concurrent.futures as cf
import os
import re
import shlex
import shutil
import subprocess
import sys

log, root, pyinc, deps = sys.argv[1:5]
log = os.path.abspath(log)
pyinc = os.path.abspath(pyinc)
deps = os.path.abspath(deps)
os.chdir(root)
SDK = subprocess.check_output(["xcrun", "--sdk", "iphoneos", "--show-sdk-path"], text=True).strip()
MINVER = "15.0"
HOSTDIR, IOSDIR = "built-host", "built-ios"
IOSFLAGS = ["-arch", "arm64", "-isysroot", SDK, "-miphoneos-version-min=" + MINVER]
RPATH = ["-Wl,-rpath,@executable_path/Frameworks", "-Wl,-rpath,@loader_path/../Frameworks"]

lines = [l.rstrip("\n") for l in open(log, errors="replace")]
# parallel compiler output can be interleaved before a command on the same line: find the command anywhere
CMD_RE = re.compile(r"(?:^|(?<=[\s:]))(clang\+\+|clang|libtool|cc|c\+\+) (?=-)")
cmds = []
for l in lines:
    m = CMD_RE.search(l)
    if m and (" -o " in l[m.start():]):
        cmds.append(l[m.start():])
    elif re.match(r"^ar ", l):
        cmds.append(l)
compiles, links, archives = {}, [], []
for c in cmds:
    t = shlex.split(c)
    if t[0].startswith(("clang", "cc", "c++")) and "-c" in t:
        if "-o" in t:
            compiles[t[t.index("-o") + 1]] = t
    elif any(a in t for a in ("-dynamiclib", "-bundle", "-shared")):
        links.append(t)
    elif t[0] in ("ar", "libtool"):
        archives.append(t)
arch_by_out = {}
for t in archives:
    outs = [a for a in t if a.endswith(".a")]
    if outs:
        arch_by_out[outs[0]] = t

sel_links = [t for t in links if t[t.index("-o") + 1].endswith((".dylib", ".so"))]
need = set()
for t in sel_links:
    for a in t:
        if a.endswith(".o"):
            need.add(a)
        if a.endswith(".a") and a in arch_by_out:
            for o in arch_by_out[a]:
                if o.endswith(".o"):
                    need.add(o)
print("links selected: %d, objects needed: %d, compile commands known: %d" % (len(sel_links), len(need), len(compiles)))


def map_path(p):
    return p.replace(HOSTDIR, IOSDIR)


BREW = re.compile(r"^-I(/opt/homebrew|/usr/local)")


def transform_compile(t):
    out = []
    i = 0
    while i < len(t):
        a = t[i]
        if a == "-o":
            out += ["-o", map_path(t[i + 1])]
            i += 2
            continue
        if a.startswith("-I") and "Python.framework" in a:
            out.append("-I" + pyinc)
        elif BREW.match(a):
            pass
        elif a.startswith("-mmacosx-version-min"):
            pass
        elif a == "-arch":
            i += 1
        else:
            out.append(a)
        i += 1
    out += ["-I" + deps + "/include", "-I" + deps + "/include/freetype2", "-DBUILD_IPHONE"]
    return [out[0]] + IOSFLAGS + out[1:]


def run(item):
    obj, t = item
    cmd = transform_compile(t)
    os.makedirs(os.path.dirname(map_path(obj)), exist_ok=True)
    r = subprocess.run(["xcrun", "--sdk", "iphoneos"] + cmd, capture_output=True, text=True)
    return obj, r.returncode, r.stderr


os.makedirs(IOSDIR + "/tmp", exist_ok=True)
os.makedirs(IOSDIR + "/lib", exist_ok=True)
os.makedirs(IOSDIR + "/panda3d", exist_ok=True)
todo = [(o, compiles[o]) for o in sorted(need) if o in compiles]
missing = [o for o in need if o not in compiles]
print("objects without a compile command:", len(missing), missing[:8])
fails = []
with cf.ThreadPoolExecutor(max_workers=int(os.environ.get("JOBS", "4"))) as ex:
    for obj, rc, err in ex.map(run, todo):
        if rc != 0:
            fails.append(obj)
            print("FAIL", obj)
            print("\n".join([l for l in err.splitlines() if "error" in l][:5]))
print("compile done: %d ok, %d failed" % (len(todo) - len(fails), len(fails)))

LIBMAP = {"libpng16": "-lpng16", "libpng": "-lpng16", "libfreetype": "-lfreetype", "libjpeg": "-ljpeg", "libz": "-lz", "libssl": "-lssl", "libcrypto": "-lcrypto",
          "libvorbisfile": "-lvorbisfile", "libvorbis": "-lvorbis", "libvorbisenc": "-lvorbisenc", "libogg": "-logg"}
DROP_FW = {"AppKit", "Cocoa", "Carbon", "OpenGL", "AGL", "IOKit", "ApplicationServices", "CoreServices", "AudioUnit", "CoreAudio"}


def transform_link(t):
    out = []
    i = 0
    while i < len(t):
        a = t[i]
        if a == "-o":
            out += ["-o", map_path(t[i + 1])]
            i += 2
            continue
        if a == "-install_name":
            out += ["-install_name", "@rpath/" + os.path.basename(t[i + 1])]
            i += 2
            continue
        if a == "-framework":
            fw = t[i + 1]
            if fw in DROP_FW:
                if fw == "AppKit":
                    out += ["-framework", "UIKit"]
            else:
                out += ["-framework", fw]
            i += 2
            continue
        if a.startswith("-L") and ("Python" in a or a.startswith(("-L/opt/homebrew", "-L/usr/local"))):
            i += 1
            continue
        m = re.match(r".*/(lib[a-z0-9]+?)[0-9.]*\.(dylib|a)$", a)
        if a.startswith("/opt/homebrew") and m and m.group(1) in LIBMAP:
            out.append(LIBMAP[m.group(1)])
            i += 1
            continue
        out.append(map_path(a))
        i += 1
    # static iOS libs do not pull in their own dependencies the way the macOS dylibs do
    if "-lvorbisfile" in out:
        i = out.index("-lvorbisfile")
        out[i + 1:i + 1] = [x for x in ("-lvorbis", "-logg") if x not in out]
    out += ["-L" + deps + "/lib", "-L" + IOSDIR + "/lib"] + RPATH
    if "-undefined" not in out:
        out += ["-undefined", "dynamic_lookup"]
    return [out[0]] + IOSFLAGS + out[1:]


def build_archive(t):
    out = [a for a in t if a.endswith(".a")][0]
    objs = [map_path(a) for a in t if a.endswith(".o")]
    os.makedirs(os.path.dirname(map_path(out)), exist_ok=True)
    if os.path.exists(map_path(out)):
        os.remove(map_path(out))
    r = subprocess.run(["xcrun", "--sdk", "iphoneos", "libtool", "-static", "-o", map_path(out)] + objs, capture_output=True, text=True)
    print("ARCHIVE", map_path(out), "rc=%d" % r.returncode, r.stderr[:200])


used_archives = {a for tt in sel_links for a in tt if a.endswith(".a")}
for out, t in arch_by_out.items():
    if out in used_archives and not any(o in fails for o in t if o.endswith(".o")):
        build_archive(t)

linked = 0
for t in sel_links:
    out = t[t.index("-o") + 1]
    objs = [a for a in t if a.endswith(".o")]
    if any(o in fails for o in objs):
        print("LINK SKIPPED (compile failures):", out)
        continue
    os.makedirs(os.path.dirname(map_path(out)), exist_ok=True)
    r = subprocess.run(["xcrun", "--sdk", "iphoneos"] + transform_link(t), capture_output=True, text=True)
    print("LINK", map_path(out), "rc=%d" % r.returncode)
    if r.returncode:
        print("\n".join(r.stderr.splitlines()[:8]))
    else:
        linked += 1
        base = map_path(out)
        short = re.sub(r"\.1\.10\.dylib$", ".dylib", base)
        if short != base:
            shutil.copy(base, short)
print("linked %d of %d" % (linked, len(sel_links)))

# ---- GLES1 + iPhone display, built by hand (makepanda has no iPhone target) ----
print("== building libpandagles (GLES1 + iPhone display)")
template = compiles.get("built-host/tmp/p3display_composite1.o") or next(iter(compiles.values()))
os.makedirs(IOSDIR + "/tmp/disp", exist_ok=True)
glue = IOSDIR + "/tmp/disp/pandagles_ios.cxx"
compat = os.path.abspath(IOSDIR + "/tmp/disp/panda_ios_compat.h")
open(compat, "w").write("""#include <stdint.h>
#include <string>
using std::string;
""")
open(glue, "w").write("""
#include "pandabase.h"
#define OPENGLES_1
#include "config_glesgsg.h"
#include "config_iphonedisplay.h"
#include "iPhoneGraphicsPipe.h"
#define PGL_EXPORT __attribute__((visibility("default")))
PGL_EXPORT void init_libpandagles() { init_libglesgsg(); init_libiphonedisplay(); }
extern "C" PGL_EXPORT int get_pipe_type_pandagles() { return IPhoneGraphicsPipe::get_class_type().get_index(); }
""")
sources = [("panda/src/glesgsg/config_glesgsg.cxx", False), ("panda/src/glesgsg/glesgsg.cxx", False), (glue, True)]
sources += [("panda/src/iphonedisplay/" + f, True) for f in sorted(os.listdir("panda/src/iphonedisplay")) if f.endswith(".mm")]
dobjs, dfail = [], 0
for src, objc in sources:
    obj = IOSDIR + "/tmp/disp/" + os.path.basename(src) + ".o"
    t = list(template)
    t[t.index("-o") + 1] = obj
    t[-1] = src
    cmd = transform_compile(t)
    extra = ["-DBUILDING_PANDAGLES", "-DBUILDING_MISC", "-DOPENGLES_1", "-Ipanda/src/glesgsg", "-Ipanda/src/glstuff",
             "-Ipanda/src/iphonedisplay", "-Ipanda/src/display", "-include", compat]
    if objc:
        extra += ["-x", "objective-c++", "-fno-objc-arc"]
    pos = 1 + len(IOSFLAGS)
    cmd = cmd[:pos] + extra + cmd[pos:]
    r = subprocess.run(["xcrun", "--sdk", "iphoneos"] + cmd, capture_output=True, text=True)
    print("DISPLAY", os.path.basename(src), "rc=%d" % r.returncode)
    if r.returncode:
        dfail += 1
        print("\n".join([l for l in r.stderr.splitlines() if "error" in l][:6]))
    else:
        dobjs.append(obj)
if dfail == 0:
    cmd = ["clang++"] + IOSFLAGS + ["-dynamiclib", "-install_name", "@rpath/libpandagles.dylib", "-o", IOSDIR + "/lib/libpandagles.dylib"] + dobjs + \
          ["-L" + IOSDIR + "/lib", "-lpanda", "-lpandaexpress", "-lp3dtool", "-lp3dtoolconfig", "-framework", "UIKit", "-framework", "Foundation",
           "-framework", "OpenGLES", "-framework", "QuartzCore", "-framework", "CoreGraphics", "-undefined", "dynamic_lookup"] + RPATH
    r = subprocess.run(["xcrun", "--sdk", "iphoneos"] + cmd, capture_output=True, text=True)
    print("LINK libpandagles.dylib rc=%d" % r.returncode)
    if r.returncode:
        print(r.stderr[:1500])
else:
    print("display module skipped: %d compile failures" % dfail)

print("== results")
for d in ("lib", "panda3d"):
    for f in sorted(os.listdir(os.path.join(IOSDIR, d))):
        p = os.path.join(IOSDIR, d, f)
        print(d + "/" + f, os.path.getsize(p) // 1024, "KB")
