"""Python versions of Open Toontown's CMover / CImpulse / CMoverGroup (otp movement) and the pet brain pieces (CPetBrain / CPetChase / CPetFlee)."""
import math

from panda3d.core import ClockObject, LVector3f, NodePath

from .dna import camel_aliases


class CImpulse:
    def __init__(self):
        self._mover = None
        self._node_path = NodePath()

    def process(self, dt):
        pass

    def set_mover(self, mover):
        self._mover = mover
        self._node_path = mover.get_node_path()

    def clear_mover(self, mover):
        if self._mover is mover:
            self._mover = None
            self._node_path = NodePath()
        else:
            print("clear_mover: unknown CMover")

    def get_mover(self): return self._mover
    def get_node_path(self): return self._node_path
    def is_cpp(self): return True


class CMover:
    def __init__(self, obj_node_path, fwd_speed=1, rot_speed=1):
        self._fwd_speed = fwd_speed
        self._rot_speed = rot_speed
        self._node_path = obj_node_path
        self._dt = 1
        self._last_ft = ClockObject.get_global_clock().get_frame_time()
        self._acc = LVector3f(0)
        self._vel = LVector3f(0)
        self._rot_acc = LVector3f(0)
        self._rot_vel = LVector3f(0)
        self._acc_accum = LVector3f(0)
        self._rot_acc_accum = LVector3f(0)
        self._shove = LVector3f(0)
        self._rot_shove = LVector3f(0)
        self._impulses = {}

    def set_fwd_speed(self, v): self._fwd_speed = v
    def set_rot_speed(self, v): self._rot_speed = v
    def get_fwd_speed(self): return self._fwd_speed
    def get_rot_speed(self): return self._rot_speed

    def add_c_impulse(self, name, impulse):
        self.remove_c_impulse(name)
        self._impulses[name] = impulse
        impulse.set_mover(self)

    def remove_c_impulse(self, name):
        impulse = self._impulses.pop(name, None)
        if impulse is not None:
            impulse.clear_mover(self)
            return True
        return False

    def process_c_impulses(self, dt=-1):
        self._dt = dt
        if self._dt == -1:
            ft = ClockObject.get_global_clock().get_frame_time()
            self._dt = ft - self._last_ft
            self._last_ft = ft
        for impulse in sorted(self._impulses.items()):
            impulse[1].process(self._dt)

    def integrate(self):
        self._acc = LVector3f(self._acc_accum)
        self._rot_acc = LVector3f(self._rot_acc_accum)
        self._vel += self._acc * self._dt
        self._rot_vel += self._rot_acc * self._dt
        dt = self._dt
        dt2 = dt * dt
        self._node_path.set_fluid_pos(self._node_path, (self._vel * dt) + (self._acc * dt2 * .5) + (self._shove * dt))
        self._node_path.set_hpr(self._node_path, (self._rot_vel * dt) + (self._rot_acc * dt2 * .5) + (self._rot_shove * dt))
        self._acc_accum = LVector3f(0)
        self._rot_acc_accum = LVector3f(0)
        self._shove = LVector3f(0)
        self._rot_shove = LVector3f(0)

    def add_force(self, force): self._acc += force
    def add_rot_force(self, force): self._rot_acc += force
    def add_shove(self, shove): self._shove += shove
    def add_rot_shove(self, shove): self._rot_shove += shove
    def get_node_path(self): return self._node_path
    def get_dt(self): return self._dt
    def reset_dt(self): self._last_ft = ClockObject.get_global_clock().get_frame_time()


class CMoverGroup:
    def __init__(self):
        self._dt = 1
        self._last_ft = ClockObject.get_global_clock().get_frame_time()
        self._movers = {}

    def add_c_mover(self, name, mover):
        self.remove_c_mover(name)
        self._movers[name] = mover

    def remove_c_mover(self, name):
        return self._movers.pop(name, None) is not None

    def process_c_impulses_and_integrate(self):
        for name in sorted(self._movers):
            m = self._movers[name]
            m.process_c_impulses(self._dt)
            m.integrate()


