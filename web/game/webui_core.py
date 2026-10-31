"""Touch-control logic: turns the page's thumb stick, jump and camera buttons into the game's own movement and camera calls."""
import os
import sys
import time
import traceback


def _input_state():
    from direct.showbase.InputStateGlobal import inputState
    return inputState


_dirs = {"forward": False, "reverse": False, "turnLeft": False, "turnRight": False}
_dir_keys = {"forward": ("arrow_up", "w"), "reverse": ("arrow_down", "s"),
             "turnLeft": ("arrow_left", "a"), "turnRight": ("arrow_right", "d")}


def _send_keys(names, down):
    import builtins
    m = getattr(builtins, "messenger", None)
    if m is None:
        return
    for n in names:
        m.send(n if down else n + "-up")


_CHAT_OPEN_STATES = ("normalChat", "whiteListOpenChat", "whiteListAvatarChat", "whiteListPlayerChat",
                     "whisperChat", "whisperChatPlayer")


def _cancel_chat_if_open():
    """Typed chat switches walking off until a message is sent or cancelled, and a phone has no Escape key.
    Touching the joystick or JUMP while it is open closes it and gives walking back."""
    try:
        import builtins
        la = getattr(builtins, "localAvatar", None)
        cm = getattr(la, "chatMgr", None)
        if cm is None:
            return
        st = cm.fsm.getCurrentState().getName()
        if st in _CHAT_OPEN_STATES:
            cm.fsm.request("mainMenu")
            ctl = getattr(la, "controlManager", None)
            # only give walking back if typed chat had taken it (never in the middle of a door, mailbox, etc.)
            if ctl is not None and not getattr(ctl, "isEnabled", 1):
                la.enableAvatarControls()
    except BaseException:
        print("chat cancel error", traceback.format_exc(), flush=True)


_unstick_last = [0.0]


def _unstick_walking():
    """The joystick is only shown while the player may walk. If the game still has walking switched off (seen after
    typed chat and after animated quick chats, until the Shticker Book was opened and closed), switch it back on."""
    try:
        import builtins
        import time
        la = getattr(builtins, "localAvatar", None)
        ctl = getattr(la, "controlManager", None)
        if ctl is None or getattr(ctl, "isEnabled", 1):
            return
        if _place_state() not in ("walk", "swim") or not _controls_visible():
            return
        now = time.time()
        if now - _unstick_last[0] < 1.0:
            return
        _unstick_last[0] = now
        cm = getattr(la, "chatMgr", None)
        cst = cm.fsm.getCurrentState().getName() if cm is not None and cm.fsm.getCurrentState() is not None else None
        print("walking was off with the joystick showing: re-enabling (chat=%s, emote=%s)" % (cst, getattr(la, "emoteTrack", None) is not None), flush=True)
        la.enableAvatarControls()
    except BaseException:
        print("unstick error", traceback.format_exc(), flush=True)


def ui_move(fwd, back, left, right):
    """Joystick: drive the same input states the arrow keys drive, and send the key events too
    (minigames read W/A/S/D and the arrow keys directly)."""
    try:
        if fwd or back or left or right:
            _cancel_chat_if_open()
            _unstick_walking()
        st = _input_state()
        for name, on in (("forward", fwd), ("reverse", back), ("turnLeft", left), ("turnRight", right)):
            on = bool(on)
            st.set(name, on, "touch")
            if _dirs[name] != on:
                _dirs[name] = on
                _send_keys(_dir_keys[name], on)
    except BaseException:
        print("ui_move error", traceback.format_exc(), flush=True)


def ui_jump(down):
    try:
        if down:
            _cancel_chat_if_open()
        _input_state().set("jump", bool(down), "touch")
        _send_keys(("space",), bool(down))
    except BaseException:
        print("ui_jump error", traceback.format_exc(), flush=True)


# ---- touch UI bridge: camera, action button, chat keyboard ------------------------------------

_entries = []


def _hook_entries():
    """Remember every DirectEntry so the native side can mirror the iOS keyboard into the focused one."""
    import weakref
    from direct.gui import DirectEntry as DE
    cls = DE.DirectEntry
    if getattr(cls, "_ios_hooked", False):
        return
    orig = cls.__init__

    def init(self, *a, **k):
        orig(self, *a, **k)
        _entries.append(weakref.ref(self))
    cls.__init__ = init
    cls._ios_hooked = True


def _focused_entry():
    found = None
    alive = []
    for r in _entries:
        e = r()
        if e is None:
            continue
        alive.append(r)
        try:
            if not e.isEmpty() and e.guiItem.getFocus() and not e.isHidden():
                found = e
        except BaseException:
            pass
    _entries[:] = alive
    return found


def ui_text_state():
    """'1|text' while a game text box has focus (native shows the keyboard), else '0|'."""
    try:
        e = _focused_entry()
        if e is None:
            return "0|"
        return "1|" + _plain_text(e).replace(chr(10), " ")
    except BaseException:
        return "0|"


