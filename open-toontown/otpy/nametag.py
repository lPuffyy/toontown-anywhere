"""Pure-Python replacement for Open Toontown's compiled `panda3d.otp` nametag / chat-balloon / margin-popup classes.

Written from Open Toontown's own C++ source (panda/src/nametag, BSD-licensed).  Two things work differently from the C++:
  * Panda calls compiled virtual functions (cull callbacks, mouse-region callbacks) only for C++ classes, so the per-frame work is
    attached through CallbackNode cull callbacks, and mouse regions report through the MouseWatcher's event patterns.
  * Reference-count bookkeeping is left to Python.
"""
import math
import random

from panda3d.core import (
    BoundingSphere, CallbackNode, Camera, CardMaker, ClockObject, ColorAttrib, CullBinAttrib, CullBinManager, CullFaceAttrib, DecalEffect,
    DepthWriteAttrib, LMatrix4f, LPoint3f, LPoint4f, LVecBase2f, LVecBase4f, LVector3f, LineSegs, ModelNode, MouseWatcherRegion, NodePath,
    OmniBoundingVolume, PGButton, PandaNode, PerspectiveLens, PythonCallbackObject, SceneGraphReducer, TextNode, TransformState,
    TransparencyAttrib, lookAt,
)
from direct.showbase.DirectObject import DirectObject

from .dna import camel_aliases

# ---------------------------------------------------------------------------------------------------- flags
CF_speech = 0x0001
CF_thought = 0x0002
CF_quicktalker = 0x0004
CF_timeout = 0x0008
CF_page_button = 0x0010
CF_quit_button = 0x0020
CF_reversed = 0x0040
CF_snd_openchat = 0x0080
CF_no_quit_button = 0x0100
CFSpeech, CFThought, CFQuicktalker, CFTimeout, CFPageButton = CF_speech, CF_thought, CF_quicktalker, CF_timeout, CF_page_button
CFQuitButton, CFReversed, CFSndOpenchat, CFNoQuitButton = CF_quit_button, CF_reversed, CF_snd_openchat, CF_no_quit_button

S_ready, S_depressed, S_rollover, S_inactive = 0, 1, 2, 3

nametag_fixed_bin = "fixed"
_now = lambda: ClockObject.get_global_clock().get_frame_time()


def _messenger():
    import builtins
    m = getattr(builtins, "messenger", None)
    if m is None:
        from direct.showbase.MessengerGlobal import messenger as m
    return m


def _mul4(a, b):
    return LVecBase4f(a[0] * b[0], a[1] * b[1], a[2] * b[2], a[3] * b[3])


# ---------------------------------------------------------------------------------------------------- NametagGroup enums
class _CC:
    CC_normal, CC_no_chat, CC_non_player, CC_suit, CC_toon_building, CC_suit_building, CC_house_building, CC_speed_chat, CC_free_chat = range(9)
    CCNormal, CCNoChat, CCNonPlayer, CCSuit, CCToonBuilding, CCSuitBuilding, CCHouseBuilding, CCSpeedChat, CCFreeChat = range(9)


class _WT:
    WT_normal, WT_quick_talker, WT_system, WT_battle_SOS, WT_emote, WT_toontown_boarding_group = range(6)
    WTNormal, WTQuickTalker, WTSystem, WTBattleSOS, WTEmote, WTToontownBoardingGroup = range(6)


# ---------------------------------------------------------------------------------------------------- colors
def _C(*v):
    return LVecBase4f(*v)


class _Colors:
    def __init__(self, name_fg, name_bg, chat_fg, chat_bg):
        self._name_fg = name_fg
        self._name_bg = name_bg
        self._chat_fg = chat_fg
        self._chat_bg = chat_bg


def _tbl(rows):
    return [_Colors(*[_C(*c) for c in r]) for r in rows]


_arrow_colors = [_C(1.0, 0.4, 0.2, 1.0)] * 4 + [_C(0.3, 0.6, 1.0, 1.0), _C(0.55, 0.55, 0.55, 1.0), _C(0.3, 0.6, 1.0, 1.0), _C(0.3, 0.7, 0.3, 1.0), _C(0.3, 0.3, 0.7, 1.0)]

_normal_colors = _tbl([
    [(0, 0, 1, 1), (.8, .8, .8, .5), (0, 0, 0, 1), (1, 1, 1, 1)],
    [(.5, .5, 1, 1), (.2, .2, .2, .6), (1, .5, .5, 1), (1, 1, 1, 1)],
    [(.5, .5, 1, 1), (1, 1, 1, 1), (0, .6, .6, 1), (1, 1, 1, 1)],
    [(.3, .3, .7, 1), (.8, .8, .8, .5), (0, 0, 0, 1), (1, 1, 1, 1)]])
_no_chat_colors = _tbl([
    [(.8, .4, 0, 1), (1, 1, 1, .5), (0, 0, 0, 1), (1, 1, 1, 1)],
    [(1, .5, .5, 1), (.2, .2, .2, .6), (1, .5, .5, 1), (1, 1, 1, 1)],
    [(1, .5, 0, 1), (1, 1, 1, 1), (0, .6, .6, 1), (1, 1, 1, 1)],
    [(.6, .4, .2, 1), (.8, .8, .8, .5), (0, 0, 0, 1), (1, 1, 1, 1)]])
_non_player_colors = _tbl([
    [(.8, .4, 0, 1), (1, 1, 1, .5), (0, 0, 0, 1), (1, 1, 1, 1)],
    [(1, .5, .5, 1), (.2, .2, .2, .6), (1, .5, .5, 1), (1, 1, 1, 1)],
    [(1, .5, 0, 1), (1, 1, 1, 1), (0, .6, .6, 1), (1, 1, 1, 1)],
    [(.6, .4, .2, 1), (.8, .8, .8, .5), (0, 0, 0, 1), (1, 1, 1, 1)]])
_suit_colors = _tbl([
    [(0, 0, 0, 1), (.8, .8, .8, .5), (0, 0, 0, 1), (1, 1, 1, 1)],
    [(1, 1, 1, 1), (.2, .2, .2, .6), (.5, 1, .5, 1), (1, 1, 1, 1)],
    [(.5, .5, .5, 1), (1, 1, 1, 1), (.6, 0, .6, 1), (1, 1, 1, 1)],
    [(.2, .2, .2, 1), (.8, .8, .8, .5), (0, 0, 0, 1), (1, 1, 1, 1)]])
_toon_building_colors = _tbl([
    [(0, 0, 0, 1), (.8, .8, .8, .5), (0, 0, 0, 1), (1, 1, 1, 1)],
    [(1, 1, 1, 1), (.2, .2, .2, .6), (.5, 1, .5, 1), (1, 1, 1, 1)],
    [(.5, .5, .5, 1), (1, 1, 1, 1), (.6, 0, .6, 1), (1, 1, 1, 1)],
    [(.3, .6, 1, 1), (.8, .8, .8, .5), (0, 0, 0, 1), (1, 1, 1, 1)]])
_suit_building_colors = _tbl([
    [(0, 0, 0, 1), (.8, .8, .8, .5), (0, 0, 0, 1), (1, 1, 1, 1)],
    [(1, 1, 1, 1), (.2, .2, .2, .6), (.5, 1, .5, 1), (1, 1, 1, 1)],
    [(.5, .5, .5, 1), (1, 1, 1, 1), (.6, 0, .6, 1), (1, 1, 1, 1)],
    [(.55, .55, .55, 1), (.8, .8, .8, .5), (0, 0, 0, 1), (1, 1, 1, 1)]])
_speed_chat_colors = _tbl([
    [(0, .6, .2, 1), (1, 1, 1, .5), (0, 0, 0, 1), (1, 1, 1, 1)],
    [(0, .6, .2, 1), (.2, .2, .2, .6), (.5, 1, .5, 1), (1, 1, 1, 1)],
    [(0, 1, .5, 1), (1, 1, 1, 1), (.6, 0, .6, 1), (1, 1, 1, 1)],
    [(.1, .4, .2, 1), (.8, .8, .8, .5), (0, 0, 0, 1), (1, 1, 1, 1)]])
_free_chat_colors = _tbl([
    [(.3, .3, .7, 1), (.8, .8, .8, .5), (0, 0, 0, 1), (1, 1, 1, 1)],
    [(.2, .2, .5, 1), (.2, .2, .2, .6), (1, .5, .5, 1), (1, 1, 1, 1)],
    [(.5, .5, 1, 1), (1, 1, 1, 1), (0, .6, .6, 1), (1, 1, 1, 1)],
    [(.3, .3, .7, 1), (.8, .8, .8, .5), (0, 0, 0, 1), (1, 1, 1, 1)]])
_color_table = [_normal_colors, _no_chat_colors, _non_player_colors, _suit_colors, _toon_building_colors, _suit_building_colors, _toon_building_colors,
                _speed_chat_colors, _free_chat_colors]
_whisper_colors = _tbl([
    [(0, 0, 0, 1), (.8, .8, .8, .5), (0, 0, 0, 1), (.3, .6, .8, .6)],
    [(.5, .5, .5, 1), (.2, .2, .2, .6), (1, .5, .5, 1), (1, 1, 1, 1)],
    [(.5, .5, .5, 1), (1, 1, 1, 1), (0, 0, 0, 1), (.4, .8, 1, 1)],
    [(.3, .3, .3, 1), (.8, .8, .8, .5), (0, 0, 0, 1), (.3, .6, .8, .6)]])
_emote_whisper_colors = _tbl([
    [(0, 0, 0, 1), (.8, .8, .8, .5), (0, 0, 0, 1), (.3, .8, .3, .6)],
    [(.5, .5, .5, 1), (.2, .2, .2, .6), (1, .5, .5, 1), (1, 1, 1, 1)],
    [(.5, .5, .5, 1), (1, 1, 1, 1), (0, 0, 0, 1), (.4, 1, .4, 1)],
    [(.3, .3, .3, 1), (.8, .8, .8, .5), (0, 0, 0, 1), (.3, .8, .3, .6)]])
