"""Walking directions from several places at once (the keyboard's remapped keys, a controller): a direction is held while any source holds it,
and the combined result goes to the game's own controls (controls.ui_move)."""
from . import controls

_held = {"fwd": set(), "back": set(), "left": set(), "right": set()}
_last = [(False, False, False, False)]


def set_dir(source, name, on):
    s = _held[name]
    if on:
        s.add(source)
    else:
        s.discard(source)
    _push()


def set_all(source, fwd, back, left, right):
    for name, on in (("fwd", fwd), ("back", back), ("left", left), ("right", right)):
        (_held[name].add if on else _held[name].discard)(source)
    _push()


def _push():
    state = tuple(bool(_held[n]) for n in ("fwd", "back", "left", "right"))
    if state != _last[0]:
        _last[0] = state
        controls.ui_move(*state)
