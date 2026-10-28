"""Pure-Python replacement for Open Toontown's compiled `panda3d.toontown` DNA classes (the town-layout loader).

Written from Open Toontown's own C++ source (panda/src/dna, BSD-licensed), so the browser build (which has no compiled
copy of that library) can load the same .dna files and build the same scene graph.
"""
import math
import os
import random
import re

from panda3d.core import (
    ConfigVariableSearchPath, DecalEffect, DSearchPath, Filename, FontPool, Loader, LoaderOptions, LColor, LPoint3f,
    LVecBase3f, LVecBase4f, LVector3f, ModelNode, NodePath, PandaNode, SceneGraphReducer, StaticTextFont, TextNode, TexturePool,
    VirtualFileSystem, getModelPath, oldToNewHpr, SamplerState, TextFont,
)

CSDefault = 0
_MUL = int(os.environ.get("TTR_DEPTH_MUL", "1") or 1)       # browser build: bigger depth offsets so pieces painted onto walls win reliably
_ALL = -1        # ~0, "combine everything"
_print = print


def _log(*a):
    _print("dna:", *a)


def _camel(name):
    parts = name.split("_")
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def camel_aliases(cls):
    """Give every snake_case method its camelCase twin, as Panda's own bindings do."""
    for n, v in list(vars(cls).items()):
        if n.startswith("_") or "_" not in n or not (callable(v) or isinstance(v, (staticmethod, classmethod))):
            continue
        c = _camel(n)
        if c != n and not hasattr(cls, c):
            setattr(cls, c, v)
    return cls


def _fail_copy(src, parent):
    """copy_to that survives an empty source (the C++ prints an assertion and carries on)."""
    if src is None or src.is_empty():
        _log("cannot copy an empty node")
        return NodePath()
    return src.copy_to(parent)


# ---------------------------------------------------------------------------------------------------- suit points, edges, paths
class DNASuitPoint:
    STREET_POINT = 0
    FRONT_DOOR_POINT = 1
    SIDE_DOOR_POINT = 2
    COGHQ_IN_POINT = 3
    COGHQ_OUT_POINT = 4
    STREETPOINT, FRONTDOORPOINT, SIDEDOORPOINT, COGHQINPOINT, COGHQOUTPOINT = 0, 1, 2, 3, 4

    def __init__(self, index, type, pos, lb_index=-1):
        self._index = int(index)
        self._type = int(type)
        self._pos = LPoint3f(pos)
        self._graph_id = 0
        self._lb_index = lb_index

    def set_index(self, i): self._index = i
    def get_index(self): return self._index
    def set_point_type(self, t): self._type = t
    def get_point_type(self): return self._type
    def set_pos(self, p): self._pos = LPoint3f(p)
    def get_pos(self): return self._pos
    def set_graph_id(self, g): self._graph_id = g
    def get_graph_id(self): return self._graph_id
    def set_landmark_building_index(self, i): self._lb_index = i
    def get_landmark_building_index(self): return self._lb_index

    def is_terminal(self):
        return self._type in (self.FRONT_DOOR_POINT, self.SIDE_DOOR_POINT, self.COGHQ_IN_POINT, self.COGHQ_OUT_POINT)

    def output(self, out=None):
        s = "<%d, %d, %s%s>" % (self._index, self._type, self._pos, (", %d" % self._lb_index) if self._lb_index >= 0 else "")
        return s

    def __str__(self):
        return self.output()


class DNASuitEdge:
    def __init__(self, start_point, end_point, zone_id):
        self._start_point = start_point
        self._end_point = end_point
        self._zone_id = str(zone_id)

    def get_start_point(self): return self._start_point
    def get_end_point(self): return self._end_point
    def get_zone_id(self): return self._zone_id
    def set_zone_id(self, z): self._zone_id = str(z)

    def same_as(self, other):
        return self._start_point is other._start_point and self._end_point is other._end_point

    def __str__(self):
        return "<%d %d zone %s>" % (self._start_point.get_index(), self._end_point.get_index(), self._zone_id)


class DNASuitPath:
    def __init__(self, reserve_length=0):
        self._path = []
        if isinstance(reserve_length, DNASuitPath):
            self._path = list(reserve_length._path)

    def get_num_points(self): return len(self._path)

    def get_point_index(self, i):
        if i < 0 or i >= len(self._path):
            return -1
        return self._path[i]

    def copy(self, other): self._path = list(other._path)
    def add_point(self, index): self._path.append(index)
    def reverse_path(self): self._path.reverse()
    def output(self, out=None): return "Path: [ " + "".join("%d " % i for i in self._path) + "]"


class DNABattleCell:
    def __init__(self, width, height, pos):
        self._width = width
        self._height = height
        self._pos = LPoint3f(pos)

    def set_width_height(self, w, h): self._width, self._height = w, h
    def get_width(self): return self._width
    def get_height(self): return self._height
    def set_pos(self, p): self._pos = LPoint3f(p)
    def get_pos(self): return self._pos

    def traverse(self, parent, store, editing=0):
        return parent

    def output(self, out=None):
        return "Width: %s Height: %s Pos: %s" % (self._width, self._height, self._pos)


# ---------------------------------------------------------------------------------------------------- the group classes
class DNAGroup:
    def __init__(self, initial_name=""):
        if isinstance(initial_name, DNAGroup):
            raise TypeError("copying DNA groups is not supported")
        self._name = initial_name
        self._group_vector = []
        self._parent = None

    # Namable
    def get_name(self): return self._name
    def set_name(self, n): self._name = n
    def has_name(self): return bool(self._name)
    def clear_name(self): self._name = ""
    name = property(get_name, set_name)

    # tree
    def add(self, group):
        self._group_vector.append(group)
        group._parent = self

    def remove(self, group):
        try:
            self._group_vector.remove(group)
        except ValueError:
            _log("group not found in map")
            return
        group._parent = None

    def at(self, index):
        if index < 0 or index >= len(self._group_vector):
            return None
        return self._group_vector[index]

    def current(self): return self._group_vector[-1]
    def get_num_children(self): return len(self._group_vector)
    def get_parent(self): return self._parent
    def set_parent(self, p): self._parent = p
    def clear_parent(self): self._parent = None

    def is_of_type(self, t):
        return isinstance(t, type) and isinstance(self, t)

    @classmethod
    def get_class_type(cls):
        return cls

    def traverse(self, parent, store, editing=0):
        node_path = parent.attach_new_node(PandaNode(self.get_name()))
        for g in self._group_vector:
            g.traverse(node_path, store, editing)
        if editing:
            store.store_DNAGroup(node_path.node(), self)
        return node_path

    def top_level_traverse(self, parent, store, editing=0):
        node_path = parent.attach_new_node(PandaNode(self.get_name()))
        for g in self._group_vector:
            g.traverse(node_path, store, editing)
            g.clear_parent()
        if editing:
            store.store_DNAGroup(node_path.node(), self)
        return node_path

    def write(self, out, store, indent_level=0):
        raise NotImplementedError("writing DNA is not supported")

    def ls(self): pass


class DNANode(DNAGroup):
    def __init__(self, initial_name=""):
        DNAGroup.__init__(self, initial_name)
        self._pos = LVecBase3f(0, 0, 0)
        self._hpr = LVecBase3f(0, 0, 0)
        self._scale = LVecBase3f(1, 1, 1)

    def set_pos(self, p): self._pos = LVecBase3f(p)
    def get_pos(self): return LVecBase3f(self._pos)
    def set_hpr(self, h): self._hpr = LVecBase3f(h)
    def get_hpr(self): return LVecBase3f(self._hpr)
    def set_scale(self, s): self._scale = LVecBase3f(s)
    def get_scale(self): return LVecBase3f(self._scale)

    def traverse(self, parent, store, editing=0):
        node_path = parent.attach_new_node(PandaNode(self.get_name()))
        node_path.set_pos_hpr_scale(self._pos, self._hpr, self._scale)
        for g in self._group_vector:
            g.traverse(node_path, store, editing)
        if editing:
            store.store_DNAGroup(node_path.node(), self)
        return node_path


