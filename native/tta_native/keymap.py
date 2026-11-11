"""Keyboard key remapping, the same behaviour as the browser version: the player's key for an action is turned into the game's own key for that
action (and the game's own keys keep working too). Keys are named the way Panda3D names them ('w', 'space', 'f8'); the spec lists the
game's key for each action. Nothing is remapped while a text box (chat, a name) has the focus."""
import traceback

from . import controls, inputs

MOVES = {"fwd": "fwd", "back": "back", "left": "left", "right": "right"}
_SAME = {"lcontrol": "control", "rcontrol": "control", "lalt": "alt", "ralt": "alt", "lshift": "shift", "rshift": "shift",
         "lmeta": "meta", "rmeta": "meta"}
_SHOWN = {"arrow_up": "Up", "arrow_down": "Down", "arrow_left": "Left", "arrow_right": "Right", "control": "Ctrl", "alt": "Alt", "shift": "Shift",
          "space": "Space", "backspace": "Backspace", "delete": "Delete", "enter": "Enter", "page_up": "Page Up", "page_down": "Page Down"}


def norm(button):
    name = getattr(button, "getName", lambda: str(button))()
    return _SAME.get(name, name)


def key_label(name):
    if name in _SHOWN:
        return _SHOWN[name]
    return name.upper() if len(name) <= 3 else name.replace("_", " ").title()


class KeyMap:
    def __init__(self, base, settings, spec):
        self.base = base
        self.settings = settings
        self.spec = spec
        self.actions = {a["id"]: a for a in spec["keys"]["actions"]}
        self.map = {}
        try:
            self.map = {k: v for k, v in dict(settings.get("keys") or {}).items() if v in self.actions}
        except Exception:
            self.map = {}
        self.held = {}
        self.capture = None            # callback taking the next key pressed (the keys card uses it)
        node = base.buttonThrowers[0].node()
        node.setButtonDownEvent("tta-btn-down")
        node.setButtonUpEvent("tta-btn-up")
        base.accept("tta-btn-down", self.down)
        base.accept("tta-btn-up", self.up)

    # ---- saved mapping
    def save(self):
        self.settings.set("keys", dict(self.map))

    def keys_for(self, action):
        return [k for k, v in self.map.items() if v == action]

    def assign(self, action, key):
        for k in [k for k, v in self.map.items() if v == action]:
            del self.map[k]
        if key != self.actions[action]["game_key"]:          # the game's own key needs no remap
            self.map[key] = action
        self.save()

    def reset(self):
        self.map = {}
        self.save()

    def use_wasd(self):
        wm = self.spec["keys"].get("wasd_map") or {}
        self.map = {k: v for k, v in wm.items() if v in self.actions}
        self.save()

    # ---- keys coming in
    def typing(self):
        try:
            return controls._focused_entry() is not None
        except BaseException:
            return False

    def down(self, button):
        name = norm(button)
        if self.capture is not None:
            cb, self.capture = self.capture, None
            cb(name)
            return
        action = self.map.get(name)
        if not action or self.typing():
            return
        self.held[name] = action
        self.fire(action, True)

    def up(self, button):
        action = self.held.pop(norm(button), None)
        if action:
            self.fire(action, False)

    def fire(self, action, down):
        try:
            if action in MOVES:
                inputs.set_dir("keys", MOVES[action], down)
            elif action == "jump":
                controls.ui_jump(down)
            elif action == "pie":
                controls.ui_action(down)
            elif action == "camera":
                if down:
                    controls.ui_camera()
            else:
                controls._send_keys((self.actions[action]["game_key"],), down)
        except BaseException:
            print("native: key action failed", traceback.format_exc())
