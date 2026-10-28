"""Connects the page's touch controls (ttr-ui.js) to the game: reads the control state every frame, drives the game through the
functions in webui_core.py, and tells the page what to show."""
import platform
import time
import traceback

import webui_core as core

T = platform.window.ttr
_state = {"vals": (0, 0, 0, 0, 0, 0, 0, 0), "cam": 0, "ui_at": 0.0, "ui": None, "tx_at": 0.0, "tx_on": False, "tx_in": 0, "tx_sub": 0}
try:
    core._hook_entries()            # remember the game's text boxes so the page's text bar can fill the focused one
except BaseException:
    print("webui: entry hook failed")
    print(traceback.format_exc())


_rc = {"since": 0.0, "tries": []}


def _auto_reconnect():
    """A phone drops the connection when the app is switched away from or the screen locks. When the player comes back and the game shows its
    "connection lost, try to connect again?" box, accept it for them (a few times at most), so they land back in Toontown."""
    try:
        import builtins
        b = getattr(builtins, "base", None)
        cr = getattr(b, "cr", None) if b is not None else None
        fsm = getattr(cr, "loginFSM", None) if cr is not None else None
        st = fsm.getCurrentState() if fsm is not None else None
        if st is None or st.getName() != "noConnection":
            _rc["since"] = 0.0
            return
        if getattr(cr, "bootedIndex", None) in (127, 152):       # thrown out on purpose: do not retry by ourselves
            return
        if str(platform.window.document.visibilityState) != "visible":
            return
        now = time.time()
        if not _rc["since"]:
            _rc["since"] = now
            return
        if now - _rc["since"] < 1.5:
            return
        _rc["tries"] = [t for t in _rc["tries"] if now - t < 180]
        if len(_rc["tries"]) >= 3:
            return
        _rc["tries"].append(now)
        _rc["since"] = 0.0
        box = getattr(cr, "lostConnectionBox", None)
        if box is not None:
            box.doneStatus = "ok"
        from direct.showbase.MessengerGlobal import messenger
        messenger.send("lostConnectionAck")
        print("webui: reconnecting automatically")
    except BaseException:
        print("webui: auto reconnect failed")
        print(traceback.format_exc())


def poll():
    _auto_reconnect()
    try:
        vals = tuple(int(x) for x in str(T.inp).split(","))
        if len(vals) == 8 and vals != _state["vals"]:
            old = _state["vals"]
            if vals[0:4] != old[0:4]:
                core.ui_move(*vals[0:4])
            if vals[4] != old[4]:
                core.ui_jump(vals[4])
            if vals[5] != old[5]:
                core.ui_action(vals[5])
            if vals[6] != old[6]:
                core.ui_pad(0, vals[6])
            if vals[7] != old[7]:
                core.ui_pad(1, vals[7])
            _state["vals"] = vals
        cam = int(T.camN)
        while _state["cam"] < cam:
            _state["cam"] += 1
            core.ui_camera()
        now = time.time()
        n_in = int(T.txtIn)
        if n_in != _state["tx_in"]:
            _state["tx_in"] = n_in
            core.ui_text_set(str(T.txtVal))
        n_sub = int(T.txtSub)
        if n_sub != _state["tx_sub"]:
            _state["tx_sub"] = n_sub
            core.ui_text_set(str(T.txtVal))
            core.ui_text_submit()
        if now - _state["tx_at"] > 0.12:
            _state["tx_at"] = now
            st = core.ui_text_state()
            on = st.startswith("1")
            if on != _state["tx_on"]:
                _state["tx_on"] = on
                try:
                    import builtins
                    b = builtins.base
                    print("webui: text", on, "win", b.win.getXSize(), b.win.getYSize(), "aspect2d scale", b.aspect2d.getScale())
                except BaseException:
                    pass
                T.setText(1 if on else 0, st[2:])
        if now - _state["ui_at"] > 0.25:
            _state["ui_at"] = now
            ui = (int(core.ui_controls_visible()), int(core.ui_action_available()), int(core.ui_tug_active()))
            if ui != _state["ui"]:
                _state["ui"] = ui
                T.setUI(*ui)
    except BaseException:
        print("webui: poll error")
        print(traceback.format_exc())
