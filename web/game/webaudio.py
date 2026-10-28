"""Sound for the browser build. Panda has no audio library in the browser, so this provides AudioManager / AudioSound look-alikes that the
game uses as normal; the actual playing is done by the page (ttr-audio.js, Web Audio). The game's own timing questions (is it still playing,
how long is it, where is it) are answered here from the clock, so nothing waits on the page."""
import os
import platform
import struct
import time
import traceback

from panda3d.core import Filename, VirtualFileSystem, getModelPath

A = platform.window.ttrAudio
_vfs = VirtualFileSystem.getGlobalPtr()
_meta = {}                      # game path -> (os path, length in seconds)
_playing = set()
_next_id = [1]
LONG = 25.0                     # longer than this (music): streamed by the page instead of being decoded into memory
BAD, READY, PLAYING = 0, 1, 2


def _probe(path):
    m = _meta.get(path)
    if m is not None:
        return m
    osname, length = None, 0.0
    try:
        f = Filename(str(path))
        if _vfs.resolveFilename(f, getModelPath().getValue()):
            osname = f.toOsSpecific()
            if not os.path.exists(osname):          # the game's folder is mounted at "/": find the real location in the browser's file system
                for base in (os.path.join(os.getcwd(), "resources"), os.getcwd()):
                    cand = os.path.join(base, osname.lstrip("/"))
                    if os.path.exists(cand):
                        osname = cand
                        break
            data = bytes(_vfs.readFile(f, True))
            i = data.find(b"\x01vorbis", 0, 200)
            if i >= 0:
                rate = struct.unpack_from("<I", data, i + 12)[0]
                j = data.rfind(b"OggS", max(0, len(data) - 70000))
                if j >= 0 and rate:
                    gran = struct.unpack_from("<q", data, j + 6)[0]
                    length = max(gran, 0) / float(rate)
    except BaseException:
        print("webaudio: probe failed", path, traceback.format_exc())
    m = (osname, length)
    _meta[path] = m
    return m


class WebSound:
    def __init__(self, mgr, name):
        self._mgr = mgr
        self._name = str(name)
        self._os, self._len = _probe(name)
        self._id = _next_id[0]
        _next_id[0] += 1
        self._vol = 1.0
        self._loop = False
        self._bal = 0.0
        self._rate = 1.0
        self._playing = False
        self._t0 = 0.0
        self._pos = 0.0
        self._event = ""
        if self._os:
            try:
                A.prep(self._os, self._len > LONG)
            except BaseException:
                pass

    # -- the AudioSound interface the game uses --
    def getName(self):
        return self._name

    def length(self):
        return self._len

    def status(self):
        self._refresh()
        if not self._os:
            return BAD
        return PLAYING if self._playing else READY

    def _refresh(self):
        if self._playing and not self._loop and self._len > 0 and time.time() - self._t0 >= self._len:
            self._playing = False
            self._pos = 0.0
            _playing.discard(self)
            if self._event:
                self._send_finished()

    def _send_finished(self):
        try:
            from direct.showbase.MessengerGlobal import messenger
            messenger.send(self._event)
        except BaseException:
            pass

    def _eff(self):
        return max(0.0, min(1.0, self._vol * self._mgr._vol)) if self._mgr._active else 0.0

    def play(self):
        if not self._os or not self._mgr._active:
            return
        self._mgr._make_room(self)
        self._start(self._pos)

    def _start(self, offset):
        self._playing = True
        self._t0 = time.time() - offset
        _playing.add(self)
        try:
            A.play(self._id, self._os, self._eff(), bool(self._loop), float(offset), self._len > LONG)
        except BaseException:
            print("webaudio: play failed", traceback.format_exc())

    def stop(self):
        if self._playing:
            self._playing = False
            _playing.discard(self)
            try:
                A.stop(self._id)
            except BaseException:
                pass
        self._pos = 0.0

    def setVolume(self, v):
        self._vol = float(v)
        self._push_volume()

    def _push_volume(self):
        if self._playing:
            try:
                A.vol(self._id, self._eff())
            except BaseException:
                pass

    def getVolume(self):
        return self._vol

    def setLoop(self, loop=True):
        self._loop = bool(loop)
        if self._playing:
            self._start(self.getTime())

    def getLoop(self):
        return self._loop

    def setLoopCount(self, n=0):
        self._loop = (n == 0 or n > 1)

    def getLoopCount(self):
        return 0 if self._loop else 1

    def setTime(self, t):
        self._pos = max(0.0, float(t))
        if self._playing:
            self._start(self._pos)

    def getTime(self):
        self._refresh()
        if self._playing:
            el = time.time() - self._t0
            return (el % self._len) if (self._loop and self._len > 0) else el
        return self._pos

    def setBalance(self, b):
        self._bal = b

    def getBalance(self):
        return self._bal

    def setPlayRate(self, r):
        self._rate = r

    def getPlayRate(self):
        return self._rate

    def setActive(self, a=True):
        pass

    def getActive(self):
        return True

    def setFinishedEvent(self, e=""):
        self._event = str(e or "")

    def getFinishedEvent(self):
        return self._event

    def finished(self):
        self._refresh()

    def __getattr__(self, n):          # 3D attributes and anything else the game may poke: do nothing
        if n.startswith("__"):
            raise AttributeError(n)
        return lambda *a, **k: 0


class WebAudioManager:
    def __init__(self):
        self._vol = 1.0
        self._active = True
        self._limit = 0

    def isValid(self):
        return True

    def getSound(self, path, positional=False, mode=0):
        return WebSound(self, path)

    def setVolume(self, v):
        self._vol = float(v)
        for s in list(_playing):
            if s._mgr is self:
                s._push_volume()

    def getVolume(self):
        return self._vol

    def setActive(self, a):
        self._active = bool(a)
        if not self._active:
            self.stopAllSounds()
        else:
            for s in list(_playing):
                if s._mgr is self:
                    s._push_volume()

    def getActive(self):
        return self._active

    def setConcurrentSoundLimit(self, n):
        self._limit = int(n)

    def getConcurrentSoundLimit(self):
        return self._limit

    def _make_room(self, new):
        if self._limit > 0:
            mine = sorted((s for s in _playing if s._mgr is self and s is not new), key=lambda s: s._t0)
            while len(mine) >= self._limit:
                mine.pop(0).stop()

    def reduceSoundsPlayingTo(self, n):
        mine = sorted((s for s in _playing if s._mgr is self), key=lambda s: s._t0)
        while len(mine) > n:
            mine.pop(0).stop()

    def stopAllSounds(self):
        for s in list(_playing):
            if s._mgr is self:
                s.stop()

    def getNumSounds(self):
        return len(_playing)

    def update(self):
        pass

    def uncacheSound(self, name):
        pass

    def clearCache(self):
        pass

    def getCacheLimit(self):
        return 0

    def shutdown(self):
        self.stopAllSounds()

    def __getattr__(self, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return lambda *a, **k: 0


def tick():
    """Once per frame: let sounds that ended notice it (and send their finished events)."""
    for s in list(_playing):
        s._refresh()


def install(ShowBase):
    from direct.showbase import SfxPlayer

    def createBaseAudioManagers(self):
        self.sfxPlayer = SfxPlayer.SfxPlayer()
        self.addSfxManager(WebAudioManager())
        self.musicManager = WebAudioManager()
        self.musicManagerIsValid = True
        self.musicManager.setConcurrentSoundLimit(1)
        self.musicManager.setActive(self.musicActive)
    ShowBase.createBaseAudioManagers = createBaseAudioManagers