class DNAVisGroup(DNAGroup):
    def __init__(self, initial_name=""):
        DNAGroup.__init__(self, initial_name)
        self._vis_vector = []
        self._suit_edge_vector = []
        self._battle_cell_vector = []

    def add_visible(self, name): self._vis_vector.append(name)

    def remove_visible(self, name):
        if name not in self._vis_vector:
            _log("vis group not found in map:", name)
            return 0
        self._vis_vector.remove(name)
        return 1

    def get_num_visibles(self): return len(self._vis_vector)

    def get_visible_name(self, i):
        return self._vis_vector[i] if 0 <= i < len(self._vis_vector) else ""

    def add_suit_edge(self, edge):
        if edge.get_start_point() is edge.get_end_point():
            return
        for e in self._suit_edge_vector:
            if e.same_as(edge):
                return
        self._suit_edge_vector.append(edge)

    def remove_suit_edge(self, edge):
        for i, e in enumerate(self._suit_edge_vector):
            if e is edge:
                del self._suit_edge_vector[i]
                return 1
        return 0

    def get_num_suit_edges(self): return len(self._suit_edge_vector)
    def get_suit_edge(self, i): return self._suit_edge_vector[i] if 0 <= i < len(self._suit_edge_vector) else None
    def add_battle_cell(self, cell): self._battle_cell_vector.append(cell)

    def remove_battle_cell(self, cell):
        for i, c in enumerate(self._battle_cell_vector):
            if c is cell:
                del self._battle_cell_vector[i]
                return 1
        return 0

    def get_num_battle_cells(self): return len(self._battle_cell_vector)
    def get_battle_cell(self, i): return self._battle_cell_vector[i] if 0 <= i < len(self._battle_cell_vector) else None

    def traverse(self, parent, store, editing=0):
        node_path = parent.attach_new_node(PandaNode(self.get_name()))
        for g in self._group_vector:
            g.traverse(node_path, store, editing)
        if editing:
            store.store_DNAGroup(node_path.node(), self)
        store.store_DNAVisGroup(node_path.node(), self)
        return node_path


class DNAProp(DNANode):
    def __init__(self, initial_name=""):
        DNANode.__init__(self, initial_name)
        self._code = ""
        self._color = LVecBase4f(1, 1, 1, 1)

    def set_code(self, c): self._code = c
    def get_code(self): return self._code
    def set_color(self, c): self._color = LVecBase4f(c)
    def get_color(self): return LVecBase4f(self._color)

    def _make_prop_node(self, parent, store):
        if self._code == "DCS":
            model_node = ModelNode(self.get_name())
            model_node.set_preserve_transform(ModelNode.PT_net)
            return parent.attach_new_node(model_node)
        source_prop = store.find_node(self._code)
        if source_prop.is_empty():
            return None
        prop_node_path = source_prop.copy_to(parent)
        if source_prop.has_tag("DNARoot"):
            prop_node_path.set_tag("DNARoot", source_prop.get_tag("DNARoot"))
        if source_prop.has_tag("DNACode"):
            prop_node_path.set_tag("DNACode", source_prop.get_tag("DNACode"))
        prop_node_path.node().set_name(self.get_name())
        return prop_node_path

    def _extra_tags(self, np):
        pass

    def traverse(self, parent, store, editing=0):
        prop_node_path = self._make_prop_node(parent, store)
        if prop_node_path is None:
            return NodePath()
        self._extra_tags(prop_node_path)
        prop_node_path.set_pos_hpr_scale(self._pos, self._hpr, self._scale)
        prop_node_path.set_color_scale(self._color)
        for g in self._group_vector:
            g.traverse(prop_node_path, store, editing)
        if editing:
            store.store_DNAGroup(prop_node_path.node(), self)
        return prop_node_path


class DNAAnimProp(DNAProp):
    def __init__(self, initial_name=""):
        DNAProp.__init__(self, initial_name)
        self._anim = ""

    def set_anim(self, a): self._anim = a
    def get_anim(self): return self._anim

    def _extra_tags(self, np):
        np.set_tag("DNAAnim", self._anim)


class DNAInteractiveProp(DNAAnimProp):
    def __init__(self, initial_name=""):
        DNAAnimProp.__init__(self, initial_name)
        self._cell_id = -1

    def set_cell_id(self, c): self._cell_id = int(c)
    def get_cell_id(self): return self._cell_id

    def _extra_tags(self, np):
        np.set_tag("DNAAnim", self._anim)
        np.set_tag("DNACellIndex", chr(self._cell_id) if 0 <= self._cell_id < 0x110000 else "")      # the C++ appends the number as one character


# ---------------------------------------------------------------------------------------------------- buildings
class DNAWall(DNANode):
    current_wall_height = 0.0

    def __init__(self, initial_name=""):
        DNANode.__init__(self, initial_name)
        self._code = ""
        self._height = 10.0
        self._color = LVecBase4f(1, 1, 1, 1)

    def set_code(self, c): self._code = c
    def get_code(self): return self._code
    def set_height(self, h): self._height = h
    def get_height(self): return self._height
    def set_color(self, c): self._color = LVecBase4f(c)
    def get_color(self): return LVecBase4f(self._color)

    def traverse(self, parent, store, editing=0):
        wall_node_path = _fail_copy(store.find_node(self._code), parent)
        self._pos.set_z(DNAWall.current_wall_height)
        self._scale.set_z(self._height)
        wall_node_path.set_pos_hpr_scale(self._pos, self._hpr, self._scale)
        wall_node_path.set_color(self._color)
        for g in self._group_vector:
            g.traverse(wall_node_path, store, editing)
        if editing:
            store.store_DNAGroup(wall_node_path.node(), self)
        DNAWall.current_wall_height += self._height
        return wall_node_path


def _is_taken_over_name(name):
    return len(name) > 2 and name[0] == "t" and name[1] == "b" and name[2].isdigit() and ":" in name


class DNAFlatBuilding(DNANode):
    def __init__(self, initial_name=""):
        DNANode.__init__(self, initial_name)
        self._width = 10.0

    def set_width(self, w): self._width = w
    def get_width(self): return self._width
    def get_current_wall_height(self): return DNAWall.current_wall_height

    def has_door(self, parent_group):
        for i in range(parent_group.get_num_children()):
            group = parent_group.at(i)
            if isinstance(group, DNAFlatDoor):
                return True
            if self.has_door(group):
                return True
        return False

    def _setup_suit_like_flat_building(self, parent, store, prefix, catalog):
        name = self.get_name()
        if not _is_taken_over_name(name):
            return
        name = prefix + name[1:]
        suit_node = ModelNode(name)
        suit_building_node_path = parent.attach_new_node(suit_node)
        scale = self.get_scale()
        scale[2] *= DNAWall.current_wall_height
        suit_building_node_path.set_pos_hpr_scale(self.get_pos(), self.get_hpr(), scale)
        count = store.get_num_catalog_codes(catalog)
        name = store.get_catalog_code(catalog, random.randrange(count) if count > 0 else 0)
        np = store.find_node(name)
        if not np.is_empty():
            np.copy_to(suit_building_node_path)
            if self.has_door(self):
                wall_node_path = suit_building_node_path.find("wall_*")
                door_node_path = store.find_node("suit_door").copy_to(wall_node_path)
                door_node_path.set_scale(NodePath(), 1, 1, 1)
                door_node_path.set_pos_hpr(0.5, 0, 0, 0, 0, 0)
                wall_node_path.node().set_effect(DecalEffect.make())
        suit_building_node_path.flatten_medium()
        suit_building_node_path.stash()

    def setup_suit_flat_building(self, parent, store):
        self._setup_suit_like_flat_building(parent, store, "s", "suit_wall")

    def setup_cogdo_flat_building(self, parent, store):
        self._setup_suit_like_flat_building(parent, store, "c", "cogdo_wall")

    def traverse(self, parent, store, editing=0):
        DNAWall.current_wall_height = 0
        building_node_path = parent.attach_new_node(self.get_name())
        internal_node_path = building_node_path.attach_new_node(self.get_name() + "-internal")
        self._scale.set_x(self._width)
        internal_node_path.set_scale(self._scale)
        building_node_path.set_pos_hpr(self._pos, self._hpr)
        for group in self._group_vector:
            if isinstance(group, DNAWall):
                group.traverse(internal_node_path, store, editing)
            else:
                group.traverse(building_node_path, store, editing)
        if DNAWall.current_wall_height == 0.0:
            _log("empty flat building with no walls")
            return parent
        wall_camera_barrier_node_path = _fail_copy(store.find_node("wall_camera_barrier"), internal_node_path)
        wall_camera_barrier_node_path.set_scale(1.0, 1.0, DNAWall.current_wall_height)
        self.setup_suit_flat_building(parent, store)
        self.setup_cogdo_flat_building(parent, store)
        gr = SceneGraphReducer()
        gr.apply_attribs(internal_node_path.node())
        if editing:
            store.store_DNAGroup(building_node_path.node(), self)
        else:
            door_sphere_node_path = building_node_path.find("**/door_*/+CollisionNode")
            if not door_sphere_node_path.is_empty():
                block = store.get_block(self.get_name())
                door_sphere_node_path.node().set_name("KnockKnockDoorSphere_" + block)
            wall_camera_barrier_node_path.wrt_reparent_to(parent)
            wall_collection = internal_node_path.find_all_matches("wall*")
            wall_holder = building_node_path.attach_new_node("wall_holder")
            wall_decal_holder = building_node_path.attach_new_node("wall_decal_holder")
            window_collection = internal_node_path.find_all_matches("**/window*")
            door_collection = internal_node_path.find_all_matches("**/door*")
            cornice_collection = internal_node_path.find_all_matches("**/cornice*_d")
            wall_collection.reparent_to(wall_holder)
            if _MUL > 1:
                wall_decal_holder.set_depth_offset(_MUL)
            window_collection.reparent_to(wall_decal_holder)
            door_collection.reparent_to(wall_decal_holder)
            cornice_collection.reparent_to(wall_decal_holder)
            for i in range(wall_holder.get_num_children()):
                child = wall_holder.get_child(i)
                child.clear_tag("DNACode")
                child.clear_tag("DNARoot")
            gr.flatten(wall_holder.node(), _ALL)
            gr.flatten(wall_decal_holder.node(), _ALL)
            if wall_holder.get_num_children() != 1:
                _log("flat building", self.get_name(), "flattened to", wall_holder.get_num_children(), "walls")
                return parent
            wall = wall_holder.get_child(0)
            wall_decal_holder.get_children().reparent_to(wall)
            wall.reparent_to(internal_node_path)
            wall.node().set_effect(DecalEffect.make())
            wall_holder.remove_node()
            wall_decal_holder.remove_node()
            gr.flatten(building_node_path.node(), _ALL)
        return building_node_path