_system_colors = _tbl([
    [(0, 0, 0, 1), (.8, .8, .8, .5), (0, 0, 0, 1), (.8, .3, .6, .6)],
    [(.5, .5, .5, 1), (.2, .2, .2, .6), (1, .5, .5, 1), (1, 1, 1, 1)],
    [(.5, .5, .5, 1), (1, 1, 1, 1), (0, 0, 0, 1), (.8, .4, 1, 1)],
    [(.3, .3, .3, 1), (.8, .8, .8, .5), (0, 0, 0, 1), (.8, .3, .6, .6)]])
_boarding_group_colors = _tbl([
    [(0, 0, 0, 1), (.8, .8, .8, .5), (0, 0, 0, 1), (.97, .43, .1, .6)],
    [(.5, .5, .5, 1), (.2, .2, .2, .6), (1, .5, .5, 1), (1, 1, 1, 1)],
    [(.5, .5, .5, 1), (1, 1, 1, 1), (0, 0, 0, 1), (.98, .6, .38, .6)],
    [(.3, .3, .3, 1), (.8, .8, .8, .5), (0, 0, 0, 1), (.97, .43, .1, .6)]])
_whisper_color_table = [_whisper_colors, _whisper_colors, _system_colors, _system_colors, _emote_whisper_colors, _boarding_group_colors]


# ---------------------------------------------------------------------------------------------------- NametagGlobals
class NametagGlobals:
    billboard_offset = 3.0
    far_distance = 50.0
    far_scale = 0.56
    scale_exponent = 0.5
    arrow_scale = 0.5
    arrow_offset = 1.0
    card_pad = LVecBase4f(0.1, 0.1, 0.1, 0.0)
    nominal_avatar_width = 5.0
    name_wordwrap = 7.5
    building_name_wordwrap = 8.5
    house_name_wordwrap = 10.0
    chat_2d_wordwrap = 8.0
    chat_3d_wordwrap = 10.0
    balloon_internal_width = 9.0
    balloon_external_width = 10.0
    balloon_min_hscale = 0.25
    balloon_text_origin = LPoint3f(1.0, 0.0, 2.0)
    grid_count_horizontal = 6.0
    grid_count_vertical = 6.0
    grid_spacing_horizontal = 0.02
    grid_spacing_vertical = 0.02
    cell_memory_time = 30.0
    whisper_priority_time = 5.0
    whisper_total_time = 15.0
    button_delay_time = 0.2
    building_nametag_distance = 250.0     # (the playground guide arrows reach across the whole square)
    default_qt_color = LVecBase4f(0.8, 0.8, 1.0, 1.0)
    default_balloon_modulation_color = LVecBase4f(1.0, 1.0, 1.0, 1.0)
    margin_prop_seq = 0

    _camera = NodePath()
    _toon = NodePath()
    _arrow_model = NodePath()
    _page_button = [NodePath(), NodePath(), NodePath(), NodePath()]
    _quit_button = [NodePath(), NodePath(), NodePath(), NodePath()]
    _nametag_card = NodePath()
    _nametag_card_frame = LVecBase4f(0, 0, 0, 0)
    _rollover_sound = None
    _click_sound = None
    _mouse_watcher = None
    _text_node = None
    _speech_balloon_2d = None
    _thought_balloon_2d = None
    _speech_balloon_3d = None
    _thought_balloon_3d = None
    _master_nametags_active = True
    _master_nametags_visible = True
    _master_arrows_on = True
    _onscreen_chat_forced = False
    _max_2d_alpha = 0.6
    _min_2d_alpha = 0.0
    _global_nametag_scale = 1.0
    _balloon_modulation_color = LVecBase4f(1, 1, 1, 1)

    @staticmethod
    def get_name_wordwrap(): return NametagGlobals.name_wordwrap
    @staticmethod
    def get_card_pad(): return NametagGlobals.card_pad
    @staticmethod
    def set_camera(n): NametagGlobals._camera = n
    @staticmethod
    def get_camera(): return NametagGlobals._camera
    @staticmethod
    def set_toon(n): NametagGlobals._toon = n
    @staticmethod
    def get_toon(): return NametagGlobals._toon
    @staticmethod
    def set_arrow_model(n): NametagGlobals._arrow_model = n
    @staticmethod
    def get_arrow_model(): return NametagGlobals._arrow_model
    @staticmethod
    def set_page_button(state, n): NametagGlobals._page_button[state] = n
    @staticmethod
    def get_page_button(state): return NametagGlobals._page_button[state]
    @staticmethod
    def set_quit_button(state, n): NametagGlobals._quit_button[state] = n
    @staticmethod
    def get_quit_button(state): return NametagGlobals._quit_button[state]

    @staticmethod
    def set_nametag_card(n, frame):
        NametagGlobals._nametag_card = n
        NametagGlobals._nametag_card_frame = LVecBase4f(frame)

    @staticmethod
    def get_nametag_card(): return NametagGlobals._nametag_card
    @staticmethod
    def get_nametag_card_frame(): return NametagGlobals._nametag_card_frame
    @staticmethod
    def set_rollover_sound(s): NametagGlobals._rollover_sound = s
    @staticmethod
    def get_rollover_sound(): return NametagGlobals._rollover_sound
    @staticmethod
    def set_click_sound(s): NametagGlobals._click_sound = s
    @staticmethod
    def get_click_sound(): return NametagGlobals._click_sound

    @staticmethod
    def set_mouse_watcher(w):
        NametagGlobals._mouse_watcher = w
        if w is not None:
            # the compiled version gets mouse callbacks directly; here the regions report through the watcher's event patterns
            for getter, setter, pattern in (("get_enter_pattern", "set_enter_pattern", "otpy-enter-%r"), ("get_leave_pattern", "set_leave_pattern", "otpy-leave-%r"),
                                            ("get_button_down_pattern", "set_button_down_pattern", "otpy-down-%r"),
                                            ("get_button_up_pattern", "set_button_up_pattern", "otpy-up-%r")):
                if not getattr(w, getter)():
                    getattr(w, setter)(pattern)

    @staticmethod
    def get_mouse_watcher(): return NametagGlobals._mouse_watcher
    @staticmethod
    def set_speech_balloon_2d(b): NametagGlobals._speech_balloon_2d = b
    @staticmethod
    def get_speech_balloon_2d(): return NametagGlobals._speech_balloon_2d
    @staticmethod
    def set_thought_balloon_2d(b): NametagGlobals._thought_balloon_2d = b
    @staticmethod
    def get_thought_balloon_2d(): return NametagGlobals._thought_balloon_2d
    @staticmethod
    def set_speech_balloon_3d(b): NametagGlobals._speech_balloon_3d = b
    @staticmethod
    def get_speech_balloon_3d(): return NametagGlobals._speech_balloon_3d
    @staticmethod
    def set_thought_balloon_3d(b): NametagGlobals._thought_balloon_3d = b
    @staticmethod
    def get_thought_balloon_3d(): return NametagGlobals._thought_balloon_3d
    @staticmethod
    def set_master_nametags_active(a): NametagGlobals._master_nametags_active = bool(a)
    @staticmethod
    def get_master_nametags_active(): return NametagGlobals._master_nametags_active
    @staticmethod
    def set_master_nametags_visible(v): NametagGlobals._master_nametags_visible = bool(v)
    @staticmethod
    def get_master_nametags_visible(): return NametagGlobals._master_nametags_visible
    @staticmethod
    def set_master_arrows_on(a): NametagGlobals._master_arrows_on = bool(a)
    @staticmethod
    def get_master_arrows_on(): return NametagGlobals._master_arrows_on
    @staticmethod
    def set_onscreen_chat_forced(a): NametagGlobals._onscreen_chat_forced = bool(a)
    @staticmethod
    def get_onscreen_chat_forced(): return NametagGlobals._onscreen_chat_forced

    @staticmethod
    def set_max_2d_alpha(a):
        NametagGlobals._max_2d_alpha = a
        NametagGlobals.margin_prop_seq += 1

    @staticmethod
    def get_max_2d_alpha(): return NametagGlobals._max_2d_alpha

    @staticmethod
    def set_min_2d_alpha(a):
        NametagGlobals._min_2d_alpha = a
        NametagGlobals.margin_prop_seq += 1

    @staticmethod
    def get_min_2d_alpha(): return NametagGlobals._min_2d_alpha
    @staticmethod
    def set_global_nametag_scale(s): NametagGlobals._global_nametag_scale = s
    @staticmethod
    def get_global_nametag_scale(): return NametagGlobals._global_nametag_scale
    @staticmethod
    def get_name_fg(color_code, state): return NametagGlobals.get_colors(color_code, state)._name_fg
    @staticmethod
    def get_name_bg(color_code, state): return NametagGlobals.get_colors(color_code, state)._name_bg
    @staticmethod
    def get_balloon_modulation_color(): return NametagGlobals._balloon_modulation_color
    @staticmethod
    def set_balloon_modulation_color(c): NametagGlobals._balloon_modulation_color = LVecBase4f(c)

    @staticmethod
    def get_text_node():
        if NametagGlobals._text_node is None:
            NametagGlobals._text_node = TextNode("nametag")
        return NametagGlobals._text_node

    @staticmethod
    def get_arrow_color(color_code): return _arrow_colors[color_code]
    @staticmethod
    def get_colors(color_code, state): return _color_table[color_code][state]
    @staticmethod
    def get_whisper_colors(type_, state): return _whisper_color_table[type_][state]


# ---------------------------------------------------------------------------------------------------- mouse-region plumbing
_region_counter = [0]


