"""Typed-chat helpers, the same behaviour as the browser version (web/tta-ui.js plainChat and web/game/webui_core.py):

* The game server rejects chat that is not plain text (curly quotes, long dashes, emoji, accented letters typed or pasted from elsewhere) and
  throws the player out with error 127. Whatever goes into the chat box is turned into plain characters the moment it appears, with the
  same replacements the browser uses; the chat box's red-word colouring is then redone for the cleaned text.
* The other chat helpers (typed chat giving walking back after quick chat, closing typed chat when the player starts walking with a
  controller, letting go of held controls when they disappear) live in controls.py, which is the browser's own code; poll() below runs the
  part the browser's page runs about four times a second.
"""
import re
import traceback

from . import controls

_SINGLE = re.compile("[‘’‚‛′]")
_DOUBLE = re.compile("[“”„″]")
_DASH = re.compile("[–—−]")
_SPACE = re.compile("[   ]")
_OTHER = re.compile("[^\x20-\x7E]")


def plain_chat(text):
    """Exactly plainChat() of the browser page."""
    t = _SINGLE.sub("'", str(text))
    t = _DOUBLE.sub('"', t)
    t = _DASH.sub("-", t)
    t = t.replace("…", "...")
    t = _SPACE.sub(" ", t)
    return _OTHER.sub("", t)


class ChatHelper:
    def __init__(self, base):
        self.base = base
        try:
            controls._hook_entries()          # remember every text box the game makes from now on (the chat boxes are made after sign-in)
        except BaseException:
            print("native: chat helper could not hook text boxes", traceback.format_exc())
        base.taskMgr.doMethodLater(0.1, self._clean, "tta-chat-plain")
        base.taskMgr.doMethodLater(0.25, self._poll, "tta-controls-poll")

    def _clean(self, task):
        try:
            e = controls._focused_entry()
            if e is not None:
                raw = e.get()
                clean = plain_chat(raw)
                if clean != raw:
                    e.enterText(clean)
                    controls._refilter(e)
        except BaseException:
            print("native: chat clean error", traceback.format_exc())
        return task.again

    def _poll(self, task):
        """What the browser's page asks the game every quarter second: whether the controls should show (this is also where walking is given
        back after typed chat and held controls are let go)."""
        try:
            controls.ui_controls_visible()
        except BaseException:
            print("native: controls poll error", traceback.format_exc())
        return task.again


def install(base):
    return ChatHelper(base)
