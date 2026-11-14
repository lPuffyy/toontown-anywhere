"""A small log that always reaches disk (logs/native.log in the data folder): one line per call, opened and closed each time, so it works
with no console and survives a crash. The game's own output goes to client.log."""
import os
import time


def note(msg):
    try:
        from .settings import data_dir
        d = os.path.join(data_dir(), "logs")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "native.log")
        if os.path.exists(p) and os.path.getsize(p) > 1024 * 1024:
            os.replace(p, p + ".old")
        with open(p, "a", encoding="utf8") as f:
            f.write("%s %s\n" % (time.strftime("%m-%d %H:%M:%S"), msg))
    except BaseException:
        pass