class ClickablePopup:
    """Mixin: a popup that can be rolled over / pressed / clicked through a MouseWatcherRegion."""

    def upcastToPandaNode(self):
        """The C++ nametags are PandaNodes the game attaches with attachNewNode(tag.upcastToPandaNode()); ours already are."""
        return self

    upcast_to_PandaNode = upcastToPandaNode

    def _init_clickable(self):
        self._pstate = S_ready
        self._region = None
        self._region_name = ""
        self._region_events = None
        self._hovered = False
        self._pressed = False

    # state (named so it does not hide PandaNode.get_state / set_state)
    def get_popup_state(self): return self._pstate

    def set_popup_state(self, state):
        if self._pstate != state:
            self._pstate = state
            self.update_contents()

    def update_contents(self): pass
    def click(self): pass

    def enter_region(self, param=None):
        s = NametagGlobals.get_rollover_sound()
        if s is not None:
            s.play()
        self.set_popup_state(S_rollover)

    def exit_region(self, param=None):
        self.set_popup_state(S_ready)

    def press(self, param=None):
        s = NametagGlobals.get_click_sound()
        if s is not None:
            s.play()
        self.set_popup_state(S_depressed)

    def release(self, outside=False):
        if outside:
            self.set_popup_state(S_ready)
        else:
            self.set_popup_state(S_rollover)
            self.click()

    # region management -------------------------------------------------------------------------------
    def _make_region(self, name, frame):
        _region_counter[0] += 1
        self._region_name = "otpy-%d" % _region_counter[0]
        self._region = MouseWatcherRegion(self._region_name, LVecBase4f(*frame)[0], frame[1], frame[2], frame[3])
        self._region.set_active(True)

    def _hook_events(self):
        if self._region_events is not None:
            return
        ev = DirectObject()
        self._region_events = ev
        n = self._region_name
        ev.accept("otpy-enter-" + n, self._on_enter)
        ev.accept("otpy-leave-" + n, self._on_leave)
        ev.accept("otpy-down-" + n, self._on_down)
        ev.accept("otpy-up-" + n, self._on_up)

    def _unhook_events(self):
        if self._region_events is not None:
            self._region_events.ignore_all()
            self._region_events = None
        self._hovered = False
        self._pressed = False

    def _on_enter(self, *a):
        self._hovered = True
        self.enter_region()

    def _on_leave(self, *a):
        self._hovered = False
        self.exit_region()

    def _on_down(self, region, button=None, *a):
        if button is None or str(button) == "mouse1":
            self._pressed = True
            self.press()

    def _on_up(self, region, button=None, *a):
        if (button is None or str(button) == "mouse1") and self._pressed:
            self._pressed = False
            self.release(not self._hovered)


# ---------------------------------------------------------------------------------------------------- ChatBalloon
class ChatBalloon:
    def __init__(self, root_node):
        self._hscale = 0.0
        self._text_height = 0.0
        self._text_frame = LVecBase4f(0, 0, 0, 0)
        self._parent = None
        self._top_node = self._middle_node = self._bottom_node = None
        self._top_mat = LMatrix4f()
        self._middle_mat = LMatrix4f()
        if not self._scan(root_node):
            print("nametag: ChatBalloon found no chatBalloon geometry")

    def get_hscale(self): return self._hscale
    def get_text_height(self): return self._text_height
    def get_text_frame(self): return self._text_frame

    def _scan(self, node):
        if node.get_name() == "chatBalloon":
            return self._scan_balloon(node)
        for i in range(node.get_num_children()):
            if self._scan(node.get_child(i)):
                return True
        return False

    def _scan_balloon(self, node):
        self._parent = node.copy_subgraph()
        self._top_node = self._middle_node = self._bottom_node = None
        for i in range(self._parent.get_num_children()):
            child = self._parent.get_child(i)
            name = child.get_name()
            if name == "top":
                self._top_node = child
                self._top_mat = LMatrix4f(child.get_transform().get_mat())
            elif name == "middle":
                self._middle_node = child
                self._middle_mat = LMatrix4f(child.get_transform().get_mat())
            elif name == "bottom":
                self._bottom_node = child
        if self._top_node is None or self._middle_node is None or self._bottom_node is None:
            print("nametag: ChatBalloon geometry does not include top, middle, and bottom nodes.")
            return False
        return True

    @staticmethod
    def _find_geom_node(parent):
        if parent.is_geom_node():
            return parent
        for i in range(parent.get_num_children()):
            f = ChatBalloon._find_geom_node(parent.get_child(i))
            if f is not None:
                return f
        return None

    @staticmethod
    def _find_middle_geom(parent):
        for i in range(parent.get_num_children()):
            child = parent.get_child(i)
            if child.get_name() == "middle":
                return ChatBalloon._find_geom_node(child)
            r = ChatBalloon._find_middle_geom(child)
            if r is not None:
                return r
        return None

    def generate(self, text, font, wordwrap, text_color, balloon_color, for_3d, has_draw_order, draw_order, page_button, space_for_button, reversed_,
                 new_button=None):
        """Returns (root node, new button NodePath)."""
        root = PandaNode("chat")
        root.set_attrib(CullFaceAttrib.make(CullFaceAttrib.M_cull_none))
        text_node = NametagGlobals.get_text_node()
        text_node.set_font(font)
        text_node.set_wordwrap(wordwrap)
        text_node.set_align(TextNode.A_left)
        text_node.set_text(text)
        xoffset = NametagGlobals.balloon_text_origin[0]
        if reversed_:
            xoffset += NametagGlobals.balloon_internal_width
        self._hscale = text_node.get_width() / NametagGlobals.balloon_internal_width
        if self._hscale < NametagGlobals.balloon_min_hscale:
            self._hscale = NametagGlobals.balloon_min_hscale
            text_node.set_align(TextNode.A_center)
            if reversed_:
                xoffset -= NametagGlobals.balloon_internal_width * 0.5
            else:
                xoffset += NametagGlobals.balloon_internal_width * 0.5
        if reversed_:
            self._hscale = -self._hscale
        self._text_frame = LVecBase4f(text_node.get_card_actual())
        button_space = 0.2 if space_for_button else 0.0
        num_lines = max(text_node.get_num_rows(), 1)
        line_height = text_node.get_line_height()
        self._text_height = num_lines * line_height + button_space
        text_height_below = (num_lines - 1) * line_height + button_space
        parent_mat = LMatrix4f.scale_mat(self._hscale, 1.0, 1.0)
        middle_mat = LMatrix4f.scale_mat(1.0, 1.0, self._text_height) * self._middle_mat
        top_mat = LMatrix4f.translate_mat(0.0, 0.0, self._text_height - 1.0) * self._top_mat
        text_trans = LVector3f(xoffset * self._hscale, 0.0, NametagGlobals.balloon_text_origin[2] + text_height_below + 0.2)
        self._text_frame = LVecBase4f(self._text_frame[0] + text_trans[0], self._text_frame[1] + text_trans[0],
                                      self._text_frame[2] + text_trans[2], self._text_frame[3] + text_trans[2])
        if self._top_node is not None:
            self._top_node.set_transform(TransformState.make_mat(top_mat))
        if self._middle_node is not None:
            self._middle_node.set_transform(TransformState.make_mat(middle_mat))
        parent = self._parent.copy_subgraph()
        root.add_child(parent)
        parent.set_transform(TransformState.make_mat(parent_mat))
        if has_draw_order:
            parent.set_attrib(CullBinAttrib.make(nametag_fixed_bin, draw_order))
        parent.set_attrib(ColorAttrib.make_flat(balloon_color))
        if balloon_color[3] != 1.0:
            parent.set_attrib(TransparencyAttrib.make(TransparencyAttrib.M_alpha))
        reducer = SceneGraphReducer()
        reducer.apply_attribs(parent)
        reducer.flatten(root, -1)
        text_geom_node = text_node.generate()
        text_node.clear_text()
        text_geom_node.set_attrib(DepthWriteAttrib.make(DepthWriteAttrib.M_off))
        if for_3d:
            text_parent_node = self._find_middle_geom(root)
            if text_parent_node is None:
                text_parent_node = self._find_geom_node(root)
            if text_parent_node is None:
                print("nametag: chat balloon has no geometry to decal the text onto")
                return root, NodePath()
            text_parent_node.set_effect(DecalEffect.make())
        else:
            text_parent_node = root
            if has_draw_order:
                text_geom_node.set_attrib(CullBinAttrib.make(nametag_fixed_bin, draw_order + 1))
        text_parent = NodePath(text_parent_node)
        text_geom = text_parent.attach_new_node(text_geom_node)
        text_trans[1] -= 0.01                                   # panda_depth_hack is on
        text_geom.set_pos(text_trans)
        text_geom.set_color(text_color)
        if text_color[3] != 1.0:
            text_geom.set_transparency(TransparencyAttrib.M_alpha)
        new_button_np = NodePath()
        if page_button is not None and not page_button.is_empty():
            new_button_np = text_parent.attach_new_node(ModelNode("button"))
            button = page_button.copy_to(new_button_np)
            if reversed_:
                button.set_pos(self._hscale * 1.7, 0.0, 1.8)
            else:
                button.set_pos(self._hscale * NametagGlobals.balloon_internal_width, 0.0, 1.8)
            button.set_scale(8.0)
            button.set_y(-0.01)
        reducer.apply_attribs(text_geom_node)
        reducer.flatten(root, 1)
        return root, new_button_np


# ---------------------------------------------------------------------------------------------------- MarginPopup / MarginManager
def _cull_cb(fn):
    """Wrap a Python method as a cull callback that continues the traversal afterwards."""
    def run(cbdata):
        try:
            fn(cbdata)
        except Exception:                               # noqa
            import traceback
            traceback.print_exc()
        cbdata.upcall()
    return PythonCallbackObject(run)


class MarginPopup(CallbackNode):
    def __init__(self):
        CallbackNode.__init__(self, "")
        self._managed = False
        self._visible = False
        self._cell_width = 1.0
        self._master_margin_prop_seq = NametagGlobals.margin_prop_seq
        self._this_np = NodePath()

    def get_score(self): return 0.0
    def get_object_code(self): return 0
    def is_managed(self): return self._managed
    def is_visible(self): return self._visible
    def get_cell_width(self): return self._cell_width
    def update_contents(self): pass
    def frame_callback(self): pass
    def consider_manage(self): return True

    def consider_visible(self):
        if self._master_margin_prop_seq != NametagGlobals.margin_prop_seq:
            self._master_margin_prop_seq = NametagGlobals.margin_prop_seq
            self.update_contents()
        return True

    def set_managed(self, flag):
        self._managed = flag
        self._this_np = NodePath(self) if flag else NodePath()

    def set_visible(self, flag):
        self._visible = flag


class _PopupInfo:
    __slots__ = ("cell_index", "wants_visible", "score", "code")

    def __init__(self):
        self.cell_index = -1
        self.wants_visible = False
        self.score = 0.0
        self.code = 0


