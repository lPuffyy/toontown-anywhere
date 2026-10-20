"""M3 on-device test: open a Panda window through the iPhone display and render a small scene."""
import traceback

_base = None
_err = []


def start(frameworks, resdir):
    global _base
    from panda3d.core import loadPrcFileData
    for line in ("plugin-path " + frameworks, "load-display pandagles", "audio-library-name null", "sync-video 0",
                 "window-type onscreen", "notify-level-display info", "default-directnotify-level warning"):
        loadPrcFileData("", line)
    from direct.showbase.ShowBase import ShowBase
    _base = ShowBase()
    from panda3d.core import CardMaker, TextNode
    from direct.gui.OnscreenText import OnscreenText

    cm = CardMaker("bg")
    cm.set_frame(-2, 2, -1, 1)
    bg = _base.render2d.attach_new_node(cm.generate())
    bg.set_color(0.1, 0.35, 0.8, 1)

    OnscreenText(text="Panda3D 1.10.11 on iPhone", pos=(0, 0.25), scale=0.12, fg=(1, 1, 1, 1))
    OnscreenText(text="window: %s" % (_base.win,), pos=(0, 0.05), scale=0.05, fg=(1, 1, 0.6, 1))

    # a spinning 3D card
    cm3 = CardMaker("card3d")
    cm3.set_frame(-1, 1, -1, 1)
    card = _base.render.attach_new_node(cm3.generate())
    card.set_pos(0, 8, 0)
    card.set_color(1, 0.6, 0.1, 1)
    card.set_two_sided(True)

    def spin(task):
        card.set_h(task.time * 90)
        return task.cont

    _base.task_mgr.add(spin, "spin")
    return "M3 OK window=%s size=%sx%s" % (_base.win, _base.win.get_x_size(), _base.win.get_y_size())


def step():
    if _base is None:
        return
    try:
        _base.task_mgr.step()
    except BaseException:
        if not _err:
            _err.append(traceback.format_exc())
            print(_err[0])
