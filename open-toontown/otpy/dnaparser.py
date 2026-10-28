"""Reader for Disney's text DNA files (the grammar of Open Toontown's dnaParser.yxx / dnaLexer.lxx), written as a small recursive-descent parser."""
import re

from panda3d.core import Filename, FontPool, Loader, LoaderOptions, LVecBase3f, LVecBase4f, NodePath, TexturePool, oldToNewHpr

from . import dna as D

# set by the browser build: called with every model the DNA file loads (see-through textures need converting there)
MODEL_HOOK = None

_KEYWORDS = frozenset("""ANIM ANIM_BUILDING ANIM_PROP ARTICLE BATTLE_CELL CELL_ID CODE COLOR COUNT CORNICE DOOR FLAT_BUILDING FLAT_DOOR
FRONT_DOOR_POINT GROUP HEIGHT HPR INTERACTIVE_PROP LANDMARK_BUILDING MODEL NHPR NODE HOOD_MODEL BUILDING_TYPE PLACE_MODEL POS PROP SCALE SIGN
BASELINE INDENT KERN WIGGLE SIDE_DOOR_POINT STREET_POINT COGHQ_IN_POINT COGHQ_OUT_POINT STUMBLE STOMP GRAPHIC TEXT LETTERS FLAGS STORE_FONT
STORE_NODE STORE_SUIT_POINT STORE_TEXTURE STREET SUIT_EDGE TEXTURE TITLE VIS VISGROUP WINDOWS WALL WIDTH""".split())

_TOKEN = re.compile(r"""
    (?P<ws>[ \t\r\n]+)
  | (?P<lc>//[^\n]*)
  | (?P<bc>/\*.*?\*/)
  | (?P<punct>[\[\],])
  | (?P<num>[+-]?(?:[0-9]*\.[0-9]+|[0-9]+\.?)(?:[eE][+-]?[0-9]+)?)
  | (?P<str>"[^"]*")
  | (?P<word>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<other>.)
""", re.X | re.S)

# token kinds: ("kw", NAME) ("num", value, text) ("str", text) ("p", char)


def _tokenize(text, errors):
    out = []
    line = 1
    for m in _TOKEN.finditer(text):
        kind = m.lastgroup
        s = m.group()
        if kind in ("ws", "lc", "bc"):
            line += s.count("\n")
            continue
        if kind == "punct":
            out.append(("p", s, line))
        elif kind == "num":
            out.append(("num", float(s), s, line))
        elif kind == "str":
            out.append(("str", s[1:-1], line))
            line += s.count("\n")
        elif kind == "word":
            up = s.upper()
            if up in _KEYWORDS:
                out.append(("kw", up, line))
            else:
                errors.append("line %d: unknown word %r" % (line, s))
        else:
            errors.append("line %d: stray character %r" % (line, s))
    return out