class _Cell:
    __slots__ = ("mat", "width", "is_available", "np", "popup", "popup_code", "hide_time")

    def __init__(self):
        self.mat = LMatrix4f()
        self.width = 1.0
        self.is_available = True
        self.np = NodePath()
        self.popup = None
        self.popup_code = 0
        self.hide_time = 0.0


class MarginManager(CallbackNode):
    def __init__(self):
        CallbackNode.__init__(self, "popups")
        self.set_cull_callback(_cull_cb(lambda cbdata: self.update()))
        self.set_bounds(OmniBoundingVolume())
        self.set_final(True)
        self._popups = {}
        self._popups_by_code = {}
        self._cells = []
        self._num_available_cells = 0
        self._show_cells = NodePath()

    def add_grid_cell(self, x, y, screen_left, screen_right, screen_bottom, screen_top):
        cell_width = (screen_right - screen_left) / NametagGlobals.grid_count_horizontal
        cell_height = (screen_top - screen_bottom) / NametagGlobals.grid_count_vertical
        left = screen_left + x * cell_width
        right = left + cell_width
        bottom = screen_bottom + y * cell_height
        top = bottom + cell_height
        hm = NametagGlobals.grid_spacing_horizontal * 0.5
        vm = NametagGlobals.grid_spacing_vertical * 0.5
        return self.add_cell(left + hm, right - hm, bottom + vm, top - vm)

    def add_cell(self, left, right, bottom, top):
        vert_scale = (top - bottom) * 0.5
        mat = LMatrix4f.scale_mat(vert_scale, vert_scale, vert_scale)
        mat.set_row(3, LVector3f((left + right) * 0.5, 0.0, (bottom + top) * 0.5))
        cell = _Cell()
        cell.mat = mat
        cell.width = ((right - left) * 0.5) / vert_scale
        self._cells.append(cell)
        self._num_available_cells += 1
        return len(self._cells) - 1

    def clear_cells(self):
        """Forget every cell (the screen shape changed and they are about to be laid out again)."""
        for i in range(len(self._cells)):
            try:
                if not self._cells[i].np.is_empty():
                    self._hide(i)
            except Exception:
                pass
        self._cells = []
        self._num_available_cells = 0

    def get_num_cells(self):
        return len(self._cells)

    def set_cell_available(self, cell_index, available):
        if not 0 <= cell_index < len(self._cells):
            return
        cell = self._cells[cell_index]
        if cell.is_available:
            self._num_available_cells -= 1
        cell.is_available = bool(available)
        if cell.is_available:
            self._num_available_cells += 1
        if not cell.np.is_empty():
            self._hide(cell_index)
            cell.popup = None
            cell.popup_code = 0

    def get_cell_available(self, cell_index):
        return self._cells[cell_index].is_available if 0 <= cell_index < len(self._cells) else False

    def show_cells(self):
        self.hide_cells()
        lines = LineSegs()
        for cell in self._cells:
            lines.set_color(0.5, 0.2, 1.0) if cell.is_available else lines.set_color(0.5, 0.5, 0.5)
            w = cell.width
            pts = [LPoint3f(-w, 0, 1), LPoint3f(-w, 0, -1), LPoint3f(w, 0, -1), LPoint3f(w, 0, 1), LPoint3f(-w, 0, 1)]
            lines.move_to(cell.mat.xform_point(pts[0]))
            for p in pts[1:]:
                lines.draw_to(cell.mat.xform_point(p))
        self._show_cells = NodePath(self).attach_new_node(lines.create())

    def hide_cells(self):
        self._show_cells.remove_node()

    def manage_popup(self, popup):
        popup.set_managed(True)
        info = _PopupInfo()
        info.code = popup.get_object_code()
        self._popups[popup] = info
        if info.code != 0:
            self._popups_by_code.setdefault(info.code, set()).add(popup)

    def unmanage_popup(self, popup):
        info = self._popups.get(popup)
        if info is None:
            return
        if info.cell_index >= 0:
            self._hide(info.cell_index)
        popup.set_managed(False)
        if info.code != 0:
            self._popups_by_code.get(info.code, set()).discard(popup)
        del self._popups[popup]

    def update(self):
        for popup in list(self._popups):
            info = self._popups[popup]
            if not popup.consider_manage():
                if info.cell_index >= 0:
                    self._hide(info.cell_index)
                popup.set_managed(False)
                if info.code != 0:
                    self._popups_by_code.get(info.code, set()).discard(popup)
                del self._popups[popup]
            else:
                info.wants_visible = popup.consider_visible()
                if info.wants_visible and info.code != 0:
                    info.score = popup.get_score()
        num_visible = 0
        any_new_visible = False
        for popup, info in list(self._popups.items()):
            if info.wants_visible and info.code != 0:
                popup_set = self._popups_by_code.get(info.code, set())
                if len(popup_set) > 1:
                    best_score = info.score
                    best_popup = popup
                    for tp in popup_set:
                        ti = self._popups.get(tp)
                        if ti is not None and ti.wants_visible and ti.score > best_score:
                            best_score = ti.score
                            best_popup = tp
                    for tp in popup_set:
                        ti = self._popups.get(tp)
                        if ti is not None and tp is not best_popup:
                            ti.wants_visible = False
            if info.wants_visible:
                num_visible += 1
            if not info.wants_visible and popup.is_visible():
                self._hide(info.cell_index)
            elif info.wants_visible and not popup.is_visible():
                any_new_visible = True
        if any_new_visible:
            if num_visible <= self._num_available_cells:
                self._show_visible_no_conflict()
            else:
                self._show_visible_resolve_conflict()
        for popup in list(self._popups):
            popup.frame_callback()

    def _empty_cells(self):
        e = [i for i, c in enumerate(self._cells) if c.is_available and c.np.is_empty()]
        random.shuffle(e)
        return e

    def _show_visible_no_conflict(self):
        empty = self._empty_cells()
        for popup, info in list(self._popups.items()):
            if info.wants_visible and not popup.is_visible():
                cell_index = self._choose_cell(popup, empty)
                if cell_index >= 0:
                    self._show(popup, cell_index)

    def _show_visible_resolve_conflict(self):
        by_score = []
        for popup, info in self._popups.items():
            if info.wants_visible:
                info.score = popup.get_score()
                by_score.append(popup)
        by_score.sort(key=lambda p: -self._popups[p].score)
        for popup in by_score[self._num_available_cells:]:
            if popup.is_visible():
                self._hide(self._popups[popup].cell_index)
        empty = self._empty_cells()
        for popup in by_score[:self._num_available_cells]:
            if not popup.is_visible():
                cell_index = self._choose_cell(popup, empty)
                if cell_index >= 0:
                    self._show(popup, cell_index)

    def _choose_cell(self, popup, empty_cells):
        now = _now()
        code = popup.get_object_code()
        for k, cell_index in enumerate(empty_cells):
            cell = self._cells[cell_index]
            if (cell.popup is popup or (code != 0 and cell.popup_code == code)) and (now - cell.hide_time) <= NametagGlobals.cell_memory_time:
                del empty_cells[k]
                return cell_index
        for k in range(len(empty_cells) - 1, -1, -1):
            cell_index = empty_cells[k]
            cell = self._cells[cell_index]
            if cell.popup is None or (now - cell.hide_time) > NametagGlobals.cell_memory_time:
                del empty_cells[k]
                return cell_index
        if not empty_cells:
            return -1
        return empty_cells.pop()

    def _show(self, popup, cell_index):
        cell = self._cells[cell_index]
        cell.popup = popup
        cell.popup_code = popup.get_object_code()
        cell.np = NodePath(self).attach_new_node(popup)
        cell.np.set_mat(cell.mat)
        self._popups[popup].cell_index = cell_index
        popup._cell_width = cell.width
        popup.set_visible(True)

    def _hide(self, cell_index):
        if not 0 <= cell_index < len(self._cells):
            return
        cell = self._cells[cell_index]
        popup = cell.popup
        if cell.np.is_empty() or popup is None:
            return
        cell.np.remove_node()
        cell.hide_time = _now()
        info = self._popups.get(popup)
        if info is not None:
            info.cell_index = -1
        popup.set_visible(False)


