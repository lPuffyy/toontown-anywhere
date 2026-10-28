# Open Toontown, with our changes

This folder holds two things: our changes to [Open Toontown](https://github.com/open-toontown/open-toontown), and
`otpy`, the pure-Python replacement for the game's compiled libraries. The Open Toontown code itself is **not** copied
here, and neither are any game files (art, sound, models).

What the changes are, and why, is in [../docs/CHANGES.md](../docs/CHANGES.md).

## Contents

| Path | What it is |
|---|---|
| `patches/open-toontown-anywhere.patch` | All our changes, as a git patch against upstream commit `2b366a2`. |
| `patches/CHANGED_FILES.txt` | The files the patch touches (`M` changed, `A` added, `D` deleted). |
| `otpy/` | Pure-Python versions of `panda3d.otp` and `panda3d.toontown` (nametags, DNA, Cog paths, movement). |

## Get a patched checkout

```
git clone https://github.com/open-toontown/open-toontown.git
cd open-toontown
git checkout 2b366a2
git apply --whitespace=nowarn /path/to/this/repo/open-toontown/patches/open-toontown-anywhere.patch
```

`git apply --check` first if you want to see that it applies cleanly (it does on `2b366a2`).

The game's resource folders (`resources/phase_*`, `resources/models`) are not part of the upstream repository either; you
bring your own. Put them in `open-toontown/resources/`.

## Use it

- **Build the browser packs:** `OT_DIR=/path/to/open-toontown python ../web/make_ot_packs.py` (see
  [../docs/OPERATIONS.md](../docs/OPERATIONS.md)). It picks up `otpy` from this folder.
- **Run the server:** copy the patched checkout, `otpy/` (next to `toontown/`) and the Linux Astron files into the
  folder the container mounts as `/ot/src`. [../server/](../server) has the container.

## Regenerating the patch after more changes

Make the changes in your checkout, then, without touching the checkout's own index:

```
export GIT_INDEX_FILE=/tmp/ot_index
git read-tree HEAD
git -c core.autocrlf=input add -A -- . ':!resources' ':!astron/databases' ':!astron/logs' ':!logs' \
    ':!*.bak*' ':!**/__pycache__/**' ':!astron/win32' ':!astron/darwin'
git -c core.autocrlf=input diff --cached --binary > open-toontown-anywhere.patch
git -c core.autocrlf=input diff --cached --name-status > CHANGED_FILES.txt
unset GIT_INDEX_FILE
```

`core.autocrlf=input` matters on Windows: without it, files that only differ by line endings make the patch 100 times
bigger.

## Licence

The patch contains lines of Open Toontown's code and is under Open Toontown's **BSD 3-Clause** licence, copyright (c)
2019 Open Toontown, see [../THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md). `otpy` and everything else in this
repository is under the BSD 3-Clause License, see [../LICENSE](../LICENSE).