class CPetBrain:
    def is_attending_us(self, us, them):
        rel = LVector3f(them.get_pos(us))
        if rel.length_squared() > 100:
            return False
        self_rel = LVector3f(us.get_pos(them))
        self_rel.normalize()
        if self_rel.dot(LVector3f.forward()) < .8:
            return False
        return True


class _PetSteer(CImpulse):
    """Shared steering code of CPetChase and CPetFlee."""

    def __init__(self):
        CImpulse.__init__(self)
        self._look_at_node = NodePath("lookatNode")
        self._vel = LVector3f(0)
        self._rot_vel = LVector3f(0)

    def __del__(self):
        try:
            self._look_at_node.remove_node()
        except Exception:                           # noqa
            pass

    def set_mover(self, mover):
        CImpulse.set_mover(self, mover)
        self._look_at_node.reparent_to(self._node_path)
        self._vel = LVector3f(0)
        self._rot_vel = LVector3f(0)

    def _turn_and_move(self, dt, rel_h, move, distance_left, limit_forward):
        epsilon = .005
        rot_speed = self._mover.get_rot_speed()
        v_h = 0
        if rel_h < -epsilon:
            v_h = -rot_speed
        elif rel_h > epsilon:
            v_h = rot_speed
        if abs(v_h * dt) > abs(rel_h):
            v_h = rel_h / dt
        v_forward = self._mover.get_fwd_speed() if move else 0
        if limit_forward and (v_forward * dt) > distance_left:
            v_forward = distance_left / dt
        if v_forward:
            self._vel.set_y(v_forward)
            self._mover.add_shove(self._vel)
        if v_h:
            self._rot_vel.set_x(v_h)
            self._mover.add_rot_shove(self._rot_vel)


class CPetChase(_PetSteer):
    def __init__(self, target=None, min_dist=5., move_angle=20.):
        _PetSteer.__init__(self)
        self._min_dist = min_dist
        self._move_angle = move_angle
        self._target = NodePath(target) if target is not None else NodePath()

    def set_target(self, t): self._target = t
    def get_target(self): return self._target
    def set_min_dist(self, d): self._min_dist = d
    def get_min_dist(self): return self._min_dist

    def process(self, dt):
        CImpulse.process(self, dt)
        if self._target.is_empty():
            return
        target_pos = self._target.get_pos(self._node_path)
        distance = math.sqrt(target_pos[0] * target_pos[0] + target_pos[1] * target_pos[1])
        self._look_at_node.look_at(self._target)
        rel_h = self._look_at_node.get_h(self._node_path)
        rel_h = math.fmod(rel_h + 180, 360) - 180
        distance_left = distance - self._min_dist
        self._turn_and_move(dt, rel_h, distance > self._min_dist and abs(rel_h) < self._move_angle, distance_left, distance > self._min_dist)


class CPetFlee(_PetSteer):
    def __init__(self, chaser=None, max_dist=50., move_angle=20.):
        _PetSteer.__init__(self)
        self._max_dist = max_dist
        self._move_angle = move_angle
        self._chaser = NodePath(chaser) if chaser is not None else NodePath()

    def set_chaser(self, c): self._chaser = c

    def process(self, dt):
        CImpulse.process(self, dt)
        if self._chaser.is_empty():
            return
        chaser_pos = self._chaser.get_pos(self._node_path)
        distance = chaser_pos.length()
        self._look_at_node.look_at(self._chaser)
        rel_h = self._look_at_node.get_h(self._node_path) + 180.
        rel_h = math.fmod(rel_h + 180, 360) - 180
        distance_left = self._max_dist - distance
        self._turn_and_move(dt, rel_h, distance < self._max_dist and abs(rel_h) < self._move_angle, distance_left, distance_left > 0.)


for _c in (CImpulse, CMover, CMoverGroup, CPetBrain, CPetChase, CPetFlee):
    camel_aliases(_c)