# ---------------------------------------------------------------------------------------------------- Nametag base
class Nametag(ClickablePopup):
    C_name = 0x0001
    C_speech = 0x0002
    C_thought = 0x0004
    CName, CSpeech, CThought = C_name, C_speech, C_thought

    def _init_nametag(self, chat_wordwrap):
        self._init_clickable()
        self._draw_order = 0
        self._has_draw_order = False
        self._contents = self.C_name | self.C_speech | self.C_thought
        self._active = True
        self._current_contents = 0
        self._group = None
        self._chat_wordwrap = chat_wordwrap
        self._avatar = NodePath()
        self._flash_track = None
        self._region_active = False
        self._region_seq = 0
        self._region_watcher = None
        self._nt_mouse_watcher = None

    def deactivate(self): self.clear_region()
    def set_contents(self, flags):
        self._contents = flags
        self.update_contents()

    def get_contents(self): return self._contents

    def set_active(self, active):
        self._active = active
        self.update_contents()

    def is_active(self): return self._active

    def display_as_active(self):
        active = self.is_active()
        if self.has_group():
            active = active and self._group.display_as_active()
        else:
            active = active and NametagGlobals.get_master_nametags_active()
        return active

    def has_group(self): return self._group is not None
    def get_group(self): return self._group

    def set_draw_order(self, d):
        self._draw_order = d
        self._has_draw_order = True
        self.update_contents()

    def clear_draw_order(self):
        self._has_draw_order = False
        self.update_contents()

    def set_chat_wordwrap(self, w): self._chat_wordwrap = w
    def get_chat_wordwrap(self): return self._chat_wordwrap
    def set_avatar(self, node): self._avatar = node
    def clear_avatar(self): self._avatar = NodePath()

    def get_avatar(self):
        if not self._avatar.is_empty():
            return self._avatar
        if self.has_group():
            return self._group.get_avatar()
        return self._avatar

    def is_group_managed(self): return self.has_group() and self._group.is_managed()

    def click(self):
        if self.has_group():
            self._group.click()

    def get_popup_state(self):
        return self._pstate if self.display_as_active() else S_inactive

    def determine_contents(self):
        current = 0
        if self.has_group():
            group = self._group
            if group.is_managed():
                contents = self.get_contents() & group.get_contents()
                chat_flags = group.get_chat_flags()
                if chat_flags & CF_speech:
                    if contents & self.C_speech:
                        current = self.C_speech
                elif chat_flags & CF_thought:
                    if contents & self.C_thought:
                        current = self.C_thought
                if current == 0:
                    if (contents & self.C_name) and group.get_name() and NametagGlobals.get_master_nametags_visible():
                        current = self.C_name
        return current

    def manage(self, manager):
        self.update_contents()

    def unmanage(self, manager):
        self.update_contents()
        self.clear_region()

    def set_region(self, frame, sort=0):
        if self._region is None:
            self._make_region("nametag", frame)
        else:
            self._region.set_frame(frame[0], frame[1], frame[2], frame[3])
        self._region.set_sort(sort)
        self._region_seq = self._group.get_region_seq()

    def keep_region(self):
        if self._region is not None:
            self._region_seq = self._group.get_region_seq()

    def clear_region(self):
        if self._region_active:
            if self._nt_mouse_watcher is not None:
                self._nt_mouse_watcher.remove_region(self._region)
                self._nt_mouse_watcher = None
            self._unhook_events()
            self._region_active = False
        self._region_seq = 0

    def start_flash(self, button):
        self.stop_flash()
        from direct.interval.IntervalGlobal import LerpColorScaleInterval, Sequence
        fade_out = LerpColorScaleInterval(button, 0.5, (1, 1, 1, 0.5), (1, 1, 1, 1), blendType="easeOut")
        fade_in = LerpColorScaleInterval(button, 0.5, (1, 1, 1, 1), (1, 1, 1, 0.5), blendType="easeIn")
        seq = Sequence(fade_out, fade_in)
        seq.loop()
        self._flash_track = seq

    def stop_flash(self):
        if self._flash_track is not None:
            self._flash_track.finish()
            self._flash_track = None

    def update_region(self, region_seq):
        wants_active = (self._region_seq == region_seq) and self.display_as_active()
        watcher = NametagGlobals.get_mouse_watcher()
        if self._region_active and self._nt_mouse_watcher is not watcher:
            if self._nt_mouse_watcher is not None:
                self._nt_mouse_watcher.remove_region(self._region)
            self._unhook_events()
            self._region_active = False
            self.set_popup_state(S_ready)
        if wants_active:
            if not self._region_active:
                self._nt_mouse_watcher = watcher
                if watcher is not None and self._region is not None:
                    watcher.add_region(self._region)
                    self._hook_events()
                self._region_active = True
        elif self._region_active:
            if self._nt_mouse_watcher is not None:
                self._nt_mouse_watcher.remove_region(self._region)
            self._unhook_events()
            self._region_active = False
            self._nt_mouse_watcher = None
            self.set_popup_state(S_ready)

    # shared by Nametag2d / Nametag3d ---------------------------------------------------------------
    def _chat_colors(self, group, ctype):
        colors = NametagGlobals.get_colors(group.get_color_code(), self.get_popup_state())
        text_color = LVecBase4f(colors._chat_fg)
        balloon_color = LVecBase4f(colors._chat_bg)
        if group.get_chat_flags() & CF_quicktalker:
            qt = group.get_qt_color()
            text_color = _mul4(text_color, qt)
            balloon_color = _mul4(balloon_color, qt)
        balloon_color = _mul4(balloon_color, group.get_balloon_modulation_color())
        return text_color, balloon_color

    def _page_button(self, group):
        state = self.get_popup_state()
        page_button = NodePath()
        if group.has_page_button():
            if group.get_page_number() >= group.get_num_chat_pages() - 1:
                if group.has_quit_button():
                    page_button = NametagGlobals.get_quit_button(state)
                elif not group.has_no_quit_button():
                    page_button = NametagGlobals.get_page_button(state)
            else:
                page_button = NametagGlobals.get_page_button(state)
        elif group.has_quit_button():
            page_button = NametagGlobals.get_quit_button(state)
        return page_button


# ---------------------------------------------------------------------------------------------------- Nametag3d
class Nametag3d(Nametag, CallbackNode):
    def __init__(self):
        CallbackNode.__init__(self, "unnamed")
        self._init_nametag(NametagGlobals.chat_3d_wordwrap)
        self.set_cull_callback(_cull_cb(self._on_cull))
        self._billboard_offset = NametagGlobals.billboard_offset
        self._top = NodePath("top")
        self._for_3d = True
        self._has_frame = False
        self._frame = LVecBase4f(0, 0, 0, 0)
        self._name = NodePath()
        self._card = NodePath()
        self._balloon = NodePath()
        self.set_bounds(BoundingSphere(LPoint3f(0, 0, 0), 2.0))

    def set_billboard_offset(self, v): self._billboard_offset = v
    def get_billboard_offset(self): return self._billboard_offset
    def safe_to_flatten(self): return False
    def safe_to_flatten_below(self): return False

    def release(self, outside=False):
        # a 3-d nametag is clicked on release
        self.set_popup_state(S_rollover)
        if self.has_group():
            self._group.click()

    def _on_cull(self, cbdata):
        if self.has_group() and self._group.is_managed():
            this_np = cbdata.get_data().node_path
            bin_sort = 0
            try:
                attrib = this_np.get_net_state().get_attrib(CullBinAttrib)
                if attrib is not None:
                    mgr = CullBinManager.get_global_ptr()
                    idx = mgr.find_bin(attrib.get_bin_name())
                    bin_sort = mgr.get_bin_sort(idx) if idx >= 0 else 0
            except Exception:                           # noqa
                pass
            self._adjust_to_camera(this_np, bin_sort)

    def update_contents(self):
        self.stop_flash()
        if self._has_draw_order:
            self._top.set_bin(nametag_fixed_bin, self._draw_order)
        else:
            self._top.clear_bin()
        self.set_name(self._group.get_name() if self.has_group() else "unnamed")
        self._name.remove_node()
        self._card.remove_node()
        self._balloon.remove_node()
        self._top.node().remove_all_children()
        self._has_frame = False
        self._current_contents = self.determine_contents()
        if self.is_group_managed():
            if self._current_contents & self.C_speech:
                self._generate_chat(NametagGlobals.get_speech_balloon_3d())
            elif self._current_contents & self.C_thought:
                self._generate_chat(NametagGlobals.get_thought_balloon_3d())
            elif self._current_contents & self.C_name:
                self._generate_name()

    def manage(self, manager):
        self._top.reparent_to(NodePath.any_path(self))
        Nametag.manage(self, manager)

    def unmanage(self, manager):
        self._top.detach_node()
        Nametag.unmanage(self, manager)

    def _generate_name(self):
        group = self._group
        colors = NametagGlobals.get_colors(group.get_color_code(), self.get_popup_state())
        text_color = colors._name_fg
        card_color = colors._name_bg
        f = group.get_name_frame()
        pad = NametagGlobals.card_pad
        self._frame = LVecBase4f(f[0] - pad[0], f[1] + pad[1], f[2] - pad[2], f[3] + pad[3])
        self._has_frame = True
        decal_node = NodePath()
        if card_color[3] != 0.0:
            card_maker = CardMaker("nametag")
            card_maker.set_frame(self._frame)
            card_maker.set_color(card_color)
            card_source = NametagGlobals.get_nametag_card()
            if not card_source.is_empty():
                card_maker.set_source_geometry(card_source.node(), NametagGlobals.get_nametag_card_frame())
            self._card = self._top.attach_new_node(card_maker.generate())
            if card_color[3] != 1.0:
                self._card.set_transparency(TransparencyAttrib.M_alpha)
            decal_node = self._top.find("**/+GeomNode")
        if self._for_3d:
            icon = group.get_name_icon()
            if not icon.is_empty():
                icon.instance_to(self._top)
        if self._for_3d and not decal_node.is_empty():
            self._name = group.copy_name_to(decal_node)
            self._name.set_depth_write(False)
            self._name.set_y(-0.01)                            # panda_depth_hack is on
            decal_node.node().set_effect(DecalEffect.make())
        else:
            self._name = group.copy_name_to(self._top)
            if self._has_draw_order:
                group.get_name_icon().set_bin(nametag_fixed_bin, self._draw_order + 1)
                self._name.set_bin(nametag_fixed_bin, self._draw_order + 2)
        self._name.set_color(text_color)
        if text_color[3] != 1.0:
            self._name.set_transparency(TransparencyAttrib.M_alpha)

    def _generate_chat(self, balloon):
        if balloon is None:
            return
        group = self._group
        text_color, balloon_color = self._chat_colors(group, 3)
        font = group.get_chat_font()
        text = group.get_chat()
        if not text or font is None:
            return
        page_button = self._page_button(group)
        reversed_ = bool(group.get_chat_flags() & CF_reversed)
        geom, new_button = balloon.generate(text, font, self.get_chat_wordwrap(), text_color, balloon_color, self._for_3d, self._has_draw_order,
                                            self._draw_order, page_button, group.will_have_button(), reversed_)
        self._balloon = self._top.attach_new_node(geom)
        if not new_button.is_empty():
            self.start_flash(new_button)
        self._frame = LVecBase4f(balloon.get_text_frame())
        self._has_frame = True

    def _adjust_to_camera(self, this_np, bin_sort):
        group = self._group
        if not self._for_3d:
            group.increment_nametag3d_flag(NametagGroup.NF_onscreen)
            if self.display_as_active() and self._has_frame:
                transform = this_np.get_net_transform()
                if not transform.has_mat():
                    return
                m = transform.get_mat()
                ll = m.xform_point(LPoint3f(self._frame[0] - 0.5, 0.0, self._frame[2] - 1.0))
                ur = m.xform_point(LPoint3f(self._frame[1] + 0.5, 0.0, self._frame[3] + 1.0))
                sort = (bin_sort << 16) | 10000
                self.set_region(LVecBase4f(ll[0], ur[0], ll[2], ur[2]), sort)
            return
        camera = NametagGlobals.get_camera()
        if camera.is_empty() or not camera.node().is_of_type(Camera.get_class_type()):
            return
        lens = camera.node().get_lens()
        avatar = self.get_avatar()
        transform1 = camera.get_transform(this_np)
        if not transform1.has_mat():
            return
        cam_to_this = transform1.get_mat()
        up = cam_to_this.xform_vec(LVector3f.up())
        rel_pos = cam_to_this.xform_vec(LVector3f.forward())
        mat = LMatrix4f()
        lookAt(mat, rel_pos, up)
        transform2 = this_np.get_transform(camera)
        this_to_cam = transform2.get_mat()
        distance = this_to_cam.get_cell(3, 1)
        norm_distance = max(distance, 0.1) / NametagGlobals.far_distance
        scale = (norm_distance ** NametagGlobals.scale_exponent) * NametagGlobals.far_scale * NametagGlobals.get_global_nametag_scale()
        if self._billboard_offset != 0.0:
            axis = cam_to_this.get_row3(0)
            net_scale = axis.length()
            local_offset = self._billboard_offset
            world_offset = self._billboard_offset / net_scale
            if distance > 0.0:
                if lens.is_of_type(PerspectiveLens.get_class_type()):
                    near_dist = lens.get_near()
                    if distance - world_offset < near_dist + 0.001:
                        world_offset = distance - (near_dist + 0.001)
                        local_offset = world_offset * net_scale
                    scale *= (distance - world_offset) / distance
            translate = LVector3f(cam_to_this.get_row3(3))
            translate.normalize()
            translate *= local_offset
            mat.set_row(3, translate)
        final_mat = LMatrix4f.scale_mat(scale) * mat
        self._top.set_mat(final_mat)
        compute_avatar = False
        if self.display_as_active():
            has_button = False
            if self._current_contents & (self.C_speech | self.C_thought):
                has_button = group.has_button()
            if not has_button:
                compute_avatar = True
        frame = None
        frame_sort = 0
        proj_mat = lens.get_projection_mat()
        if compute_avatar:
            width = NametagGlobals.nominal_avatar_width * 0.5
            ul = final_mat.xform_vec(LVector3f(-width, 0.0, 1.0))
            ur = final_mat.xform_vec(LVector3f(width, 0.0, 1.0))
            transform3 = this_np.get_transform(avatar)
            if not transform3.has_mat():
                return
            this_to_av = transform3.get_mat()
            ul = this_to_av.xform_point(LPoint3f(ul))
            ur = this_to_av.xform_point(LPoint3f(ur))
            ll = LPoint3f(ul[0], ul[1], 0.0)
            transform4 = avatar.get_transform(camera)
            if not transform4.has_mat():
                return
            av_to_cam = transform4.get_mat()
            ur = av_to_cam.xform_point(ur)
            ll = av_to_cam.xform_point(ll)
            pur = proj_mat.xform(LPoint4f(ur[0], ur[1], ur[2], 1.0))
            pll = proj_mat.xform(LPoint4f(ll[0], ll[1], ll[2], 1.0))
            if pll[3] <= 0.0 or pur[3] <= 0.0:
                group.increment_nametag3d_flag(NametagGroup.NF_offscreen)
                self.clear_region()
                return
            frame = [pll[0] / pll[3], pur[0] / pur[3], pll[1] / pll[3], pur[1] / pur[3]]
        partly_offscreen = False
        if self._has_frame:
            ll = final_mat.xform_point(LPoint3f(self._frame[0] - 0.5, 0.0, self._frame[2] - 1.0))
            ur = final_mat.xform_point(LPoint3f(self._frame[1] + 0.5, 0.0, self._frame[3] + 1.0))
            ll = this_to_cam.xform_point(ll)
            ur = this_to_cam.xform_point(ur)
            pur = proj_mat.xform(LPoint4f(ur[0], ur[1], ur[2], 1.0))
            pll = proj_mat.xform(LPoint4f(ll[0], ll[1], ll[2], 1.0))
            if pll[3] <= 0.0 or pur[3] <= 0.0:
                partly_offscreen = True
            else:
                nf = [pll[0] / pll[3], pur[0] / pur[3], pll[1] / pll[3], pur[1] / pur[3]]
                partly_offscreen = nf[0] < -1.0 or nf[1] > 1.0 or nf[2] < -1.0 or nf[3] > 1.0
                if frame is not None:
                    frame = [min(frame[0], nf[0]), max(frame[1], nf[1]), min(frame[2], nf[2]), max(frame[3], nf[3])]
                else:
                    frame = nf
                frame_sort = int(ll[1] * -100.0)
        if frame is not None and self.display_as_active():
            self.set_region(LVecBase4f(*frame), frame_sort)
        if partly_offscreen:
            group.increment_nametag3d_flag(NametagGroup.NF_partly_offscreen)
        else:
            group.increment_nametag3d_flag(NametagGroup.NF_onscreen)