class DNALandmarkBuilding(DNANode):
    def __init__(self, initial_name=""):
        DNANode.__init__(self, initial_name)
        self._code = ""
        self._building_type = ""
        self._wall_color = LVecBase4f(1, 1, 1, 1)
        self._title = ""
        self._article = ""

    def set_title(self, t): self._title = t
    def get_title(self): return self._title
    def set_article(self, a): self._article = a
    def get_article(self): return self._article
    def set_code(self, c): self._code = c
    def get_code(self): return self._code
    def set_wall_color(self, c): self._wall_color = LVecBase4f(c)
    def get_wall_color(self): return LVecBase4f(self._wall_color)
    def set_building_type(self, t): self._building_type = t
    def get_building_type(self): return self._building_type

    def setup_suit_building_origin(self, parent, building_node_path):
        name = self.get_name()
        if not _is_taken_over_name(name):
            return
        name = "s" + name[1:]
        np = building_node_path.find("**/*suit_building_origin")
        if not np.is_empty():
            np.wrt_reparent_to(parent)
            np.node().set_name(name)
        else:
            _log("DNALandmarkBuilding", name, "did not find **/*suit_building_origin")
            suit_building_node_path = parent.attach_new_node(name)
            suit_building_node_path.set_pos_hpr_scale(self.get_pos(), self.get_hpr(), self.get_scale())

    def traverse(self, parent, store, editing=0):
        building_node_path = _fail_copy(store.find_node(self._code), parent)
        building_node_path.node().set_name(self.get_name())
        building_node_path.set_pos_hpr_scale(self._pos, self._hpr, self._scale)
        block = store.get_block(self.get_name())
        store.store_block_title(block, self._title)
        store.store_block_article(block, self._article)
        if self.get_building_type() == "":
            self.setup_suit_building_origin(parent, building_node_path)
        for g in self._group_vector:
            g.traverse(building_node_path, store, editing)
        if editing:
            store.store_DNAGroup(building_node_path.node(), self)
        else:
            gr = SceneGraphReducer()
            gr.apply_attribs(building_node_path.node())
            gr.flatten(building_node_path.node(), _ALL)
            if self.get_building_type() != "hq":
                door_origin = building_node_path.find("**/*door_origin")
                if not door_origin.is_empty():
                    door_origin.remove_node()
            sign_origin = building_node_path.find("**/*sign_origin")
            if not sign_origin.is_empty():
                sign_origin.remove_node()
        return building_node_path


class DNAAnimBuilding(DNALandmarkBuilding):
    def __init__(self, initial_name=""):
        DNALandmarkBuilding.__init__(self, initial_name)
        self._anim = ""

    def set_anim(self, a): self._anim = a
    def get_anim(self): return self._anim

    def traverse(self, parent, store, editing=0):
        building_node_path = _fail_copy(store.find_node(self._code), parent)
        building_node_path.node().set_name(self.get_name())
        building_node_path.set_pos_hpr_scale(self._pos, self._hpr, self._scale)
        building_node_path.set_tag("DNAAnim", self._anim)
        block = store.get_block(self.get_name())
        store.store_block_title(block, self._title)
        store.store_block_article(block, self._article)
        self.setup_suit_building_origin(parent, building_node_path)
        for g in self._group_vector:
            g.traverse(building_node_path, store, editing)
        if editing:
            store.store_DNAGroup(building_node_path.node(), self)
        else:
            gr = SceneGraphReducer()
            gr.apply_attribs(building_node_path.node())
            gr.flatten(building_node_path.node(), _ALL)
        return building_node_path


# ---------------------------------------------------------------------------------------------------- doors, windows, cornices
class DNADoor(DNAGroup):
    def __init__(self, initial_name=""):
        DNAGroup.__init__(self, initial_name)
        self._code = ""
        self._color = LVecBase4f(1, 1, 1, 1)

    def set_color(self, c): self._color = LVecBase4f(c)
    def get_color(self): return LVecBase4f(self._color)
    def set_code(self, c): self._code = c
    def get_code(self): return self._code

    def traverse(self, parent, store, editing=0):
        building_front = parent.find("**/*_front")
        if building_front.is_empty():
            _log("door: no _front under", parent.get_name())
            return parent
        if not building_front.node().is_geom_node():
            building_front = building_front.find("**/+GeomNode")
            if building_front.is_empty():
                return parent
        building_front.node().set_effect(DecalEffect.make())
        door_code = store.find_node(self._code)
        if door_code.is_empty():
            _log("Door not found:", self._code)
            return parent
        door_node_path = door_code.copy_to(building_front)
        door_origin = parent.find("**/*door_origin")
        if door_origin.is_empty():
            _log("door: no door_origin under", parent.get_name())
            return parent
        block = store.get_block(parent.node().get_name())
        DNADoor.setup_door(door_node_path, parent, door_origin, store, block, self._color)
        store.store_block_door_pos_hpr(block, door_origin.get_pos(NodePath()), door_origin.get_hpr(NodePath()))
        if editing:
            store.store_DNAGroup(door_node_path.node(), self)
        return door_node_path

    @staticmethod
    def setup_door(door_node_path, parent, door_origin, store, block, color):
        door_node_path.set_pos_hpr_scale(door_origin, LVector3f(0), LVector3f(0), LVector3f(1))
        door_node_path.set_color(color)
        hole_left = door_node_path.find("door_*_hole_left")
        hole_left.node().set_name("doorFrameHoleLeft")
        hole_right = door_node_path.find("door_*_hole_right")
        hole_right.node().set_name("doorFrameHoleRight")
        right_door = door_node_path.find("door_*_right")
        right_door.node().set_name("rightDoor")
        left_door = door_node_path.find("door_*_left")
        left_door.node().set_name("leftDoor")
        door_frame = door_node_path.find("door_*_flat")
        if not door_frame.is_empty():
            hole_left.wrt_reparent_to(door_frame)
            hole_right.wrt_reparent_to(door_frame)
            door_frame.node().set_effect(DecalEffect.make())
            if _MUL > 1:
                door_frame.set_depth_offset(_MUL - 1)
                hole_left.set_depth_offset(_MUL)
                hole_right.set_depth_offset(_MUL)
            right_door.wrt_reparent_to(parent)
            left_door.wrt_reparent_to(parent)
            right_door.hide()
            left_door.hide()
        hole_left.hide()
        hole_right.hide()
        right_door.set_color(color)
        left_door.set_color(color)
        hole_left.set_color(LVecBase4f(0, 0, 0, 1))
        hole_right.set_color(LVecBase4f(0, 0, 0, 1))
        door_trigger = door_node_path.find("door_*_trigger")
        door_trigger.wrt_reparent_to(parent)
        door_trigger.node().set_name("door_trigger_" + str(block))


class DNAFlatDoor(DNADoor):
    def traverse(self, parent, store, editing=0):
        door_node_path = _fail_copy(store.find_node(self._code), parent)
        door_node_path.set_scale(NodePath(), 1, 1, 1)
        door_node_path.set_pos_hpr(0.5, 0, 0, 0, 0, 0)
        door_node_path.set_color(self._color)
        if editing:
            parent.node().set_effect(DecalEffect.make())
            store.store_DNAGroup(door_node_path.node(), self)
        return door_node_path


_pos_jitter = 0.025
_hpr_jitter = 6.0
_scale_jitter = 0.025


def _rj(amount):
    return random.random() * amount - amount / 2.0


