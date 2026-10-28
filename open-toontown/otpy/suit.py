"""Python version of Open Toontown's SuitLeg / SuitLegList (the Cog walking schedule built from a DNA suit path)."""
from panda3d.core import LPoint3f

from .dna import DNASuitPoint, camel_aliases, _log


class SuitLeg:
    T_walk_from_street = 0
    T_walk_to_street = 1
    T_walk = 2
    T_from_sky = 3
    T_to_sky = 4
    T_from_suit_building = 5
    T_to_suit_building = 6
    T_to_toon_building = 7
    T_from_coghq = 8
    T_to_coghq = 9
    T_off = 10

    _NAMES = ("WalkFromStreet", "WalkToStreet", "Walk", "FromSky", "ToSky", "FromSuitBuilding", "ToSuitBuilding", "ToToonBuilding", "FromCogHQ", "ToCogHQ", "Off")

    def __init__(self, type, start_time, leg_time, zone_id, block_number, point_a, point_b):
        self._type = type
        self._start_time = start_time
        self._leg_time = leg_time
        self._zone_id = zone_id
        self._block_number = block_number
        self._point_a = point_a.get_index()
        self._point_b = point_b.get_index()
        self._pos_a = LPoint3f(point_a.get_pos())
        self._pos_b = LPoint3f(point_b.get_pos())

    def get_type(self): return self._type
    def get_start_time(self): return self._start_time
    def get_leg_time(self): return self._leg_time
    def get_zone_id(self): return self._zone_id
    def get_block_number(self): return self._block_number
    def get_point_a(self): return self._point_a
    def get_point_b(self): return self._point_b
    def get_pos_a(self): return LPoint3f(self._pos_a)
    def get_pos_b(self): return LPoint3f(self._pos_b)

    def get_pos_at_time(self, time):
        t = self._type
        if t in (self.T_from_sky, self.T_from_suit_building, self.T_from_coghq):
            return LPoint3f(self._pos_a)
        if t in (self.T_to_sky, self.T_to_suit_building, self.T_to_toon_building, self.T_to_coghq, self.T_off):
            return LPoint3f(self._pos_b)
        if time < 0.0:
            return LPoint3f(self._pos_a)
        if time > self._leg_time:
            return LPoint3f(self._pos_b)
        return self._pos_a + (self._pos_b - self._pos_a) * (time / self._leg_time)

    @staticmethod
    def get_type_name(type):
        return SuitLeg._NAMES[type] if 0 <= type < len(SuitLeg._NAMES) else "**invalid**"

    def output(self, out=None):
        return "(%d, %s (%s), %d, %d, %d)" % (self._type, self._start_time, self._leg_time, self._zone_id, self._point_a, self._point_b)


for _n in ("T_walk_from_street", "T_walk_to_street", "T_walk", "T_from_sky", "T_to_sky", "T_from_suit_building", "T_to_suit_building", "T_to_toon_building",
           "T_from_coghq", "T_to_coghq", "T_off"):
    _v = getattr(SuitLeg, _n)
    _parts = _n.split("_")
    setattr(SuitLeg, _parts[0] + "".join(p.capitalize() for p in _parts[1:]), _v)         # TWalkFromStreet, TFromCoghq, ...


