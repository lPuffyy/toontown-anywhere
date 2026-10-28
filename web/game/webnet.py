"""Browser replacements for two Panda3D classes that the WebAssembly build leaves out because they need Panda's socket
layer: CConnectionRepository (the connection to the game server and the incoming-message handling) and
CDistributedSmoothNodeBase (sends the toon's position updates).  Written from the behaviour of Panda3D's C++ source.
The connection is a WebSocket (to a small bridge that forwards to the game server's TCP port)."""
import base64
import math
import platform
import struct
import sys

from panda3d.core import Datagram, DatagramIterator, ClockObject
import panda3d.direct as _direct

WS_URL = "ws://localhost:8766"      # set by the page before the game starts
CLIENT_OBJECT_SET_FIELD = 120
STATESERVER_OBJECT_SET_FIELD = 2020

_JS = """
window.webnet = {
  ws: null, state: 'idle', rx: [], err: '',
  open: function (url) {
    var n = window.webnet;
    try {
      var ws = new WebSocket(url);
      ws.binaryType = 'arraybuffer';
      n.ws = ws; n.state = 'connecting'; n.rx = []; n.err = '';
      ws.onopen = function () { if (n.ws === ws) n.state = 'open'; };
      ws.onmessage = function (e) {
        if (n.ws !== ws) return;
        var b = new Uint8Array(e.data), s = '';
        for (var i = 0; i < b.length; i++) s += String.fromCharCode(b[i]);
        n.rx.push(s);
      };
      ws.onclose = function () { if (n.ws === ws) n.state = 'closed'; };
      ws.onerror = function () { if (n.ws === ws) n.err = 'websocket error'; };
    } catch (x) { n.state = 'closed'; n.err = String(x); }
  },
  send: function (b64) {
    var n = window.webnet;
    if (!n.ws || n.state !== 'open') return false;
    var s = atob(b64), b = new Uint8Array(s.length);
    for (var i = 0; i < s.length; i++) b[i] = s.charCodeAt(i);
    n.ws.send(b.buffer);
    return true;
  },
  pull: function () {
    var n = window.webnet;
    if (!n.rx.length) return '';
    var s = n.rx.join(''); n.rx = [];
    return btoa(s);
  },
  close: function () {
    var n = window.webnet;
    var ws = n.ws; n.ws = null; n.state = 'idle'; n.rx = [];
    try { if (ws) ws.close(); } catch (x) {}
  }
};
"""
platform.window.eval(_JS)
_wn = platform.window.webnet


def _log(*a):
    print("webnet:", *a)