class _Parser:
    def __init__(self, tokens, top, filename):
        self.t = tokens
        self.i = 0
        self.top = top
        self.store = top.get_dna_storage()
        self.filename = filename
        self.errors = []
        self.zone = ""
        self.model = NodePath()
        self.model_kind = 0          # 0 pool model, 1 hood model, 2 place model

    # ---- token helpers
    def err(self, msg):
        line = self.t[self.i][-1] if self.i < len(self.t) else 0
        self.errors.append("%s line %s: %s" % (self.filename, line, msg))

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def next(self):
        t = self.peek()
        self.i += 1
        return t

    def expect_punct(self, c):
        t = self.peek()
        if t is not None and t[0] == "p" and t[1] == c:
            self.i += 1
            return True
        self.err("expected %r" % c)
        return False

    def is_punct(self, c):
        t = self.peek()
        return t is not None and t[0] == "p" and t[1] == c

    def string_tok(self):
        t = self.peek()
        if t is not None and t[0] == "str":
            self.i += 1
            return t[1]
        if t is not None and t[0] == "num":
            self.i += 1
            return t[2]
        return None

    def required_string(self):
        s = self.string_tok()
        if s is None:
            self.err("String required.")
            return ""
        return s

    def real(self):
        t = self.peek()
        if t is not None and t[0] == "num":
            self.i += 1
            return t[1]
        self.err("number expected")
        return 0.0

    def reals(self, n):
        return [self.real() for _ in range(n)]

    def bracket_reals(self, n):
        self.expect_punct("[")
        v = self.reals(n)
        self.expect_punct("]")
        return v

    def bracket_string(self):
        self.expect_punct("[")
        s = self.required_string()
        self.expect_punct("]")
        return s

    def bracket_loose_string(self):
        self.expect_punct("[")
        s = self.string_tok() or ""
        self.expect_punct("]")
        return s

    def skip_to_close(self):
        depth = 1
        while self.i < len(self.t) and depth:
            t = self.next()
            if t[0] == "p" and t[1] == "[":
                depth += 1
            elif t[0] == "p" and t[1] == "]":
                depth -= 1

    # ---- top level
    def parse(self):
        while self.i < len(self.t):
            t = self.peek()
            if t[0] != "kw":
                self.err("unexpected token %r" % (t[1],))
                self.i += 1
                continue
            kw = t[1]
            if kw in ("MODEL", "HOOD_MODEL", "PLACE_MODEL"):
                self.i += 1
                self.parse_model(kw)
            elif kw == "STORE_TEXTURE":
                self.i += 1
                self.parse_store_texture()
            elif kw == "STORE_FONT":
                self.i += 1
                self.parse_store_font()
            elif kw == "STORE_SUIT_POINT":
                self.i += 1
                self.parse_store_suit_point()
            else:
                node = self.parse_element()
                if node is not None:
                    self.top.add(node)
        return not self.errors

    # ---- model / storage statements
    def parse_model(self, kw):
        model_name = self.required_string()
        self.expect_punct("[")
        fn = Filename(model_name)
        fn.set_extension("bam")
        loader = Loader.get_global_ptr()
        try:
            if kw == "MODEL":
                self.model_kind = 0
                node = loader.load_sync(fn)
            else:
                self.model_kind = 1 if kw == "HOOD_MODEL" else 2
                opts = LoaderOptions()
                opts.set_flags(opts.get_flags() | LoaderOptions.LF_no_ram_cache)
                node = loader.load_sync(fn, opts)
        except Exception as e:                       # noqa
            D._log("could not load model", fn, e)
            node = None
        self.model = NodePath(node) if node is not None else NodePath()
        if MODEL_HOOK is not None and not self.model.is_empty():
            try:
                MODEL_HOOK(self.model)
            except Exception as e:                    # noqa
                D._log("model hook failed", e)
        while not self.is_punct("]"):
            t = self.peek()
            if t is None:
                self.err("unterminated model block")
                return
            if t[0] == "kw" and t[1] == "STORE_NODE":
                self.i += 1
                self.parse_store_node()
            else:
                self.err("unexpected token in model block")
                self.i += 1
        self.expect_punct("]")

    def _store_model_node(self, code, node, category):
        if self.model_kind == 1:
            self.store.store_hood_node(code, node, category)
        elif self.model_kind == 2:
            self.store.store_place_node(code, node, category)
        else:
            self.store.store_node(code, node, category)

    def parse_store_node(self):
        self.expect_punct("[")
        vals = []
        while not self.is_punct("]") and self.peek() is not None:
            s = self.string_tok()
            if s is None:
                self.err("string expected in store_node")
                self.i += 1
                continue
            vals.append(s)
        self.expect_punct("]")
        if len(vals) >= 3:
            category, code, node_name = vals[0], vals[1], vals[2]
            if node_name == "":
                node = self.model
                if node.is_empty():
                    self.err("Empty NodePath (model not loaded)")
                    return
            else:
                if self.model.is_empty():
                    self.err("Empty NodePath (model not loaded)")
                    return
                node = self.model.find("**/" + node_name)
                if node.is_empty():
                    self.err("Empty NodePath (%s)" % node_name)
                    return
            self._store_model_node(code, node, category)
            self.store.store_catalog_string(category, code)
        elif len(vals) == 2:
            category, code = vals
            if self.model.is_empty():
                self.err("Empty NodePath (model not loaded)")
                return
            node = self.model.find("**/" + code)
            if node.is_empty():
                self.err("Empty NodePath (%s)" % code)
                return
            self._store_model_node(code, node, category)
            self.store.store_catalog_string(category, code)
        else:
            self.err("store_node needs 2 or 3 strings")

    def parse_store_texture(self):
        self.expect_punct("[")
        category = self.required_string()
        code = self.required_string()
        path = self.required_string()
        self.expect_punct("]")
        try:
            tex = TexturePool.load_texture(path)
        except Exception:                          # noqa
            tex = None
        if tex is None:
            D._log("Unable to load texture file", path)
        else:
            self.store.store_texture(code, tex)
            self.store.store_catalog_string(category, code)

    def parse_store_font(self):
        self.expect_punct("[")
        category = self.required_string()
        code = self.required_string()
        path = self.required_string()
        self.expect_punct("]")
        fn = Filename(path)
        if fn.get_extension() == "":
            fn.set_extension("bam")
        try:
            font = FontPool.load_font(fn.get_fullpath())
        except Exception:                          # noqa
            font = None
        if font is not None and font.is_valid():
            self.store.store_font(code, font)
            self.store.store_catalog_string(category, code)
        else:
            D._log("Unable to load font file", path)

    _POINT_TYPES = {"STREET_POINT": 0, "FRONT_DOOR_POINT": 1, "SIDE_DOOR_POINT": 2, "COGHQ_IN_POINT": 3, "COGHQ_OUT_POINT": 4}

    def parse_store_suit_point(self):
        self.expect_punct("[")
        vals = []
        while not self.is_punct("]") and self.peek() is not None:
            t = self.next()
            if t[0] == "num":
                vals.append(t[1])
            elif t[0] == "kw" and t[1] in self._POINT_TYPES:
                vals.append(self._POINT_TYPES[t[1]])
            elif t[0] == "p" and t[1] == ",":
                continue
            else:
                self.err("unexpected token in store_suit_point")
        self.expect_punct("]")
        if len(vals) < 5:
            self.err("store_suit_point needs at least 5 values")
            return
        index, ptype = int(vals[0]), int(vals[1])
        pos = D.LPoint3f(vals[2], vals[3], vals[4])
        lb = int(vals[5]) if len(vals) > 5 else -1
        self.store.store_suit_point(D.DNASuitPoint(index, ptype, pos, lb))

    # ---- nodes
    def name_tok(self):
        if self.is_punct("["):
            self.err("Name required.")
            return ""
        s = self.string_tok()
        if s is None:
            self.err("Name required.")
            return ""
        return s

    _ELEMENTS = ("GROUP", "VISGROUP", "NODE", "FLAT_BUILDING", "LANDMARK_BUILDING", "ANIM_BUILDING", "STREET", "ANIM_PROP", "INTERACTIVE_PROP",
                 "PROP", "CORNICE", "DOOR", "FLAT_DOOR", "WALL", "WINDOWS", "SIGN", "BASELINE", "GRAPHIC", "TEXT")
    _NAMED = ("GROUP", "VISGROUP", "NODE", "FLAT_BUILDING", "LANDMARK_BUILDING", "ANIM_BUILDING", "STREET", "ANIM_PROP", "INTERACTIVE_PROP", "PROP")

    def parse_element(self):
        t = self.next()
        if t[0] != "kw" or t[1] not in self._ELEMENTS:
            self.err("unexpected %r" % (t[1],))
            return None
        kw = t[1]
        name = self.name_tok() if kw in self._NAMED else ""
        obj = {
            "GROUP": D.DNAGroup, "VISGROUP": D.DNAVisGroup, "NODE": D.DNANode, "FLAT_BUILDING": D.DNAFlatBuilding,
            "LANDMARK_BUILDING": D.DNALandmarkBuilding, "ANIM_BUILDING": D.DNAAnimBuilding, "STREET": D.DNAStreet,
            "ANIM_PROP": D.DNAAnimProp, "INTERACTIVE_PROP": D.DNAInteractiveProp, "PROP": D.DNAProp, "CORNICE": D.DNACornice,
            "DOOR": D.DNADoor, "FLAT_DOOR": D.DNAFlatDoor, "WALL": D.DNAWall, "WINDOWS": D.DNAWindows, "SIGN": D.DNASign,
            "BASELINE": D.DNASignBaseline, "GRAPHIC": D.DNASignGraphic, "TEXT": D.DNASignText,
        }[kw](name) if kw in self._NAMED else {
            "CORNICE": D.DNACornice, "DOOR": D.DNADoor, "FLAT_DOOR": D.DNAFlatDoor, "WALL": D.DNAWall, "WINDOWS": D.DNAWindows,
            "SIGN": D.DNASign, "BASELINE": D.DNASignBaseline, "GRAPHIC": D.DNASignGraphic, "TEXT": D.DNASignText,
        }[kw]()
        if kw == "VISGROUP":
            self.zone = obj.get_name()
            self.store.store_DNAVisGroupAI(obj)
        elif kw in ("LANDMARK_BUILDING", "ANIM_BUILDING"):
            self.store.store_block_number(name, self.zone)
        if not self.expect_punct("["):
            return obj
        self.parse_body(kw, obj)
        return obj

    def parse_body(self, kw, obj):
        colors_seen = 0
        textures_seen = 0
        while True:
            t = self.peek()
            if t is None:
                self.err("unterminated block")
                return
            if t[0] == "p" and t[1] == "]":
                self.i += 1
                return
            if t[0] != "kw":
                self.err("unexpected token %r" % (t[1],))
                self.i += 1
                continue
            k = t[1]
            if k in self._ELEMENTS:
                child = self.parse_element()
                if child is not None:
                    obj.add(child)
                continue
            self.i += 1
            try:
                if k == "POS":
                    obj.set_pos(LVecBase3f(*self.bracket_reals(3)))
                elif k == "HPR":
                    obj.set_hpr(oldToNewHpr(LVecBase3f(*self.bracket_reals(3))))
                elif k == "NHPR":
                    obj.set_hpr(LVecBase3f(*self.bracket_reals(3)))
                elif k == "SCALE":
                    obj.set_scale(LVecBase3f(*self.bracket_reals(3)))
                elif k == "CODE":
                    obj.set_code(self.bracket_string())
                elif k == "COLOR":
                    c = LVecBase4f(*self.bracket_reals(4))
                    if isinstance(obj, D.DNAStreet):
                        colors_seen += 1
                        if colors_seen == 1:
                            obj.set_street_color(c)
                        elif colors_seen == 2:
                            obj.set_sidewalk_color(c)
                            obj.set_curb_color(c)
                        else:
                            obj.set_curb_color(c)
                    elif isinstance(obj, D.DNALandmarkBuilding):
                        obj.set_wall_color(c)
                    else:
                        obj.set_color(c)
                elif k == "TEXTURE":
                    tex = self.bracket_string()
                    textures_seen += 1
                    if textures_seen == 1:
                        obj.set_street_texture(tex)
                    elif textures_seen == 2:
                        obj.set_sidewalk_texture(tex)
                        obj.set_curb_texture(tex)
                    else:
                        obj.set_curb_texture(tex)
                elif k == "WIDTH":
                    obj.set_width(self.bracket_reals(1)[0])
                elif k == "HEIGHT":
                    obj.set_height(self.bracket_reals(1)[0])
                elif k == "ANIM":
                    obj.set_anim(self.bracket_string())
                elif k == "CELL_ID":
                    obj.set_cell_id(self.bracket_reals(1)[0])
                elif k == "COUNT":
                    obj.set_window_count(self.bracket_reals(1)[0])
                elif k == "TITLE":
                    obj.set_title(self.bracket_string())
                elif k == "ARTICLE":
                    obj.set_article(self.bracket_string())
                elif k == "BUILDING_TYPE":
                    bt = self.bracket_loose_string()
                    if bt:
                        obj.set_building_type(bt)
                        self.store.store_block_building_type(obj.get_name(), bt)
                elif k == "LETTERS":
                    obj.set_letters(self.bracket_string())
                elif k == "FLAGS":
                    obj.set_flags(self.bracket_string())
                elif k == "INDENT":
                    obj.set_indent(self.bracket_reals(1)[0])
                elif k == "KERN":
                    obj.set_kern(self.bracket_reals(1)[0])
                elif k == "WIGGLE":
                    obj.set_wiggle(self.bracket_reals(1)[0])
                elif k == "STUMBLE":
                    obj.set_stumble(self.bracket_reals(1)[0])
                elif k == "STOMP":
                    obj.set_stomp(self.bracket_reals(1)[0])
                elif k == "VIS":
                    self.expect_punct("[")
                    while not self.is_punct("]") and self.peek() is not None:
                        s = self.string_tok()
                        if s is None:
                            self.err("string expected in vis list")
                            self.i += 1
                            continue
                        obj.add_visible(s)
                    self.expect_punct("]")
                elif k == "SUIT_EDGE":
                    a, b = self.bracket_reals(2)
                    edge = self.store.store_suit_edge(int(a), int(b), obj.get_name())
                    if edge is not None:
                        obj.add_suit_edge(edge)
                elif k == "BATTLE_CELL":
                    w, h, x, y, z = self.bracket_reals(5)
                    cell = D.DNABattleCell(w, h, D.LPoint3f(x, y, z))
                    self.store.store_battle_cell(cell)
                    obj.add_battle_cell(cell)

                else:
                    self.err("unexpected keyword %s in %s" % (k, kw))
                    if self.is_punct("["):
                        self.i += 1
                        self.skip_to_close()
            except AttributeError:
                self.err("%s is not allowed in %s" % (k, kw))


def parse(text, top, filename=""):
    """Fill `top` (a DNAData with a storage) from DNA source text.  Returns True when there were no errors."""
    errors = []
    tokens = _tokenize(text, errors)
    p = _Parser(tokens, top, filename)
    p.errors = errors
    ok = p.parse()
    for e in p.errors[:20]:
        D._log("ERROR", e)
    return ok