def _plain_text(e):
    """The entry's text without its formatting: the chat box colours words that are not on the whitelist red by wrapping them in
    \\x01WLEnter\\x01 ... \\x02, which must never reach the page (it came back as the literal word "WLEnter")."""
    try:
        return e.get(plain=True)
    except TypeError:
        import re
        return re.sub("\x01[^\x01]*\x01|\x02", "", e.get())


def _refilter(e):
    """After the page sets the chat text, colour it again and decide again whether it may be sent, as typing in the box would."""
    try:
        import builtins
        cm = getattr(getattr(builtins, "localAvatar", None), "chatMgr", None)
        wl = getattr(cm, "chatInputWhiteList", None)
        if wl is not None and getattr(wl, "chatEntry", None) is e:
            wl.applyFilter(None)
    except BaseException:
        print("chat refilter error", traceback.format_exc(), flush=True)


def ui_text_set(text):
    try:
        e = _focused_entry()
        if e is not None:
            e.set(text)
            _refilter(e)
    except BaseException:
        print("ui_text_set error", traceback.format_exc(), flush=True)


def ui_text_submit():
    try:
        e = _focused_entry()
        if e is not None:
            e.commandFunc(None)
    except BaseException:
        print("ui_text_submit error", traceback.format_exc(), flush=True)


def ui_camera():
    """Camera button: the same as the Tab key (next camera position)."""
    try:
        import builtins
        la = getattr(builtins, "localAvatar", None)
        if la is not None:
            la.nextCameraPos(1)
    except BaseException:
        print("ui_camera error", traceback.format_exc(), flush=True)


_ACTION_NAMES = ("control", "delete", "insert", "alt")
_ACTION_OWNERS = {
    "DistributedCashbotBossCrane", "DistCogdoCrane", "DistributedBanquetTable", "DistributedGolfSpot",
    "DistributedVehicle", "DistributedCannonGame", "DistributedCogThiefGame", "DistributedPairingGame",
    "CogdoMazeLocalPlayer", "CogdoFlyingLocalPlayer", "DistributedPartyTrampolineActivity",
    "DistributedToonfestTrampolineActivity", "DistributedIceGame",
    "ArrowKeys",            # minigames that read the arrow keys and Control (vine swinging jumps with Control)
}
_action_down = [None]


def _action_key():
    """The key some game object (crane, banquet table, minigame...) is listening for, ignoring the plain
    movement/jump input that always listens to Control."""
    import builtins
    m = getattr(builtins, "messenger", None)
    if m is None:
        return None
    for name in _ACTION_NAMES:
        who = m.whoAccepts(name)
        if not who:
            continue
        for entry in list(who.values()):
            owner = getattr(entry[0], "__self__", None)
            if owner is None:
                continue
            # only the specific cranes, tables and minigames that really use an action key
            if any(c.__name__ in _ACTION_OWNERS for c in type(owner).__mro__):
                return name
    return None


def ui_action_available():
    try:
        return 1 if _action_key() else 0
    except BaseException:
        return 0


def _slingshot_active():
    """True while the Toon Slingshot minigame runs: there the parachute opens with "down" (down arrow / joystick back), not Control."""
    import builtins
    cr = getattr(getattr(builtins, "base", None), "cr", None)
    for do in list(getattr(cr, "doId2do", {}).values()):
        if type(do).__name__ == "DistributedTargetGame":
            return True
    return False


def ui_action(down):
    """ACTION button: press the key the current game is waiting for (Control, Delete, Insert or Alt)."""
    try:
        if down:
            _action_down[0] = "arrow_down" if _slingshot_active() else (_action_key() or "control")
            _send_keys((_action_down[0],), True)
        else:
            _send_keys((_action_down[0] or "control",), False)
            _action_down[0] = None
    except BaseException:
        print("ui_action error", traceback.format_exc(), flush=True)


def ui_tug_active():
    """1 while the tug-of-war minigame is being played (it needs fast alternating left/right presses)."""
    try:
        import builtins
        cr = getattr(getattr(builtins, "base", None), "cr", None)
        if cr is None:
            return 0
        for do in list(cr.doId2do.values()):
            if type(do).__name__ == "DistributedTugOfWarGame" and getattr(do, "arrowKeys", None):
                return 1
    except BaseException:
        pass
    return 0


def ui_pad(side, down):
    """Tug-of-war buttons: side 0 = left (A), 1 = right (D)."""
    try:
        _send_keys(("a", "arrow_left") if side == 0 else ("d", "arrow_right"), bool(down))
    except BaseException:
        print("ui_pad error", traceback.format_exc(), flush=True)