class NametagFloat3d(Nametag3d):
    def __init__(self):
        Nametag3d.__init__(self)
        self.set_active(False)


class NametagFloat2d(Nametag3d):
    def __init__(self):
        Nametag3d.__init__(self)
        self._for_3d = False
        self.set_active(False)


# ---------------------------------------------------------------------------------------------------- Nametag2d
class Nametag2d(Nametag, MarginPopup):
    def __init__(self):
        MarginPopup.__init__(self)
        self._init_nametag(NametagGlobals.chat_2d_wordwrap)
        self._name = NodePath()
        self._card = NodePath()
        self._arrow = NodePath()
        self._balloon = NodePath()
        self._arrow_center = LPoint3f(0, 0, 0)
        self.set_cull_callback(_cull_cb(lambda cbdata: self._rotate_arrow()))
        self.set_name("unnamed")
        self.set_contents(self.C_name | self.C_speech)
        self._master_arrows = NametagGlobals.get_master_arrows_on()

    def get_score(self):
        if not self.has_group():
            return 0.0
        # building arrows (the guide to the shops, HQ, hall...) outrank the toons, NPCs and doodles standing around, which used to take all
        # the screen-edge slots and hide them; chat balloons and whispers still rank above these
        if self._group.get_color_code() in (_CC.CC_toon_building, _CC.CC_suit_building, _CC.CC_house_building):
            return 1500.0 - self._get_distance2() / 1.0e6
        return 1000.0 - self._get_distance2()

    def get_object_code(self):
        return self._group.get_object_code() if self.has_group() else 0

    def update_contents(self):
        self.stop_flash()
        self.set_name(self._group.get_name() if self.has_group() else "unnamed")
        self._name.remove_node()
        self._card.remove_node()
        self._arrow.remove_node()
        self._balloon.remove_node()
        self._current_contents = self.determine_contents()
        if not NametagGlobals.get_master_arrows_on():
            self._current_contents &= ~self.C_name
        if self.is_visible() and self.is_group_managed():
            if self._current_contents & self.C_speech:
                self._generate_chat(NametagGlobals.get_speech_balloon_2d())
            elif self._current_contents & self.C_thought:
                self._generate_chat(NametagGlobals.get_thought_balloon_2d())
            elif self._current_contents & self.C_name:
                self._generate_name()

    def manage(self, manager):
        Nametag.manage(self, manager)
        manager.manage_popup(self)

    def unmanage(self, manager):
        Nametag.unmanage(self, manager)
        manager.unmanage_popup(self)

    def frame_callback(self):
        if self.is_visible():
            self.keep_region()
        if self.has_group():
            self._group.update_regions()

    def consider_visible(self):
        force_update = False
        if self._master_arrows != NametagGlobals.get_master_arrows_on():
            self._master_arrows = NametagGlobals.get_master_arrows_on()
            force_update = True
        if self._master_margin_prop_seq != NametagGlobals.margin_prop_seq:
            self._master_margin_prop_seq = NametagGlobals.margin_prop_seq
            force_update = True
        if force_update:
            self.update_contents()
        if self._current_contents == 0:
            return False
        if not self.has_group():
            return False
        group = self._group
        visible = group.get_nametag3d_flag() != NametagGroup.NF_onscreen
        if NametagGlobals.get_onscreen_chat_forced() and (self._current_contents & (self.C_speech | self.C_thought)):
            visible = True
        group.set_nametag3d_flag(NametagGroup.NF_offscreen)
        cc = group.get_color_code()
        if visible and cc in (_CC.CC_toon_building, _CC.CC_suit_building, _CC.CC_house_building):
            visible = self._get_distance2() <= NametagGlobals.building_nametag_distance ** 2
        # the guide arrows are for the buildings (and friends): NPCs and doodles standing around do not get one unless they are talking
        if visible and cc == _CC.CC_non_player and not (self._current_contents & (self.C_speech | self.C_thought)):
            visible = False
        return visible

    def set_managed(self, flag):
        MarginPopup.set_managed(self, flag)

    def set_visible(self, flag):
        MarginPopup.set_visible(self, flag)
        self.update_contents()

    def _generate_name(self):
        group = self._group
        colors = NametagGlobals.get_colors(group.get_color_code(), self.get_popup_state())
        text_color = colors._name_fg
        card_color = LVecBase4f(colors._name_bg)
        card_color[3] = max(min(card_color[3], NametagGlobals.get_max_2d_alpha()), NametagGlobals.get_min_2d_alpha())
        f = group.get_name_frame()
        pad = NametagGlobals.card_pad
        frame = LVecBase4f(f[0] - pad[0], f[1] + pad[1], f[2] - pad[2], f[3] + pad[3])
        name_wordwrap = group.get_name_wordwrap()
        scale = 2.0 * self.get_cell_width() / name_wordwrap
        mat = LMatrix4f.scale_mat(scale)
        y_center = (frame[2] + frame[3]) * 0.5
        y_trans = min(0.333 / scale - y_center, 1.0 / scale - frame[3])
        mat = LMatrix4f.translate_mat(0.0, 0.0, y_trans) * mat
        if card_color[3] != 0.0:
            card_maker = CardMaker("nametag")
            card_maker.set_frame(frame)
            card_maker.set_color(card_color)
            card_source = NametagGlobals.get_nametag_card()
            if not card_source.is_empty():
                card_maker.set_source_geometry(card_source.node(), NametagGlobals.get_nametag_card_frame())
            self._card = self._this_np.attach_new_node(card_maker.generate())
            self._card.set_mat(mat)
            if card_color[3] != 1.0:
                self._card.set_transparency(TransparencyAttrib.M_alpha)
            if self._has_draw_order:
                self._card.set_bin(nametag_fixed_bin, self._draw_order)
        self._name = group.copy_name_to(self._this_np)
        self._name.set_mat(mat)
        if self._has_draw_order:
            self._name.set_bin(nametag_fixed_bin, self._draw_order + 1)
        self._name.set_color(text_color)
        if text_color[3] != 1.0:
            self._name.set_transparency(TransparencyAttrib.M_alpha)
        reducer = SceneGraphReducer()
        reducer.apply_attribs(self._name.node())
        if not self._card.is_empty():
            reducer.apply_attribs(self._card.node())
        arrow_model = NametagGlobals.get_arrow_model()
        if arrow_model.is_empty():
            self._arrow.remove_node()
        else:
            self._arrow = arrow_model.copy_to(self._this_np)
            if self._has_draw_order:
                self._arrow.set_bin(nametag_fixed_bin, self._draw_order)
            self._arrow_center = mat.xform_point(LPoint3f(0.0, 0.0, frame[2] - NametagGlobals.arrow_offset))
            arrow_color = NametagGlobals.get_arrow_color(group.get_color_code())
            self._arrow.set_color(arrow_color)
            if arrow_color[3] != 1.0:
                self._arrow.set_transparency(TransparencyAttrib.M_alpha)
            self._rotate_arrow()
        rel_mat = mat * self._this_np.get_net_transform().get_mat()
        ll = rel_mat.xform_point(LPoint3f(frame[0], 0.0, frame[2]))
        ur = rel_mat.xform_point(LPoint3f(frame[1], 0.0, frame[3]))
        self.set_region(LVecBase4f(ll[0], ur[0], ll[2], ur[2]))

    def _generate_chat(self, balloon):
        if balloon is None:
            return
        group = self._group
        text_color, balloon_color = self._chat_colors(group, 2)
        balloon_color[3] = max(min(balloon_color[3], NametagGlobals.get_max_2d_alpha()), NametagGlobals.get_min_2d_alpha())
        font = group.get_chat_font()
        text = group.get_chat()
        if not text or font is None:
            return
        if group.get_name():
            text = group.get_name() + ": " + text
        page_button = self._page_button(group)
        wordwrap = self.get_chat_wordwrap()
        geom, new_button = balloon.generate(text, font, wordwrap, text_color, balloon_color, False, self._has_draw_order, self._draw_order, page_button,
                                            group.will_have_button(), False)
        self._balloon = self._this_np.attach_new_node(geom)
        if not new_button.is_empty():
            self.start_flash(new_button)
        scale = 2.0 * self.get_cell_width() / (wordwrap + 1.0)
        width = NametagGlobals.balloon_external_width * balloon.get_hscale()
        height = balloon.get_text_height() * balloon.get_hscale()
        half_width = width * 0.5
        half_height = height * 0.5
        x_trans = half_width + 0.5 * balloon.get_hscale()
        y_trans = half_height + NametagGlobals.balloon_text_origin[2]
        mat = LMatrix4f.translate_mat(-x_trans, 0.0, -y_trans) * LMatrix4f.scale_mat(scale)
        self._balloon.set_mat(mat)
        SceneGraphReducer().apply_attribs(self._balloon.node())
        rel_mat = self._this_np.get_net_transform().get_mat()
        half_height += 1.0
        ll = rel_mat.xform_point(LPoint3f(-half_width * scale, 0.0, -half_height * scale))
        ur = rel_mat.xform_point(LPoint3f(half_width * scale, 0.0, half_height * scale))
        self.set_region(LVecBase4f(ll[0], ur[0], ll[2], ur[2]))

    def _rotate_arrow(self):
        if self._arrow.is_empty() or not self.has_group():
            return
        toon = NametagGlobals.get_toon()
        camera = NametagGlobals.get_camera()
        avatar = self.get_avatar()
        if toon.is_empty() or camera.is_empty() or avatar.is_empty():
            return
        rel_center_to_camera = toon.get_pos(camera)
        rel_pos_to_camera = avatar.get_pos(camera)
        rel = rel_pos_to_camera - rel_center_to_camera
        rotate = math.degrees(math.atan2(rel[1], rel[0]))
        from panda3d.core import compose_matrix, LVecBase3f
        mat = LMatrix4f()
        compose_matrix(mat, LVecBase3f(NametagGlobals.arrow_scale, NametagGlobals.arrow_scale, NametagGlobals.arrow_scale), LVecBase3f(0.0, 0.0, -rotate),
                       LVecBase3f(self._arrow_center))
        self._arrow.set_mat(mat)

    def _get_distance2(self):
        avatar = self.get_avatar()
        toon = NametagGlobals.get_toon()
        if avatar.is_empty() or toon.is_empty():
            return 0.0
        rel = avatar.get_pos(toon)
        return rel.dot(rel)


