import os, sys, json, hashlib
root = sys.argv[1] if len(sys.argv) > 1 else "."   # the folder your file server serves
files, code = [], []
for d, dirs, fs in os.walk(root):
    dirs[:] = [x for x in dirs if x not in (".git", "debug", "_packs", "_ui", "_app")]
    for f in fs:
        p = os.path.join(d, f)
        rel = os.path.relpath(p, root).replace(os.sep, "/")
        if rel in ("README.md", "mf_compile_extract.bat", "manifest.json", "packs.json") or rel.startswith(".git"):
            continue
        sz = os.path.getsize(p)
        if rel.startswith("_code/"):
            code.append([rel[len("_code/"):], sz, hashlib.md5(open(p, "rb").read()).hexdigest()])
        else:
            files.append([rel, sz])
json.dump({"files": files, "code": code}, open(os.path.join(root, "manifest.json"), "w"), separators=(",", ":"))
print(len(files), "resource files,", len(code), "code files")