def _arrowkeys_active():
    """True while a minigame's ArrowKeys helper (W/A/S/D + Space) is listening."""
    import builtins
    m = getattr(builtins, "messenger", None)
    if m is None:
        return False
    for name in ("a", "d", "w", "s", "arrow_left", "arrow_right", "arrow_up", "arrow_down"):       # (Open Toontown's helper listens to the arrow keys)
        who = m.whoAccepts(name)
        if not who:
            continue
        for entry in list(who.values()):
            owner = getattr(entry[0], "__self__", None)
            if owner is not None and type(owner).__name__ == "ArrowKeys":
                return True
    return False


_last_ui_state = [None]


def _place_state():
    """Name of the current place state ('walk', 'stopped', 'stickerBook', ...), or None."""
    import builtins
    cr = getattr(getattr(builtins, "base", None), "cr", None)
    pg = getattr(cr, "playGame", None)
    place = getattr(pg, "place", None)
    fsm = getattr(place, "fsm", None)
    st = fsm.getCurrentState() if fsm is not None else None
    return st.getName() if st is not None else None


_vis_prev = [True]
_chat_prev = [None]


def _release_inputs():
    """The touch controls just disappeared (door, mailbox, menu...). A thumb still on the joystick will never send
    'released' to a hidden view, so let go of everything here or the toon keeps running when the controls return."""
    try:
        ui_move(0, 0, 0, 0)
        ui_jump(0)
        ui_action(0)
        ui_pad(0, 0)
        ui_pad(1, 0)
    except BaseException:
        print("release inputs error", traceback.format_exc(), flush=True)


def ui_controls_visible():
    v = _controls_visible()
    if _vis_prev[0] and not v:
        _release_inputs()
    _vis_prev[0] = bool(v)
    return v


_movies = {"set": None}


def _cogdo_movie_playing():
    """True while a Field Office intro / outro movie (the Toon Resistance panel) is playing: the buttons would cover its skip button."""
    try:
        if _movies["set"] is None:
            import weakref
            from toontown.cogdominium.CogdoUtil import CogdoGameMovie
            _movies["set"] = weakref.WeakSet()
            orig = CogdoGameMovie.play

            def play(self, *a, **k):
                _movies["set"].add(self)
                return orig(self, *a, **k)
            CogdoGameMovie.play = play
        for m in list(_movies["set"]):
            ival = getattr(m, "_ival", None)
            if ival is not None and ival.isPlaying():
                return True
    except BaseException:
        pass
    return False


def _controls_visible():
    """1 only while the player can actually move or act: hidden on the start screen, avatar chooser, Make-A-Toon
    and in menus/conversations (so the buttons never cover them)."""
    try:
        import builtins
        cr = getattr(getattr(builtins, "base", None), "cr", None)
        if cr is not None and getattr(cr, "avCreate", None):
            return 0
        la = getattr(builtins, "localAvatar", None)
        if la is None:
            return 0
        try:
            from toontown.friends import FriendsListPanel
            if FriendsListPanel.isFriendsListShown():
                return 0   # the friends panel is on the right side, where JUMP and CAM would cover it
        except BaseException:
            pass
        try:
            from otp.avatar import AvatarPanel
            if AvatarPanel.AvatarPanel.currentAvatarPanel is not None:
                return 0   # a friend / toon info panel is open
            from toontown.toon import ToonAvatarDetailPanel
            if ToonAvatarDetailPanel.globalAvatarDetail is not None:
                return 0   # the detailed toon info page is open
        except BaseException:
            pass
        if _cogdo_movie_playing():
            return 0
        cm = getattr(la, "chatMgr", None)
        if cm is not None:
            cst = cm.fsm.getCurrentState()
            cname = cst.getName() if cst is not None else None
            # typed chat switches walking off; leaving it for quick chat (instead of sending/cancelling) never
            # switches it back on, so the toon would not move until the Shticker Book is opened and closed
            if _chat_prev[0] in _CHAT_OPEN_STATES and cname not in _CHAT_OPEN_STATES:
                ctl = getattr(la, "controlManager", None)
                if ctl is not None and not getattr(ctl, "isEnabled", 1) and _place_state() in ("walk", "swim"):
                    la.enableAvatarControls()
                    print("re-enabled walking after typed chat", flush=True)
            _chat_prev[0] = cname
            if cname in ("speedChat", "whisperSpeedChat", "whisperSpeedChatPlayer"):
                return 0   # the quick chat menu covers the controls' area: keep it tappable
        state = _place_state()
        if state != _last_ui_state[0]:
            _last_ui_state[0] = state
            print("UI place state:", state, flush=True)
        if state in ("walk", "swim"):
            return 1
        if _action_key() or ui_tug_active() or _arrowkeys_active():
            return 1
        if state is None:
            cm = getattr(la, "controlManager", None)
            return 1 if (cm is not None and getattr(cm, "isEnabled", 0)) else 0
        return 0
    except BaseException:
        return 1