# ---------------------------------------------------------------------------------------------------- NametagGroup
class NametagGroup(_CC):
    NF_offscreen, NF_partly_offscreen, NF_onscreen = 0, 1, 2
    _unique_index = 0

    def __init__(self):
        self._name_icon = NodePath("icon")
        self._name_wordwrap = -1.0
        self._color_code = self.CC_normal
        self._qt_color = LVecBase4f(NametagGlobals.default_qt_color)
        self._balloon_modulation_color = LVecBase4f(NametagGlobals.get_balloon_modulation_color())
        self._shadow_offset = LVecBase2f(0, 0)
        self._has_shadow = False
        self._chat_flags = 0
        self._chat_timeout = 0.0
        self._button_timeout = 0.0
        self._page_number = 0
        self._buttons_pending = False
        self._chat_stomp_accum = 0
        self._chat_timeblock = 0.0
        self._chat_block_length = 0.5
        self._chat_block_hold = ""
        self._chat_flags_hold = 0
        NametagGroup._unique_index += 1
        self._unique_id = "nametag-%d" % NametagGroup._unique_index
        self._object_code = 0
        self._nametag3d_flag = self.NF_offscreen
        self._manager = None
        self._region_seq = 1
        self._contents = Nametag.C_name | Nametag.C_speech | Nametag.C_thought
        self._active = True
        self._master_active = NametagGlobals.get_master_nametags_active()
        self._master_visible = NametagGlobals.get_master_nametags_visible()
        self._avatar = NodePath()
        self._name_font = None
        self._chat_font = None
        self._name_geom = None
        self._name_frame = LVecBase4f(0, 0, 0, 0)
        self._name = ""
        self._display_name = ""
        self._chat_pages = []
        self._nametags = []
        self._nametag2d = Nametag2d()
        self._nametag3d = Nametag3d()
        self.add_nametag(self._nametag2d)
        self.add_nametag(self._nametag3d)

    def get_nametag2d(self): return self._nametag2d
    def get_nametag3d(self): return self._nametag3d

    def add_nametag(self, tag):
        if tag.has_group() and tag.get_group() is self:
            return
        tag._group = self
        tag.update_contents()
        self._nametags.append(tag)
        if self.is_managed():
            tag.manage(self._manager)

    def remove_nametag(self, tag):
        if not tag.has_group():
            return
        if self.is_managed():
            tag.unmanage(self._manager)
        tag._group = None
        tag.update_contents()
        if tag in self._nametags:
            self._nametags.remove(tag)

    def clear_aux_nametags(self):
        keep = []
        for tag in self._nametags:
            if tag is self._nametag2d or tag is self._nametag3d:
                keep.append(tag)
            else:
                tag._group = None
                tag.update_contents()
        self._nametags = keep

    def get_num_nametags(self): return len(self._nametags)
    def get_nametag(self, n): return self._nametags[n]
    def set_font(self, font):
        self._name_font = font
        self._chat_font = font

    def set_name_font(self, font): self._name_font = font
    def get_name_font(self): return self._name_font
    def set_chat_font(self, font): self._chat_font = font
    def get_chat_font(self): return self._chat_font
    def set_avatar(self, node): self._avatar = node
    def get_avatar(self): return self._avatar
    def get_name_icon(self): return self._name_icon

    def set_name_wordwrap(self, w):
        self._name_wordwrap = w
        self.set_display_name(self._display_name)

    def get_name_wordwrap(self):
        if self._name_wordwrap > 0.0:
            return self._name_wordwrap
        if self._color_code in (self.CC_toon_building, self.CC_suit_building):
            return NametagGlobals.building_name_wordwrap
        if self._color_code == self.CC_house_building:
            return NametagGlobals.house_name_wordwrap
        return NametagGlobals.name_wordwrap

    def set_color_code(self, code):
        self._color_code = code
        self._update_contents_all()

    def get_color_code(self): return self._color_code
    def set_qt_color(self, c): self._qt_color = LVecBase4f(c)
    def get_qt_color(self): return self._qt_color
    def get_balloon_modulation_color(self): return self._balloon_modulation_color

    def set_shadow(self, x, y):
        self._has_shadow = True
        self._shadow_offset = LVecBase2f(x, y)

    def clear_shadow(self): self._has_shadow = False
    def has_shadow(self): return self._has_shadow
    def get_shadow(self): return self._shadow_offset if self._has_shadow else LVecBase2f(0, 0)

    def set_name(self, name):
        self._name = name
        self.set_display_name(name)

    def get_name(self): return self._name

    def set_display_name(self, name):
        self._display_name = name
        if self._display_name and self._name_font is not None:
            text_node = NametagGlobals.get_text_node()
            text_node.set_font(self._name_font)
            text_node.set_wordwrap(self.get_name_wordwrap())
            text_node.set_align(TextNode.A_center)
            text_node.set_text(self._display_name)
            self._name_geom = text_node.generate()
            self._name_frame = LVecBase4f(text_node.get_card_actual())
            text_node.clear_text()
            if self.has_shadow():
                name = self._name_geom
                self._name_geom = PandaNode("name")
                np = NodePath(self._name_geom)
                shadow = np.attach_new_node("shadow")
                shadow.attach_new_node(name)
                shadow.set_pos(self._shadow_offset[0], 0.0, -self._shadow_offset[1])
                shadow.set_color(0.0, 0.0, 0.0, 1.0)
                np.attach_new_node(name)
        else:
            self._name_geom = None
        self._update_contents_all()

    def get_display_name(self): return self._display_name

    def set_chat(self, chat, chat_flags, page_number=0):
        self._chat_flags = chat_flags
        self._page_number = page_number
        now = _now()
        if chat_flags == 0 or not chat:
            self._chat_pages = []
            self._chat_flags = 0
            self._chat_stomp_accum = 0
        else:
            self._chat_pages = []
            self._chat_stomp_accum += 1
            if self._chat_stomp_accum < 2 or self._chat_block_length < 0.05:
                self._chat_pages = chat.split("\a")
            else:
                self._chat_block_hold = chat
                self._chat_timeblock = now + self._chat_block_length
                self._chat_flags_hold = self._chat_flags
                self._chat_pages = []
                self._chat_flags = 0
        if (self._chat_flags & CF_timeout) and self._chat_timeblock < now:
            keep_for = max(min(len(chat) * 0.5, 12.0), 4.0)
            self._chat_timeout = now + keep_for
        if self.will_have_button():
            self._button_timeout = now + NametagGlobals.button_delay_time
            self._buttons_pending = True
        else:
            self._button_timeout = 0.0
            self._buttons_pending = False
        self._update_contents_all()

    def clear_chat(self): self.set_chat("", 0)

    def get_chat(self, page_number=None):
        if page_number is None:
            if not self._chat_pages:
                return ""
            page_number = self._page_number
        if 0 <= page_number < len(self._chat_pages):
            return self._chat_pages[page_number]
        return ""

    def get_stomp_text(self):
        return "" if self._chat_stomp_accum < 1 else self._chat_block_hold

    def get_chat_flags(self): return self._chat_flags

    def set_page_number(self, page_number):
        if self._page_number != page_number:
            self._page_number = page_number
            if self.will_have_button():
                self._button_timeout = _now() + NametagGlobals.button_delay_time
                self._buttons_pending = True
            self._update_contents_all()

    def get_page_number(self): return self._page_number
    def get_num_chat_pages(self): return len(self._chat_pages)
    def get_chat_stomp(self): return self._chat_stomp_accum
    def get_stomp_delay(self): return self._chat_block_length
    def set_unique_id(self, e): self._unique_id = e
    def get_unique_id(self): return self._unique_id
    def set_object_code(self, c): self._object_code = c
    def get_object_code(self): return self._object_code

    def click(self):
        _messenger().send(self.get_unique_id())

    def manage(self, manager):
        if not self.is_managed():
            self._manager = manager
            for tag in list(self._nametags):
                tag.manage(manager)

    def unmanage(self, manager):
        if self.is_managed():
            self._manager = None
            for tag in list(self._nametags):
                tag.unmanage(manager)

    def is_managed(self): return self._manager is not None
    def set_contents(self, flags):
        self._contents = flags
        self._update_contents_all()

    def get_contents(self): return self._contents

    def set_active(self, active):
        self._active = active
        self._update_contents_all()

    def is_active(self): return self._active
    def has_page_button(self): return not self._buttons_pending and bool(self._chat_flags & CF_page_button)
    def has_quit_button(self): return not self._buttons_pending and bool(self._chat_flags & CF_quit_button)
    def has_no_quit_button(self): return not self._buttons_pending and bool(self._chat_flags & CF_no_quit_button)

    def has_button(self):
        if self._buttons_pending:
            return False
        if self._chat_flags & (CF_page_button | CF_quit_button):
            if (self._chat_flags & CF_no_quit_button) and self.get_page_number() >= self.get_num_chat_pages() - 1:
                return False
            return True
        return False

    def will_have_button(self): return bool(self._chat_flags & (CF_page_button | CF_quit_button))

    def display_as_active(self):
        return (self.is_active() and NametagGlobals.get_master_nametags_active()) or self.has_button()

    def copy_name_to(self, dest):
        if self._name_geom is None:
            return NodePath()
        return dest.attach_new_node(self._name_geom.copy_subgraph())

    def get_name_frame(self): return self._name_frame
    def set_nametag3d_flag(self, f): self._nametag3d_flag = f
    def increment_nametag3d_flag(self, f): self._nametag3d_flag = max(self._nametag3d_flag, f)
    def get_nametag3d_flag(self): return self._nametag3d_flag
    def get_region_seq(self): return self._region_seq

    def update_regions(self):
        for tag in list(self._nametags):
            tag.update_region(self._region_seq)
        self._region_seq += 1
        now = _now()
        if self._chat_timeblock < now and self._chat_stomp_accum > 1:
            self._chat_stomp_accum = 0
            self.set_chat(self._chat_block_hold, self._chat_flags_hold, self._page_number)
        if (self._chat_flags & CF_timeout) and now >= self._chat_timeout:
            self.clear_chat()
            self._chat_stomp_accum = 0
        force_update = False
        if self._buttons_pending and now >= self._button_timeout:
            self._buttons_pending = False
            force_update = True
        if self._master_active != NametagGlobals.get_master_nametags_active():
            self._master_active = NametagGlobals.get_master_nametags_active()
            force_update = True
        if self._master_visible != NametagGlobals.get_master_nametags_visible():
            self._master_visible = NametagGlobals.get_master_nametags_visible()
            force_update = True
        if force_update:
            self._update_contents_all()

    def _update_contents_all(self):
        for tag in list(self._nametags):
            tag.update_contents()


