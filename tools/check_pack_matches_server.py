"""Check that the protocol (DC) files in the code pack players download are the same as the ones the game server loaded.

A mismatch locks every player out ("Your installed files appear to be invalid", Astron error 125: DC hash mismatch), so run this
after changing etc/toon.dc or etc/otp.dc, once the pack is uploaded.

    python check_pack_matches_server.py https://toontown.puffsco.com /path/to/src/etc
(the second argument is the server's etc folder; on the server itself that is $ROOT/src/etc)
"""
import hashlib
import io
import os
import sys
import urllib.request
import zipfile

site, etc = sys.argv[1].rstrip("/"), sys.argv[2]
pack = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(site + "/_packs/_code.zip").read()))
bad = 0
for name in ("toon.dc", "otp.dc"):
    a = hashlib.md5(pack.read("_code/etc/" + name).replace(b"\r", b"")).hexdigest()[:8]
    b = hashlib.md5(open(os.path.join(etc, name), "rb").read().replace(b"\r", b"")).hexdigest()[:8]
    print("%-8s pack %s  server %s  %s" % (name, a, b, "ok" if a == b else "MISMATCH"))
    bad += a != b
sys.exit(1 if bad else 0)
