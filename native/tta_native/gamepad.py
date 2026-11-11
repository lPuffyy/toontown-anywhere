"""Controller support (Xbox, PlayStation, Steam Deck, anything Panda3D recognises as a gamepad). It drives the same game controls the browser
version's touch buttons do (see controls.py), with the layout the web page uses: left stick or D-pad walks, A jumps, B is the action
button, X changes the camera, Start or Y opens the sticker book, the shoulder buttons are the tug-of-war pads."""
import traceback

from panda3d.core import InputDevice

from . import controls

DEAD = 0.35


class Pad:
    def __init__(self, base):
        self.base = base
        self.devices = []
        self.dpad = [False, False, False, False]        # up, down, left, right
        self.last = (False, False, False, False)
        base.accept("connect-device", self.on_connect)
        base.accept("disconnect-device", self.on_disconnect)
        for dev in base.devices.getDevices(InputDevice.DeviceClass.gamepad):
            self.on_connect(dev)
        for name, fn in (("face_a", self.a), ("face_b", self.b), ("face_x", self.x), ("face_y", self.y), ("start", self.start),
                         ("lshoulder", lambda d: controls.ui_pad(0, d)), ("rshoulder", lambda d: controls.ui_pad(1, d)),
                         ("dpad_up", lambda d: self._d(0, d)), ("dpad_down", lambda d: self._d(1, d)),
                         ("dpad_left", lambda d: self._d(2, d)), ("dpad_right", lambda d: self._d(3, d))):
            base.accept("gamepad-" + name, lambda fn=fn: fn(True))
            base.accept("gamepad-" + name + "-up", lambda fn=fn: fn(False))
        base.taskMgr.add(self.poll, "tta-gamepad")

    # ---- devices
    def on_connect(self, device):
        if device.device_class == InputDevice.DeviceClass.gamepad and device not in self.devices:
            self.devices.append(device)
            self.base.attachInputDevice(device, prefix="gamepad")
            print("native: controller connected:", device.name)

    def on_disconnect(self, device):
        if device in self.devices:
            self.devices.remove(device)
            self.base.detachInputDevice(device)
            controls.ui_move(False, False, False, False)
            print("native: controller removed:", device.name)

    # ---- buttons
    def _d(self, i, down):
        self.dpad[i] = down

    def a(self, down):
        controls.ui_jump(down)

    def b(self, down):
        controls.ui_action(down)

    def x(self, down):
        if down:
            controls.ui_camera()

    def y(self, down):
        if down:
            self.book()

    def start(self, down):
        if down:
            self.book()

    def book(self):
        import builtins
        try:
            la = getattr(builtins, "localAvatar", None)
            if la is None:
                return
            btn = la.book.bookCloseButton if getattr(la.book, '_ShtikerBook__isOpen', 0) else la.book.bookOpenButton
            btn.commandFunc(None)
        except BaseException:
            print("native: could not toggle the sticker book", traceback.format_exc())

    # ---- sticks
    def poll(self, task):
        x = y = 0.0
        for dev in self.devices:
            ax = dev.findAxis(InputDevice.Axis.left_x)
            ay = dev.findAxis(InputDevice.Axis.left_y)
            x = x or ax.value
            y = y or ay.value
        state = (y > DEAD or self.dpad[0], y < -DEAD or self.dpad[1], x < -DEAD or self.dpad[2], x > DEAD or self.dpad[3])
        if state != self.last:
            self.last = state
            controls.ui_move(*state)
        return task.cont


def install(base):
    Pad(base)
