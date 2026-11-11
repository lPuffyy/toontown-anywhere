"""Entry point for the packaged app (PyInstaller needs a plain script, not a package's __main__)."""
import sys

from tta_native.app import main

if __name__ == "__main__":
    sys.exit(main())
