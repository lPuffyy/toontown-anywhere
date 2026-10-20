"""M2 on-device test: import panda3d, make the iPhone display pipe. Returns a short text report."""
import os
import sys
import traceback


def run(frameworks):
    out = []

    def step(name, fn):
        try:
            out.append("OK   " + name + ": " + str(fn())[:80])
        except BaseException as e:
            tb = traceback.format_exc().strip().splitlines()
            out.append("FAIL " + name + ": " + (tb[-1] if tb else repr(e))[:230])

    out.append("python " + sys.version.split()[0])
    import_core = {}

    def imp_core():
        import panda3d.core as c
        import_core["c"] = c
        return c.PandaSystem.get_global_ptr().get_version_string()

    step("panda3d.core", imp_core)
    c = import_core.get("c")
    if c:
        def pipe():
            c.loadPrcFileData("", "plugin-path " + frameworks)
            c.loadPrcFileData("", "load-display pandagles")
            sel = c.GraphicsPipeSelection.get_global_ptr()
            p = sel.make_default_pipe()
            return "%s (types: %d)" % (p, sel.get_num_pipe_types())

        step("DISPLAY PIPE", pipe)
        step("panda3d.direct", lambda: __import__("panda3d.direct").direct)
        step("direct.showbase.DirectObject", lambda: __import__("direct.showbase.DirectObject").showbase.DirectObject)
        step("panda3d.physics", lambda: __import__("panda3d.physics").physics)
        step("panda3d.fx", lambda: __import__("panda3d.fx").fx)
        step("openssl", lambda: c.PandaSystem.get_global_ptr().has_system("OpenSSL"))
        step("freetype", lambda: c.PandaSystem.get_global_ptr().has_system("Freetype"))
        step("png image", lambda: c.PNMImage(4, 4).get_x_size())
    return "\n".join(out)