class DNAWindows(DNAGroup):
    def __init__(self, initial_name=""):
        DNAGroup.__init__(self, initial_name)
        self._code = ""
        self._window_count = 1
        self._color = LVecBase4f(1, 1, 1, 1)

    def set_code(self, c): self._code = c
    def get_code(self): return self._code
    def set_color(self, c): self._color = LVecBase4f(c)
    def get_color(self): return LVecBase4f(self._color)
    def set_window_count(self, n): self._window_count = int(n)
    def get_window_count(self): return self._window_count

    def traverse(self, parent, store, editing=0):
        if self._window_count == 0:
            return parent
        window_node_path = NodePath()
        width = parent.get_parent().get_sx()
        hpr = LVector3f(0.0, 0.0, _rj(_hpr_jitter))
        if width <= 5.0:
            s = 1.0 + _rj(_scale_jitter)
        elif width <= 10.0:
            s = 1.15 + _rj(_scale_jitter)
        else:
            s = 1.3 + _rj(_scale_jitter)
        scale = LVector3f(s, s, s)

        def place(code, pos):
            np = _fail_copy(store.find_node(code), parent)
            np.set_color(self._color)
            np.set_scale(NodePath(), scale)
            np.set_pos(LVector3f(*pos))
            np.set_hpr(hpr)
            return np

        n = self._window_count
        if n == 1:
            window_node_path = place(self._code, (0.5 + _rj(_pos_jitter), 0.0, 0.5 + _rj(_pos_jitter)))
        elif n == 2:
            code_size = len(self._code)
            for i in (1, 2):
                # the C++ writes the new ending into the stored code itself, as well as using it
                self._code = self._code[:code_size - 2] + ("ur" if i == 1 else "ul")
                window_node_path = place(self._code, ((i / float(n + 1)) + _rj(_pos_jitter), 0.0, 0.5 + _rj(_pos_jitter)))
        elif n == 3:
            spots = ((0.33, 0.66), (0.5, 0.33), (0.66, 0.66))
            for x, z in spots:
                window_node_path = place(self._code, (x + _rj(_pos_jitter), 0.0, z + _rj(_pos_jitter)))
        elif n == 4:
            spots = ((0.33, 0.75), (0.66, 0.75), (0.33, 0.25), (0.66, 0.25))
            for x, z in spots:
                window_node_path = place(self._code, (x + _rj(_pos_jitter), 0.0, z + _rj(_pos_jitter)))
        if editing:
            parent.node().set_effect(DecalEffect.make())
            store.store_DNAGroup(window_node_path.node(), self)
        return parent


class DNACornice(DNAGroup):
    def __init__(self, initial_name=""):
        DNAGroup.__init__(self, initial_name)
        self._code = ""
        self._color = LVecBase4f(1, 1, 1, 1)

    def set_color(self, c): self._color = LVecBase4f(c)
    def get_color(self): return LVecBase4f(self._color)
    def set_code(self, c): self._code = c
    def get_code(self): return self._code

    def traverse(self, parent, store, editing=0):
        height = parent.get_sz()
        width = parent.get_parent().get_sx()
        z = DNAWall.current_wall_height + height
        cornice_node_path = store.find_node(self._code)
        cornice_d = _fail_copy(cornice_node_path.find("**/*_d"), parent)
        cornice_d.set_pos_hpr_scale(LVector3f(0.0, 0.0, 1.0), LVector3f(0.0), LVector3f(1.0, width / height, width / height))
        cornice_d.set_color(self._color)
        cornice_nd = _fail_copy(cornice_node_path.find("**/*_nd"), parent.get_parent())
        cornice_nd.set_pos_hpr_scale(LVector3f(0.0, 0.0, z), LVector3f(0.0), LVector3f(1.0, width, width))
        cornice_nd.set_color(self._color)
        if editing:
            store.store_DNAGroup(cornice_d.node(), self)
        return cornice_d


class DNAStreet(DNANode):
    def __init__(self, initial_name=""):
        DNANode.__init__(self, initial_name)
        self._code = ""
        self._street_texture = ""
        self._sidewalk_texture = ""
        self._curb_texture = ""
        self._street_color = LVecBase4f(1, 1, 1, 1)
        self._sidewalk_color = LVecBase4f(1, 1, 1, 1)
        self._curb_color = LVecBase4f(1, 1, 1, 1)

    def set_code(self, c): self._code = c
    def get_code(self): return self._code
    def set_street_color(self, c): self._street_color = LVecBase4f(c)
    def get_street_color(self): return LVecBase4f(self._street_color)
    def set_sidewalk_color(self, c): self._sidewalk_color = LVecBase4f(c)
    def get_sidewalk_color(self): return LVecBase4f(self._sidewalk_color)
    def set_curb_color(self, c): self._curb_color = LVecBase4f(c)
    def get_curb_color(self): return LVecBase4f(self._curb_color)
    def set_street_texture(self, t): self._street_texture = t
    def get_street_texture(self): return self._street_texture
    def set_sidewalk_texture(self, t): self._sidewalk_texture = t
    def get_sidewalk_texture(self): return self._sidewalk_texture
    def set_curb_texture(self, t): self._curb_texture = t
    def get_curb_texture(self): return self._curb_texture

    def traverse(self, parent, store, editing=0):
        street_node_path = _fail_copy(store.find_node(self._code), parent)
        street_node_path.node().set_name(self.get_name())
        street_texture = store.find_texture(self._street_texture)
        sidewalk_texture = store.find_texture(self._sidewalk_texture)
        curb_texture = store.find_texture(self._curb_texture)
        for pattern, tex, color in (("**/*_street", street_texture, self._street_color),
                                    ("**/*_sidewalk", sidewalk_texture, self._sidewalk_color),
                                    ("**/*_curb", curb_texture, self._curb_color)):
            part = street_node_path.find(pattern)
            if not part.is_empty():
                if tex is not None:
                    part.set_texture(tex, 1)
                part.set_color_scale(color)
        street_node_path.set_pos_hpr_scale(self._pos, self._hpr, self._scale)
        if editing:
            store.store_DNAGroup(street_node_path.node(), self)
        return street_node_path


# ---------------------------------------------------------------------------------------------------- signs
class DNASign(DNANode):
    def __init__(self, initial_name=""):
        DNANode.__init__(self, initial_name)
        self._code = ""
        self._color = LVecBase4f(1, 1, 1, 1)

    def set_code(self, c): self._code = c
    def get_code(self): return self._code
    def set_color(self, c): self._color = LVecBase4f(c)
    def get_color(self): return LVecBase4f(self._color)

    def traverse(self, parent, store, editing=0):
        building_front = parent.find("**/sign_decal")
        if building_front.is_empty():
            building_front = parent.find("**/*_front")
        if building_front.is_empty():
            return parent
        if not building_front.node().is_geom_node():
            building_front = building_front.find("**/+GeomNode")
            if building_front.is_empty():
                return parent
        building_front.node().set_effect(DecalEffect.make())
        if self._code:
            found = store.find_node(self._code)
            if found.is_empty():
                _log("Sign not found in storage:", self._code)
                return parent
            sign_node_path = found.copy_to(building_front)
            sign_node_path.node().set_name("sign")
        else:
            sign_node_path = building_front.attach_new_node(ModelNode("sign"))
        sign_node_path.set_depth_offset(_MUL)
        sign_origin = parent.find("**/*sign_origin")
        if sign_origin.is_empty():
            _log("sign: no sign_origin under", parent.get_name())
            return parent
        sign_node_path.set_pos_hpr_scale(sign_origin, self._pos, self._hpr, self._scale)
        sign_node_path.set_color(self._color)
        for g in self._group_vector:
            g.traverse(sign_node_path, store, editing)
        if editing:
            store.store_DNAGroup(sign_node_path.node(), self)
        else:
            building = parent
            while not building.is_empty() and (not building.get_name() or building.get_name()[:2] != "tb"):
                building = building.get_parent()
            if not building.is_empty() and "landmark" in building.get_name():
                block = store.get_block(building.get_name())
                store.store_block_sign_transform(block, sign_origin.get_transform(building).get_mat())
            if not sign_node_path.is_empty():
                gr = SceneGraphReducer()
                gr.apply_attribs(sign_node_path.node())
                gr.flatten(sign_node_path.node(), _ALL)
        return sign_node_path


_PI = 3.141592653589793