# ---------------------------------------------------------------------------------------------------- WhisperPopup
class WhisperPopup(_WT, ClickablePopup, MarginPopup):
    def __init__(self, text, font, whisper_type):
        MarginPopup.__init__(self)
        self._init_clickable()
        self.set_cull_callback(_cull_cb(self._on_cull))
        self._text = text
        self._font = font
        self._whisper_type = whisper_type
        self._has_rendered = False
        self._first_appeared = 0.0
        self._clickable = False
        self._avatar_name = ""
        self._avatar_id = 0
        self._is_player_id = False
        self._balloon = NodePath()
        self._wp_mouse_watcher = None
        self._pstate = S_inactive

    def set_clickable(self, avatar_name, avatar_id, is_player_id=0):
        self._clickable = True
        self._avatar_name = avatar_name
        self._avatar_id = avatar_id
        self._is_player_id = bool(is_player_id)
        self._pstate = S_ready

    def manage(self, manager):
        manager.manage_popup(self)

    def unmanage(self, manager):
        manager.unmanage_popup(self)

    def _on_cull(self, cbdata):
        if not self._has_rendered:
            self._has_rendered = True
            self._first_appeared = _now()

    def get_score(self):
        if not self._has_rendered:
            return 2000.0
        return 2000.0 - 1000.0 * (_now() - self._first_appeared) / NametagGlobals.whisper_priority_time

    def click(self):
        _messenger().send("clickedWhisper", [self._avatar_id, int(self._is_player_id)])

    def update_contents(self):
        self._balloon.remove_node()
        if self.is_visible():
            self._generate_text(NametagGlobals.get_speech_balloon_2d(), self._text, self._font)

    def consider_manage(self):
        if not self._has_rendered:
            return True
        return (_now() - self._first_appeared) < NametagGlobals.whisper_total_time

    def consider_visible(self):
        if self._clickable and self.is_visible() and self._wp_mouse_watcher is not NametagGlobals.get_mouse_watcher():
            return False
        return MarginPopup.consider_visible(self)

    def set_visible(self, flag):
        MarginPopup.set_visible(self, flag)
        self.update_contents()
        if self._clickable and self._region is not None:
            if self.is_visible():
                self._wp_mouse_watcher = NametagGlobals.get_mouse_watcher()
                if self._wp_mouse_watcher is not None:
                    self._wp_mouse_watcher.add_region(self._region)
                    self._hook_events()
            else:
                if self._wp_mouse_watcher is not None:
                    self._wp_mouse_watcher.remove_region(self._region)
                    self._wp_mouse_watcher = None
                self._unhook_events()

    def _generate_text(self, balloon, text, font):
        if balloon is None or font is None or not text:
            return
        colors = NametagGlobals.get_whisper_colors(self._whisper_type, self.get_popup_state())
        text_color = colors._chat_fg
        balloon_color = LVecBase4f(colors._chat_bg)
        balloon_color[3] = max(min(balloon_color[3], NametagGlobals.get_max_2d_alpha()), NametagGlobals.get_min_2d_alpha())
        wordwrap = NametagGlobals.chat_2d_wordwrap
        geom, _unused = balloon.generate(text, font, wordwrap, text_color, balloon_color, False, False, 0, NodePath(), False, False)
        self._balloon = self._this_np.attach_new_node(geom)
        scale = 2.0 * self.get_cell_width() / (wordwrap + 1.0)
        width = NametagGlobals.balloon_external_width * balloon.get_hscale()
        height = balloon.get_text_height() * balloon.get_hscale()
        half_width = width * 0.5
        half_height = height * 0.5
        x_trans = half_width + 0.5 * balloon.get_hscale()
        y_trans = half_height + NametagGlobals.balloon_text_origin[2]
        mat = LMatrix4f.translate_mat(-x_trans, 0.0, -y_trans) * LMatrix4f.scale_mat(scale)
        self._balloon.set_mat(mat)
        SceneGraphReducer().apply_attribs(self._balloon.node())
        if self._clickable:
            rel_mat = self._this_np.get_net_transform().get_mat()
            half_height += 1.0
            ll = rel_mat.xform_point(LPoint3f(-half_width * scale, 0.0, -half_height * scale))
            ur = rel_mat.xform_point(LPoint3f(half_width * scale, 0.0, half_height * scale))
            frame = (ll[0], ur[0], ll[2], ur[2])
            if self._region is None:
                self._make_region("whisper", frame)
            else:
                self._region.set_frame(*frame)
            self._region.set_sort(0)


# ---------------------------------------------------------------------------------------------------- aliases
for _c in (NametagGlobals, ChatBalloon, MarginPopup, MarginManager, Nametag, Nametag3d, NametagFloat3d, NametagFloat2d, Nametag2d, NametagGroup, WhisperPopup,
           ClickablePopup):
    camel_aliases(_c)