class CConnectionRepository:
    _overflow_event_name = "CRDatagramOverflow"

    def __init__(self, hasOwnerView=False, threadedNet=False):
        self._dc_file = _direct.DCFile()
        self._has_owner_view = bool(hasOwnerView)
        self._handle_c_updates = True
        self._client_datagram = True
        self._handle_datagrams_internally = True
        self._tcp_header_size = 2
        self._python_repository = None
        self._simulated_disconnect = False
        self._verbose = False
        self._in_quiet_zone = False
        self._time_warning = 0.0
        self._want_message_bundling = True
        self._bundling_msgs = 0
        self._bundle_msgs = []
        self._dg = Datagram()
        self._di = DatagramIterator(self._dg)
        self._msg_channels = []
        self._msg_sender = 0
        self._msg_type = 0
        self._out = []          # framed bytes waiting for the socket to open
        self._inbuf = b""
        self._started = False

    # ---- simple settings ----
    def getDcFile(self):
        return self._dc_file

    get_dc_file = getDcFile

    def hasOwnerView(self):
        return self._has_owner_view

    def setHandleCUpdates(self, v):
        self._handle_c_updates = bool(v)

    def getHandleCUpdates(self):
        return self._handle_c_updates

    def setClientDatagram(self, v):
        self._client_datagram = bool(v)

    def getClientDatagram(self):
        return self._client_datagram

    def setHandleDatagramsInternally(self, v):
        self._handle_datagrams_internally = bool(v)

    def getHandleDatagramsInternally(self):
        return self._handle_datagrams_internally

    def setTcpHeaderSize(self, n):
        self._tcp_header_size = int(n)

    def getTcpHeaderSize(self):
        return self._tcp_header_size

    def setPythonRepository(self, repo):
        self._python_repository = repo

    def setWantMessageBundling(self, v):
        self._want_message_bundling = bool(v)

    def getWantMessageBundling(self):
        return self._want_message_bundling

    def setInQuietZone(self, v):
        self._in_quiet_zone = bool(v)

    def getInQuietZone(self):
        return self._in_quiet_zone

    def setSimulatedDisconnect(self, v):
        self._simulated_disconnect = bool(v)

    def getSimulatedDisconnect(self):
        return self._simulated_disconnect

    def toggleVerbose(self):
        self._verbose = not self._verbose

    def setVerbose(self, v):
        self._verbose = bool(v)

    def getVerbose(self):
        return self._verbose

    def setTimeWarning(self, v):
        self._time_warning = float(v)

    def getTimeWarning(self):
        return self._time_warning

    @staticmethod
    def getOverflowEventName():
        return CConnectionRepository._overflow_event_name

    # ---- connecting ----
    def connectNative(self, url=None):
        _log("opening", WS_URL, "for", url)
        _wn.open(WS_URL)
        # a new connection starts clean: anything queued while the old one was closing must not go out first (the server only accepts
        # CLIENT_HELLO as the first packet and throws the player out with error 107 otherwise)
        self._out = []
        self._bundle_msgs = []
        self._simulated_disconnect = False
        self._inbuf = b""
        self._started = True
        return True        # the socket opens in the background; sends wait until it is open

    def tryConnectNet(self, url=None):
        return self.connectNative(url)

    def isConnected(self):
        if not self._started:
            return False
        st = str(_wn.state)
        return st in ("connecting", "open")

    def disconnect(self):
        try:
            _wn.close()
        except Exception:
            pass
        self._started = False
        self._out = []
        self._inbuf = b""
        self._simulated_disconnect = False

    def shutdown(self):
        self.disconnect()

    # ---- sending ----
    def _push_out(self):
        if not self._out or str(_wn.state) != "open":
            return
        data = b"".join(self._out)
        self._out = []
        _wn.send(base64.b64encode(data).decode("ascii"))

    def sendDatagram(self, dg):
        if self._simulated_disconnect:
            return False
        if self.isBundlingMessages() and self._want_message_bundling:
            self._bundle_msgs.append(bytes(dg.getMessage()))
            return True
        if not self._started:
            return False
        if str(_wn.state) in ("closed", "idle"):
            return False           # the connection is gone: do not queue for the next one
        payload = bytes(dg.getMessage())
        if self._tcp_header_size == 2:
            frame = struct.pack("<H", len(payload)) + payload
        elif self._tcp_header_size == 4:
            frame = struct.pack("<I", len(payload)) + payload
        else:
            frame = payload
        self._out.append(frame)
        self._push_out()
        return True

    def considerFlush(self):
        self._push_out()
        return self._started

    def flush(self):
        self._push_out()
        return self._started

    # ---- message bundling ----
    def startMessageBundle(self):
        if self._bundling_msgs == 0:
            self._bundle_msgs = []
        self._bundling_msgs += 1

    def isBundlingMessages(self):
        return self._bundling_msgs > 0

    def sendMessageBundle(self, channel, senderChannel):
        self._bundling_msgs -= 1
        if self._bundling_msgs == 0 and self._want_message_bundling:
            dg = Datagram()
            dg.addInt8(1)
            dg.addUint64(channel)
            dg.addUint64(senderChannel)
            for m in self._bundle_msgs:
                dg.addString(m)
            self.sendDatagram(dg)

    def abandonMessageBundles(self):
        self._bundling_msgs = 0
        self._bundle_msgs = []

    def bundleMsg(self, dg):
        self._bundle_msgs.append(bytes(dg.getMessage()))

    # ---- receiving ----
    def _pump(self):
        self._push_out()
        s = str(_wn.pull())
        if s:
            self._inbuf += base64.b64decode(s)

    def _next_datagram(self):
        h = self._tcp_header_size
        if h == 0:
            if not self._inbuf:
                return False
            data, self._inbuf = self._inbuf, b""
        else:
            if len(self._inbuf) < h:
                return False
            n = struct.unpack("<H" if h == 2 else "<I", self._inbuf[:h])[0]
            if len(self._inbuf) < h + n:
                return False
            data = self._inbuf[h:h + n]
            self._inbuf = self._inbuf[h + n:]
        self._dg = Datagram(data)
        return True

    def checkDatagram(self):
        if self._simulated_disconnect:
            return False
        self._pump()
        while self._next_datagram():
            self._di = DatagramIterator(self._dg)
            if not self._client_datagram:
                cnt = self._di.getUint8()
                self._msg_channels = [self._di.getUint64() for _ in range(cnt)]
                self._msg_sender = self._di.getUint64()
                if self._python_repository is not None:
                    self._python_repository.msgSender = self._msg_sender
            self._msg_type = self._di.getUint16()
            if not self._handle_datagrams_internally:
                return True
            if self._msg_type in (CLIENT_OBJECT_SET_FIELD, STATESERVER_OBJECT_SET_FIELD):
                if self._handle_c_updates:
                    if self._has_owner_view:
                        self._handle_update_field_owner()
                    else:
                        self._handle_update_field()
                else:
                    return True
            else:
                return True
        return False

    def _handle_update_field(self):
        do_id = self._di.getUint32()
        repo = self._python_repository
        if repo is None:
            return
        distobj = repo.doId2do.get(do_id)
        if distobj is not None:
            if self._in_quiet_zone and not getattr(distobj, "neverDisable", 0):
                return
            distobj.dclass.receiveUpdate(distobj, self._di)

    def _handle_update_field_owner(self):
        do_id = self._di.getUint32()
        repo = self._python_repository
        if repo is None:
            return
        ov = repo.doId2ownerView.get(do_id)
        if ov is not None:
            data = bytes(self._di.getRemainingBytes())
            field_id = struct.unpack("<H", data[:2])[0]
            field = ov.dclass.getFieldByIndex(field_id)
            if field.isOwnrecv():
                odi = DatagramIterator(self._di)
                ov.dclass.receiveUpdate(ov, odi)
        distobj = repo.doId2do.get(do_id)
        if distobj is not None:
            distobj.dclass.receiveUpdate(distobj, self._di)

    def getDatagram(self, dg):
        try:
            dg.assign(self._dg)
        except Exception:
            Datagram.__init__(dg, self._dg)

    def getDatagramIterator(self, di):
        # same position inside the same datagram as our own iterator (the C++ class just assigns it)
        idx = self._di.getCurrentIndex()
        try:
            DatagramIterator.__init__(di, self._dg, idx)
        except Exception:
            di.assign(self._dg, idx)

    def getMsgChannel(self, offset=0):
        return self._msg_channels[offset]

    def getMsgChannelCount(self):
        return len(self._msg_channels)

    def getMsgSender(self):
        return self._msg_sender

    def getMsgType(self):
        return self._msg_type