class DNASignBaseline(DNANode):
    def __init__(self, initial_name=""):
        DNANode.__init__(self, initial_name)
        self._code = ""
        self._color = LVecBase4f(1, 1, 1, 1)
        self._next_pos = LVector3f(0, 0, 0)
        self._next_hpr = LVector3f(0, 0, 0)
        self._next_scale = LVector3f(1, 1, 1)
        self._indent = 0.0
        self._kern = 0.0
        self._wiggle = 0.0
        self._stumble = 0.0
        self._stomp = 0.0
        self._counter = 0
        self._total_width = 0.0
        self._flags = ""
        self._prior_char_was_blank = True
        self._width = 0.0
        self._height = 0.0
        self._prior_cursor = 0.0
        self._cursor = 0.0
        self._font = None

    def set_code(self, c): self._code = c
    def get_code(self): return self._code
    def set_color(self, c): self._color = LVecBase4f(c)
    def get_color(self): return LVecBase4f(self._color)
    def set_font(self, f): self._font = f
    def get_font(self): return self._font
    def set_indent(self, v): self._indent = v
    def get_indent(self): return self._indent
    def set_kern(self, v): self._kern = v
    def get_kern(self): return self._kern
    def get_current_kern(self): return self._counter * self._kern
    def set_wiggle(self, v): self._wiggle = v
    def get_wiggle(self): return self._wiggle
    def get_current_wiggle(self): return self._wiggle if (self._counter & 1) else -self._wiggle
    def set_stumble(self, v): self._stumble = v
    def get_stumble(self): return self._stumble
    def get_current_stumble(self): return self._stumble if (self._counter & 1) else -self._stumble
    def set_stomp(self, v): self._stomp = v
    def get_stomp(self): return self._stomp
    def get_current_stomp(self): return self._stomp if (self._counter & 1) else -self._stomp
    def reset_counter(self): self._counter = 0
    def inc_counter(self): self._counter += 1
    def set_width(self, v): self._width = v
    def get_width(self): return self._width
    def set_height(self, v): self._height = v
    def get_height(self): return self._height
    def set_flags(self, f): self._flags = f
    def get_flags(self): return self._flags

    def baseline_next_pos_hpr_scale(self, pos, hpr, scale, size):
        if self._width != 0.0 or self._height != 0.0:
            self.circle_next_pos_hpr_scale(pos, hpr, scale, size)
        else:
            self.line_next_pos_hpr_scale(pos, hpr, scale, size)

    def reset(self):
        self._next_pos = LVector3f(0, 0, 0)
        self._next_hpr = LVector3f(0, 0, 0)
        self._next_scale = LVector3f(1, 1, 1)
        self._counter = 0
        self._prior_char_was_blank = True
        self._total_width = 0.0
        self._prior_cursor = 0.0
        self._cursor = 0.0

    def is_first_letter_of_word(self, letter):
        if letter[:1] == " ":
            self._prior_char_was_blank = True
            return False
        elif self._prior_char_was_blank:
            self._prior_char_was_blank = False
            return True
        self._prior_char_was_blank = False
        return False

    def traverse(self, parent, store, editing=0):
        self.reset()
        baseline_np = parent.attach_new_node("baseline")
        if self._code:
            self._font = store.find_font(self._code)
            if self._font is None:
                _log("unable to find baseline font", self._code)
        baseline_np.set_color(self._color)
        groups = reversed(self._group_vector) if (self._width < 0.0 or self._height < 0.0) else self._group_vector
        for g in groups:
            g.traverse(baseline_np, store, editing)
        pos = LVector3f(self._pos)
        hpr = LVector3f(self._hpr)
        pos, hpr = self.center(pos, hpr)
        baseline_np.set_depth_write(False)
        baseline_np.set_pos_hpr_scale(parent, pos, hpr, LVector3f(1))
        if editing:
            store.store_DNAGroup(baseline_np.node(), self)
        return baseline_np

    def center(self, pos, hpr):
        quarter_circle = _PI * 0.5
        angle = -self._hpr[2] * (_PI / 180.0)          # temp_hpr_fix is on
        if self._width != 0.0 or self._height != 0.0:
            x_radius = self._width * 0.5
            z_radius = self._height * 0.5
            angle += quarter_circle
            sin_ang, cos_ang = math.sin(angle), math.cos(angle)
            pos[0] -= x_radius * cos_ang
            pos[2] -= z_radius * sin_ang
            hpr[2] += self._prior_cursor * 0.5
        else:
            self._counter -= 1
            gap_width = self.get_current_kern() + self.get_current_stumble()
            self._counter += 1
            radius = (self._total_width + gap_width) * 0.5
            sin_ang, cos_ang = math.sin(angle), math.cos(angle)
            pos[0] -= radius * cos_ang
            pos[2] -= radius * sin_ang
        pos[1] -= 0.05                                   # panda_depth_hack is on
        return pos, hpr

    def line_next_pos_hpr_scale(self, pos, hpr, scale, size):
        scale[0] *= self._scale[0]
        scale[1] *= self._scale[1]
        scale[2] *= self._scale[2]
        pos += self._next_pos
        pos[0] += self.get_current_kern() + self.get_current_stumble()
        pos[2] += self.get_current_stomp()
        scaled_width = scale[0] * size[0]
        self._next_pos[0] += scaled_width
        self._total_width += scaled_width
        hpr[2] -= self.get_current_wiggle()
        self.inc_counter()

    def circle_next_pos_hpr_scale(self, pos, hpr, scale, size):
        quarter_circle = _PI * 0.5
        d2r = _PI / 180.0
        r2d = 180.0 / _PI
        scale[0] *= self._scale[0]
        scale[1] *= self._scale[1]
        scale[2] *= self._scale[2]
        x_radius = self._width * 0.5
        z_radius = self._height * 0.5
        x_offset = pos[0] if self._width < 0.0 else -pos[0]
        half_circ = _PI * x_radius
        radian_width_delta = x_offset / half_circ * _PI
        degree_delta = -self.get_indent() if self._width < 0.0 else self.get_indent()
        radian_delta = degree_delta * d2r + radian_width_delta
        radian_cursor = self._cursor * d2r
        radian_total = radian_cursor + quarter_circle + radian_delta
        radius_delta = pos[2] + self.get_current_stomp()
        if self._width < 0.0:
            radius_delta = -radius_delta
        sin_ang, cos_ang = math.sin(radian_total), math.cos(radian_total)
        new_x = (x_radius + radius_delta) * cos_ang
        new_z = (z_radius + radius_delta) * sin_ang
        pos[0] = new_x
        pos[2] = new_z
        hpr[2] -= self._cursor + degree_delta + self.get_current_wiggle()
        hypot = math.sqrt(new_x * new_x + new_z * new_z)
        if self._width < 0.0:
            self._prior_cursor = radian_cursor * r2d
        scaled_width = scale[0] * size[0]
        radian_cursor = radian_cursor - 2.0 * math.asin(min(scaled_width / (2.0 * hypot), 1.0))
        if self._width >= 0.0:
            self._prior_cursor = radian_cursor * r2d
        gap_width = self.get_kern() - self.get_current_stumble()
        radian_cursor = radian_cursor - 2.0 * math.asin(max(-1.0, min(gap_width / (2.0 * hypot), 1.0)))
        temp_cursor = self._cursor
        self._cursor = radian_cursor * r2d
        knock_back = (self._cursor - temp_cursor) * 0.5
        if self._width >= 0.0:
            hpr[2] -= knock_back
        self.inc_counter()


class _SignPiece(DNANode):
    """Common part of DNASignText and DNASignGraphic: a decal on the nearest geom, placed by the baseline."""

    def _decal_on_geom_ancestor(self, parent):
        geom_parent = parent
        node = geom_parent.node()
        while not node.is_geom_node() and not geom_parent.is_singleton():
            geom_parent = geom_parent.get_parent()
            node = geom_parent.node()
        if node.is_geom_node():
            node.set_effect(DecalEffect.make())


class DNASignGraphic(_SignPiece):
    def __init__(self, initial_name=""):
        DNANode.__init__(self, initial_name)
        self._code = ""
        self._color = LVecBase4f(1, 1, 1, 1)
        self._width = 0.0
        self._height = 0.0
        self._use_baseline_color = True

    def set_code(self, c): self._code = c
    def get_code(self): return self._code
    def set_color(self, c): self._color = LVecBase4f(c)
    def get_color(self): return LVecBase4f(self._color)
    def set_width(self, v): self._width = v
    def get_width(self): return self._width
    def set_height(self, v): self._height = v
    def get_height(self): return self._height

    def traverse(self, parent, store, editing=0):
        self._decal_on_geom_ancestor(parent)
        graphic_np = _fail_copy(store.find_node(self._code), parent)
        baseline = self.get_parent()
        color = LVecBase4f(self._color)
        if self._use_baseline_color:
            color = baseline.get_color()
        bl_pos = LVector3f(self._pos)
        bl_hpr = LVector3f(self._hpr)
        bl_scale = LVector3f(self._scale)
        baseline.baseline_next_pos_hpr_scale(bl_pos, bl_hpr, bl_scale, LVector3f(self.get_width(), 0.0, self.get_height()))
        graphic_np.set_pos_hpr_scale(parent, bl_pos, bl_hpr, bl_scale)
        graphic_np.set_color(color)
        if _MUL > 1:
            graphic_np.set_depth_offset(_MUL)
        for g in self._group_vector:
            g.traverse(graphic_np, store, editing)
        if editing:
            store.store_DNAGroup(graphic_np.node(), self)
        return graphic_np


