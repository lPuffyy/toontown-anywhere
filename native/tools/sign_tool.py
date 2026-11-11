"""Release signing for the native app's updates.

    python tools/sign_tool.py keygen KEYFILE          make a signing key (KEYFILE holds the private key, keep it OUT of the repo and back it up
                                                      in two places); prints the public key to put in tta_native/updatekey.py
    python tools/sign_tool.py check KEYFILE           fail unless KEYFILE matches the public key built into the app
    python tools/sign_tool.py publish KEYFILE ZIP OUTDIR [--url URL] [--notes TEXT] [--min-version X.Y.Z]
                                                      write OUTDIR/windows.json and windows.json.sig (the zip's address is URL, e.g. its
                                                      GitHub release asset) and copy the zip beside them. The release workflow
                                                      (.github/workflows/native-release.yml) does this and attaches the files to the release.

The app checks the signature with the public key built into it before it trusts anything in windows.json, so only the holder of the
private key can push an update.
"""
import hashlib
import json
import os
import shutil
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))


def load_key(path):
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(open(path).read().strip()))


def keygen(path):
    if os.path.exists(path):
        sys.exit("refusing to overwrite " + path)
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    with open(path, "w") as f:
        f.write(raw.hex() + "\n")
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    print("private key written to", path, "(back it up in two places, never commit it)")
    print("public key (hex):", pub.hex())


def publish(keyfile, zip_path, outdir, notes="", min_version="", url=""):
    from tta_native import __version__
    key = load_key(keyfile)
    os.makedirs(outdir, exist_ok=True)
    name = os.path.basename(zip_path)
    sha = hashlib.sha256(open(zip_path, "rb").read()).hexdigest()
    manifest = {"version": __version__, "file": name, "size": os.path.getsize(zip_path), "sha256": sha, "notes": notes,
                "min_version": min_version or "", "url": url or ""}
    data = json.dumps(manifest, indent=1, sort_keys=True).encode("utf8")
    with open(os.path.join(outdir, "windows.json"), "wb") as f:
        f.write(data)
    with open(os.path.join(outdir, "windows.json.sig"), "w") as f:
        f.write(key.sign(data).hex())
    shutil.copyfile(zip_path, os.path.join(outdir, name))
    print("published", __version__, "to", outdir, "(upload the folder to <server>/native/)")


def check(keyfile):
    """Fails unless KEYFILE is the private half of the public key built into the app (an update signed with any other key would be refused
    by every installed app, so a release must never be made with one)."""
    from tta_native.updatekey import PUBLIC_KEY_HEX
    pub = load_key(keyfile).public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    if pub != PUBLIC_KEY_HEX:
        sys.exit("the signing key does not match tta_native/updatekey.py: installed apps would refuse this release")
    print("signing key matches the app's public key")


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == "check":
        check(a[1])
    elif len(a) == 2 and a[0] == "keygen":
        keygen(a[1])
    elif len(a) >= 4 and a[0] == "publish":
        notes = a[a.index("--notes") + 1] if "--notes" in a else ""
        minv = a[a.index("--min-version") + 1] if "--min-version" in a else ""
        url = a[a.index("--url") + 1] if "--url" in a else ""
        publish(a[1], a[2], a[3], notes, minv, url)
    else:
        print(__doc__)
