/* Sound for the browser build: plays what webaudio.py asks for. Short sounds are decoded into Web Audio buffers; long ones (music)
   are streamed through a few page audio elements so they do not take memory. */
(function () {
  const A = window.ttrAudio = {};
  const log = (m) => { try { if (window.ttr && window.ttr.plog) window.ttr.plog('JS| audio ' + m); } catch (e) {} };
  let ctx = null, master = null, unlocked = false, keep = null;
  const bufs = new Map(), pend = new Map(), voices = new Map(), urls = new Map();
  let bufBytes = 0; const CAP = 90 * 1024 * 1024;
  const pool = [];
  const SILENT = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=';

  function context() {
    if (!ctx) {
      const C = window.AudioContext || window.webkitAudioContext;
      if (!C) return null;
      ctx = new C(); master = ctx.createGain(); master.connect(ctx.destination);
    }
    return ctx;
  }
  function wake() {
    const c = ctx; if (!c) return;
    if (c.state !== 'running') c.resume().then(() => log('context ' + c.state)).catch((e) => log('resume failed ' + e));
    if (keep && keep.paused) keep.play().catch(() => {});
  }
  function unlock() {
    if (unlocked) { wake(); return; }
    const c = context(); if (!c) return;
    c.resume().then(() => log('context ' + c.state)).catch((e) => log('resume failed ' + e));
    try {
      // a silent looping page-audio element keeps iOS playing sound even with the silent switch on, and unlocks the music elements
      keep = new Audio(SILENT); keep.loop = true; keep.play().catch(() => {});
      for (let i = 0; i < 3; i++) {
        const a = new Audio(SILENT); a.loop = false;
        const slot = { el: a, id: 0, gain: null };
        try { const src = c.createMediaElementSource(a); slot.gain = c.createGain(); src.connect(slot.gain); slot.gain.connect(master); } catch (e) { log('media source failed ' + e); }
        a.play().then(() => a.pause()).catch(() => {});
        pool.push(slot);
      }
    } catch (e) {}
    unlocked = true; log('unlocked');
  }
  ['pointerup', 'touchend', 'click', 'keydown'].forEach((t) => addEventListener(t, unlock, true));
  // switching to another app: stop everything (music included) and pick it up again when the player comes back
  const held = [];
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      held.length = 0;
      pool.forEach((sl) => { if (!sl.el.paused) { held.push(sl.el); sl.el.pause(); } });
      if (keep) keep.pause();
      if (ctx) ctx.suspend();
    } else {
      if (ctx) ctx.resume();
      if (keep) keep.play().catch(() => {});
      held.forEach((el) => el.play().catch(() => {}));
      held.length = 0;
    }
  });

  function bytes(path) { return window.FS.readFile(path); }
  function decode(path) {
    if (bufs.has(path)) { const b = bufs.get(path); bufs.delete(path); bufs.set(path, b); return Promise.resolve(b); }
    if (pend.has(path)) return pend.get(path);
    const c = context(); if (!c) return Promise.resolve(null);
    const p = new Promise((res) => {
      let ab; try { const u8 = bytes(path); ab = u8.buffer.slice(u8.byteOffset, u8.byteOffset + u8.byteLength); } catch (e) { log('read failed ' + path); res(null); return; }
      const done = (b) => {
        pend.delete(path);
        if (b) { bufs.set(path, b); bufBytes += b.length * b.numberOfChannels * 4; while (bufBytes > CAP && bufs.size > 1) { const k = bufs.keys().next().value; const o = bufs.get(k); bufs.delete(k); bufBytes -= o.length * o.numberOfChannels * 4; } }
        res(b || null);
      };
      try { const r = c.decodeAudioData(ab, done, (e) => { log('decode failed ' + path + ' ' + (e && e.message)); done(null); }); if (r && r.catch) r.catch(() => {}); }
      catch (e) { log('decode threw ' + path); done(null); }
    });
    pend.set(path, p); return p;
  }
  A.prep = function (path, isLong) { if (!isLong) decode(path); };

  function stopVoice(id) {
    const v = voices.get(id); if (!v) return;
    v.dead = true; voices.delete(id);
    try { if (v.src) { v.src.onended = null; v.src.stop(); } } catch (e) {}
    try { if (v.gain) v.gain.disconnect(); } catch (e) {}
    if (v.el) { try { v.el.pause(); } catch (e) {} v.slot.id = 0; }
  }
  A.stop = function (id) { stopVoice(id); };
  A.vol = function (id, vol) { const v = voices.get(id); if (!v) return; if (v.gain) v.gain.gain.value = vol; if (v.slot && v.slot.gain) v.slot.gain.gain.value = vol; };

  function blobUrl(path) {
    let u = urls.get(path);
    if (!u) {
      u = URL.createObjectURL(new Blob([bytes(path)], { type: 'audio/ogg' })); urls.set(path, u);
      if (urls.size > 4) { const k = urls.keys().next().value; URL.revokeObjectURL(urls.get(k)); urls.delete(k); }
    }
    return u;
  }
  A.play = function (id, path, vol, loop, offset, isLong) {
    stopVoice(id);
    const v = { dead: false }; voices.set(id, v);
    if (isLong) {
      const slot = pool.find((s) => !s.id) || pool[0];
      if (!slot) { log('no audio element'); return; }
      if (slot.id) stopVoice(slot.id);
      slot.id = id; v.slot = slot; v.el = slot.el;
      try {
        const el = slot.el; el.src = blobUrl(path); el.loop = !!loop; if (slot.gain) slot.gain.gain.value = vol; else el.volume = Math.max(0, Math.min(1, vol));
        const go = () => { try { if (offset > 0) el.currentTime = offset; } catch (e) {} el.play().catch((e) => log('music play blocked: ' + e)); };
        if (el.readyState >= 1) go(); else el.addEventListener('loadedmetadata', go, { once: true });
      } catch (e) { log('music failed ' + e); }
      return;
    }
    const c = context(); if (!c) return;
    decode(path).then((b) => {
      if (!b || v.dead || voices.get(id) !== v) return;
      const src = c.createBufferSource(); src.buffer = b; src.loop = !!loop;
      const g = c.createGain(); g.gain.value = vol; src.connect(g); g.connect(master);
      v.src = src; v.gain = g;
      src.onended = () => { if (voices.get(id) === v) voices.delete(id); try { g.disconnect(); } catch (e) {} };
      try { src.start(0, Math.min(offset || 0, Math.max(0, b.duration - 0.01))); } catch (e) { log('start failed ' + e); }
    });
  };
  setTimeout(() => log('ready; ogg vorbis: ' + (new Audio().canPlayType('audio/ogg; codecs="vorbis"') || 'no')), 1500);
})();