class DNASignText(_SignPiece):
    def __init__(self, initial_name=""):
        DNANode.__init__(self, initial_name)
        self._code = ""
        self._color = LVecBase4f(1, 1, 1, 1)
        self._letters = ""
        self._use_baseline_color = True

    def set_code(self, c): self._code = c
    def get_code(self): return self._code
    def set_color(self, c): self._color = LVecBase4f(c)
    def get_color(self): return LVecBase4f(self._color)
    def set_letters(self, s): self._letters = s
    def get_letters(self): return self._letters

    def traverse(self, parent, store, editing=0):
        self._decal_on_geom_ancestor(parent)
        baseline = self.get_parent()
        font = None
        if not self._code:
            font = baseline.get_font()
        else:
            font_node = store.find_node(self._code)
            if font_node.is_empty():
                _log("unable to find SignText font", self._code)
            else:
                font = StaticTextFont(font_node.node())
        if font is None and self._letters:
            font = TextNode.get_default_font()
            if font is None:
                _log("no font specified for", repr(self._letters), "and no default font available")
        color = LVecBase4f(self._color)
        if self._use_baseline_color:
            color = baseline.get_color()
        text_node = TextNode("sign")
        text_node.set_text_color(color)
        if font is not None:
            text_node.set_font(font)
        letters = self._letters
        flags = baseline.get_flags()
        if "c" in flags:
            letters = letters.upper()
        if "d" in flags:
            text_node.set_shadow_color(color[0] * 0.3, color[1] * 0.3, color[2] * 0.3, color[3] * 0.7)
            text_node.set_shadow(0.03, 0.03)
        text_node.set_text(letters)
        bl_pos = LVector3f(self._pos)
        bl_hpr = LVector3f(self._hpr)
        bl_scale = LVector3f(self._scale)
        if "b" in flags and baseline.is_first_letter_of_word(letters):
            bl_scale[0] *= 1.5
            bl_scale[2] *= 1.5
        baseline.baseline_next_pos_hpr_scale(bl_pos, bl_hpr, bl_scale, LVector3f(text_node.get_width(), 0.0, text_node.get_height()))
        text_np = parent.attach_new_node(text_node.generate())
        text_np.set_pos_hpr_scale(parent, bl_pos, bl_hpr, bl_scale)
        text_np.set_color_off()
        if _MUL > 1:
            text_np.set_depth_offset(_MUL)
        text_np.set_color(color)
        for g in self._group_vector:
            g.traverse(text_np, store, editing)
        if editing:
            store.store_DNAGroup(text_np.node(), self)
        return text_np


# ---------------------------------------------------------------------------------------------------- storage
class PosHpr:
    def __init__(self, pos=None, hpr=None):
        self._pos = LPoint3f(pos) if pos is not None else LPoint3f(0)
        self._hpr = LPoint3f(hpr) if hpr is not None else LPoint3f(0)

    def get_pos(self): return self._pos
    def get_hpr(self): return self._hpr


class _WorkingSuitPath:
    __slots__ = ("next_in_path", "next_in_chain", "point_index")

    def __init__(self, point_index, nxt=None):
        self.next_in_path = nxt
        self.next_in_chain = None
        self.point_index = point_index

    def get_point_index(self): return self.point_index

    def get_path(self, path):
        chain = []
        p = self
        while p is not None:
            chain.append(p.point_index)
            p = p.next_in_path
        for i in reversed(chain):
            path.add_point(i)


def _atoi(s):
    m = re.match(r"\s*[+-]?\d+", str(s))
    return int(m.group(0)) if m else 0