class CDistributedSmoothNodeBase:
    F_new_x, F_new_y, F_new_z, F_new_h, F_new_p, F_new_r = 1, 2, 4, 8, 16, 32
    EPS = 0.01

    def __init__(self):
        self._repository = None
        self._is_ai = False
        self._ai_id = 0
        self._clock_delta = None
        self._currL = [0, 0]
        self._node_path = None
        self._dclass = None
        self._do_id = 0
        self._store_xyz = [0.0, 0.0, 0.0]
        self._store_hpr = [0.0, 0.0, 0.0]
        self._store_stop = False

    def setRepository(self, repository, isAI, aiId):
        self._repository = repository
        self._is_ai = bool(isAI)
        self._ai_id = aiId

    def setClockDelta(self, clockDelta):
        self._clock_delta = clockDelta

    def initialize(self, nodePath, dclass, doId):
        self._node_path = nodePath
        self._dclass = dclass
        self._do_id = doId
        p = nodePath.getPos()
        h = nodePath.getHpr()
        self._store_xyz = [p[0], p[1], p[2]]
        self._store_hpr = [h[0], h[1], h[2]]
        self._store_stop = False

    def sendEverything(self):
        self._currL[0] = self._currL[1]
        self.d_setSmPosHprL(*self._store_xyz, *self._store_hpr, self._currL[0])

    @staticmethod
    def _only(flags, compare):
        return (flags & compare) != 0 and (flags & ~compare) == 0

    def _diff(self, store, new, flag, flags):
        if abs(store[0] - new) > self.EPS:
            return flags | flag, new
        return flags, store[0]

    def _scan(self, idxs_xyz, idxs_hpr):
        pos = self._node_path.getPos()
        hpr = self._node_path.getHpr()
        flags = 0
        for i, f in zip(range(3), (self.F_new_x, self.F_new_y, self.F_new_z)):
            if i in idxs_xyz and abs(self._store_xyz[i] - pos[i]) > self.EPS:
                self._store_xyz[i] = pos[i]
                flags |= f
        for i, f in zip(range(3), (self.F_new_h, self.F_new_p, self.F_new_r)):
            if i in idxs_hpr and abs(self._store_hpr[i] - hpr[i]) > self.EPS:
                self._store_hpr[i] = hpr[i]
                flags |= f
        return flags

    def broadcastPosHprFull(self):
        flags = self._scan((0, 1, 2), (0, 1, 2))
        x, y, z = self._store_xyz
        h, p, r = self._store_hpr
        F = self
        if self._currL[0] != self._currL[1]:
            self._currL[0] = self._currL[1]
            self._store_stop = False
            self.d_setSmPosHprL(x, y, z, h, p, r, self._currL[0])
        elif flags == 0:
            if not self._store_stop:
                self._store_stop = True
                self.d_setSmStop()
        else:
            self._store_stop = False
            o = self._only
            if o(flags, F.F_new_h):
                self.d_setSmH(h)
            elif o(flags, F.F_new_z):
                self.d_setSmZ(z)
            elif o(flags, F.F_new_x | F.F_new_y):
                self.d_setSmXY(x, y)
            elif o(flags, F.F_new_x | F.F_new_z):
                self.d_setSmXZ(x, z)
            elif o(flags, F.F_new_x | F.F_new_y | F.F_new_z):
                self.d_setSmPos(x, y, z)
            elif o(flags, F.F_new_h | F.F_new_p | F.F_new_r):
                self.d_setSmHpr(h, p, r)
            elif o(flags, F.F_new_x | F.F_new_y | F.F_new_h):
                self.d_setSmXYH(x, y, h)
            elif o(flags, F.F_new_x | F.F_new_y | F.F_new_z | F.F_new_h):
                self.d_setSmXYZH(x, y, z, h)
            else:
                self.d_setSmPosHpr(x, y, z, h, p, r)

    def broadcastPosHprXyh(self):
        flags = self._scan((0, 1), (0,))
        x, y, _z = self._store_xyz
        h = self._store_hpr[0]
        if flags == 0:
            if not self._store_stop:
                self._store_stop = True
                self.d_setSmStop()
        else:
            self._store_stop = False
            if self._only(flags, self.F_new_h):
                self.d_setSmH(h)
            elif self._only(flags, self.F_new_x | self.F_new_y):
                self.d_setSmXY(x, y)
            else:
                self.d_setSmXYH(x, y, h)

    def broadcastPosHprXy(self):
        flags = self._scan((0, 1), ())
        x, y, _z = self._store_xyz
        if flags == 0:
            if not self._store_stop:
                self._store_stop = True
                self.d_setSmStop()
        else:
            self._store_stop = False
            self.d_setSmXY(x, y)

    def setCurrL(self, l):
        self._currL[1] = l

    def printCurrL(self):
        print("printCurrL: sent l:", self._currL[1], "last set l:", self._currL[0])

    # ---- packing ----
    def _begin(self, name):
        packer = _direct.DCPacker()
        field = self._dclass.getFieldByName(name)
        if self._is_ai:
            packer.rawPackUint8(1)
            packer.rawPackUint64(self._do_id)
            packer.rawPackUint64(self._ai_id)
            packer.rawPackUint16(STATESERVER_OBJECT_SET_FIELD)
        else:
            packer.rawPackUint16(CLIENT_OBJECT_SET_FIELD)
        packer.rawPackUint32(self._do_id)
        packer.rawPackUint16(field.getNumber())
        packer.beginPack(field)
        packer.push()
        return packer

    def _finish(self, packer):
        delta = float(self._clock_delta.delta)
        local_time = ClockObject.getGlobalClock().getRealTime()
        net_time = int(math.floor((local_time - delta) * 100.0 + 0.5))
        net_time = ((net_time + 0x8000) & 0xFFFF) - 0x8000
        packer.packInt(net_time)
        packer.pop()
        if packer.endPack():
            self._repository.sendDatagram(Datagram(packer.getBytes()))
        else:
            raise ValueError("Node position out of range for DC file or unexpected pack error")

    def _send(self, name, *values, l=None):
        packer = self._begin(name)
        if l is not None:
            packer.packUint64(l)
        for v in values:
            packer.packDouble(v)
        self._finish(packer)

    def d_setSmStop(self):
        self._send("setSmStop")

    def d_setSmH(self, h):
        self._send("setSmH", h)

    def d_setSmZ(self, z):
        self._send("setSmZ", z)

    def d_setSmXY(self, x, y):
        self._send("setSmXY", x, y)

    def d_setSmXZ(self, x, z):
        self._send("setSmXZ", x, z)

    def d_setSmPos(self, x, y, z):
        self._send("setSmPos", x, y, z)

    def d_setSmHpr(self, h, p, r):
        self._send("setSmHpr", h, p, r)

    def d_setSmXYH(self, x, y, h):
        self._send("setSmXYH", x, y, h)

    def d_setSmXYZH(self, x, y, z, h):
        self._send("setSmXYZH", x, y, z, h)

    def d_setSmPosHpr(self, x, y, z, h, p, r):
        self._send("setSmPosHpr", x, y, z, h, p, r)

    def d_setSmPosHprL(self, x, y, z, h, p, r, l):
        self._send("setSmPosHprL", x, y, z, h, p, r, l=self._currL[0])


def install():
    """Put the replacements where the game's own code looks for them (panda3d.direct)."""
    for name, cls in (("CConnectionRepository", CConnectionRepository), ("CDistributedSmoothNodeBase", CDistributedSmoothNodeBase)):
        if not hasattr(_direct, name):
            setattr(_direct, name, cls)
            _log("installed", name)