class SuitLegList:
    def __init__(self, path, storage, suit_walk_speed, from_sky_time, to_sky_time, from_suit_building_time, to_suit_building_time, to_toon_building_time):
        self._legs = []
        if path.get_num_points() <= 0:
            return
        i = 0
        pi = path.get_point_index(i)
        point = storage.get_suit_point_with_index(pi)
        next_pi = path.get_point_index(i + 1)
        next_point = storage.get_suit_point_with_index(next_pi)
        type_ = self._first_leg_type(point)
        time = 0.0
        zone_id = 0
        if type_ == SuitLeg.T_from_sky:
            leg_time = from_sky_time
        elif type_ == SuitLeg.T_from_suit_building:
            leg_time = from_suit_building_time
        else:
            leg_time = 0.0
        legs = self._legs
        legs.append(SuitLeg(type_, time, leg_time, zone_id, 0, point, next_point))
        time += leg_time
        i += 1
        while i < path.get_num_points():
            next_pi = path.get_point_index(i)
            next_point = storage.get_suit_point_with_index(next_pi)
            zone_id = self._zone_id_of(storage, pi, next_pi)
            if point.get_point_type() == DNASuitPoint.COGHQ_OUT_POINT:
                type_ = SuitLeg.T_from_coghq
                leg_time = from_suit_building_time
                legs.append(SuitLeg(type_, time, leg_time, zone_id, point.get_landmark_building_index(), point, point))
                time += leg_time
            type_ = self._next_leg_type(point, next_point)
            leg_time = storage.get_suit_edge_travel_time(pi, next_pi, suit_walk_speed)
            legs.append(SuitLeg(type_, time, leg_time, zone_id, 0, point, next_point))
            time += leg_time
            if next_point.get_point_type() == DNASuitPoint.COGHQ_IN_POINT:
                type_ = SuitLeg.T_to_coghq
                leg_time = to_suit_building_time
                legs.append(SuitLeg(type_, time, leg_time, zone_id, next_point.get_landmark_building_index(), next_point, next_point))
                time += leg_time
            point = next_point
            pi = next_pi
            i += 1
        type_ = self._last_leg_type(point)
        if type_ == SuitLeg.T_to_sky:
            leg_time = to_sky_time
        elif type_ == SuitLeg.T_to_suit_building:
            leg_time = to_suit_building_time
        elif type_ == SuitLeg.T_to_toon_building:
            leg_time = to_toon_building_time
        else:
            leg_time = 0.0
        pi = path.get_point_index(i - 2)
        point = storage.get_suit_point_with_index(pi)
        legs.append(SuitLeg(type_, time, leg_time, zone_id, 0, point, next_point))
        time += leg_time
        legs.append(SuitLeg(SuitLeg.T_off, time, 0.0, zone_id, 0, point, next_point))
        legs[0]._zone_id = legs[1]._zone_id

    def get_num_legs(self): return len(self._legs)

    def get_leg(self, n):
        if not 0 <= n < len(self._legs):
            _log("SuitLegList.get_leg: bad index", n)
            return self._legs[0]
        return self._legs[n]

    def __getitem__(self, n): return self.get_leg(n)

    def get_leg_index_at_time(self, time, start):
        legs = self._legs
        if start < 0 or start >= len(legs) or legs[start]._start_time > time:
            start = 0
        i = start
        while i + 1 < len(legs) and legs[i + 1]._start_time <= time:
            i += 1
        return i

    def get_type(self, n): return self.get_leg(n).get_type()
    def get_start_time(self, n): return self.get_leg(n).get_start_time()
    def get_leg_time(self, n): return self.get_leg(n).get_leg_time()
    def get_zone_id(self, n): return self.get_leg(n).get_zone_id()
    def get_block_number(self, n): return self.get_leg(n).get_block_number()
    def get_point_a(self, n): return self.get_leg(n).get_point_a()
    def get_point_b(self, n): return self.get_leg(n).get_point_b()

    def is_point_in_range(self, point, begin, end):
        point_index = point.get_index()
        start_index = self.get_leg_index_at_time(begin, 0)
        end_index = self.get_leg_index_at_time(end, start_index)
        for i in range(start_index, end_index + 1):
            leg = self._legs[i]
            if leg.get_point_a() == point_index or leg.get_point_b() == point_index:
                return True
        return False

    def output(self, out=None): return "SuitLegList, %d legs." % len(self._legs)

    def write(self, out=None):
        return "SuitLegList:\n" + "".join("  %d. %s\n" % (i, l.output()) for i, l in enumerate(self._legs))

    @staticmethod
    def _first_leg_type(point):
        return SuitLeg.T_from_suit_building if point.get_point_type() == DNASuitPoint.SIDE_DOOR_POINT else SuitLeg.T_from_sky

    @staticmethod
    def _next_leg_type(prev_point, curr_point):
        door = (DNASuitPoint.FRONT_DOOR_POINT, DNASuitPoint.SIDE_DOOR_POINT)
        if curr_point.get_point_type() in door:
            return SuitLeg.T_walk_from_street
        if prev_point.get_point_type() in door:
            return SuitLeg.T_walk_to_street
        return SuitLeg.T_walk

    @staticmethod
    def _last_leg_type(point):
        t = point.get_point_type()
        if t == DNASuitPoint.FRONT_DOOR_POINT:
            return SuitLeg.T_to_toon_building
        if t == DNASuitPoint.SIDE_DOOR_POINT:
            return SuitLeg.T_to_suit_building
        return SuitLeg.T_to_sky

    @staticmethod
    def _zone_id_of(storage, pi_a, pi_b):
        name = storage.get_suit_edge_zone(pi_a, pi_b)
        colon = name.find(":")
        if colon >= 0:
            name = name[:colon]
        try:
            return int(name)
        except ValueError:
            _log("SuitLegList: bad zone name", repr(name))
            return 0


camel_aliases(SuitLeg)
camel_aliases(SuitLegList)