class DNAStorage:
    def __init__(self):
        self._code_catalog = {}
        self._texture_map = {}
        self._node_map = {}
        self._font_map = {}
        self._hood_node_map = {}
        self._block_map = {}
        self._block_door_pos_hpr_map = {}
        self._block_sign_transform_map = {}
        self._block_title_map = {}
        self._block_article_map = {}
        self._block_building_type_map = {}
        self._place_node_map = {}
        self._n2group_map = {}
        self._n2visgroup_map = {}
        self._suit_point_vector = []
        self._suit_point_map = {}
        self._suit_start_point_map = {}
        self._battle_cell_vector = []
        self._vis_group_vector = []

    # -- plain storage
    def store_texture(self, code_string, texture):
        if texture is None:
            return
        texture.set_minfilter(SamplerState.FT_linear_mipmap_linear)
        texture.set_magfilter(SamplerState.FT_linear)
        texture.set_anisotropic_degree(4)
        self._texture_map[code_string] = texture

    def store_font(self, code_string, font):
        if font is not None:
            self._font_map[code_string] = font

    def _prepare_node(self, code_string, node, code_category):
        if code_category == "holiday_prop" and not node.node().is_of_type(ModelNode.get_class_type()):
            model_np = NodePath(ModelNode(node.get_name()))
            node.copy_to(model_np)
            node = model_np
        node.set_tag("DNACode", code_string)
        node.set_tag("DNARoot", code_category)
        return node

    def store_node(self, code_string, node, code_category=""):
        self._node_map[code_string] = self._prepare_node(code_string, node, code_category)

    def store_hood_node(self, code_string, node, code_category=""):
        self._hood_node_map[code_string] = self._prepare_node(code_string, node, code_category)

    def store_place_node(self, code_string, node, code_category=""):
        self._place_node_map[code_string] = self._prepare_node(code_string, node, code_category)

    def find_texture(self, dna_string):
        t = self._texture_map.get(dna_string)
        if t is None:
            _log("texture:", dna_string, "not found in map")
        return t

    def find_node(self, dna_string):
        for m in (self._node_map, self._hood_node_map, self._place_node_map):
            n = m.get(dna_string)
            if n is not None:
                return n
        return NodePath()

    def find_font(self, dna_string):
        f = self._font_map.get(dna_string)
        if f is None:
            _log("font:", dna_string, "not found in map")
        return f

    def reset_nodes(self): self._node_map.clear()
    def reset_textures(self): self._texture_map.clear()

    def reset_hood(self):
        self.reset_hood_nodes()
        self.reset_place_nodes()
        self.reset_suit_points()
        self.reset_battle_cells()

    def reset_hood_nodes(self): self._hood_node_map.clear()
    def reset_place_nodes(self): self._place_node_map.clear()

    def reset_suit_points(self):
        self._suit_point_vector.clear()
        self._suit_point_map.clear()
        self._suit_start_point_map.clear()

    def reset_battle_cells(self): self._battle_cell_vector.clear()
    def reset_DNAGroups(self): self._n2group_map.clear()
    def reset_DNAVisGroups(self): self._n2visgroup_map.clear()
    def reset_DNAVisGroupsAI(self): self._vis_group_vector.clear()
    def reset_block_numbers(self): self._block_map.clear()
    def reset_block_door_pos_hprs(self): self._block_door_pos_hpr_map.clear()
    def reset_block_sign_transforms(self): self._block_sign_transform_map.clear()
    def reset_block_title(self): self._block_title_map.clear()
    def reset_block_article(self): self._block_article_map.clear()

    # -- catalog
    def store_catalog_string(self, catalog_string, dna_string):
        self._code_catalog.setdefault(catalog_string, set()).add(dna_string)

    def get_num_catalog_codes(self, catalog_string):
        c = self._code_catalog.get(catalog_string)
        return -1 if c is None else len(c)

    def get_catalog_code(self, catalog_string, index):
        c = self._code_catalog.get(catalog_string)
        if c is None:
            return ""
        s = sorted(c)                                    # the C++ set is ordered
        return s[index] if 0 <= index < len(s) else ""

    # -- groups
    def store_DNAGroup(self, node, group):
        if node is not None and group is not None:
            self._n2group_map[node] = group

    def find_DNAGroup(self, node):
        return self._n2group_map.get(node)

    def find_PandaNode(self, group):
        for n, g in self._n2group_map.items():
            if g is group:
                return n
        for n, g in self._n2visgroup_map.items():
            if g is group:
                return n
        _log("find_PandaNode: DNAGroup", group.get_name(), "not found")
        return None

    def remove_DNAGroup(self, rr):
        group = rr if isinstance(rr, DNAGroup) else self.find_DNAGroup(rr)
        if group is None:
            return 0
        removed = 0
        node = self.find_PandaNode(group)
        if node is not None and node in self._n2group_map:
            del self._n2group_map[node]
            removed += 1
        for i in range(group.get_num_children()):
            removed += self.remove_DNAGroup(group.at(i))
        return removed

    def store_DNAVisGroup(self, node, group):
        if node is not None and group is not None:
            self._n2visgroup_map[node] = group

    def remove_DNAVisGroup(self, node):
        return 1 if self._n2visgroup_map.pop(node, None) is not None else 0

    def find_DNAVisGroup(self, node):
        g = self._n2visgroup_map.get(node)
        if g is None:
            _log("find_DNAVisGroup: NodePath not found in Node2VisGroupMap")
        return g

    def get_num_DNAVisGroups(self): return len(self._n2visgroup_map)

    def get_DNAVisGroup(self, i):
        vals = list(self._n2visgroup_map.values())
        return vals[i] if 0 <= i < len(vals) else None

    def get_num_visibles_in_DNAVisGroup(self, i):
        g = self.get_DNAVisGroup(i)
        return g.get_num_visibles() if g is not None else -1

    def get_DNAVisGroup_name(self, i):
        g = self.get_DNAVisGroup(i)
        return g.get_name() if g is not None else ""

    def get_visible_name(self, visgroup_index, visible_index):
        g = self.get_DNAVisGroup(visgroup_index)
        return g.get_visible_name(visible_index) if g is not None else ""

    def store_DNAVisGroupAI(self, vis_group):
        if vis_group is not None:
            self._vis_group_vector.append(vis_group)

    def get_num_DNAVisGroupsAI(self): return len(self._vis_group_vector)

    def get_DNAVisGroupAI(self, i):
        return self._vis_group_vector[i] if 0 <= i < len(self._vis_group_vector) else None

    def get_num_PandaNodes(self): return len(self._n2group_map)

    def get_PandaNode_at(self, i):
        keys = list(self._n2group_map.keys())
        return keys[i] if 0 <= i < len(keys) else None

    # -- blocks
    def store_block_number(self, block, zone_id):
        if not block or not zone_id:
            return
        colon = block.find(":")
        self._block_map[_atoi(block[2:colon if colon >= 0 else len(block)])] = _atoi(zone_id)

    def get_zone_from_block_number(self, block_number):
        if block_number not in self._block_map:
            _log("block number:", block_number, "not found in map")
            return 0
        return self._block_map[block_number]

    def get_num_block_numbers(self): return len(self._block_map)

    def get_block_number_at(self, index):
        keys = sorted(self._block_map)
        return keys[index] if 0 <= index < len(keys) else 0

    def store_block_door_pos_hpr(self, block, pos, hpr):
        if block:
            self._block_door_pos_hpr_map[_atoi(block)] = PosHpr(pos, hpr)

    def get_door_pos_hpr_from_block_number(self, block_number):
        if block_number not in self._block_door_pos_hpr_map:
            _log("block number:", block_number, "not found in map")
            return PosHpr()
        return self._block_door_pos_hpr_map[block_number]

    def get_num_block_door_pos_hprs(self): return len(self._block_door_pos_hpr_map)

    def get_door_pos_hpr_block_at(self, index):
        keys = sorted(self._block_door_pos_hpr_map)
        return keys[index] if 0 <= index < len(keys) else 0

    def store_block_sign_transform(self, block, mat):
        if block:
            self._block_sign_transform_map[_atoi(block)] = mat

    def get_sign_transform_from_block_number(self, block_number):
        from panda3d.core import LMatrix4f
        if block_number not in self._block_sign_transform_map:
            _log("block number:", block_number, "not found in map")
            return LMatrix4f.ident_mat()
        return self._block_sign_transform_map[block_number]

    def get_num_block_sign_transforms(self): return len(self._block_sign_transform_map)

    def get_sign_transform_block_at(self, index):
        keys = sorted(self._block_sign_transform_map)
        return keys[index] if 0 <= index < len(keys) else 0

    def store_block_title(self, block, title):
        if block:
            self._block_title_map[_atoi(block)] = title

    def get_title_from_block_number(self, block_number):
        if block_number not in self._block_title_map:
            _log("block number:", block_number, "not found in title map")
            return ""
        return self._block_title_map[block_number]

    def get_num_block_titles(self): return len(self._block_title_map)

    def get_title_block_at(self, index):
        keys = sorted(self._block_title_map)
        return keys[index] if 0 <= index < len(keys) else 0

    def store_block_article(self, block, article):
        if block:
            self._block_article_map[_atoi(block)] = article

    def get_article_from_block_number(self, block_number):
        if block_number not in self._block_article_map:
            _log("block number:", block_number, "not found in article map")
            return ""
        return self._block_article_map[block_number]

    def store_block_building_type(self, block, type):
        if not block:
            return
        colon = block.find(":")
        self._block_building_type_map[_atoi(block[2:colon if colon >= 0 else len(block)])] = type

    def get_block_building_type(self, block_number):
        return self._block_building_type_map.get(block_number, "")

    def get_block(self, name):
        pos = name.find(":")
        return name[2:pos] if pos >= 0 else name[2:]

    # -- battle cells
    def store_battle_cell(self, cell):
        if cell is not None:
            self._battle_cell_vector.append(cell)

    def remove_battle_cell(self, cell):
        for i, c in enumerate(self._battle_cell_vector):
            if c is cell:
                del self._battle_cell_vector[i]
                return 1
        return 0

    # -- suit points and edges
    def store_suit_point(self, a, b=None, c=None):
        if isinstance(a, DNASuitPoint):
            self._suit_point_vector.append(a)
            self._suit_point_map[a.get_index()] = a
            return a.get_index()
        type_, pos = a, b
        for point in self._suit_point_vector:
            if pos.almost_equal(point.get_pos(), 0.9):
                return point
        index = self.get_highest_suit_point_index() + 1
        point = DNASuitPoint(index, type_, pos)
        self.store_suit_point(point)
        return point

    def get_highest_suit_point_index(self):
        highest = -1
        for p in self._suit_point_vector:
            if p.get_index() > highest:
                highest = p.get_index()
        return highest

    def fix_coincident_suit_points(self):
        n = 0
        for p1 in self._suit_point_vector:
            for p2 in self._suit_point_vector:
                if p1 is not p2 and p1.get_pos().almost_equal(p2.get_pos(), 0.9):
                    n += 1
        return n

    def delete_unused_suit_points(self):
        n = 0
        for point in list(self._suit_point_vector):
            if point.get_index() in self._suit_start_point_map:
                continue
            used = False
            for vg in self._vis_group_vector:
                for e in range(vg.get_num_suit_edges()):
                    edge = vg.get_suit_edge(e)
                    if edge.get_start_point() is point or edge.get_end_point() is point:
                        used = True
                        break
                if used:
                    break
            if not used:
                self._suit_point_vector.remove(point)
                n += 1
        return n

    def remove_suit_point(self, point):
        result = 0
        for edges in self._suit_start_point_map.values():
            for edge in list(edges):
                if edge.get_start_point() is point or edge.get_end_point() is point:
                    edges.remove(edge)
                    for vg in self._vis_group_vector:
                        vg.remove_suit_edge(edge)
        if self._suit_start_point_map.pop(point.get_index(), None) is not None:
            result += 1
        if point in self._suit_point_vector:
            self._suit_point_vector.remove(point)
            result += 1
        return result

    def store_suit_edge(self, a, b=None, c=None):
        if isinstance(a, DNASuitEdge):
            edge = a
            if edge.get_start_point() is edge.get_end_point():
                return edge
            sev = self._suit_start_point_map.setdefault(edge.get_start_point().get_index(), [])
            for e in sev:
                if e.same_as(edge):
                    return e
            sev.append(edge)
            return edge
        start_point = self.get_suit_point_with_index(a)
        end_point = self.get_suit_point_with_index(b)
        if start_point is None or end_point is None:
            return None
        return self.store_suit_edge(DNASuitEdge(start_point, end_point, c))

    def remove_suit_edge(self, edge):
        found = 0
        sev = self._suit_start_point_map.get(edge.get_start_point().get_index())
        if sev is not None and edge in sev:
            sev.remove(edge)
            found = 1
        for vg in self._vis_group_vector:
            vg.remove_suit_edge(edge)
        return found

    def get_num_suit_points(self): return len(self._suit_point_vector)

    def get_suit_point_at_index(self, index):
        return self._suit_point_vector[index] if 0 <= index < len(self._suit_point_vector) else None

    def get_suit_point_with_index(self, index):
        return self._suit_point_map.get(index)

    def get_suit_edge(self, start_index, end_index):
        edges = self._suit_start_point_map.get(start_index)
        if edges is None:
            _log("DNASuitStartPoint index:", start_index, "not found in map")
            return None
        for e in edges:
            if e.get_end_point().get_index() == end_index:
                return e
        _log("DNASuitStartPoint start index:", start_index, "not connected to end index:", end_index)
        return None

    def get_suit_edge_zone(self, start_index, end_index):
        edge = self.get_suit_edge(start_index, end_index)
        return edge.get_zone_id() if edge is not None else ""

    def get_suit_edge_travel_time(self, start_index, end_index, rate):
        if not rate > 0.0:
            return -1.0
        edge = self.get_suit_edge(start_index, end_index)
        if edge is None:
            return -1.0
        distance = (edge.get_end_point().get_pos() - edge.get_start_point().get_pos()).length()
        return distance / rate

    def get_adjacent_points(self, start_point):
        path = DNASuitPath()
        for edge in self._suit_start_point_map.get(start_point.get_index(), ()):
            path.add_point(edge.get_end_point().get_index())
        return path

    def discover_continuity(self):
        graph_id = 0
        for point in self._suit_point_vector:
            if point.get_graph_id() == 0:
                graph_id += 1
                self._discover_connections(point, graph_id)
        return graph_id

    def _discover_connections(self, point, graph_id):
        stack = [point]
        while stack:
            p = stack.pop()
            if p.get_graph_id() != 0:
                if p.get_graph_id() != graph_id:
                    _log(p, "is connected to graph only one-way")
                continue
            p.set_graph_id(graph_id)
            edges = self._suit_start_point_map.get(p.get_index())
            if edges is None:
                _log("Could not find point", p.get_index(), "in map")
            else:
                for edge in reversed(edges):
                    stack.append(edge.get_end_point())

    def get_suit_path(self, start_point, end_point, min_length, max_length):
        if start_point.get_graph_id() != end_point.get_graph_id():
            return None
        path = self._get_suit_path_breadth_first(start_point, end_point, min_length, max_length)
        return path          # (the planner tries many end points and expects most to fail: stay quiet)

    def _get_suit_path_breadth_first(self, start_point, end_point, min_length, max_length):
        chain = _WorkingSuitPath(start_point.get_index())
        length = 1
        while length < min_length - 1:
            length += 1
            chain = self._generate_next_suit_path_chain(chain)
        visited = set()
        while length < max_length and chain is not None:
            length += 1
            found, chain = self._consider_next_suit_path_chain(chain, end_point, visited)
            if found:
                path = DNASuitPath(length)
                chain.get_path(path)
                return path
        return None

    def _generate_next_suit_path_chain(self, chain):
        next_chain = None
        current_path = chain
        while current_path is not None:
            next_path = current_path.next_in_chain
            current_path.next_in_chain = None
            current_index = current_path.get_point_index()
            prev_index = current_path.next_in_path.get_point_index() if current_path.next_in_path is not None else -1
            edges = self._suit_start_point_map.get(current_index)
            if edges is None:
                _log("Could not find point", current_index, "in map")
            else:
                for edge in edges:
                    next_index = edge.get_end_point().get_index()
                    if not edge.get_end_point().is_terminal():
                        if next_index == current_index or next_index == prev_index:
                            _log("Invalid edge detected in dna:", edge)
                        else:
                            new_path = _WorkingSuitPath(next_index, current_path)
                            new_path.next_in_chain = next_chain
                            next_chain = new_path
            current_path = next_path
        return next_chain

    def _consider_next_suit_path_chain(self, chain, end_point, visited):
        next_chain = None
        current_path = chain
        while current_path is not None:
            next_path = current_path.next_in_chain
            current_path.next_in_chain = None
            current_index = current_path.get_point_index()
            prev_index = current_path.next_in_path.get_point_index() if current_path.next_in_path is not None else -1
            edges = self._suit_start_point_map.get(current_index)
            if edges is None:
                _log("Could not find point", current_index, "in map")
            else:
                for edge in edges:
                    next_index = edge.get_end_point().get_index()
                    if next_index == end_point.get_index():
                        return True, _WorkingSuitPath(next_index, current_path)
                    if not edge.get_end_point().is_terminal():
                        if next_index == current_index or next_index == prev_index:
                            _log("Invalid edge detected in dna:", edge)
                        elif next_index not in visited:
                            visited.add(next_index)
                            new_path = _WorkingSuitPath(next_index, current_path)
                            new_path.next_in_chain = next_chain
                            next_chain = new_path
            current_path = next_path
        return False, next_chain

    # -- misc
    def fixup(self):
        self.delete_unused_suit_points()
        self.fix_coincident_suit_points()

    def print_node_storage(self): pass
    def print_texture_storage(self): pass
    def print_font_storage(self): pass
    def print_suit_point_storage(self): pass
    def print_battle_cell_storage(self): pass
    def print_catalog(self): pass
    def print_PandaNodes(self): pass
    def write(self, out, indent_level=0): pass


# ---------------------------------------------------------------------------------------------------- data + loader
class DNAData(DNAGroup):
    def __init__(self, initial_name=""):
        DNAGroup.__init__(self, initial_name)
        self._coordsys = CSDefault
        self._dna_filename = Filename()
        self._dna_store = None

    def set_dna_filename(self, f): self._dna_filename = Filename(f)
    def get_dna_filename(self): return self._dna_filename
    def set_dna_storage(self, s): self._dna_store = s
    def get_dna_storage(self): return self._dna_store
    def set_coordinate_system(self, cs): self._coordsys = cs
    def get_coordinate_system(self): return self._coordsys

    @staticmethod
    def resolve_dna_filename(dna_filename, searchpath=None):
        vfs = VirtualFileSystem.get_global_ptr()
        searchpath = searchpath if searchpath is not None else DSearchPath()
        if not (vfs.resolve_filename(dna_filename, searchpath, "dna") or
                vfs.resolve_filename(dna_filename, get_dna_path(), "dna") or
                vfs.resolve_filename(dna_filename, getModelPath().getValue(), "dna")):
            pass
        return vfs.exists(dna_filename)

    def read(self, source, error=None):
        from . import dnaparser
        if isinstance(source, (str, Filename)):
            filename = Filename(source)
            if not self.resolve_dna_filename(filename):
                _log("Could not find", filename)
                return False
            self.set_dna_filename(filename)
            data = VirtualFileSystem.get_global_ptr().read_file(filename, True)
            text = bytes(data).decode("latin-1")
        elif isinstance(source, (bytes, bytearray)):
            text = bytes(source).decode("latin-1")
        else:
            text = source.read()
        self._group_vector.clear()
        return dnaparser.parse(text, self, str(self._dna_filename))


def get_dna_path():
    return ConfigVariableSearchPath("dna-path").get_value()


class DNALoader:
    def __init__(self):
        self._data = DNAData("loader_data")
        self._root = NodePath(PandaNode("dna"))

    def build_graph(self, dna_store, editing=0):
        top = self._data.top_level_traverse(self._root, dna_store, editing)
        if top.get_num_children() != 0:
            return top.get_child(0).node()
        _log("DNA File contained no geometry, returning empty node")
        return None

    def get_data(self):
        return self._data


def _read_into(loader, dna_store, filename, cs):
    dna_filename = Filename(filename)
    if not dna_filename.is_fully_qualified() or not VirtualFileSystem.get_global_ptr().exists(dna_filename):
        if not DNAData.resolve_dna_filename(dna_filename):
            _log("could not find", filename, "in dna_path", get_dna_path(), "or model_path", getModelPath().getValue())
            return None
    loader._data.set_dna_filename(dna_filename)
    loader._data.set_dna_storage(dna_store)
    if cs != CSDefault:
        loader._data.set_coordinate_system(cs)
    return dna_filename


def load_DNA_file(dna_store, filename, cs=CSDefault, editing=0):
    loader = DNALoader()
    dna_filename = _read_into(loader, dna_store, filename, cs)
    if dna_filename is None:
        return None
    if not loader._data.read(dna_filename):
        _log("Error reading", dna_filename)
        return None
    return loader.build_graph(dna_store, editing)


def load_DNA_file_AI(dna_store, filename, cs=CSDefault):
    loader = DNALoader()
    dna_filename = _read_into(loader, dna_store, filename, cs)
    if dna_filename is None:
        return None
    if not loader._data.read(dna_filename):
        _log("Error reading", dna_filename)
        return None
    return loader._data


for _c in (DNASuitPoint, DNASuitEdge, DNASuitPath, DNABattleCell, DNAGroup, DNANode, DNAVisGroup, DNAProp, DNAAnimProp, DNAInteractiveProp,
           DNAWall, DNAFlatBuilding, DNALandmarkBuilding, DNAAnimBuilding, DNADoor, DNAFlatDoor, DNAWindows, DNACornice, DNAStreet, DNASign,
           DNASignBaseline, DNASignGraphic, DNASignText, PosHpr, DNAStorage, DNAData, DNALoader):
    camel_aliases(_c)

loadDNAFile = load_DNA_file
loadDNAFileAI = load_DNA_file_AI
getDnaPath = get_dna_path
