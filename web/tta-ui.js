/* Toontown: Anywhere (web) - loading screen, game-file downloader, sign-in, server choice, recovery cards and the in-game
   touch controls. The layout numbers are copied from the iOS app (main.m). The game itself runs in Python (main.py). */
(function () {
  'use strict';
  const ICONS = window.TTA_ICONS || {};
  const DEFAULT = { name: 'Toontown: Anywhere', host: 'toontown.puffsco.com' };
  const LS = (() => { try { return window.localStorage; } catch (e) { return { getItem() { return null; }, setItem() {}, removeItem() {} }; } })();
// Bump when a new release should offer the texture choice once again on every device.
const TEXTURE_PICK_VERSION = 2;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  // The HD packs can be rebuilt with the same byte sizes but different bytes (e.g. an
  // RLE fix). Bump this when that happens so cached packs are not reused.
  const HD_PACK_V = 19;
  // settings and saved sign-ins were kept under another prefix before: copy them to the current names once, so nobody starts over
  // (the old copies stay where they are, so an older page still finds them)
  try {
    const OLD = 'ttr_', NEW = 'tta_';
    for (let i = LS.length - 1; i >= 0; i--) {
      const k = LS.key(i);
      if (k && k.indexOf(OLD) === 0 && LS.getItem(NEW + k.slice(OLD.length)) === null) LS.setItem(NEW + k.slice(OLD.length), LS.getItem(k));
    }
  } catch (e) {}
  // storage names that hold the downloaded game files keep their earlier names, so those 390 MB are not fetched again
  const T = window.ttr = window.tta = {   // (the game code in the server pack still looks for window.ttr)
    aa: (() => {
      try {
        const touchScreen = ('ontouchstart' in document.documentElement) ||
          (window.matchMedia && matchMedia('(pointer: coarse)').matches);
        // Smooth edges is on for everyone now. Older builds forced it off on touch
        // devices to save MSAA cost; migrate that stale value once so the game gets
        // antialiased cut-out edges. A choice made in Settings after this migration
        // is still honoured; the one-time flag prevents changing it on every load.
        if (touchScreen && LS.getItem('tta_smooth_edges_on_v2') !== '1') {
          LS.setItem('tta_aa', '1');
          LS.setItem('tta_aa_user_choice', '1');
          LS.setItem('tta_smooth_edges_on_v2', '1');
        }
        const saved = LS.getItem('tta_aa');
        return saved === '0' ? '0' : '1';
      } catch (e) { return '1'; }
    })(),
    pyReady: false, go: false, gameConfig: '', typeBtn: '', dbg: false, safeL: 0, safeR: 0, safeT: 0, safeB: 0, vh: 0, pycode: '', winW: 0, winH: 0, mc: 0, cookie: '', inp: '0,0,0,0,0,0,0,0', camN: 0, txtIn: 0, txtSub: 0, txtVal: '',
    // The game connection normally goes through the same address as the page (via the tunnel). A tester can use the direct route instead by opening
    // the page with ?ws=wss://ws.puffsco.com/ws (remembered on that device; ?ws=off goes back). Only addresses under our own domain are accepted:
    // the connection carries the sign-in, so a link must never be able to point it somewhere else.
    wsUrl: window.TTA_WS || (() => {
      try {
        const m = location.search.match(/[?&]ws=([^&]+)/);
        if (m) { const v = decodeURIComponent(m[1]); if (/^wss:\/\/[a-z0-9-]+\.puffsco\.com(:\d+)?\/ws$/i.test(v)) window.localStorage.setItem('tta_ws', v); else if (v === 'off') window.localStorage.removeItem('tta_ws'); }
        const saved = window.localStorage.getItem('tta_ws');
        if (saved && /^wss:\/\/[a-z0-9-]+\.puffsco\.com(:\d+)?\/ws$/i.test(saved)) return saved;
      } catch (e) {}
      return (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws';
    })(),
    // the graphics chip's name (e.g. "Mali-G925"): the game works around some chips' driver bugs, and the log shows it
    gpu: (() => {
      try {
        const c = document.createElement('canvas'), gl = c.getContext('webgl');
        if (!gl) return '';
        const ext = gl.getExtension('WEBGL_debug_renderer_info');
        const name = String(gl.getParameter(ext ? ext.UNMASKED_RENDERER_WEBGL : gl.RENDERER) || '');
        const lose = gl.getExtension('WEBGL_lose_context'); if (lose) lose.loseContext();
        return name;
      } catch (e) { return ''; }
    })(),
  };

  // ------------------------------------------------------------------ preferences
  const prefs = {
    get mode() { return LS.getItem('tta_srv_mode'); },
    get res() { return LS.getItem('tta_srv_res') || ''; },
    get game() { return LS.getItem('tta_srv_game') || ''; },
    get isDefault() { return this.mode !== 'custom'; },
    get base() { return this.isDefault ? '' : this.res.replace(/\/+$/, ''); },
    get ws() {
      if (this.isDefault) return T.wsUrl;
      const g = this.game;
      return /^wss?:/i.test(g) ? g : ((location.protocol === 'https:' ? 'wss://' : 'ws://') + g);
    },
    get userKey() { return this.isDefault ? 'tta_user' : 'tta_user_' + btoa(this.res).slice(0, 12); },
  };

  // ------------------------------------------------------------------ helpers
  const root = document.createElement('div');
  root.id = 'tta';
  document.body.appendChild(root);
  function el(tag, cls, parent, css) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (css) Object.assign(e.style, css);
    (parent || root).appendChild(e);
    return e;
  }
  function place(e, x, y, w, h) {
    const s = e.style;
    s.left = x + 'px'; s.top = y + 'px';
    if (w != null) s.width = w + 'px';
    if (h != null) s.height = h + 'px';
  }
  let W = 0, H = 0, sc = 1, pixelRatio = 1;
  let touchScreen = false;
  let lastViewport = '', lastInner = '';
  let dn = 0;
  // Test sessions: open the page with ?log=1 (kept for the rest of the visit) and everything the game prints, plus any page error or crash
  // message, is sent to the server's /__log, where it is saved with the time and this device's address.
  let LOGGING = location.port === '8001' || location.port === '8002';
  try {
    if (/[?&]log=1/.test(location.search)) sessionStorage.setItem('tta.log', '1');
    if (sessionStorage.getItem('tta.log') === '1') LOGGING = true;
  } catch (e) {}
  // Everyone else is logged quietly: crash information, one device/sign-in line and a few startup stage timings.
  // No passwords, touches or ongoing frame timings are recorded. At most 400 lines per visit.
  let quietSent = 0, tbLeft = 0, lastQuiet = '';
  let perfNext = 0, perfFollow = 0;
  const QUIET_WANT = /Traceback|[A-Za-z_]*(Error|Exception)\b|STEP FAILED|reconnecting|webnet: (closed|error)|Aborted|TTA startup timing:|web: (cut-out mode|smooth edges|decal node|extra decal|eye depth|eye smooth|task timing|task cost|task profiling requested)|pnmimage|RLE error/;
  function quietLog(m) {
    if (quietSent >= 400) return;
    let want = false;
    if (m.indexOf('PY|') === 0) {
      const t = m.slice(3).trim();
      if (/Traceback \(most recent call last\)/.test(t)) { tbLeft = 150; want = true; }   // (the frame that failed comes last)
      else if (tbLeft > 0) { want = true; tbLeft--; if (/^[A-Za-z_.]*(Error|Exception)\b/.test(t)) tbLeft = 0; }
      else if (/^web: perf device=/.test(t)) {
        // One FPS/frame-time sample every 30s even in quiet mode, plus its context lines.
        // This is what FPS reports need: the quiet log used to drop every perf line.
        const now = Date.now();
        if (now >= perfNext) { want = true; perfNext = now + 30000; perfFollow = 2; }
      } else if (perfFollow > 0 && /^web: (perf where|hitches)/.test(t)) { want = true; perfFollow--; }
      else if (QUIET_WANT.test(t)) want = true;
    } else if (/^JS\| (page error|unhandled|console\.error|session|startup (first-draw|login-ready|packs-ready|still-waiting|manifest)|auto reload|texture picker|return state|restored keyboard|resume prompt|resume tap)/.test(m)) want = true;
    if (!want || m === lastQuiet) return;
    lastQuiet = m; quietSent++;
    try { navigator.sendBeacon('/__log', m); } catch (e) {}
  }
  function plog(m) {
    if (LOGGING) { try { navigator.sendBeacon('/__log', m); } catch (e) {} return; }
    if (m.indexOf('JS| env') !== 0) { quietLog(m); return; }
    // the real site: only the screen-fact lines, a few per visit, as a plain request the web server's log records
    if (m.indexOf('JS| env') !== 0 || dn >= 40) return;
    dn++; try { new Image().src = '/__d?' + encodeURIComponent(m) + '&r=' + Date.now(); } catch (e) {}
  }
  T.plog = plog;
  T.profileTasks = false;
  {
    addEventListener('error', (e) => plog('JS| page error: ' + e.message + ' @ ' + (e.filename || '') + ':' + (e.lineno || '')));
    addEventListener('unhandledrejection', (e) => plog('JS| unhandled rejection: ' + (e.reason && (e.reason.stack || e.reason.message) || e.reason)));
    (LOGGING ? ['error', 'warn'] : ['error']).forEach((lv) => { const o = console[lv]; console[lv] = function () { o.apply(console, arguments); try { plog('JS| console.' + lv + ': ' + Array.prototype.slice.call(arguments).map(String).join(' ').slice(0, 600)); } catch (e) {} }; });
    plog((LOGGING ? 'JS| log session started: ' : 'JS| session: ') + navigator.userAgent + ' ' + innerWidth + 'x' + innerHeight + ' gpu ' + (T.gpu || '?') + ' route ' + (T.wsUrl.indexOf('//' + location.host + '/') >= 0 ? 'tunnel' : 'direct'));       // (the direct route is decided a moment later: see "JS| route")
  }
  const _cl = console.log; console.log = function () { _cl.apply(console, arguments); try { const m = String(arguments[0]); if (m.indexOf('PY|') === 0) { plog(m); T.lastPy = m.slice(3).trim().slice(0, 140); } } catch (e) {} };
  let installUp = false;
  let kbHold = false;             // in game, the keyboard must not resize the game's window
  const SAFE = { t: 0, b: 0, l: 0, r: 0 };
  const layouts = [];
  function measure() {
    // Pygbag converts pointer coordinates using the canvas rectangle; use that exact rectangle
    // for Panda's logical window and the HUD layout so visual controls and taps share a space.
    const canvas = document.querySelector('canvas.emscripten');
    const r = (canvas || root).getBoundingClientRect();
    const vv = window.visualViewport;
    W = r.width || (vv && vv.width) || innerWidth;
    H = r.height || (vv && vv.height) || innerHeight;
    lastInner = innerWidth + 'x' + innerHeight;
    lastViewport = [r.left, r.top, r.width, r.height].map((n) => Math.round(n * 100) / 100).join(',');
    sc = Math.min(W, H) >= 700 ? 1.45 : 1.0;      // the app scales up on iPad
    document.documentElement.style.setProperty('--sc', sc);
    const probe = el('div', null, root, { position: 'absolute', visibility: 'hidden', paddingTop: 'env(safe-area-inset-top,0px)', paddingBottom: 'env(safe-area-inset-bottom,0px)', paddingLeft: 'env(safe-area-inset-left,0px)', paddingRight: 'env(safe-area-inset-right,0px)' });
    const cs = getComputedStyle(probe);
    SAFE.t = parseFloat(cs.paddingTop) || 0; SAFE.b = parseFloat(cs.paddingBottom) || 0; SAFE.l = parseFloat(cs.paddingLeft) || 0; SAFE.r = parseFloat(cs.paddingRight) || 0;
    probe.remove();
  }
  function relayout() {
    if (kbHold) return;
    // Home-screen iPad Safari can report a short innerHeight; apply the same correction to the
    // canvas and overlay, then measure their shared CSS viewport for Panda and touch controls.
    let FH = innerHeight;
    try {
      const home = navigator.standalone === true || (window.matchMedia && matchMedia('(display-mode: standalone)').matches);
      if (home && Math.min(innerWidth, innerHeight) >= 600 && outerWidth === innerWidth && outerHeight > innerHeight && outerHeight - innerHeight <= 100) FH = outerHeight;
    } catch (e) { FH = innerHeight; }
    if (Math.abs(FH - innerHeight) > 0.5) document.documentElement.style.setProperty('--fh', FH + 'px');
    else document.documentElement.style.removeProperty('--fh');
    measure(); fitTitle(); layouts.forEach((f) => f());
    // Render at a capped device scale, but derive the game window from the exact CSS viewport
    // used by both the canvas and the browser HUD.
    let cap = 2; try { cap = parseFloat(new URLSearchParams(location.search).get('res') || localStorage.getItem('tta_res') || '2') || 2; } catch (e) { cap = 2; }
    cap = Math.max(0.5, Math.min(cap, 2));
    // Pygbag maps pointer positions from the canvas CSS rectangle to its backing dimensions.
    // Keep touch browsers at 1:1 for calibrated input. The installed-app lower-resolution
    // experiment did not improve the measured frame time, so don't keep its touch risk.
    touchScreen = ('ontouchstart' in document.documentElement) ||
      (window.matchMedia && matchMedia('(pointer: coarse)').matches);
    pixelRatio = touchScreen ? 1 : Math.min(window.devicePixelRatio || 1, cap);
    T.winW = Math.round(W * pixelRatio); T.winH = Math.round(H * pixelRatio);
    T.safeL = SAFE.l; T.safeR = SAFE.r; T.safeT = SAFE.t; T.safeB = SAFE.b; T.vh = H;
  }
  function fitTitle() {
    if (typeof title === 'undefined') return;
    let fs = Math.min(56 * sc, W / 17);
    title.style.fontSize = fs + 'px'; title.style.top = ''; title.style.visibility = '';
    // measure the text itself (the box is always as wide as the screen, so its scrollWidth never says the text is too wide)
    const textW = () => { const r = document.createRange(); r.selectNodeContents(title.firstChild); return r.getBoundingClientRect().width; };
    for (let i = 0; i < 12 && textW() > W * 0.92; i++) { fs *= 0.9; title.style.fontSize = fs + 'px'; }
  }
  addEventListener('resize', relayout);
  // iOS (especially a Home Screen app) sometimes reports a stale window size until the phone is rotated: keep checking, and re-measure
  // a few times shortly after start-up, so the game never stays drawn for the wrong size
  addEventListener('pageshow', () => setTimeout(relayout, 100));
  if (window.visualViewport) {
    visualViewport.addEventListener('resize', () => { if (!kbHold) relayout(); });
    visualViewport.addEventListener('scroll', () => { if (!kbHold) relayout(); });
  }
  setInterval(() => {
    if (!kbHold && (innerWidth + 'x' + innerHeight) !== lastInner) relayout();
  }, 500);
  // Opening the app already in landscape, iOS can report a viewport that is shorter than the screen (e.g. 932x371 on a 932x430 phone) and
  // not correct it until something nudges it: ask for a fresh measurement a few times right after the page starts
  // Opening the app already in landscape, iOS can stick on a viewport shorter than the window (932x371 on a 932x430 phone) until the phone is
  // turned to portrait and back. If it is still short once the page has settled, try ways of making iOS measure again, one at a time, and
  // log which one worked (a reload does not).
  const vpStuck = () => innerWidth > innerHeight && outerWidth === innerWidth && outerHeight - innerHeight >= 20 && outerHeight - innerHeight <= 100;
  const vpTries = [
    ['viewport meta replaced', () => { const m = document.querySelector('meta[name=viewport]'); if (m) { const n = m.cloneNode(); m.remove(); document.head.appendChild(n); } }],
    ['reflow', () => { const d = document.documentElement; d.style.display = 'none'; void d.offsetHeight; d.style.display = ''; }],
    ['scroll nudge', () => { document.body.style.minHeight = '120vh'; scrollTo(0, 1); setTimeout(() => { scrollTo(0, 0); document.body.style.minHeight = ''; }, 50); }],
    ['viewport-fit toggled', () => { const m = document.querySelector('meta[name=viewport]'); if (m) { const c = m.getAttribute('content'); m.setAttribute('content', c.replace('viewport-fit=cover', 'viewport-fit=auto')); setTimeout(() => m.setAttribute('content', c), 80); } }],
    ['rotated page turn', () => { const d = document.documentElement; d.style.transition = 'none'; d.style.transform = 'rotate(0.01deg)'; void d.offsetHeight; d.style.transform = ''; }],
  ];
  let vpStep = 0;
  function vpTry() {
    if (!vpStuck() || vpStep >= vpTries.length) { if (vpStep > 0) plog('JS| env viewport ' + (vpStuck() ? 'still short after all tries: ' : 'fixed after: ') + (vpStep ? vpTries[vpStep - 1][0] : '-') + ' inner ' + innerWidth + 'x' + innerHeight); return; }
    const t = vpTries[vpStep++];
    try { t[1](); } catch (e) {}
    setTimeout(() => { plog('JS| env vp try "' + t[0] + '" inner ' + innerWidth + 'x' + innerHeight + ' outer ' + outerWidth + 'x' + outerHeight); relayout(); setTimeout(vpTry, 200); }, 450);
  }
  setTimeout(vpTry, 2500);
  [250, 800, 1800, 3500].forEach((ms) => setTimeout(() => { try { window.scrollTo(0, 0); dispatchEvent(new Event('resize')); if (!kbHold) relayout(); } catch (e) {} }, ms));
  [400, 1500, 4000, 9000].forEach((ms) => setTimeout(() => { if (!kbHold) relayout(); }, ms));
  addEventListener('orientationchange', () => setTimeout(relayout, 200));

  // ------------------------------------------------------------------ backdrop: splash art
  const bg = el('div', null, root);
  bg.id = 'tta-bg';
  [[0.3, 0.1, 150], [0.75, 0.55, 110], [0.1, 0.7, 130], [0.6, 0.15, 90], [0.9, 0.85, 120], [0.45, 0.8, 100], [0.2, 0.3, 80]].forEach((d) => {
    const dot = el('div', 'dot', bg); dot.dataset.fx = d[0]; dot.dataset.fy = d[1]; dot.dataset.d = d[2];
  });
  const title = el('div', null, root);
  title.id = 'tta-title';
  title.textContent = 'TOONTOWN: ANYWHERE';
  const logo = el('img', null, root);
  logo.id = 'tta-logo';
  logo.style.display = 'none';
  const bgImg = el('img', null, bg);
  bgImg.style.display = 'none';
  let haveArt = false;
  layouts.push(() => {
    bg.querySelectorAll('.dot').forEach((d) => { const s = +d.dataset.d; Object.assign(d.style, { width: s + 'px', height: s + 'px', left: d.dataset.fx * W + 'px', top: d.dataset.fy * H + 'px' }); });
    if (haveArt && logo.naturalWidth) {
      const lh = Math.min(H * 0.40, 200 * sc), lw = lh * logo.naturalWidth / logo.naturalHeight;
      Object.assign(logo.style, { height: lh + 'px', width: lw + 'px', top: Math.max(H * 0.04, 10) + 'px', visibility: '' });
    }
  });
  async function loadArt() {
    try {
      if (typeof caches === 'undefined') {                       // not a secure page: no Cache API, just fetch the two pictures
        const urls = await Promise.all([prefs.base + '/_ui/background.jpg', prefs.base + '/_ui/logo.png'].map(async (u) => {
          const r = await fetch(u, { cache: 'no-store' }); return r.ok ? URL.createObjectURL(await r.blob()) : null; }));
        if (urls[0]) {          // the logo is optional: the sky alone is enough
          bgImg.src = urls[0]; if (urls[1]) logo.src = urls[1];
          await Promise.all([bgImg.decode().catch(() => {}), logo.decode().catch(() => {})]);
          bgImg.style.display = ''; if (urls[1]) { logo.style.display = ''; title.style.display = 'none'; }
          bg.querySelectorAll('.dot').forEach((d) => { d.style.display = 'none'; });
          haveArt = true; relayout();
        }
        return;
      }
      const cache = await caches.open('ttr-art-v1');
      const get = async (url) => {
        // ask the server first: a picture it no longer has (404) is dropped from the saved copy; the saved copy is only for when we are offline
        let status = 0, r = null;
        try {
          const n = await fetch(url + '?t=' + Date.now(), { cache: 'no-store' });
          status = n.status;
          if (n.ok) { await cache.put(url, n.clone()); r = n; } else if (n.status === 404) await cache.delete(url);
        } catch (e) { /* offline */ }
        if (!r && status !== 404) r = await cache.match(url);
        return r ? URL.createObjectURL(await r.blob()) : null;
      };
      const [b, l] = await Promise.all([get(prefs.base + '/_ui/background.jpg'), get(prefs.base + '/_ui/logo.png')]);
      if (b) {
        bgImg.src = b; if (l) logo.src = l;
        await Promise.all([bgImg.decode().catch(() => {}), logo.decode().catch(() => {})]);
        bgImg.style.display = ''; if (l) { logo.style.display = ''; title.style.display = 'none'; }
        bg.querySelectorAll('.dot').forEach((d) => { d.style.display = 'none'; });
        haveArt = true; relayout();
      }
    } catch (e) { /* the gradient and title stay */ }
  }

  // ------------------------------------------------------------------ loading screen
  const load = el('div', null, root);
  load.id = 'tta-load';
  const bar = el('div', null, load); bar.id = 'tta-bar'; const barFill = el('i', null, bar);
  const status = el('div', null, load); status.id = 'tta-status';
  const detail = el('div', null, load); detail.id = 'tta-detail';
  const spin = el('div', null, load); spin.id = 'tta-spin'; spin.style.display = 'none';
  const errBox = el('div', null, load); errBox.id = 'tta-error'; errBox.style.display = 'none';
  const errBtn = el('button', 'tta-pill light on', load); errBtn.textContent = 'Change server'; errBtn.style.display = 'none';
  layouts.push(() => {
    const bw = Math.min(W * 0.6, 640);
    Object.assign(bar.style, { width: bw + 'px', top: H * 0.68 - 29 + 'px' });
    status.style.top = H * 0.68 + 30 + 'px';
    detail.style.top = H * 0.68 + 30 + 34 * sc * 1.45 + 10 * sc + 'px';      // under the (outlined, larger) status line, whatever the screen size
    Object.assign(errBtn.style, { left: (W - 170) / 2 + 'px', top: H - 64 + 'px', width: '170px', height: '40px', fontSize: '16px' });
  });
  function setStatus(msg, det, frac) {
    status.textContent = msg || ''; detail.textContent = det || '';
    if (frac != null) { bar.style.display = ''; barFill.style.width = Math.max(0, Math.min(1, frac)) * 100 + '%'; }
  }
  function showLoad(on) { load.style.display = on ? '' : 'none'; }
  function showError(msg) {
    spin.style.display = 'none'; status.textContent = 'Something went wrong';
    errBox.textContent = msg; errBox.style.display = ''; errBtn.style.display = '';
  }
  errBtn.addEventListener('click', () => { errBox.style.display = 'none'; errBtn.style.display = 'none'; showServerCard(false); });

  // ------------------------------------------------------------------ the downloader
  // Saved packs: the Cache API on secure (https) pages, IndexedDB everywhere else, so the files are not downloaded every launch.
  const idb = (() => {
    let dbp = null;
    function open() {
      if (!dbp) dbp = new Promise((res, rej) => {
        if (typeof indexedDB === 'undefined') { rej(new Error('no IndexedDB')); return; }
        const r = indexedDB.open('ttr', 1);
        r.onupgradeneeded = () => r.result.createObjectStore('packs');
        r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error);
      });
      return dbp;
    }
    async function tx(mode, fn) {
      const db = await open();
      return new Promise((res, rej) => {
        const t = db.transaction('packs', mode), rq = fn(t.objectStore('packs'));
        t.oncomplete = () => res(rq && rq.result); t.onerror = () => rej(t.error); t.onabort = () => rej(t.error);
      });
    }
    return { get: (k) => tx('readonly', (s) => s.get(k)), put: (k, v) => tx('readwrite', (s) => s.put(v, k)),
             keys: () => tx('readonly', (s) => s.getAllKeys()), del: (k) => tx('readwrite', (s) => s.delete(k)) };
  })();
  function fsReady() { return typeof window.FS !== 'undefined' && T.pyReady; }
  // Low-memory mode (?lowmem=1 on the address, or tta_lowmem=1 saved in this browser): long sound files (the music, about a quarter of all the game
  // files) are not copied into the game's in-memory file system. They stay inside the saved pack, which the browser keeps on disk, and the audio
  // code reads them from there when they play. The game still needs to see the file to ask how long it is, so a stub is left in its place: the
  // first 4 KB (the Ogg header) and the last 70 KB (the final page, which holds the length).
  // Always on, on every device, because every phone and tablet closes a page that uses too much memory. ?lowmem=0 on the address, or tta_lowmem set to 0
  // in this browser, turns it off. (It also turns itself off when the browser cannot keep the saved packs; see downloadAll.)
  let LOWMEM = (() => {
    try {
      if (/[?&]lowmem=0/.test(location.search)) return false;
      if (/[?&]lowmem=1/.test(location.search)) return true;
      if (localStorage.getItem('tta_lowmem') === '0') return false;
    } catch (e) {}
    return true;
  })();
  const LAZY_MIN = 400000, STUB_HEAD = 4096, STUB_TAIL = 70000;
  // Lazy game files (prototype; ?lazyfs=1 on the address turns it on for this browser, ?lazyfs=0 off). Files over 16 KB are not copied into the game's
  // in-memory file system at all. The file system gets an empty placeholder that knows where the bytes are in the saved pack, and reads them when the game
  // asks (a synchronous range request, 256 KB at a time, a few blocks kept for the next read). The memory holds only what the game is using.
  let LAZYFS = false;
  try {
    if (/[?&]lazyfs=1/.test(location.search)) localStorage.setItem('tta_lazyfs', '1');
    if (/[?&]lazyfs=0/.test(location.search)) localStorage.removeItem('tta_lazyfs');
    LAZYFS = localStorage.getItem('tta_lazyfs') === '1';
  } catch (e) {}
  const LZ_MIN = 16384, LZ_BLOCK = 262144, LZ_CACHE_MAX = 24 * 1048576;
  const LZ = T.lz = { files: 0, bytes: 0, blocks: 0, blockBytes: 0, ms: 0, hits: 0, slow: 0, maxMs: 0, errors: 0 };
  const lzCache = new Map(); let lzCacheBytes = 0;
  function lzBlock(url, idx) {
    const k = url + '|' + idx, hit = lzCache.get(k);
    if (hit) { LZ.hits++; lzCache.delete(k); lzCache.set(k, hit); return hit; }
    const t = performance.now();
    const x = new XMLHttpRequest();
    x.open('GET', url, false);
    x.setRequestHeader('Range', 'bytes=' + (idx * LZ_BLOCK) + '-' + ((idx + 1) * LZ_BLOCK - 1));
    x.overrideMimeType('text/plain; charset=x-user-defined');      // the only way a synchronous request on the main thread can return bytes
    x.send(null);
    if (x.status !== 206) { LZ.errors++; throw new Error('range read of ' + url + ' gave ' + x.status); }
    const s = x.responseText, b = new Uint8Array(s.length);
    for (let i = 0; i < s.length; i++) b[i] = s.charCodeAt(i) & 255;
    const ms = performance.now() - t;
    LZ.blocks++; LZ.blockBytes += b.length; LZ.ms += ms; if (ms > LZ.maxMs) LZ.maxMs = ms; if (ms > 50) LZ.slow++;
    lzCache.set(k, b); lzCacheBytes += b.length;
    while (lzCacheBytes > LZ_CACHE_MAX && lzCache.size > 1) { const first = lzCache.keys().next().value; lzCacheBytes -= lzCache.get(first).length; lzCache.delete(first); }
    return b;
  }
  function fsLazy(path, url, off, size) {
    const FSr = window.FS;
    const dir = path.slice(0, path.lastIndexOf('/')), name = path.slice(path.lastIndexOf('/') + 1);
    try { FSr.mkdirTree(dir); } catch (e) { /* exists */ }
    const node = FSr.createFile(dir, name, null, true, false);
    node.contents = null;
    Object.defineProperty(node, 'usedBytes', { get: () => size, configurable: true });
    const ops = {}; Object.keys(node.stream_ops).forEach((k) => { ops[k] = node.stream_ops[k]; });
    ops.read = (stream, buffer, offset, length, position) => {
      if (position >= size) return 0;
      const n = Math.min(length, size - position);
      let done = 0;
      while (done < n) {
        const abs = off + position + done, idx = Math.floor(abs / LZ_BLOCK), blk = lzBlock(url, idx);
        const from = abs - idx * LZ_BLOCK, take = Math.min(n - done, blk.length - from);
        if (take <= 0) break;
        buffer.set(blk.subarray(from, from + take), offset + done);
        done += take;
      }
      return done;
    };
    ops.mmap = null;
    node.stream_ops = ops;
    LZ.files++; LZ.bytes += size;
  }
  const lazy = new Map();                  // file system path -> { key, off, size }
  const store = { cache: null, blobs: new Map() };
  T.lowmem = LOWMEM;
  T.lazyHas = (path) => lazy.has(path);

  // Memory and kill log (test sessions only, i.e. when logging is on). A phone that kills the page leaves no message, so the page writes a note
  // about itself every few seconds; the next visit reads it and says whether the last one ended cleanly, in the foreground or the background,
  // how much memory it held, and the last line the game printed.
  const MEM = T.mem = { fsFiles: 0, fsBytes: 0, stubs: 0, savedBytes: 0, reads: 0, readBytes: 0, packBlobs: 0 };
  const ALIVE = 'tta_alive', t0 = Date.now();
  const mbs = (n) => Math.round(n / 1e5) / 10;
  function memLine(why) {
    let wasm = 0, heap = 0, snd = '';
    try { const s = window.ttaAudio && window.ttaAudio.stats && window.ttaAudio.stats(); if (s) snd = ', decoded sounds ' + mbs(s.bytes) + ' of ' + mbs(s.cap) + ' MB (' + s.count + ' held, ' + s.decoded + ' decoded, ' + s.evicted + ' dropped)'; } catch (e) {}
    try { wasm = window.Module && window.Module.HEAPU8 ? window.Module.HEAPU8.length : (window.wasmMemory ? window.wasmMemory.buffer.byteLength : 0); } catch (e) {}
    try { heap = performance.memory ? performance.memory.usedJSHeapSize : 0; } catch (e) {}
    return { wasm: mbs(wasm), heap: mbs(heap), fs: mbs(MEM.fsBytes), text: 'JS| mem ' + why + ' up ' + Math.round((Date.now() - t0) / 1000) + 's ' + (document.hidden ? 'hidden' : 'visible') +
      ' wasm ' + mbs(wasm) + ' MB, js heap ' + (heap ? mbs(heap) + ' MB' : 'n/a') + ', game files in memory ' + mbs(MEM.fsBytes) + ' MB (' + MEM.fsFiles + ' files, ' + MEM.stubs + ' music stubs, ' + mbs(MEM.savedBytes) +
      ' MB kept out)' + (LAZYFS ? ', LAZY FILES ' + LZ.files + ' (' + mbs(LZ.bytes) + ' MB not in memory), range reads ' + LZ.blocks + ' (' + mbs(LZ.blockBytes) + ' MB, ' + Math.round(LZ.ms) + ' ms, slowest ' + Math.round(LZ.maxMs) + ' ms, ' + LZ.slow + ' over 50 ms, ' + LZ.hits + ' from the block cache, ' + LZ.errors + ' failed)' : '') + snd + ', music reads ' + MEM.reads + ' (' + mbs(MEM.readBytes) + ' MB), lowmem ' + (LOWMEM ? 'on' : 'off') + ', device memory ' + (navigator.deviceMemory || '?') + ' GB, last game line: ' + (T.lastPy || '-') };
  }
  if (LOGGING) {
    try {
      const prev = JSON.parse(localStorage.getItem(ALIVE) || 'null');
      if (prev) plog('JS| mem PREVIOUS VISIT ' + (prev.clean ? 'closed cleanly' : 'ENDED WITHOUT A CLEAN EXIT (page killed or crashed)') + '; last note ' + Math.round((Date.now() - prev.t) / 1000) + 's ago while ' + prev.vis +
        ', up ' + prev.up + 's, wasm ' + prev.wasm + ' MB, game files ' + prev.fs + ' MB, last game line: ' + prev.py);
    } catch (e) {}
    const beat = (why) => {
      const m = memLine(why);
      try { localStorage.setItem(ALIVE, JSON.stringify({ t: Date.now(), clean: 0, vis: document.hidden ? 'hidden' : 'visible', up: Math.round((Date.now() - t0) / 1000), wasm: m.wasm, fs: m.fs, py: (T.lastPy || '').slice(0, 160) })); } catch (e) {}
      plog(m.text);
    };
    T.memBeat = beat;
    setInterval(() => beat('beat'), 10000);
    document.addEventListener('visibilitychange', () => beat(document.hidden ? 'went to background' : 'came back'));
    addEventListener('pagehide', () => { try { const r = JSON.parse(localStorage.getItem(ALIVE) || '{}'); r.clean = 1; r.t = Date.now(); localStorage.setItem(ALIVE, JSON.stringify(r)); } catch (e) {} plog('JS| mem pagehide (page closing)'); });
    setTimeout(() => beat('start'), 1500);
  }
  // The saved pack holding a lazy file, as a Blob (a Blob is read from disk as needed, not held in memory), then the file's bytes as a slice of it.
  T.lazyBlob = async (path) => {
    const e = lazy.get(path); if (!e) return null;
    let bp = store.blobs.get(e.key);
    const tr = performance.now(), created = !bp;
    if (!bp) {
      MEM.packBlobs++;
      bp = (async () => {
        if (store.cache) { const r = await store.cache.match(e.key); if (r) return await r.blob(); }
        else { const b = await idb.get(e.key); if (b) return b; }
        // the saved copy is gone (the browser cleared it, or it could not be kept): fetch the pack again
        plog('JS| mem saved pack missing, fetching it again: ' + e.key);
        const net = await fetch(e.key, { cache: 'no-store' });
        if (!net.ok) throw new Error('pack not available: ' + e.key + ' ' + net.status);
        return await net.blob();
      })();
      store.blobs.set(e.key, bp);
      bp.catch(() => store.blobs.delete(e.key));
    }
    const whole = await bp;
    MEM.reads++; MEM.readBytes += e.size;
    plog('JS| mem music read ' + path.slice(path.lastIndexOf('/') + 1) + ' ' + Math.round(e.size / 1024) + ' KB, ' + Math.round(performance.now() - tr) + ' ms' + (created ? ' (first read from this pack)' : '') + ', pack ' + Math.round(whole.size / 1e6) + ' MB');
    return whole.slice(e.off, e.off + e.size, 'audio/ogg');
  };
  const ASSETS = '/data/data/game_ot/assets/';
  function fsWrite(path, data) {
    const FSr = window.FS;
    const dir = path.slice(0, path.lastIndexOf('/'));
    try { FSr.mkdirTree(dir); } catch (e) { /* exists */ }
    FSr.writeFile(path, data);
    MEM.fsFiles++; MEM.fsBytes += data.length;
  }
  async function streamUnzip(body, onBytes, onEntry, tap) {
    const reader = body.getReader();
    let buf = new Uint8Array(1 << 20), len = 0, pos = 0, shifted = 0;      // (shifted: bytes of the zip dropped from the front of buf so far, so shifted + pos is the place in the zip)
    async function fill(min) {
      while (len - pos < min) {
        const r = await reader.read();
        if (r.done) return false;
        const v = r.value;
        onBytes(v.length);
        if (tap) tap(v);
        if (len + v.length > buf.length) {
          if (pos > 0) { buf.copyWithin(0, pos, len); len -= pos; shifted += pos; pos = 0; }
          if (len + v.length > buf.length) { const nb = new Uint8Array(Math.max(buf.length * 2, len + v.length)); nb.set(buf.subarray(0, len)); buf = nb; }
        }
        buf.set(v, len); len += v.length;
      }
      return true;
    }
    const dec = new TextDecoder();
    for (;;) {
      if (!(await fill(30))) break;
      const dv = new DataView(buf.buffer, buf.byteOffset + pos, 30);
      if (dv.getUint32(0, true) !== 0x04034b50) break;                       // central directory: done
      const flags = dv.getUint16(6, true), method = dv.getUint16(8, true);
      const csize = dv.getUint32(18, true), nlen = dv.getUint16(26, true), elen = dv.getUint16(28, true);
      if ((flags & 8) || method !== 0) throw new Error('unsupported pack format');
      if (!(await fill(30 + nlen + elen))) throw new Error('pack ended early');
      const name = dec.decode(buf.subarray(pos + 30, pos + 30 + nlen));
      pos += 30 + nlen + elen;
      if (!(await fill(csize))) throw new Error('pack ended early');
      if (!name.endsWith('/')) onEntry(name, buf.subarray(pos, pos + csize), shifted + pos);
      pos += csize;
    }
    try { await reader.cancel(); } catch (e) { /* ignore */ }
  }
  async function downloadAll() {
    const bootAt = Number.isFinite(T.bootStart) ? T.bootStart : performance.now();
    const engineWaitAt = performance.now();
    setStatus('Getting ready...', '', 0);
    let waited = 0;
    while (!fsReady()) {
      await sleep(150); waited += 150;
      if (waited === 30000) setStatus('Getting ready...', 'Starting the game engine. This can take a little while the first time.', 0);
      if (waited === 90000) setStatus('Getting ready...', 'Still starting. If nothing changes, reload this page.', 0);
    }
    const engineReadyAt = performance.now();
    plog('JS| startup engine-ready waitMs=' + Math.round(engineReadyAt - engineWaitAt) + ' totalMs=' + Math.round(engineReadyAt - bootAt));
    setStatus('Checking game files...', '', 0);
    const base = prefs.base;
    const packKey = (folder, size) => '?s=' + size + (folder === '/_packs_hd/' ? '&v=' + HD_PACK_V : '');
    const manifestAt = performance.now();
    const texMode = (() => { try { const v = LS.getItem('tta_textures'); return v == null ? 'original' : v; } catch (e) { return 'original'; } })();
    try { LS.setItem('tta_textures_active', texMode); } catch (e) {}
    const packPrefix = (texMode === 'remastered') ? '/_packs_hd' : '/_packs';
    const packsJsonUrl = (texMode === 'remastered') ? (base + '/packs_hd.json?t=' + Date.now()) : (base + '/packs.json?t=' + Date.now());
    let packs;
    try {
      const resp = await fetch(packsJsonUrl, { cache: 'no-store' });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      packs = await resp.json();
    } catch (e) {
      if (texMode === 'remastered') throw new Error('Could not load the Remastered texture manifest: ' + e);
      packs = await (await fetch(base + '/packs.json?t=' + Date.now(), { cache: 'no-store' })).json();
    }
    const total = packs.reduce((a, p) => a + p[1], 0);
    plog('JS| startup manifest mode=' + texMode + ' ms=' + Math.round(performance.now() - manifestAt) + ' packs=' + packs.length + ' zipMB=' + Math.round(total / 1e6));
    let got = 0, done = 0;
    const cachePrepAt = performance.now();
    let cache = null;
    try { if (typeof caches !== 'undefined' && !/nocache/.test(location.search)) cache = await caches.open('ttr-packs-v2'); } catch (e) { cache = null; }
    store.cache = cache;
    if (LOWMEM && !cache) {            // low-memory mode needs the browser to keep the packs: check that it does
      try { await idb.put('tta-probe', new Blob(['x'])); const pb = await idb.get('tta-probe'); await idb.del('tta-probe'); if (!pb) throw new Error('not kept'); }
      catch (e) { LOWMEM = false; T.lowmem = false; plog('JS| mem low-memory mode turned off: this browser cannot keep the saved game files (' + e + ')'); }
    }
    const want = new Set(packs.map((p) => {
      const folder = (p[0] === '_code') ? '/_packs/' : (packPrefix + '/');
      return base + folder + p[0] + '.zip' + packKey(folder, p[1]);
    }));
    try {
      const altUrl = (texMode === 'remastered') ? (base + '/packs.json?t=' + Date.now()) : (base + '/packs_hd.json?t=' + Date.now());
      const altPrefix = (texMode === 'remastered') ? '/_packs/' : '/_packs_hd/';
      const altResp = await fetch(altUrl, { cache: 'no-store' });
      if (altResp.ok) {
        const altPacks = await altResp.json();
        altPacks.forEach((p) => {
          const folder = (p[0] === '_code') ? '/_packs/' : altPrefix;
          want.add(base + folder + p[0] + '.zip' + packKey(folder, p[1]));
        });
      }
    } catch (e) { /* alternate manifest fetch is optional */ }
    try {
      if (cache) { for (const k of await cache.keys()) { if (!want.has(k.url.replace(location.origin, '')) && !want.has(k.url)) await cache.delete(k); } }
      else { for (const k of await idb.keys()) { if (!want.has(k)) await idb.del(k); } }
    } catch (e) { /* cleaning up is optional */ }
    plog('JS| startup cache-ready ms=' + Math.round(performance.now() - cachePrepAt) + ' store=' + (cache ? 'cache-api' : 'indexeddb'));
    const mb = (n) => Math.round(n / 1e6);
    const upd = (first) => setStatus(first ? 'Downloading game files' : 'Loading game files',
      mb(got) + ' of ' + mb(total) + ' MB   (' + done + ' of ' + packs.length + ' packs)', total ? got / total : 0);
    let fromNet = false;
    const restoreAt = performance.now();
    for (const [name, size] of packs) {
      const packAt = performance.now();
      const folder = (name === '_code') ? '/_packs/' : (packPrefix + '/');
      const url = base + folder + name + '.zip';
      const key = url + packKey(folder, size);
      let body, putP = null, chunks = null, fresh = false;
      let resp = cache ? await cache.match(key) : null;
      if (cache && !resp && name !== '_code') {            // copy saved by an older page version (its address had no size in it): keep it, so game art is not downloaded twice
        const old = await cache.match(url);
        if (old) { resp = old; try { await cache.put(key, old.clone()); await cache.delete(url); } catch (e) { /* fine */ } }
      }
      let blob = null;
      if (!cache) { try { blob = await idb.get(key); } catch (e) { blob = null; } }
      if (blob) body = blob.stream();
      else if (!resp) {
        fromNet = true; fresh = true;
        resp = await fetch(key, { cache: 'no-store' });
        if (!resp.ok) throw new Error('could not download ' + name + ' (' + resp.status + ')');
        if (cache) {
          const [x, y] = resp.body.tee();
          body = x;
          putP = cache.put(key, new Response(y, { headers: { 'content-type': 'application/zip' } })).catch(() => {});
        } else { body = resp.body; chunks = []; }
      } else body = resp.body;
      const source = fresh ? 'network' : (blob ? 'indexeddb' : 'cache-api');
      await streamUnzip(body, (n) => { got += n; upd(fromNet); }, (path, data, off) => {
        const dest = path.startsWith('_code/') ? ASSETS + path.slice(6) : ASSETS + 'resources/' + path;
        if (LOWMEM && data.length > LAZY_MIN && /\/audio\/[^]*\.ogg$/.test(path) && !path.startsWith('_code/')) {
          lazy.set(dest, { key, off, size: data.length });
          let stub = data.slice();
          if (data.length > STUB_HEAD + STUB_TAIL) { stub = new Uint8Array(STUB_HEAD + STUB_TAIL); stub.set(data.subarray(0, STUB_HEAD), 0); stub.set(data.subarray(data.length - STUB_TAIL), STUB_HEAD); }
          fsWrite(dest, stub);
          MEM.stubs++; MEM.savedBytes += data.length - stub.length;
          return;
        }
        // Emscripten FS.writeFile copies synchronously; pass this live zip-buffer view directly to avoid an extra per-file allocation.
        fsWrite(dest, data);
      }, chunks ? (v) => chunks.push(v) : null);
      if (putP) await putP;
      if (chunks) { try { await idb.put(key, new Blob(chunks, { type: 'application/zip' })); } catch (e) { console.warn('could not save ' + name, e); } chunks = null; }
      done++; upd(fromNet);
      plog('JS| mem pack ' + name + ' loaded (' + mb(size) + ' MB, ' + (fresh ? 'downloaded' : 'from the saved copy') + '); game files in memory so far ' + mbs(MEM.fsBytes) + ' MB, ' + MEM.stubs + ' music stubs');
      plog('JS| startup pack ' + name + ' source=' + source + ' zipMB=' + mb(size) + ' elapsedMs=' + Math.round(performance.now() - packAt) + ' totalMs=' + Math.round(performance.now() - restoreAt));
      await sleep(0);
    }
    plog('JS| startup packs-ready elapsedMs=' + Math.round(performance.now() - restoreAt) + ' totalMs=' + Math.round(performance.now() - bootAt));
    plog('JS| mem ALL PACKS LOADED: ' + packs.length + ' packs, ' + mb(total) + ' MB of zips; ' + mbs(MEM.fsBytes) + ' MB held in memory as ' + MEM.fsFiles + ' files; ' + MEM.stubs + ' music files kept in the saved pack (' + mbs(MEM.savedBytes) + ' MB not in memory); lowmem ' + (LOWMEM ? 'on' : 'off') + '; saved copies in ' + (cache ? 'Cache API' : 'IndexedDB'));
    if (T.memBeat) T.memBeat('packs loaded');
    setStatus('Ready', '', 1);
  }

  // ------------------------------------------------------------------ shared pieces: pills, fields
  function pill(text, icon, fill, parent, cls) {
    const b = el('button', 'tta-pill ' + (cls || ''), parent);
    if (fill) b.style.background = fill;
    if (icon && ICONS[icon]) { const i = el('img', null, b); i.src = ICONS[icon]; }
    const s = document.createElement('span'); s.textContent = text; b.appendChild(s);
    b.classList.add('on');
    return b;
  }
  function field(ph, secure, parent, name, ac) {
    const f = el('input', 'tta-field on', parent);
    f.type = secure ? 'password' : 'text'; f.placeholder = ph;
    f.autocapitalize = 'none'; f.autocorrect = 'off'; f.spellcheck = false;
    if (name) f.name = name; if (ac) f.autocomplete = ac;
    return f;
  }

  // ------------------------------------------------------------------ the sign-in screen (same layout as the app)
  const login = el('div', null, root);
  login.id = 'tta-login'; login.style.display = 'none';
  const uField = field('Toon name', false, login, 'username', 'username');
  const pField = field('Password', true, login, 'password', 'current-password');
  const playBtn = el('button', 'tta-btn on', login); playBtn.textContent = 'PLAY!';
  const forgot = el('button', 'tta-link on', login); forgot.textContent = 'Forgot password?';
  // (the new-player hint stays up on its own line; sign-in errors and progress go on the line below it instead of replacing it)
  const hint = el('div', null, login, { position: 'absolute', left: '40px', right: '40px', textAlign: 'center', fontWeight: '700', color: '#1a408c' });
  hint.textContent = 'New here? Pick a name and password and tap PLAY!';
  const lmsg = el('div', null, login); lmsg.id = 'tta-msg';
  const credit = el('div', null, login); credit.id = 'tta-credit';
  credit.textContent = 'Official client for Toontown: Anywhere';
  // Toontown Infinite's licence asks that the attribution can be found through normal use of the game: it stays on the sign-in screen at all times
  const legal = el('div', null, login); legal.id = 'tta-legal';
  legal.innerHTML = 'Built on <a href="https://github.com/open-toontown/open-toontown" target="_blank" rel="noopener">Open Toontown</a><br>Based on Toontown Infinite &mdash; <a href="https://github.com/TT-Infinite-Archive/source" target="_blank" rel="noopener">https://github.com/TT-Infinite-Archive/source</a>';
  const chg = pill('Change server', null, null, login, 'light');
  const dis = pill('Discord', 'discord', 'rgb(88,101,242)', login);
  const red = pill('Reddit', 'reddit', 'rgb(255,69,0)', login);
  dis.addEventListener('click', () => window.open('https://discord.gg/f7YYstu7dA', '_blank', 'noopener'));
  red.addEventListener('click', () => window.open('https://www.reddit.com/r/ToontownAnywhere/s/p7FFnl9jGJ', '_blank', 'noopener'));
  let kbMode = false;
  function loginLayout() {
    const vv = window.visualViewport;
    const kb = kbMode && vv;
    const top = kb ? vv.offsetTop : 0;                  // the visible area above the keyboard starts here
    const w = Math.min(W * 0.5, 380 * sc);
    let y0 = kb ? top + 10 * sc : H * (haveArt ? 0.47 : 0.36);
    // (short screens, e.g. a phone browser with its toolbars: lift the fields, button and message so they end above the credit line,
    // shrink the logo to the room left over, and give up the credit line only when even that does not fit)
    const legalH = 25 * sc, legalTop = H - legalH - Math.max(SAFE.b, 4);
    const creditTop = legalTop - 14 * sc, stack = 208 * sc, minTop = Math.max(SAFE.t, 6) + 8;
    let showCredit = true;
    if (!kb) {
      let bottom = creditTop - 4;
      if (bottom - stack < minTop + 40 * sc) { bottom = legalTop; showCredit = false; }
      y0 = Math.max(minTop, Math.min(y0, bottom - stack));
      if (haveArt && logo.naturalWidth && login.style.display !== 'none') {
        const lt = Math.max(H * 0.04, 10), lh = Math.min(H * 0.40, 200 * sc, y0 - 6 - lt);
        if (lh < 36) logo.style.visibility = 'hidden';
        else Object.assign(logo.style, { visibility: '', height: lh + 'px', width: lh * logo.naturalWidth / logo.naturalHeight + 'px' });
      }
      if (title.style.display !== 'none' && login.style.display !== 'none') {
        // the text title (shown until the logo picture loads) sits above the fields too: up and smaller on a short screen
        const tt = Math.max(minTop, H * 0.04), room = y0 - 8 - tt;
        let fs = parseFloat(title.style.fontSize) || 56 * sc;
        if (fs * 1.2 > room) fs = room / 1.2;
        if (fs < 14) title.style.visibility = 'hidden';
        else Object.assign(title.style, { visibility: '', fontSize: fs + 'px', top: Math.min(H * 0.16, y0 - 8 - fs * 1.2) + 'px' });
      }
    }
    [uField, pField].forEach((f, i) => { Object.assign(f.style, { width: w + 'px', top: y0 + i * 52 * sc + 'px', left: W / 2 + 'px' }); });
    const bw = 220 * sc, bh = 48 * sc;
    place(playBtn, (W - bw) / 2, y0 + 106 * sc, bw, bh);
    place(forgot, (W + bw) / 2 + 10 * sc, y0 + 106 * sc, 150 * sc, bh);
    hint.style.top = y0 + 160 * sc + 'px'; hint.style.fontSize = 17 * sc + 'px';
    lmsg.style.top = y0 + 184 * sc + 'px'; lmsg.style.fontSize = 17 * sc + 'px';
    credit.style.top = creditTop + 'px';
    legal.style.top = legalTop + 'px';
    const pw = 126 * sc, ph = 30 * sc;
    place(chg, W - pw - 14 - SAFE.r, Math.max(SAFE.t, 6) + 8, pw, ph);
    const lby = H - Math.max(SAFE.b, 4) - 22 * sc - 8 - 30 * sc, lbx = 14 + SAFE.l;
    place(dis, lbx, lby - 38 * sc, 112 * sc, ph);
    place(red, lbx, lby, 112 * sc, ph);
    // (keep the hint and message clear of the Discord/Reddit buttons: a long message wraps instead of running under them)
    const clear = lbx + 112 * sc + 12, side = (W - 2 * clear >= 300 ? Math.max(40, clear) : 40) + 'px';
    [hint, lmsg].forEach((n) => { n.style.left = side; n.style.right = side; });
    [credit, legal, chg, dis, red].forEach((n) => { n.style.visibility = kb ? 'hidden' : ''; });
    if (!showCredit) credit.style.visibility = 'hidden';
    logo.style.opacity = kb ? '0' : '';
    title.style.opacity = kb ? '0' : '';
  }
  layouts.push(loginLayout);
  if (window.visualViewport) {
    visualViewport.addEventListener('resize', () => { if (kbMode) loginLayout(); });
    visualViewport.addEventListener('scroll', () => { if (kbMode) loginLayout(); });
  }
  function loginMessage(m, bad) { lmsg.textContent = m; lmsg.className = bad ? 'bad' : ''; lmsg.id = 'tta-msg'; }
  function showLogin() {
    showLoad(false); login.style.display = ''; cardClose();
    uField.value = LS.getItem(prefs.userKey) || '';
    pField.value = LS.getItem(prefs.userKey + '.pw') || '';
    loginMessage('', false);
    relayout();
  }
  async function authCall(path, text) {
    try {
      const r = await fetch(prefs.base + path, { method: 'POST', body: text, headers: { 'Content-Type': 'text/plain' } });
      const t = (await r.text()).trim();
      if (r.status === 404) return { ok: true, tag: 'ok', text: t };
      return { ok: r.ok, tag: r.ok ? t : '', text: t };
    } catch (e) { return { ok: false, tag: '', text: "Can't reach the Toontown server. Check your Wi-Fi." }; }
  }
  async function signIn() {
    const user = uField.value.trim().toLowerCase(), pw = pField.value;
    if (!user || !pw) { loginMessage('Enter your toon name and password.', true); return; }
    if (user.includes(':')) { loginMessage("Please don't use colons in your name.", true); return; }
    playBtn.disabled = true; loginMessage('Signing in...', false);
    const cookie = user + ':' + pw;
    const r = await authCall('/auth', cookie);
    playBtn.disabled = false;
    if (!r.ok) { loginMessage(r.text || 'Sign-in failed.', true); return; }
    LS.setItem(prefs.userKey, user); LS.setItem(prefs.userKey + '.pw', pw);
    const proceed = () => startGame(cookie);
    if (r.tag === 'setup') showRecoveryCard(false, cookie, user, proceed); else proceed();
  }

  // ------------------------------------------------------------------ pre-download texture picker card
  function showTextureCard(done) {
    const g = newCard(420);
    // Keep the game title and background from showing through the picker text.
    g.card.style.background = '#fff';
    // Title
    cText(g.card, 't', 'Choose Your Texture Quality', 16, 20);
    // Subtitle
    const sub = el('div', 's', g.card, {
      top: 48 * sc + 'px', left: g.pad + 'px', right: g.pad + 'px',
      fontSize: 13 * sc + 'px', lineHeight: '1.35', color: '#1a408c'
    });
    sub.textContent = 'Pick how the game looks. You can change this later in Shticker Book → Options → Device.';

    // Helper: build a tall pick button tile
    function pickTile(topPx, label, sublabel, badge, color, borderColor, pick) {
      const tileH = 118, tileW = g.w / sc;
      const tile = el('button', 'tta-btn on', g.card);
      Object.assign(tile.style, {
        position: 'absolute',
        left: g.pad + 'px',
        width: g.w + 'px',
        height: tileH * sc + 'px',
        top: topPx * sc + 'px',
        background: color,
        border: '3px solid ' + borderColor,
        borderRadius: 16 * sc + 'px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 4 * sc + 'px',
        cursor: 'pointer',
        textAlign: 'center',
        padding: '0 ' + 10 * sc + 'px',
      });
      const lbl = el('span', null, tile);
      lbl.textContent = label;
      lbl.style.cssText = 'font-size:' + 20 * sc + 'px;font-weight:800;color:' + (color === '#ffd926' ? '#733805' : '#fff') + ';line-height:1.1;pointer-events:none;';
      const slbl = el('span', null, tile);
      slbl.textContent = sublabel;
      slbl.style.cssText = 'font-size:' + 12 * sc + 'px;font-weight:600;color:' + (color === '#ffd926' ? '#5a2e02' : 'rgba(255,255,255,.85)') + ';pointer-events:none;';
      if (badge) {
        const bdg = el('span', null, tile);
        bdg.textContent = badge;
        bdg.style.cssText = 'margin-top:' + 3 * sc + 'px;font-size:' + 10 * sc + 'px;font-weight:700;color:#fff;background:rgba(0,0,0,.35);border-radius:' + 8 * sc + 'px;padding:1px ' + 7 * sc + 'px;pointer-events:none;';
      }
      tile.addEventListener('click', () => {
        LS.setItem('tta_textures', pick);
        LS.setItem('tta_textures_chosen', '1');
        LS.setItem('tta_textures_chosen_v' + TEXTURE_PICK_VERSION, '1');
        cardClose();
        done();
      });
      return tile;
    }

    // Original tile (yellow/gold — primary action)
    pickTile(92, '🎨  Original Textures', 'Classic look, faster loading', null, '#ffd926', '#8c520d', 'original');

    // Remastered tile (world textures 4x; interface textures 2x to limit mobile memory use)
    pickTile(220, '✨  Remastered Textures', '4× world textures · 2× interface', '⚠ Work in Progress', '#1f4da6', '#0d2a6b', 'remastered');

    // Fine-print note
    const note = el('div', 's', g.card, {
      top: 354 * sc + 'px', left: g.pad + 'px', right: g.pad + 'px',
      fontSize: 11 * sc + 'px', color: '#888', lineHeight: '1.3'
    });
    note.textContent = 'World textures use a clean 4× resize; interface art is 2× to stay lighter on phones. Changing textures later will restart the game.';
  }
  [uField, pField].forEach((f) => {
    f.setAttribute('enterkeyhint', f === pField ? 'go' : 'next');
    f.addEventListener('focus', () => { kbMode = true; loginLayout(); });
    f.addEventListener('blur', () => setTimeout(() => {
      if (document.activeElement !== uField && document.activeElement !== pField) { kbMode = false; loginLayout(); window.scrollTo(0, 0); }
    }, 80));
  });
  login.addEventListener('pointerdown', (e) => { if (e.target === login || e.target === credit || e.target === lmsg || e.target === hint) { if (document.activeElement && document.activeElement.blur) document.activeElement.blur(); } });
  playBtn.addEventListener('click', signIn);
  // Enter / Go / Send on a phone keyboard does not always arrive as a plain "Enter" key press (Android keyboards that are suggesting words
  // report key "Unidentified" and send the line break as an input event instead), so listen for both ways.
  function onEnter(el, fn) {
    let t = 0;
    const go = (e) => { const n = Date.now(); if (n - t < 250) return; t = n; fn(e); };
    el.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.keyCode === 13 || e.which === 13) { e.preventDefault(); go(e); } });
    el.addEventListener('beforeinput', (e) => { if (e.inputType === 'insertLineBreak' || e.inputType === 'insertParagraph') { e.preventDefault(); go(e); } });
  }
  onEnter(pField, () => signIn());
  onEnter(uField, () => pField.focus());
  forgot.addEventListener('click', () => {
    const user = uField.value.trim().toLowerCase();
    if (!user) { loginMessage('Type your toon name above first, then tap Forgot password.', true); return; }
    showRecoveryCard(true, '', user, () => { showLogin(); });
  });
  chg.addEventListener('click', () => showServerCard(true));

  // ------------------------------------------------------------------ cards (server choice, recovery)
  const cardWrap = el('div', null, root);
  cardWrap.id = 'tta-cardwrap'; cardWrap.style.display = 'none';
  function cardClose() { cardWrap.style.display = 'none'; cardWrap.innerHTML = ''; cardWrap.style.bottom = ''; }
  // A phone keyboard covers the lower part of the screen: end the card area above it (the card then scrolls), keep the field being typed in
  // in view, and let a tap on the card's empty space (or the Return key on the last field) put the keyboard away.
  function cardKb() {
    const vv = window.visualViewport;
    if (!vv || cardWrap.style.display === 'none') { cardWrap.style.bottom = ''; return; }
    const lost = Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
    cardWrap.style.bottom = lost + 'px';
    const a = document.activeElement;
    if (lost > 100 && a && cardWrap.contains(a)) setTimeout(() => { try { a.scrollIntoView({ block: 'center' }); } catch (e) {} }, 60);
  }
  if (window.visualViewport) { visualViewport.addEventListener('resize', cardKb); visualViewport.addEventListener('scroll', cardKb); }
  cardWrap.addEventListener('focusin', () => setTimeout(cardKb, 120));
  cardWrap.addEventListener('pointerdown', (e) => {
    const a = document.activeElement;
    if (a && a !== document.body && a.blur && !/^(INPUT|BUTTON|TEXTAREA|SELECT)$/.test(e.target.tagName)) { try { a.blur(); } catch (err) {} }
  });
  function chainFields(fields) {
    fields.forEach((f, i) => {
      const last = i === fields.length - 1;
      f.setAttribute('enterkeyhint', last ? 'done' : 'next');
      onEnter(f, () => { if (last) f.blur(); else fields[i + 1].focus(); });
    });
  }
  function newCard(h) {
    cardWrap.innerHTML = ''; cardWrap.style.display = '';
    login.style.display = 'none';
    const cw = Math.min(W - 40, 520 * sc), ch = h * sc;
    const card = el('div', 'tta-card', cardWrap, { width: cw + 'px', height: ch + 'px', top: Math.max(16, (H - ch) / 2) + 'px' });
    card.style.marginBottom = '16px';
    return { card, cw, ch, pad: 20 * sc, w: cw - 40 * sc };
  }
  function cText(parent, cls, txt, top, size, extra) {
    const t = el('div', cls, parent, Object.assign({ top: top * sc + 'px', fontSize: size * sc + 'px' }, extra || {}));
    t.textContent = txt; return t;
  }
  function cField(parent, ph, secure, top, geo) {
    const f = field(ph, secure, parent);
    Object.assign(f.style, { position: 'absolute', left: geo.pad + 'px', width: geo.w + 'px', top: top * sc + 'px', height: 42 * sc + 'px' });
    return f;
  }
  function cButton(parent, txt, cls, top, wpx, hpx, geo, fill) {
    const b = el('button', cls + ' on', parent);
    b.textContent = txt;
    Object.assign(b.style, { position: 'absolute', left: (geo.cw - wpx * sc) / 2 + 'px', top: top * sc + 'px', width: wpx * sc + 'px', height: hpx * sc + 'px' });
    if (fill) b.style.background = fill;
    return b;
  }
  function useServer(mode, res, game) {
    LS.setItem('tta_srv_mode', mode);
    if (mode === 'custom') { LS.setItem('tta_srv_res', res); LS.setItem('tta_srv_game', game); }
  }
  function showServerCard(canGoBack) {
    showLoad(false);
    const g = newCard(canGoBack ? 430 : 392);
    cText(g.card, 't', 'Choose a server', 12, 26);
    const def = cButton(g.card, 'Connect to ' + DEFAULT.name, 'tta-btn', 52, (g.w / sc), 48, g);
    Object.assign(def.style, { left: g.pad + 'px', width: g.w + 'px', fontSize: 21 * sc + 'px' });
    cText(g.card, 's', DEFAULT.host, 102, 12);
    cText(g.card, 't', 'or connect to a different server', 128, 16, { fontWeight: 700 });
    const rf = cField(g.card, 'File server  (https://...)', false, 154, g);
    const gf = cField(g.card, 'Game server  (host:port)', false, 202, g);
    if (!prefs.isDefault) { rf.value = prefs.res; gf.value = prefs.game; }
    const warn = cText(g.card, 's', "Only connect to servers you trust. A server supplies the game's code, which runs inside this app.", 250, 11, { color: 'rgb(115,51,26)', padding: '0 ' + g.pad + 'px' });
    const cbtn = cButton(g.card, 'Connect', 'tta-btn', 290, 200, 44, g, 'rgb(89,166,255)');
    Object.assign(cbtn.style, { color: '#fff', fontSize: 22 * sc + 'px', border: '3px solid #1f4da6' });
    const msg = cText(g.card, 's', '', 338, 14, { padding: '0 ' + g.pad + 'px' });
    const setMsg = (t, bad) => { msg.textContent = t; msg.style.color = bad ? '#d91a1a' : '#1a408c'; };
    if (canGoBack) {
      const bk = cButton(g.card, 'Back', 'tta-pill gray', 384, 120, 32, g);
      bk.addEventListener('click', () => { cardClose(); login.style.display = ''; });
    }
    def.addEventListener('click', () => {
      const same = prefs.isDefault && prefs.mode;
      useServer('default'); cardClose();
      if (same && canGoBack) { login.style.display = ''; return; }
      beginDownload();
    });
    const connect = async () => {
      const res = rf.value.trim(), game = gf.value.trim();
      if (!res || !game) { setMsg('Fill in both boxes, or tap the button above.', true); return; }
      if (/[^A-Za-z0-9.\-:/_\[\]%]/.test(res + game)) { setMsg("Those addresses have a character that isn't allowed.", true); return; }
      cbtn.disabled = def.disabled = true; setMsg('Checking the server...', false);
      let url = /^https?:\/\//i.test(res) ? res : 'https://' + res;
      url = url.replace(/\/+$/, '');
      let err = '';
      try {
        const r = await fetch(url + '/manifest.json', { cache: 'no-store' });
        if (!r.ok) err = 'The file server answered with an error (' + r.status + '). Check the address.';
        else { const rd = r.body.getReader(); const c = await rd.read(); rd.cancel(); if (!c.value || c.value[0] !== 123) err = "That address doesn't look like a Toontown file server."; }
      } catch (e) { err = "Can't reach the file server. Check the address, your connection, and that the server allows web access."; }
      cbtn.disabled = def.disabled = false;
      if (err) { setMsg(err, true); return; }
      useServer('custom', url, game); cardClose(); beginDownload();
    };
    cbtn.addEventListener('click', connect);
    onEnter(gf, () => { gf.blur(); connect(); });
    onEnter(rf, () => gf.focus());
    rf.setAttribute('enterkeyhint', 'next'); gf.setAttribute('enterkeyhint', 'go');
  }
  function showRecoveryCard(reset, cookie, user, done) {
    const g = newCard(reset ? 392 : 344);
    cText(g.card, 't', reset ? 'Reset password' : 'Forgot-password help', 12, 26);
    cText(g.card, 's', reset ? 'Answer the two questions you saved for ' + user + ', then pick a new password.' :
      'Pick two answers only you will remember. If you ever forget your password, they let you set a new one.', 52, 14, { padding: '0 ' + g.pad + 'px', fontWeight: 600 });
    const nick = cField(g.card, 'Your nickname', false, 100, g);
    const toon = cField(g.card, 'A toon name you made', false, 148, g);
    const npw = reset ? cField(g.card, 'New password', true, 196, g) : null;
    chainFields(npw ? [nick, toon, npw] : [nick, toon]);
    const y = reset ? 244 : 196;
    const msg = cText(g.card, 's', '', y + 2, 14, { padding: '0 ' + g.pad + 'px' });
    const setMsg = (t, bad) => { msg.textContent = t; msg.style.color = bad ? '#d91a1a' : '#1a408c'; };
    const prim = cButton(g.card, reset ? 'Reset password' : 'Save', 'tta-pill blue', y + 40, 220, 44, g);
    prim.style.fontSize = 22 * sc + 'px';
    // The prompt comes back at every sign-in until answers are saved. The first two times it can be skipped; after that it has to be
    // filled in (a player with no answers cannot reset their own password, and moderators have to do it by hand).
    let skips = 0; try { skips = +LS.getItem('tta.recskips') || 0; } catch (e) { skips = 0; }
    const mustSet = !reset && skips >= 2;
    const sec = cButton(g.card, reset ? 'Cancel' : 'Skip for now', 'tta-pill gray', y + 92, 160, 32, g);
    if (mustSet) sec.style.display = 'none';
    sec.addEventListener('click', () => { if (!reset) { try { LS.setItem('tta.recskips', String(skips + 1)); } catch (e) {} } cardClose(); done(); });
    prim.addEventListener('click', async () => {
      const n = nick.value.trim(), t = toon.value.trim(), p = npw ? npw.value : '';
      if (!n || !t || (reset && !p)) { setMsg('Fill in every box.', true); return; }
      if (reset && p.includes(':')) { setMsg("Please don't use colons in a password.", true); return; }
      prim.disabled = sec.disabled = true; setMsg(reset ? 'Checking...' : 'Saving...', false);
      const r = await authCall(reset ? '/recover' : '/setrecovery', reset ? [user, n, t, p].join('\n') : [cookie, n, t].join('\n'));
      prim.disabled = sec.disabled = false;
      if (!r.ok) { setMsg(r.text || "That didn't work.", true); return; }
      cardClose();
      if (reset) { showLogin(); pField.value = p; loginMessage('Password changed! Tap PLAY.', false); } else done();
    });
  }

  // ------------------------------------------------------------------ the game connection: straight to the server, not through the tunnel
  // The live site's game connection goes to ws.puffsco.com (a DNS-only address that reaches the server directly) when that answers: the tunnel
  // drops connections at random. The page checks it as soon as it loads (a WebSocket that must open within 4 seconds), and falls back to the
  // old route (the page's own address) when it does not, so a player is never left without a connection. ?ws=off keeps a device on the old route.
  const DIRECT_WS = 'wss://ws.puffsco.com:4443/ws';
  const directProbe = (() => {
    if (location.hostname !== 'toontown.puffsco.com') return Promise.resolve(false);       // test copies and other servers keep their own route
    try { if (window.localStorage.getItem('tta_ws') === 'off') return Promise.resolve(false); } catch (e) {}
    return new Promise((resolve) => {
      const t0 = Date.now(); let done = false, sock = null;
      const fin = (ok, why) => {
        if (done) return; done = true;
        try { if (sock) sock.close(); } catch (e) {}
        plog('JS| route ' + (ok ? 'direct' : 'tunnel') + ' (' + why + ', ' + (Date.now() - t0) + ' ms)');
        resolve(ok);
      };
      try { sock = new WebSocket(DIRECT_WS); sock.onopen = () => fin(true, 'opened'); sock.onerror = () => fin(false, 'error'); sock.onclose = () => fin(false, 'closed'); }
      catch (e) { fin(false, 'blocked'); }
      setTimeout(() => fin(false, 'no answer'), 4000);
    });
  })();
  // ------------------------------------------------------------------ the flow
  async function beginDownload() {
    T.bootStart = performance.now();
    errBox.style.display = 'none'; errBtn.style.display = 'none'; spin.style.display = 'none';
    loadArt();
    const downloadSelectedPacks = async () => {
      login.style.display = 'none'; showLoad(true);
      try {
        await downloadAll();
        showLogin();
        plog('JS| startup login-ready totalMs=' + Math.round(performance.now() - T.bootStart));
      } catch (e) { console.error(e); showError(String(e && e.stack || e)); }
    };
    // The first texture choice must happen before downloadAll(): otherwise the
    // picker appears after the default/original pack has already been unpacked.
    if (LS.getItem('tta_textures_chosen_v' + TEXTURE_PICK_VERSION) !== '1') {
      login.style.display = 'none'; showLoad(false);
      plog('JS| texture picker shown v' + TEXTURE_PICK_VERSION);
      showTextureCard(downloadSelectedPacks);
      return;
    }
    await downloadSelectedPacks();
  }
  async function startGame(cookie) {
    T.gameStartAt = performance.now();
    login.style.display = 'none'; cardClose(); showLoad(true);
    setStatus('Starting Toontown...', '', null); bar.style.display = 'none'; spin.style.display = '';
    T.wsUrl = prefs.ws;
    if (prefs.isDefault && T.wsUrl.indexOf('//' + location.host + '/') >= 0 && await directProbe) T.wsUrl = DIRECT_WS;      // (a ?ws= choice, or a custom server, is left as it is)
    try {            // the server's game settings (gameconfig.json); no file, or no answer in 3 seconds, means the game's own defaults
      const ctl = new AbortController(); const timer = setTimeout(() => ctl.abort(), 3000);
      const r = await fetch('/gameconfig.json?t=' + Date.now(), { cache: 'no-store', signal: ctl.signal });
      clearTimeout(timer);
      if (r.ok) T.gameConfig = await r.text();
    } catch (e) { }
    T.cookie = cookie; T.go = true;
    plog('JS| session user: ' + String(cookie).split(':')[0] + ' route ' + (T.wsUrl.indexOf('//' + location.host + '/') >= 0 ? 'tunnel' : 'direct'));       // the name only, never the password
    // If the first drawn frame never arrives, leave one line in the quiet log, with the last Python line, so a
    // "stuck on Starting Toontown" report can be diagnosed without reloading with ?log=1.
    const waitAt = performance.now();
    setTimeout(() => {
      if (!T.didStart) plog('JS| startup still-waiting afterMs=' + Math.round(performance.now() - waitAt) + ' lastPy=' + (T.lastPy || '(none)'));
    }, 90000);
  }
  T.started = function () {          // called by the game once it is drawing
    T.didStart = true;
    if (Number.isFinite(T.gameStartAt)) plog('JS| startup first-draw afterLoginMs=' + Math.round(performance.now() - T.gameStartAt));
    bg.style.display = 'none'; logo.style.display = 'none'; title.style.display = 'none'; load.style.display = 'none';
    hud.style.display = '';
    relayout(); keepAwake();
    [500, 2000, 6000].forEach((ms) => setTimeout(() => { if (!kbHold) relayout(); }, ms));
  };

  // ------------------------------------------------------------------ in-game controls (same layout as the app)
  const hud = el('div', null, root);
  hud.id = 'tta-hud'; hud.style.display = 'none';
  const joy = el('div', 'pad', hud); joy.id = 'tta-joy';
  const knob = el('div', null, joy); knob.id = 'tta-knob';
  const jump = el('div', 'pad', hud); jump.id = 'tta-jump'; jump.textContent = 'JUMP';
  const cam = el('div', 'pad', hud); cam.id = 'tta-cam'; cam.textContent = 'CAM';
  const act = el('div', 'pad', hud); act.id = 'tta-act'; act.textContent = 'ACTION';
  const tasks = el('div', 'pad', hud); tasks.id = 'tta-tasks'; tasks.textContent = 'TASKS';
  const padl = el('div', 'pad', hud); padl.id = 'tta-padl'; padl.textContent = '◀';
  const padr = el('div', 'pad', hud); padr.id = 'tta-padr'; padr.textContent = '▶';
  // frames-per-second counter (the page's own animation frames, which is how often the game can draw)
  const fps = el('div', null, hud); fps.id = 'tta-fps'; fps.textContent = '-- FPS';
  (function () {
    let n = 0, t0 = performance.now();
    function tick(t) {
      n++;
      if (t - t0 >= 500) { if (hud.style.display !== 'none') fps.textContent = Math.round(n * 1000 / (t - t0)) + ' FPS'; n = 0; t0 = t; }
      requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  })();
  const st = { f: 0, b: 0, l: 0, r: 0, j: 0, a: 0, pl: 0, pr: 0 };
  const gp = { f: 0, b: 0, l: 0, r: 0, j: 0, a: 0, pl: 0, pr: 0 };     // the same controls from a game controller
  let hudVisible = false;
  function pushInput() { T.inp = [st.f | gp.f, st.b | gp.b, st.l | gp.l, st.r | gp.r, st.j | gp.j, st.a | gp.a, st.pl | gp.pl, st.pr | gp.pr].join(','); }
  // The stick is analog: the game gets its real position (-1..1, a small dead zone, then a gentle curve so small pushes walk slowly and a
  // full push runs), so walking speed and turning follow the thumb. The four on/off flags above still go too (minigames read the keys).
  const an = { touch: [0, 0], pad: [0, 0], sent: '' };
  const stickSens = () => Math.max(50, Math.min(160, parseFloat(lsGet('tta_stick', '100')) || 100));
  function shape(nx, ny) {
    const m = Math.min(1, Math.hypot(nx, ny)), DZ = 0.12;
    if (m <= DZ) return [0, 0];
    // the sensitivity bends the curve (a full push is always full speed): 100 is the usual feel, lower is gentler, higher quicker
    const k = Math.pow((m - DZ) / (1 - DZ), 1.25 * Math.pow(100 / stickSens(), 1.2)) / m;
    return [nx * k, ny * k];
  }
  function pushAnalog() {
    const a = (an.touch[0] || an.touch[1]) ? an.touch : an.pad;
    const v = Math.round(a[0] * 1000) + ',' + Math.round(a[1] * 1000);
    if (v !== an.sent) { an.sent = v; T.joy = v; if (!an.logged && v !== '0,0') { an.logged = true; try { plog('JS| analog stick first push ' + v + ' sensitivity ' + stickSens()); } catch (e) {} } }
  }
  layouts.push(() => {
    const js = 150 * sc, jb = 92 * sc, cb = 58 * sc, pb = 112 * sc;
    place(joy, Math.max(SAFE.l, 24) + 20 * sc, H - js - Math.max(SAFE.b, 16) - 24 * sc, js, js);
    const kd = js * 0.42; Object.assign(knob.style, { width: kd + 'px', height: kd + 'px', left: (js - kd) / 2 + 'px', top: (js - kd) / 2 + 'px' });
    const jx = W - jb - Math.max(SAFE.r, 24) - 30 * sc, jy = H - jb - Math.max(SAFE.b, 16) - 130 * sc;
    place(jump, jx, jy, jb, jb);
    place(cam, jx + (jb - cb) / 2, jy - cb - 16 * sc, cb, cb); cam.style.fontSize = cb * 0.26 + 'px';
    // ACTION sits lower than JUMP, nearer the thumb (players kept missing it when throwing in Field Offices), but clear of the screen's bottom edge
    place(act, jx - jb - 20 * sc, Math.min(jy + 70 * sc, H - jb - Math.max(SAFE.b, 16) - 8 * sc), jb, jb); act.style.fontSize = jb * 0.26 + 'px';
    place(fps, W / 2 - 40 * sc, Math.max(SAFE.t, 6) + 4 * sc, 80 * sc, 20 * sc); fps.style.fontSize = 13 * sc + 'px';
    const tb = 62 * sc;           // TASKS: left edge, above the stick
    place(tasks, Math.max(SAFE.l, 24) + 20 * sc + (js - tb) / 2, H - js - Math.max(SAFE.b, 16) - 24 * sc - tb - 24 * sc, tb, tb); tasks.style.fontSize = tb * 0.24 + 'px';
    const py = H - pb - Math.max(SAFE.b, 16) - 20 * sc;
    place(padl, W / 2 - pb - 14 * sc, py, pb, pb); padl.style.fontSize = pb * 0.26 + 'px';
    place(padr, W / 2 + 14 * sc, py, pb, pb); padr.style.fontSize = pb * 0.26 + 'px';
  });
  function joyUpdate(e) {
    const rc = joy.getBoundingClientRect(), cx = rc.width / 2, cy = rc.height / 2;
    let dx = e.clientX - rc.left - cx, dy = e.clientY - rc.top - cy;
    const maxr = rc.width * 0.38, len = Math.hypot(dx, dy);
    if (len > maxr) { dx = dx / len * maxr; dy = dy / len * maxr; }
    const kd = rc.width * 0.42;
    knob.style.left = cx + dx - kd / 2 + 'px'; knob.style.top = cy + dy - kd / 2 + 'px';
    const nx = dx / maxr, ny = -dy / maxr;
    an.touch = shape(nx, ny); pushAnalog();
    const f = +(ny > 0.35), b = +(ny < -0.35), l = +(nx < -0.35), r = +(nx > 0.35);
    if (f !== st.f || b !== st.b || l !== st.l || r !== st.r) { st.f = f; st.b = b; st.l = l; st.r = r; pushInput(); }
  }
  function joyReset() {
    const rc = joy.getBoundingClientRect(), kd = rc.width * 0.42;
    knob.style.left = (rc.width - kd) / 2 + 'px'; knob.style.top = (rc.height - kd) / 2 + 'px';
    st.f = st.b = st.l = st.r = 0; pushInput();
    an.touch = [0, 0]; pushAnalog();
  }
  function bindHold(node, onDown, onUp, onMove) {
    node.addEventListener('pointerdown', (e) => { e.preventDefault(); e.stopPropagation(); node.setPointerCapture(e.pointerId); node.classList.add('down'); onDown(e); });
    node.addEventListener('pointermove', (e) => { if (onMove && node.hasPointerCapture(e.pointerId)) { e.preventDefault(); onMove(e); } });
    const up = (e) => { node.classList.remove('down'); onUp(e); };
    node.addEventListener('pointerup', up); node.addEventListener('pointercancel', up); node.addEventListener('lostpointercapture', (e) => { if (node.classList.contains('down')) up(e); });
    node.addEventListener('contextmenu', (e) => e.preventDefault());
  }
  bindHold(joy, joyUpdate, () => { joy.classList.remove('down'); joyReset(); }, joyUpdate); joy.classList.remove('down');
  joy.addEventListener('pointerdown', () => joy.classList.remove('down'));
  bindHold(jump, () => { st.j = 1; pushInput(); }, () => { st.j = 0; pushInput(); });
  bindHold(cam, () => { T.camN++; }, () => {});
  bindHold(act, () => { st.a = 1; pushInput(); }, () => { st.a = 0; pushInput(); });
  // TASKS presses the game's tasks key (End): the key going down shows the task list, coming up hides it, so a tap shows it and the next tap hides it
  let tasksOn = false;
  function tasksKey(type) {
    const cv = document.querySelector('canvas.emscripten') || document;
    const k = { key: 'End', code: 'End', keyCode: 35, which: 35, bubbles: true, cancelable: true };
    try { const ev = new KeyboardEvent(type, k); ev.ttaMade = true; cv.dispatchEvent(ev); } catch (e) { plog('JS| tasks key failed ' + e); }
  }
  function tasksSet(on) { if (on === tasksOn) return; tasksOn = on; tasks.classList.toggle('on', on); tasksKey(on ? 'keydown' : 'keyup'); }
  tasks.addEventListener('click', (e) => { e.preventDefault(); gameFocus(); tasksSet(!tasksOn); });
  tasks.addEventListener('pointerdown', (e) => e.stopPropagation());
  bindHold(padl, () => { st.pl = 1; pushInput(); }, () => { st.pl = 0; pushInput(); });
  bindHold(padr, () => { st.pr = 1; pushInput(); }, () => { st.pr = 0; pushInput(); });
  // Python tells us what to show: controls, the ACTION button, the tug-of-war buttons (same rules as the app)
  let uiArgs = [0, 0, 0];
  T.setUI = function (vis, action, tug) {
    uiArgs = [vis, action, tug];
    vis = !!+vis && !touchHidden();
    if (hudVisible && !vis) { joyReset(); st.a = st.pl = st.pr = 0; pushInput(); }
    hudVisible = vis;
    if (!+uiArgs[0] || (!vis && !padUsed)) tasksSet(false);   // (a controller's Y still opens the task list with the controls hidden)
    [joy, jump, cam, tasks].forEach((n) => { n.style.display = vis ? '' : 'none'; });
    act.style.display = (vis && +action) ? '' : 'none';
    const tg = vis && +tug;
    padl.style.display = padr.style.display = tg ? '' : 'none';
  };
  [joy, jump, cam, tasks, act, padl, padr].forEach((n) => { n.style.display = 'none'; });

  // Game controller (standard layout, e.g. Android handhelds): presses the on-screen controls. Left stick or d-pad is the stick,
  // A is JUMP, B is ACTION, X is CAM, Y is TASKS, L1/R1 are the tug-of-war buttons. Only when the game would show the controls (even if
  // the player hid them), and not while typing. Like a keyboard, using one hides the on-screen controls (On-screen controls: Auto).
  let padPrev = [], padSeen = false, padUsed = false;
  requestAnimationFrame(function padPoll() {
    requestAnimationFrame(padPoll);
    let p = null;
    try { for (const x of (navigator.getGamepads ? navigator.getGamepads() : [])) if (x && x.connected) { p = x; break; } } catch (e) {}
    const on = !!p && !!+uiArgs[0] && !textOn;
    if (on && (p.buttons.some((b) => b.pressed) || p.axes.slice(0, 2).some((v) => Math.abs(v) > 0.5))) {
      if (!padUsed) { padUsed = true; plog('JS| controller in use'); applyTouchUI(); }
    }
    const btn = (i) => on && !!p.buttons[i] && (p.buttons[i].pressed || p.buttons[i].value > 0.5);
    const ax = (i) => (on && p.axes[i]) || 0;
    if (p && !padSeen) { padSeen = true; plog('JS| controller: ' + p.id + ' (' + (p.mapping || 'no mapping') + ')'); }
    const n = { f: +(btn(12) || ax(1) < -0.35), b: +(btn(13) || ax(1) > 0.35), l: +(btn(14) || ax(0) < -0.35), r: +(btn(15) || ax(0) > 0.35),
      j: +btn(0), a: +(btn(1) && !!+uiArgs[1]), pl: +(btn(4) && !!+uiArgs[2]), pr: +(btn(5) && !!+uiArgs[2]) };
    let ch = false;
    for (const k in n) if (n[k] !== gp[k]) { gp[k] = n[k]; ch = true; }
    if (ch) pushInput();
    an.pad = on ? shape(ax(0), -ax(1)) : [0, 0]; pushAnalog();
    const now = [btn(2), btn(3)];
    if (now[0] && !padPrev[0]) T.camN++;
    if (now[1] && !padPrev[1]) { gameFocus(); tasksSet(!tasksOn); }
    padPrev = now;
  });

  // ------------------------------------------------------------------ display settings (sign-in screen and in game)
  // The settings cog and the keyboard keys card are described by one spec shared with the native apps (shared/settings-spec.json,
  // served at /_ui/settings-spec.json). This is the same text, used when the spec cannot be fetched; tools/check_spec.py keeps them equal.
  const SPEC_DEFAULT = {"version":1,"about":"The one description of the settings cog and the keyboard keys card. The web app and every native app build these screens from it (served at /_ui/settings-spec.json; each app also carries this same text as a fallback). A row shows on a platform when its platforms list includes it ('web': the browser app on any device, 'desktop': the Windows, Linux and Mac apps, 'android' and 'ios': the native phone apps). Each app implements the row ids.","title":"Settings","sections":[{"id":"display","title":"Display","rows":[{"id":"window_mode","label":"Window","hint":"Full screen or a window (F11 does the same)","platforms":["desktop"],"choices":[["window","Window"],["full","Full screen"]],"default":"window"},{"id":"window_size","label":"Window size","hint":"Used while it is a window","platforms":["desktop"],"choices":[["1280x720","1280x720"],["1600x900","1600x900"],["1920x1080","1920x1080"],["2560x1440","2560x1440"]],"default":"1280x720"},{"id":"picture_quality","label":"Picture quality","hint":"Lower is smoother on slower devices","platforms":["web","android","ios"],"choices":[["2","Sharp"],["1.5","Balanced"],["1","Fast"],["0.75","Fastest"]],"default":"2"},{"id":"smooth_edges","label":"Smooth edges","hint":"Softens jagged lines; off is faster","choices":[["1","On"],["0","Off"]],"default":"1","restart_note":"Smooth edges changes when the game restarts."},{"id":"fps","label":"Speed counter","hint":"The FPS number at the top","choices":[["1","Show"],["0","Hide"]],"default":"1"},{"id":"textures","label":"Textures","hint":"Original uses authentic textures; Remastered uses upscaled textures","platforms":["web"],"choices":[["original","Original"],["remastered","Remastered"]],"default":"original","restart_note":"Texture changes take effect after restarting the game."}]},{"id":"sound","title":"Sound","rows":[{"id":"mix_others","label":"Other apps\u2019 audio","hint":"Let music from other apps keep playing. The game then follows the silent switch","platforms":["web","ios","android"],"choices":[["0","Pause"],["1","Keep playing"]],"default":"0"},{"id":"volume","type":"slider","label":"Volume","platforms":["desktop"],"min":0,"max":100,"default":"100"}]},{"id":"controls","title":"Controls","rows":[{"id":"touch_ui","label":"On-screen controls","hint":"Auto shows them for touch and hides them while using a keyboard, mouse, or controller","platforms":["web","android","ios"],"choices":[["auto","Auto"],["show","Show"],["hide","Hide"]],"default":"auto"},{"id":"pointer_mode","label":"Touch pointer","hint":"Tap: a touch clicks where it lands. Cursor: drag anywhere to move a cursor, tap to click it","platforms":["web"],"choices":[["tap","Tap"],["cursor","Cursor"]],"default":"tap"},{"id":"stick_sensitivity","type":"slider","label":"Joystick sensitivity","hint":"Low: small pushes walk slowly (finer control). High: the toon speeds up sooner","platforms":["web","ios"],"min":50,"max":160,"default":"100","left":"Gentle","right":"Quick"},{"id":"keys","type":"page","label":"Keyboard keys","platforms":["web","desktop"]}]},{"id":"notifications","title":"Notifications","rows":[{"id":"push","type":"push","platforms":["web"]}]}],"keys":{"title":"Keyboard keys","tip":"Tap an action, then press the key you want for it. The game's own keys keep working too.","waiting":"Press a key... (Esc cancels)","reset":"Use the game's keys","wasd":"Use WASD and Space","wasd_map":{"w":"fwd","s":"back","a":"left","d":"right","space":"jump"},"actions":[{"id":"fwd","label":"Walk forward","game_key":"arrow_up","web_code":"ArrowUp"},{"id":"back","label":"Walk back","game_key":"arrow_down","web_code":"ArrowDown"},{"id":"left","label":"Turn left","game_key":"arrow_left","web_code":"ArrowLeft"},{"id":"right","label":"Turn right","game_key":"arrow_right","web_code":"ArrowRight"},{"id":"jump","label":"Jump","game_key":"control","web_code":"ControlLeft"},{"id":"pie","label":"Throw pie","game_key":"delete","web_code":"Delete"},{"id":"tasks","label":"Tasks","game_key":"end","web_code":"End"},{"id":"gags","label":"Gags","game_key":"home","web_code":"Home"},{"id":"map","label":"Map","game_key":"alt","web_code":"AltLeft"},{"id":"book","label":"Shticker Book","game_key":"f8","web_code":"F8"},{"id":"friends","label":"Friends","game_key":"f7","web_code":"F7"},{"id":"camera","label":"Camera view","game_key":"tab","web_code":"Tab"}]}};
  let SPEC = SPEC_DEFAULT;
  const lsGet = (k, d) => { try { const v = LS.getItem(k); return v == null ? d : v; } catch (e) { return d; } };
  const lsSet = (k, v) => { try { LS.setItem(k, v); } catch (e) {} };
  function applyFps() { fps.style.display = lsGet('tta_fps', '1') === '0' ? 'none' : ''; }
  applyFps();
  const setWrap = el('div', null, root); setWrap.id = 'tta-set'; setWrap.style.display = 'none';
  const mine = (r) => !r.platforms || r.platforms.indexOf('web') >= 0;
  let setNote = null, setRestart = null;
  const BEHAVIOUR = {        // row id -> [current value, what choosing a value does]; a row this app has no behaviour for is left out
    picture_quality: [() => String(lsGet('tta_res', '') || '2'), (v) => { lsSet('tta_res', v); relayout(); }],
    smooth_edges: [() => T.aa, (v) => { lsSet('tta_aa', v); lsSet('tta_aa_user_choice', '1'); if (setNote) setNote.style.visibility = v === T.aa ? 'hidden' : ''; if (setRestart) setRestart.style.display = v === T.aa ? 'none' : ''; }],
    fps: [() => lsGet('tta_fps', '1'), (v) => { lsSet('tta_fps', v); applyFps(); }],
    textures: [() => lsGet('tta_textures', 'original'), (v) => {
      lsSet('tta_textures', v);
      const active = lsGet('tta_textures_active', 'original');
      if (setNote) setNote.style.visibility = (v === active) ? 'hidden' : '';
      if (setRestart) setRestart.style.display = (v === active) ? 'none' : '';
    }],
    mix_others: [() => lsGet('tta_mix', '0'), (v) => { lsSet('tta_mix', v); try { if (window.ttaAudio && window.ttaAudio.mixOthers) window.ttaAudio.mixOthers(v === '1'); } catch (e) {} }],
    touch_ui: [() => lsGet('tta_touch', 'auto'), (v) => { lsSet('tta_touch', v); applyTouchUI(); }],
    stick_sensitivity: [() => String(Math.round(stickSens())), (v) => { lsSet('tta_stick', v); try { plog('JS| stick sensitivity set to ' + v); } catch (e) {} }],
    pointer_mode: [() => lsGet('tta_pointer', 'tap'), (v) => { lsSet('tta_pointer', v); if (window.ttaPointerRefresh) window.ttaPointerRefresh(); }],
  };
  function showSettings() {
    setWrap.innerHTML = ''; setWrap.style.display = '';
    const card = el('div', 'card', setWrap);
    const h = el('h2', null, card); h.textContent = SPEC.title || 'Settings';
    const sec = (t) => { const x = el('h3', 'sec', card); x.textContent = t; };
    const row = (label, hint, choices, current, onPick) => {
      const r = el('div', 'row', card);
      const l = el('div', 'lbl', r); l.textContent = label;
      if (hint) { const sm = el('small', null, l); sm.textContent = hint; }
      const g = el('div', 'seg', r);
      choices.forEach(([val, txt]) => {
        const b = el('button', val === current ? 'sel' : '', g); b.textContent = txt;
        b.addEventListener('click', () => { [...g.children].forEach((c) => c.classList.remove('sel')); b.classList.add('sel'); onPick(val); });
      });
    };
    const slider = (r, b) => {
      const w = el('div', 'row slide', card);
      const l = el('div', 'lbl', w); l.textContent = r.label;
      if (r.hint) { const sm = el('small', null, l); sm.textContent = r.hint; }
      const g = el('div', 'sl', w);
      const lo = el('span', null, g); lo.textContent = r.left || '';
      const inp = el('input', null, g); inp.type = 'range'; inp.min = r.min; inp.max = r.max; inp.step = 5; inp.value = b[0]();
      const hi = el('span', null, g); hi.textContent = r.right || '';
      inp.addEventListener('input', () => b[1](String(inp.value)));
    };
    let note = null, restart = null;
    (SPEC.sections || []).forEach((sc) => {
      const rows = (sc.rows || []).filter(mine);
      if (!rows.length) return;
      sec(sc.title);
      rows.forEach((r) => {
        if (r.type === 'push') { pushRow(card); return; }
        if (r.type === 'page') {
          if (r.id === 'keys') { const keysBtn = el('button', 'act', card); keysBtn.textContent = r.label; keysBtn.addEventListener('click', showKeys); }
          return;
        }
        const b = BEHAVIOUR[r.id];
        if (!b) return;
        if (r.type === 'slider') { slider(r, b); return; }
        row(r.label, r.hint, r.choices, b[0](), b[1]);
        if (r.restart_note) { note = setNote = el('div', 'note', card); note.style.visibility = 'hidden'; note.textContent = r.restart_note; }
      });
    });
    restart = setRestart = el('button', 'act', card); restart.textContent = 'Restart game now'; restart.style.display = 'none';
    restart.addEventListener('click', () => location.reload());
    const done = el('button', 'act done', card); done.textContent = 'Done';
    done.addEventListener('click', () => { setWrap.style.display = 'none'; setWrap.innerHTML = ''; });
  }
  // ---- the sticker book's Device page: the game draws the rows, the page keeps the values and does what a choice does
  T.devRows = function () {
    const out = [];
    (SPEC.sections || []).forEach((sc) => (sc.rows || []).filter(mine).forEach((r) => {
      if (r.type === 'push' || r.type === 'page') out.push({ section: sc.title, id: r.id, type: r.type, label: r.label || (r.type === 'push' ? 'Event notifications' : r.id), hint: r.hint || '' });
      else if (BEHAVIOUR[r.id] && r.type === 'slider') out.push({ section: sc.title, id: r.id, type: 'slider', label: r.label, hint: r.hint || '', min: r.min, max: r.max, left: r.left || '', right: r.right || '' });
      else if (BEHAVIOUR[r.id]) out.push({ section: sc.title, id: r.id, type: 'choice', label: r.label, hint: r.hint || '', choices: r.choices, restart: r.restart_note || '' });
    }));
    return JSON.stringify(out);
  };
  T.devGet = (id) => (BEHAVIOUR[id] ? String(BEHAVIOUR[id][0]()) : '');
  T.devSet = (id, v) => { if (BEHAVIOUR[id]) BEHAVIOUR[id][1](String(v)); };
  T.devOpen = (what) => { if (what === 'keys') { keysFromBook = true; showKeys(); } else showNotifications(); };
  T.devRestart = () => { plog('JS| device restart pressed'); location.reload(); };
  let keysFromBook = false;
  function showNotifications() {
    setWrap.innerHTML = ''; setWrap.style.display = '';
    const card = el('div', 'card', setWrap);
    const h = el('h2', null, card); h.textContent = 'Notifications';
    pushRow(card);
    const done = el('button', 'act done', card); done.textContent = 'Done';
    done.addEventListener('click', () => { setWrap.style.display = 'none'; setWrap.innerHTML = ''; });
  }
  // ---- event notifications (Web Push): the server sends them from the mod panel; a phone needs the game on its Home Screen (iOS 16.4+)
  const PUSH_OK = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
  const IOS = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const STANDALONE = (window.matchMedia && matchMedia('(display-mode: standalone)').matches) || navigator.standalone === true;
  // [key, name, what a notification of that kind looks like]; the keys match the mod panel's Events tab
  const PUSH_TOPICS = [
    ['invasions', 'Cog invasions', 'A Cog invasion is taking over Toontown. Join the fight!'],
    ['bingo', 'Bingo night', 'Bingo night starts in 10 minutes in Toon Valley.'],
    ['beans', 'Extra beans', 'Double jellybeans for the next hour.'],
    ['events', 'Events', 'Silly Surge is on! Parties, holidays and special events.'],
    ['players', 'Player count', '42 toons are playing right now. Come say hi!'],
  ];
  const topicsGet = () => { try { const v = JSON.parse(lsGet('tta_push_topics', 'null')); if (Array.isArray(v)) return v.filter((k) => PUSH_TOPICS.some((t) => t[0] === k)); } catch (e) {} return PUSH_TOPICS.map((t) => t[0]); };
  const topicsSet = (a) => lsSet('tta_push_topics', JSON.stringify(a));
  const keyBytes = (b64) => { const p = (b64 + '='.repeat((4 - b64.length % 4) % 4)).replace(/-/g, '+').replace(/_/g, '/'); return Uint8Array.from(atob(p), (c) => c.charCodeAt(0)); };
  async function pushSub() { const reg = await navigator.serviceWorker.getRegistration(); return reg ? reg.pushManager.getSubscription() : null; }
  async function pushTell(sub) {   // tells the server this phone's address and which kinds it wants
    const r = await fetch('/push/subscribe', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ subscription: sub.toJSON(), topics: topicsGet() }) });
    return r.ok;
  }
  async function pushOn() {      // '' when it worked, otherwise what to tell the player
    const reg = await navigator.serviceWorker.register('sw.js'); await navigator.serviceWorker.ready;
    if ((await Notification.requestPermission()) !== 'granted') return 'Notifications are blocked. Allow them for this app in the phone\u2019s Settings, then try again.';
    const k = await fetch('/push/key'); if (!k.ok) return 'Notifications are not available right now.';
    const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes((await k.json()).key) });
    if (!(await pushTell(sub))) { try { await sub.unsubscribe(); } catch (e) {} return 'Could not turn notifications on. Try again later.'; }
    return '';
  }
  async function pushOff() {
    const sub = await pushSub(); if (!sub) return;
    try { await fetch('/push/unsubscribe', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ endpoint: sub.endpoint }) }); } catch (e) {}
    await sub.unsubscribe();
  }
  const pushSeg = (parent, label, hint, choices, current, onPick) => {
    const r = el('div', 'row', parent), l = el('div', 'lbl', r); l.textContent = label;
    if (hint) { const sm = el('small', null, l); sm.textContent = hint; }
    const g = el('div', 'seg', r);
    choices.forEach(([val, txt]) => {
      const bt = el('button', val === current ? 'sel' : '', g); bt.textContent = txt;
      bt.addEventListener('click', () => { [...g.children].forEach((c) => c.classList.remove('sel')); bt.classList.add('sel'); onPick(val); });
    });
  };
  // the settings gear: one switch for notifications, and under it one for each kind
  function pushRow(card) {
    if (!PUSH_OK || (IOS && !STANDALONE)) {
      const r = el('div', 'row', card), l = el('div', 'lbl', r); l.textContent = 'Event notifications';
      const sm = el('small', null, l);
      sm.textContent = IOS && !STANDALONE ? 'To get them, add the game to your Home Screen (Share, then Add to Home Screen) and open it from there' : 'This browser cannot show notifications';
      return;
    }
    const box = el('div', null, card), note = el('div', 'note', card); note.style.visibility = 'hidden';
    const draw = (on) => {
      box.innerHTML = '';
      pushSeg(box, 'Event notifications', 'Hear about what is happening, even when the game is closed', [['0', 'Off'], ['1', 'On']], on ? '1' : '0', async (v) => {
        note.style.visibility = 'hidden';
        try { const msg = v === '1' ? await pushOn() : (await pushOff(), ''); if (msg) { note.textContent = msg; note.style.visibility = ''; draw(false); } else draw(v === '1'); }
        catch (e) { note.textContent = 'That did not work. Try again.'; note.style.visibility = ''; draw(on); }
      });
      if (!on) return;
      PUSH_TOPICS.forEach(([key, name, eg]) => {
        pushSeg(box, name, eg, [['0', 'Off'], ['1', 'On']], topicsGet().includes(key) ? '1' : '0', async (v) => {
          const now = topicsGet().filter((k) => k !== key); if (v === '1') now.push(key); topicsSet(now);
          try { const sub = await pushSub(); if (sub) await pushTell(sub); } catch (e) {}
        });
      });
    };
    draw(false);
    pushSub().then((sub) => { if (sub && Notification.permission === 'granted') draw(true); }).catch(() => {});
  }
  // when the game opens: ask once, with examples of what would be sent
  function showPushAsk() {
    setWrap.innerHTML = ''; setWrap.style.display = '';
    const card = el('div', 'card', setWrap);
    const h = el('h2', null, card); h.textContent = 'Stay in the loop';
    const tip = el('div', 'tip', card); tip.textContent = 'Get a notification when something fun is happening in Toontown, even when the game is closed. You will hear about things like:';
    PUSH_TOPICS.forEach(([, name, eg]) => {
      const r = el('div', 'row', card), l = el('div', 'lbl', r); l.textContent = name;
      const sm = el('small', null, l); sm.textContent = '\u201C' + eg + '\u201D';
    });
    const note = el('div', 'note', card); note.style.visibility = 'hidden';
    const close = () => { lsSet('tta_push_ask', '1'); setWrap.style.display = 'none'; setWrap.innerHTML = ''; };
    const yes = el('button', 'act', card); yes.textContent = 'Turn on notifications';
    yes.addEventListener('click', async () => {
      yes.disabled = true; note.style.visibility = 'hidden';
      try { topicsSet(PUSH_TOPICS.map((t) => t[0])); const msg = await pushOn(); if (msg) { note.textContent = msg; note.style.visibility = ''; yes.disabled = false; } else close(); }
      catch (e) { note.textContent = 'That did not work. Try again.'; note.style.visibility = ''; yes.disabled = false; }
    });
    const no = el('button', 'act done', card); no.textContent = 'Not now'; no.addEventListener('click', close);
    const fine = el('div', 'tip', card); fine.style.paddingTop = '8px'; fine.textContent = 'Pick which kinds you want, or turn them off, any time under the \u2699 settings.';
  }
  if (PUSH_OK && !(IOS && !STANDALONE) && lsGet('tta_push_ask', '') !== '1') {
    setTimeout(async () => {
      try { if (Notification.permission !== 'default' || setWrap.style.display !== 'none' || (await pushSub())) return; } catch (e) { return; }
      showPushAsk();
    }, 2500);
  }
  const gearBtn = el('button', 'tta-gear on', hud); gearBtn.textContent = '⚙';
  gearBtn.addEventListener('pointerdown', (e) => e.stopPropagation());
  gearBtn.addEventListener('click', (e) => { e.preventDefault(); showSettings(); });
  gearBtn.style.setProperty('display', 'none', 'important');       // the settings live in the sticker book now (Options, Device)
  layouts.push(() => place(gearBtn, W / 2 + 46 * sc, Math.max(SAFE.t, 6), 30 * sc, 28 * sc));
  const dsp = pill('Settings', null, null, login, 'light');
  dsp.addEventListener('click', showSettings);
  layouts.push(() => { const ph = 30 * sc; place(dsp, W - 126 * sc - 14 - SAFE.r, Math.max(SAFE.t, 6) + 8 + ph + 8, 126 * sc, ph); dsp.style.visibility = kbMode ? 'hidden' : ''; });

  // ------------------------------------------------------------------ typed chat: the game's own text box shows the text live;
  // this invisible input only brings up the keyboard and passes every keystroke to the game
  const tin = document.createElement('input');
  tin.id = 'tta-textin'; tin.type = 'text'; tin.maxLength = 120; tin.autocomplete = 'off'; tin.autocapitalize = 'sentences'; tin.autocorrect = 'off';
  tin.setAttribute('enterkeyhint', 'send');
  root.appendChild(tin);
  let textOn = false, askAt = 0;
  // The game server rejects chat that is not plain text (an iPhone keyboard turns ' and " into curly quotes, adds emoji, long dashes...)
  // and throws the player out with error 127. Keep typed chat to plain characters.
  function plainChat(t) {
    return String(t).replace(/[\u2018\u2019\u201A\u201B\u2032]/g, "'").replace(/[\u201C\u201D\u201E\u2033]/g, '"')
      .replace(/[\u2013\u2014\u2212]/g, '-').replace(/\u2026/g, '...').replace(/[\u00A0\u2007\u202F]/g, ' ')
      .replace(/[^\x20-\x7E]/g, '');
  }
  tin.addEventListener('input', () => { const c = plainChat(tin.value); if (c !== tin.value) tin.value = c; T.txtVal = c; T.txtIn++; });
  // a moment's wait before sending: when Return is pressed the keyboard may still be finishing an auto-correction of the last word
  onEnter(tin, () => setTimeout(() => { T.txtVal = plainChat(tin.value); T.txtSub++; tin.blur(); }, 90));
  tin.addEventListener('focus', () => { kbHold = true; plog('JS| tin focus; inner ' + innerWidth + 'x' + innerHeight + ' vv ' + (window.visualViewport ? visualViewport.width + 'x' + visualViewport.height : '-')); });
  // After a chat is sent the invisible input gives up focus and nothing is left focused, so a hardware keyboard (iPad Magic Keyboard,
  // a desktop) stops reaching the game. Hand the focus back to the game's canvas.
  function gameFocus() {
    const cv = document.querySelector('canvas.emscripten'); if (!cv) return;
    // Make the canvas a reliable keyboard target after a browser/tab switch.
    // Pygbag's template gives it a positive tabindex, which may be skipped in
    // some embedded browser focus-return paths.
    cv.tabIndex = 0;
    try { cv.focus({ preventScroll: true }); } catch (e) {}
  }
  tin.addEventListener('blur', () => {
    kbHold = false; plog('JS| tin blur'); setTimeout(() => { window.scrollTo(0, 0); relayout(); }, 250);
    setTimeout(() => { const a = document.activeElement; if (!a || a === document.body || a === tin) gameFocus(); }, 0);
  });
  // a key press while nothing is focused: focus the game so the following keys reach it
  document.addEventListener('keydown', () => { if (focusIsStale() && hud.style.display !== 'none' && !typing()) gameFocus(); }, true);
  // iOS only opens the keyboard from a real tap, and the game answers a tap a moment later. So a tap on the typed-chat button
  // (top-left corner) opens the keyboard right away; if the game then does not open a text box, it is closed again.
  function kbTap(e) {
    if (hud.style.display === 'none' || document.activeElement === tin) return;
    const p = (e.changedTouches && e.changedTouches[0]) || e;
    // only the blue typed-chat button (the game puts it at 0.135 of the screen height from the left, the green Speed Chat button
    // at 0.36 and beyond): the keyboard opens at once, and closes again if the game opens no text box
    // (the game keeps its buttons inside the safe area, so the notch side moves them over by that much)
    const inCorner = p.clientX < SAFE.l + H * 0.13 && p.clientY < SAFE.t + H * 0.14;
    // the Type a Name button on the name screen: the game tells us where it is (T.typeBtn, as fractions of the window)
    let onTypeBtn = false;
    const nb = String(T.typeBtn || '').split(',').map(Number);
    const cv = document.querySelector('canvas.emscripten');
    if (nb.length === 2 && isFinite(nb[0]) && isFinite(nb[1]) && cv) {
      const r = cv.getBoundingClientRect();
      onTypeBtn = Math.hypot(p.clientX - (r.left + nb[0] * r.width), p.clientY - (r.top + nb[1] * r.height)) < r.height * 0.1;
    }
    if (!textOn && !inCorner && !onTypeBtn) return;
    try { tin.focus({ preventScroll: true }); } catch (err) {}
    askAt = Date.now();
    setTimeout(() => { if (!textOn && Date.now() - askAt >= 1400) tin.blur(); }, 1500);
  }
  let lastTap = 0;
  const kbOnce = (e) => {
    // in Cursor mode the finger is a trackpad: the click (and the keyboard it may need) happens where the glove is, handled there
    if (e.pointerType !== 'mouse' && lsGet('tta_pointer', 'tap') === 'cursor' && e.target && e.target.classList && e.target.classList.contains('emscripten')) return;
    if (Date.now() - lastTap < 400) return; lastTap = Date.now(); plog('JS| tap ' + e.type + ' at ' + Math.round((e.changedTouches ? e.changedTouches[0] : e).clientX) + ',' + Math.round((e.changedTouches ? e.changedTouches[0] : e).clientY) + ' W=' + W + ' H=' + H); kbTap(e); armChain(); };
  // The game opens its text box a moment AFTER the tap (it answers the tap, then the page hears of it), by which time iOS no longer
  // counts the tap as a user action and refuses to show the keyboard. iOS lets a timer started inside the tap carry the tap forward for
  // about a second, so keep a quick timer running for that long after each tap and open the keyboard from it as soon as the game's box opens.
  let chainUntil = 0, chainOn = false;
  function armChain() {
    chainUntil = Date.now() + 900;
    if (chainOn) return;
    chainOn = true;
    (function tick() {
      if (textOn && document.activeElement !== tin) { try { tin.focus({ preventScroll: true }); } catch (e) {} }
      if (Date.now() < chainUntil && document.activeElement !== tin) setTimeout(tick, 30); else chainOn = false;
    })();
  }
  document.addEventListener('touchend', kbOnce, true);
  document.addEventListener('pointerup', kbOnce, true);
  addEventListener('resize', () => plog('JS| resize inner ' + innerWidth + 'x' + innerHeight + ' kbHold=' + kbHold));
  // iOS only opens the keyboard from a real tap, and a text box the game opens by itself (the code box) cannot ask for one. If the
  // keyboard did not open, show a button that can.
  const kbIsOpen = () => { try { return !!window.visualViewport && window.innerHeight - window.visualViewport.height > 100; } catch (e) { return false; } };
  const kbPill = el('button', 'tta-kbpill', hud); kbPill.textContent = '⌨ Tap to type'; kbPill.style.display = 'none';
  kbPill.addEventListener('pointerdown', (e) => e.stopPropagation());
  kbPill.addEventListener('click', (e) => { e.preventDefault(); try { tin.blur(); tin.focus({ preventScroll: true }); } catch (err) {} kbPill.style.display = 'none'; });   // blur first: a field iOS already calls focused shows no keyboard until it is focused again from a tap
  tin.addEventListener('focus', () => { setTimeout(() => { if (kbIsOpen()) kbPill.style.display = 'none'; }, 400); });
  T.setText = function (on, val) {
    textOn = !!+on; plog('JS| setText ' + on);
    if (textOn) {
      tin.value = val || ''; try { tin.focus({ preventScroll: true }); } catch (e) {}
      // iOS calls the field focused even when it refused to show the keyboard (the focus did not come from a tap), so "focused" proves nothing: the keyboard is
      // open only if the visible part of the page has shrunk. If it did not open, show the button.
      setTimeout(() => { let hw = false; try { hw = kbUsed; } catch (e) {} if (textOn && !kbIsOpen() && !hw) kbPill.style.display = 'block'; }, 450);
    } else { tin.blur(); kbPill.style.display = 'none'; }
  };

  // ------------------------------------------------------------------ hardware keyboard (iPad Magic Keyboard, a desktop): the touch controls hide while
  // one is used, and keys can be remapped. A page cannot ask what keyboard is attached, so a real key press outside typed chat is the sign;
  // a finger on the screen after a quiet spell brings the controls back. A remapped key is swallowed and the game's own key is sent instead,
  // so the game's keys keep working too.
  let GAME_KEYS = [], actTarget = {};        // GAME_KEYS: [id, label, the game's key code], from the spec's key actions
  function applyKeySpec() {
    GAME_KEYS = ((SPEC.keys && SPEC.keys.actions) || []).map((a) => [a.id, a.label, a.web_code]);
    actTarget = {}; GAME_KEYS.forEach(([id, , code]) => { actTarget[id] = code; });
  }
  applyKeySpec();
  (async () => {            // the newest spec from the server, if it can be reached (the embedded copy is used until then and if it cannot)
    try {
      const r = await fetch(prefs.base + '/_ui/settings-spec.json', { cache: 'no-cache' });
      if (!r.ok) return;
      const j = await r.json();
      if (j && j.version === 1 && Array.isArray(j.sections) && j.keys && Array.isArray(j.keys.actions)) { SPEC = j; applyKeySpec(); }
    } catch (e) {}
  })();
  const KEYINFO = { ArrowUp: ['ArrowUp', 38], ArrowDown: ['ArrowDown', 40], ArrowLeft: ['ArrowLeft', 37], ArrowRight: ['ArrowRight', 39],
    ControlLeft: ['Control', 17], Delete: ['Delete', 46], End: ['End', 35], Home: ['Home', 36], AltLeft: ['Alt', 18], F8: ['F8', 119], F7: ['F7', 118], Tab: ['Tab', 9] };
  let keyMap = {};           // the player's key (event code) -> action id
  try { keyMap = JSON.parse(lsGet('tta_keys', '{}')) || {}; } catch (e) { keyMap = {}; }
  const saveKeys = () => lsSet('tta_keys', JSON.stringify(keyMap));
  let kbUsed = false, mouseUsed = false, keyCapture = null;
  const heldKeys = {};       // the player's key -> the game key sent for it, until it comes up
  let inputRestorePending = false; // one key receipt after returning focus, for diagnosing embedded-wrapper input loss
  function touchHidden() { const m = lsGet('tta_touch', 'auto'); return m === 'hide' || (m === 'auto' && (kbUsed || mouseUsed || padUsed)); }
  function applyTouchUI() { T.setUI(uiArgs[0], uiArgs[1], uiArgs[2]); }
  function keyName(code) {
    const named = { ArrowUp: '↑', ArrowDown: '↓', ArrowLeft: '←', ArrowRight: '→', ControlLeft: 'Ctrl', ControlRight: 'Right Ctrl', AltLeft: 'Alt/Option',
      AltRight: 'Right Alt', ShiftLeft: 'Shift', ShiftRight: 'Right Shift', MetaLeft: 'Cmd', MetaRight: 'Right Cmd', Space: 'Space', Backspace: 'Backspace' };
    if (named[code]) return named[code];
    return String(code).replace(/^Key/, '').replace(/^Digit/, '').replace(/^Numpad/, 'Num ');
  }
  // typing: the game has a text box open, or a page text field (sign-in, settings) has the focus. The hidden chat input (tin) can keep
  // the focus after a message is sent, so it only counts while the game's text box is open (textOn).
  function typing() {
    const a = document.activeElement;
    return textOn || !!(a && a !== tin && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA' || a.tagName === 'SELECT' || a.isContentEditable || a.getAttribute('role') === 'textbox'));
  }
  function sendKey(type, code, e) {
    if (!KEYINFO[code]) return;
    const [key, kc] = KEYINFO[code];
    const down = type === 'keydown';
    const ev = new KeyboardEvent(type, { key, code, keyCode: kc, which: kc, repeat: !!(e && e.repeat), bubbles: true, cancelable: true,
      ctrlKey: (code === 'ControlLeft' && down) || !!(e && e.ctrlKey), altKey: (code === 'AltLeft' && down) || !!(e && e.altKey), shiftKey: !!(e && e.shiftKey) });
    try { Object.defineProperty(ev, 'keyCode', { get: () => kc }); Object.defineProperty(ev, 'which', { get: () => kc }); } catch (err) {}
    ev.ttaMade = true;
    const cv = document.querySelector('canvas.emscripten') || document;
    try { cv.dispatchEvent(ev); } catch (err) { plog('JS| key send failed ' + err); }
  }
  function onKey(e) {
    if (e.ttaMade || !e.isTrusted) return;   // only a real keyboard counts (the TASKS button sends its own End key)
    if (inputRestorePending && e.type === 'keydown') {
      inputRestorePending = false;
      plog('JS| restored keyboard input observed (' + e.code + ')');
    }
    if (keyCapture) { e.preventDefault(); e.stopImmediatePropagation(); if (e.type === 'keydown') keyCapture(e); return; }
    if (hud.style.display === 'none' || typing()) return;
    if (e.type === 'keydown' && e.key !== 'Meta') {
      if (!kbUsed) { kbUsed = true; plog('JS| keyboard in use (' + e.code + ')'); applyTouchUI(); }
    }
    const id = keyMap[e.code];
    if (!id || !actTarget[id]) return;
    e.preventDefault(); e.stopImmediatePropagation();
    const a = document.activeElement;
    if (a === tin) tin.blur();          // (its blur hands the focus back to the game)
    else if (!a || a === document.body) gameFocus();
    if (e.type === 'keydown') { heldKeys[e.code] = actTarget[id]; sendKey('keydown', actTarget[id], e); }
    else { const t = heldKeys[e.code] || actTarget[id]; delete heldKeys[e.code]; sendKey('keyup', t, e); }
  }
  addEventListener('keydown', onKey, true); addEventListener('keyup', onKey, true);
  // The game takes typed letters from keypress, which a cancelled keydown should already stop; some browsers send it anyway.
  // A remapped key must never type its letter (that opens typed chat).
  addEventListener('keypress', (e) => {
    if (e.ttaMade || keyCapture || typing()) return;
    if ((e.code && keyMap[e.code]) || (!e.code && Object.keys(heldKeys).some((c) => c === 'Key' + String(e.key).toUpperCase()))) {
      e.preventDefault(); e.stopImmediatePropagation();
    }
  }, true);
  // switching away with a remapped key held: let it go in the game too
  // Also let go of the movement keys: a key held while switching away (Alt+Tab, another tab) never sends its key-up to the game, which then
  // thinks it is still held or has lost the keyboard, and the toon cannot move when the player comes back.
  const MOVE_KEYS = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'ControlLeft', 'AltLeft'];
  function releaseAll() {
    Object.keys(heldKeys).forEach((c) => { sendKey('keyup', heldKeys[c]); delete heldKeys[c]; });
    MOVE_KEYS.forEach((c) => sendKey('keyup', c));
  }
  // The invisible chat input can remain active after a window/tab switch even when chat is closed.
  // Treat it like an unfocused page so regular game keys reach the canvas again.
  function focusIsStale() { const a = document.activeElement; return !a || a === document.body || a === tin; }
  function regainGame(reason) {
    if (hud.style.display === 'none') return;
    if (typing()) { plog('JS| input restore deferred while typing after ' + reason); return; }
    releaseAll();
    if (keyCapture) { keyCapture = null; plog('JS| cleared key capture after ' + reason); }
    inputRestorePending = true;
    const cv = document.querySelector('canvas.emscripten');
    const active = document.activeElement;
    // Browsers can leave a wrapper div or control active after returning to the app. Clear stale focus, then refocus Panda's canvas.
    try { if (active && active !== document.body && active !== document.documentElement && active.blur) active.blur(); } catch (e) {}
    try { if (tin && document.activeElement === tin) tin.blur(); } catch (e) {}
    setTimeout(() => {
      if (hud.style.display !== 'none' && !typing()) {
        gameFocus();
        plog('JS| game input restored after ' + reason);
      }
    }, 0);
  }
  // Touch devices cannot be re-focused from script after a swipe-out/tab-out: only a real
  // gesture is trusted. Offer one on return; the click/tap also reattaches the WebSocket
  // input path. Desktop keeps the automatic focus restore below.
  const resumePad = el('div', 'tta-resume', hud);
  resumePad.textContent = 'Tap to resume';
  resumePad.style.cssText = 'position:fixed;inset:0;display:none;align-items:center;justify-content:center;' +
    'z-index:2147483647;background:rgba(0,0,0,.45);color:#fff;font-size:26px;font-weight:800;' +
    '-webkit-user-select:none;user-select:none;touch-action:none;';
  resumePad.addEventListener('pointerdown', (e) => {
    e.preventDefault(); e.stopPropagation();
    resumePad.style.display = 'none';
    try { window.focus(); } catch (err) {}
    regainGame('resume tap');
    const cv = document.querySelector('canvas.emscripten');
    if (cv) { cv.tabIndex = 0; try { cv.focus({ preventScroll: true }); } catch (err) {} }
    plog('JS| resume tap accepted');
  });
  function showResumePad(reason) {
    if (!touchScreen || hud.style.display === 'none' || typing()) return;
    resumePad.style.display = 'flex';
    plog('JS| resume prompt shown after ' + reason);
  }
  T.recoverInput = (reason) => regainGame(reason || 'reconnect');
  addEventListener('blur', () => { releaseAll(); if (keyCapture) keyCapture = null; });
  // A browser may preserve the canvas as active while the native window has lost its keyboard focus.
  // Blur and refocus it after returning so Panda's input device is reattached too.
  function recoverAfterReturn(reason) {
    try { window.focus(); } catch (err) {}
    regainGame(reason);
    // Re-focus the canvas unconditionally: after a tab/window switch the canvas can
    // still be document.activeElement while the browser's key events go somewhere else.
    const cv = document.querySelector('canvas.emscripten');
    if (cv) { cv.tabIndex = 0; try { cv.focus({ preventScroll: true }); } catch (err) {} }
    const a = document.activeElement;
    plog('JS| return state active=' + (a ? a.tagName + (a.id ? '#' + a.id : '') : 'none') +
         ' typing=' + typing() + ' hud=' + hud.style.display +
         ' webnet=' + (window.webnet ? window.webnet.state : '?') +
         ' focus=' + (document.hasFocus ? document.hasFocus() : '?'));
    showResumePad(reason);
    // A backgrounded tab can lose its WebSocket; the server then boots the session
    // (heartbeat timeout) and leaves the game in a lost-connection state where keys
    // are ignored. A clean reload reconnects and restores movement reliably.
    const wn = window.webnet;
    if (wn && wn.state === 'closed' && hud.style.display !== 'none') {
      plog('JS| auto reload after connection loss (' + reason + ')');
      setTimeout(() => location.reload(), 200);
    }
  }
  addEventListener('focus', () => setTimeout(() => recoverAfterReturn('window focus'), 50));
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { releaseAll(); if (keyCapture) keyCapture = null; }
    else setTimeout(() => recoverAfterReturn('tab return'), 50);
  });
  addEventListener('pageshow', () => setTimeout(() => recoverAfterReturn('page show'), 50));
  addEventListener('pointerdown', (e) => {
    const cv = document.querySelector('canvas.emscripten');
    if (e.isTrusted && cv && (e.target === cv || cv.contains(e.target))) {
      if (e.pointerType === 'mouse' && e.button === 0) T.mc = (T.mc + 1) >>> 0;
      // A real click/tap on the game is the most reliable focus gesture after
      // returning from another tab or app, even if the browser left a stale
      // canvas/wrapper as document.activeElement. Focusing the top-level page
      // from this user gesture also helps native wrappers hand keyboard focus
      // back to their embedded game surface.
      if (!typing()) {
        try { window.focus(); } catch (err) {}
        regainGame('game pointer');
      }
    }
    if (e.pointerType === 'mouse' && !mouseUsed) { mouseUsed = true; plog('JS| mouse in use'); applyTouchUI(); }
    if (e.pointerType === 'touch' && (kbUsed || mouseUsed || padUsed)) { kbUsed = mouseUsed = padUsed = false; plog('JS| touch in use: controls back'); applyTouchUI(); }
  }, true);
  function wasdMap() {        // the spec names keys the way the native apps do ('w', 'space'); the page uses event codes ('KeyW', 'Space')
    const out = {};
    Object.entries((SPEC.keys && SPEC.keys.wasd_map) || {}).forEach(([k, id]) => { out[k.length === 1 ? 'Key' + k.toUpperCase() : k === 'space' ? 'Space' : k] = id; });
    return out;
  }
  function showKeys() {
    keyCapture = null;
    setWrap.innerHTML = ''; setWrap.style.display = '';
    const card = el('div', 'card', setWrap);
    const h = el('h2', null, card); h.textContent = SPEC.keys.title || 'Keyboard keys';
    const tip = el('div', 'tip', card); tip.textContent = SPEC.keys.tip || '';
    GAME_KEYS.forEach(([id, label, code]) => {
      const r = el('div', 'row', card);
      const l = el('div', 'lbl', r); l.textContent = label;
      const sm = el('small', null, l); sm.textContent = 'Game key: ' + keyName(code);
      const g = el('div', 'seg', r);
      const b = el('button', null, g);
      const mine = Object.keys(keyMap).filter((c) => keyMap[c] === id);
      b.textContent = mine.length ? mine.map(keyName).join(', ') : keyName(code);
      if (mine.length) b.classList.add('sel');
      b.addEventListener('click', () => {
        [...card.querySelectorAll('.seg button.wait')].forEach((x) => x.classList.remove('wait'));
        b.classList.add('wait'); b.textContent = SPEC.keys.waiting || 'Press a key... (Esc cancels)';
        keyCapture = (e) => {
          keyCapture = null;
          if (e.code && e.code !== 'Escape') {
            Object.keys(keyMap).forEach((c) => { if (keyMap[c] === id) delete keyMap[c]; });
            if (e.code !== code) keyMap[e.code] = id;     // the game's own key needs no remap
            saveKeys(); plog('JS| key ' + e.code + ' -> ' + id);
          }
          showKeys();
        };
      });
    });
    const reset = el('button', 'act', card); reset.textContent = SPEC.keys.reset || 'Use the game\'s keys';
    reset.addEventListener('click', () => { keyMap = {}; saveKeys(); showKeys(); });
    const wasd = el('button', 'act', card); wasd.textContent = SPEC.keys.wasd || 'Use WASD and Space';
    wasd.addEventListener('click', () => { keyMap = wasdMap(); saveKeys(); showKeys(); });
    const back = el('button', 'act done', card); back.textContent = 'Back';
    back.addEventListener('click', () => { keyCapture = null; if (keysFromBook) { keysFromBook = false; setWrap.style.display = 'none'; setWrap.innerHTML = ''; } else showSettings(); });
  }

  // ------------------------------------------------------------------ portrait: ask for landscape (iOS has no way to lock it)
  const rot = el('div', null, root);
  rot.id = 'tta-rotate'; rot.style.display = 'none';
  rot.innerHTML = '<div class="box"><div class="ph"></div><div class="tx">Turn your phone sideways to play</div></div>';
  function checkRotate() {
    const coarse = window.matchMedia && matchMedia('(pointer: coarse)').matches;
    rot.style.display = (coarse && innerHeight > innerWidth && !installUp) ? '' : 'none';
  }
  addEventListener('resize', checkRotate); addEventListener('orientationchange', () => setTimeout(checkRotate, 150));

  // ------------------------------------------------------------------ go
  measure(); relayout(); checkRotate();
  showLoad(true); setStatus('Getting ready...', '', 0);
  loadArt();
  // ------------------------------------------------------------------ opened in a normal browser tab on iPhone/iPad: show how to add it to the Home Screen
  const ua = navigator.userAgent || '';
  const isIOS = /iPhone|iPad|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const standalone = window.navigator.standalone === true || (window.matchMedia && matchMedia('(display-mode: standalone)').matches);
  const qs = new URLSearchParams(location.search);
  let skipInstall = false; try { skipInstall = sessionStorage.getItem('tta.skipInstall') === '1'; } catch (e) {}
  const isAndroid = /Android/i.test(ua);
  const needInstall = (qs.get('install') === '1') || ((isIOS || isAndroid) && !standalone && !skipInstall && qs.get('install') !== '0');
  let installEvt = null;                       // Chrome on Android offers a one-tap install through this event
  addEventListener('beforeinstallprompt', (e) => { e.preventDefault(); installEvt = e; const b = document.getElementById('tta-installbtn'); if (b) b.style.display = ''; });
  // Android: full screen + landscape lock from the first tap (a normal browser tab cannot lock the rotation any other way)
  function goFull() {
    const d = document.documentElement;
    try { const r = d.requestFullscreen ? d.requestFullscreen({ navigationUI: 'hide' }) : null; if (r && r.then) r.then(() => { try { screen.orientation.lock('landscape').catch(() => {}); } catch (e) {} }).catch(() => {}); } catch (e) {}
  }
  if (isAndroid && !standalone) { const once = () => { removeEventListener('pointerup', once, true); goFull(); }; addEventListener('pointerup', once, true); }
  // keep the screen on while playing
  let wl = null;
  function keepAwake() { try { if (navigator.wakeLock && !document.hidden) navigator.wakeLock.request('screen').then((l) => { wl = l; }).catch(() => {}); } catch (e) {} }
  document.addEventListener('visibilitychange', () => { if (!document.hidden && hud.style.display !== 'none') keepAwake(); });
  // Open Toontown test build: served from the PC's own test server (port 8002), the files and the game connection are on that same machine
  if (!prefs.mode && location.port === '8002') { LS.setItem('tta_srv_mode', 'custom'); LS.setItem('tta_srv_res', location.origin); LS.setItem('tta_srv_game', 'ws://' + location.hostname + ':8766'); }
  function begin() { if (!prefs.mode) showServerCard(false); else beginDownload(); }
  if (needInstall) {
    installUp = true; checkRotate();
    const ins = el('div', null, root); ins.id = 'tta-install';
    const share = '<svg class="shr" viewBox="0 0 24 24" width="26" height="26" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M12 3v12M8 7l4-4 4 4M6 11H5a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-8a1 1 0 0 0-1-1h-1"/></svg>';
    const steps = isAndroid
      ? '<ol><li><i>1</i><span>Open this page in your browser app itself (Chrome works best), not inside another app</span></li>' +
        '<li><i>2</i><span>Tap the <b>&#8942;</b> menu, then <b>Install app</b> (or <b>Add to Home screen</b>)</span></li>' +
        '<li><i>3</i><span>Open <b>TT: Anywhere</b> from your Home screen. If it still shows a bar at the top, install it again from Chrome</span></li></ol>' +
        '<button class="go" id="tta-installbtn" style="display:none;text-decoration:none;background:#ffd926;color:#733805;border-radius:14px;padding:10px 22px;box-shadow:0 3px 0 rgba(0,0,0,.35);text-shadow:none">Install app</button>'
      : '<ol><li><i>1</i><span>Tap <b>Share</b> ' + share + ' in Safari (tap <b>&hellip;</b> first if you do not see it)</span></li>' +
        '<li><i>2</i><span>Tap <b>View More</b> if you see it, then <b>Add to Home Screen</b></span></li>' +
        '<li><i>3</i><span>Tap <b>Add</b>, then open <b>TT: Anywhere</b> from your Home Screen</span></li></ol>';
    ins.innerHTML = '<div class="box"><div class="ic">' + share.replace('width="26" height="26"', 'width="30" height="30"') + '</div>' +
      '<div class="h">Add Toontown: Anywhere to your Home Screen</div>' + steps +
      '<button class="go skip">Continue in the browser anyway</button></div>';
    const ib = ins.querySelector('#tta-installbtn');
    if (ib) { if (installEvt) ib.style.display = ''; ib.addEventListener('click', () => { if (installEvt) { installEvt.prompt(); installEvt.userChoice.then(() => {}).catch(() => {}); } }); }
    ins.querySelector('.skip').addEventListener('click', () => {
      if (isAndroid) goFull();
      try { sessionStorage.setItem('tta.skipInstall', '1'); } catch (e) {}
      installUp = false; ins.remove(); checkRotate(); begin();
    });
  } else begin();
  // screen facts for the test server's log (to work out odd screens such as foldables)
  function glInfo(c) {
    try {
      if (!c) return '-';
      // Do not call canvas.getContext() here: it creates a context if Panda has not
      // created one yet, and its browser-default attributes can lock in MSAA before
      // Emscripten/Panda requests the game's intended settings.
      const gl = c.GLctxObject && c.GLctxObject.GLctx; if (!gl) return 'not-created';
      const a = gl.getContextAttributes() || {};
      const isWebGL2 = typeof WebGL2RenderingContext !== 'undefined' && gl instanceof WebGL2RenderingContext;
      return (isWebGL2 ? 'webgl2' : 'webgl1') + ' depth=' + gl.getParameter(gl.DEPTH_BITS) + ' stencil=' + gl.getParameter(gl.STENCIL_BITS) + ' aa=' + a.antialias + ' samples=' + gl.getParameter(gl.SAMPLES);
    } catch (e) { return 'err ' + e; }
  }
  function envLog(tag) {
    try {
      const c = document.querySelector('canvas.emscripten'); const r = c ? c.getBoundingClientRect() : null; const vv = window.visualViewport;
      plog('JS| env ' + tag + ' inner ' + innerWidth + 'x' + innerHeight + ' outer ' + outerWidth + 'x' + outerHeight + ' screen ' + screen.width + 'x' + screen.height + ' avail ' + screen.availWidth + 'x' + screen.availHeight +
        ' dpr ' + devicePixelRatio + ' gameScale ' + pixelRatio + ' touchScreen ' + touchScreen + ' vv ' + (vv ? Math.round(vv.width) + 'x' + Math.round(vv.height) + '@' + Math.round(vv.offsetLeft) + ',' + Math.round(vv.offsetTop) + ' s' + vv.scale : '-') +
        ' standalone ' + standalone + ' dm ' + (matchMedia('(display-mode: standalone)').matches ? 'standalone' : matchMedia('(display-mode: fullscreen)').matches ? 'fullscreen' : 'browser') +
        ' orient ' + ((screen.orientation && screen.orientation.type) || '-') + ' safe ' + SAFE.t + ',' + SAFE.r + ',' + SAFE.b + ',' + SAFE.l +
        ' canvas ' + (c ? c.width + 'x' + c.height + ' css ' + Math.round(r.width) + 'x' + Math.round(r.height) + '@' + Math.round(r.left) + ',' + Math.round(r.top) : '-') + ' win ' + T.winW + 'x' + T.winH + ' panda ' + T.pw + 'x' + T.ph + ' gl ' + glInfo(c) + ' ua ' + ua);
    } catch (e) { plog('JS| env failed ' + e); }
  }
  setTimeout(() => envLog('load'), 1500); setTimeout(() => envLog('+10s'), 10000); setTimeout(() => envLog('+40s'), 40000); setTimeout(() => envLog('+90s'), 90000); setTimeout(() => envLog('+180s'), 180000);
  addEventListener('resize', () => { setTimeout(() => envLog('resize'), 300); setTimeout(() => envLog('resize+3s'), 3000); });
  // Touch on the game itself: the game only understands the mouse, and a finger that slides (aiming a fishing cast, dragging in a
  // minigame) never produces mouse movement in a phone browser. Turn a touch on the game into mouse move / press / release.
  // The game's menus only react to a press on a button it has already seen the pointer arrive on, so the press is sent a moment
  // after the move (a few frames), and held a moment before it is released. Sending all three at once made quick taps on small
  // buttons (the chat menus) miss.
  (function () {
    // Pygbag already translates native touchstart/move/end into mouse events when
    // this feature is present. Avoid a second synthetic stream on mobile browsers.
    if ('ontouchstart' in document.documentElement) return;
    const DOWN_DELAY = 70, MIN_HOLD = 60;
    let active = null, last = null, pressed = false, downTimer = null, downPlanned = 0;
    // Cursor mode (Settings > Touch pointer): the screen is a trackpad. Dragging anywhere moves the glove cursor drawn over the game (the
    // same pointer a desktop shows); a short tap clicks where the cursor is. Tap mode (the default) clicks where the finger lands.
    const cursorOn = () => lsGet('tta_pointer', 'tap') === 'cursor';
    const GAIN = 1.7, TAP_MS = 350, TAP_MOVE = 10, HOLD_MS = 260;   // HOLD_MS: keep a finger still this long and the glove presses and holds (fishing casts, dragging)
    const gloveAt = () => ({ clientX: vx, clientY: vy, screenX: vx, screenY: vy });
    let vx = innerWidth / 2, vy = innerHeight / 2, session = null;
    const cur = document.createElement('div');
    cur.id = 'tta-cursor';
    // Toontown's own glove (the game's toonmono.png, 96 px drawn at 34), its fingertip on the click point
    cur.style.cssText = 'position:fixed;left:0;top:0;width:34px;height:34px;pointer-events:none;z-index:2147483000;display:none;will-change:transform;background:url(data:image/png;base64,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) 0 0/34px 34px no-repeat';
    document.body.appendChild(cur);
    function showCursor() {
      vx = Math.max(0, Math.min(innerWidth - 1, vx)); vy = Math.max(0, Math.min(innerHeight - 1, vy));
      cur.style.transform = 'translate(' + (vx - 1) + 'px,' + (vy - 1) + 'px)';
      cur.style.display = (cursorOn() && hud.style.display !== 'none') ? '' : 'none';
    }
    window.ttaPointerRefresh = showCursor;
    addEventListener('resize', showCursor);
    setInterval(showCursor, 700);          // (the controls appear and go with the game screens; keep the cursor in step)
    function clickAt(x, y) {
      const at = { clientX: x, clientY: y, screenX: x, screenY: y };
      fire('mousemove', at);
      setTimeout(() => fire('mousedown', at), DOWN_DELAY);
      setTimeout(() => fire('mouseup', at), DOWN_DELAY + MIN_HOLD);
    }
    const isGame = (t) => t && t.classList && t.classList.contains('emscripten');
    function fire(type, e, buttons) {
      const cv = document.querySelector('canvas.emscripten'); if (!cv) return;
      const mouse = new MouseEvent(type, { bubbles: true, cancelable: true, view: window, clientX: e.clientX, clientY: e.clientY,
        screenX: e.screenX, screenY: e.screenY, button: 0, buttons: type === 'mouseup' ? 0 : 1 });
      // Pygbag scales mouse input from pageX/pageY against the canvas rectangle. Preserve the
      // original pointer's document coordinates; Safari can derive a different page coordinate
      // for a synthetic mouse event after the visual viewport has moved or zoomed.
      try { Object.defineProperties(mouse, {
        pageX: { configurable: true, value: Number.isFinite(e.pageX) ? e.pageX : e.clientX + (window.scrollX || 0) },
        pageY: { configurable: true, value: Number.isFinite(e.pageY) ? e.pageY : e.clientY + (window.scrollY || 0) }
      }); } catch (_) {}
      cv.dispatchEvent(mouse);
    }
    function press() { if (downTimer) { clearTimeout(downTimer); downTimer = null; } if (!pressed) { pressed = true; fire('mousedown', last); } }
    document.addEventListener('pointerdown', (e) => {
      if (e.pointerType === 'mouse' || !isGame(e.target) || active !== null) return;
      active = e.pointerId; last = e; e.preventDefault();
      if (cursorOn()) {
        const ses = session = { x: e.clientX, y: e.clientY, t: Date.now(), moved: false, dragging: false, timer: null };
        ses.timer = setTimeout(() => {
          if (session !== ses || ses.moved) return;
          ses.dragging = true; cur.style.filter = 'brightness(.7)';
          fire('mousemove', gloveAt(), 0); fire('mousedown', gloveAt());
        }, HOLD_MS);
        showCursor(); return;
      }
      session = null;
      fire('mousemove', e);
      downPlanned = Date.now() + DOWN_DELAY;
      downTimer = setTimeout(press, DOWN_DELAY);
    }, { capture: true, passive: false });
    document.addEventListener('pointermove', (e) => {
      if (e.pointerId !== active) return;
      e.preventDefault();
      if (session) {
        if (!session.moved && Math.hypot(e.clientX - session.x, e.clientY - session.y) > TAP_MOVE) { session.moved = true; if (!session.dragging) clearTimeout(session.timer); }
        const px = session.lx === undefined ? session.x : session.lx, py = session.ly === undefined ? session.y : session.ly;
        vx += (e.clientX - px) * GAIN; vy += (e.clientY - py) * GAIN; session.lx = e.clientX; session.ly = e.clientY;
        showCursor(); fire('mousemove', gloveAt(), session.dragging ? 1 : 0);
        return;
      }
      last = e; fire('mousemove', e);
    }, { capture: true, passive: false });
    const up = (e) => {
      if (e.pointerId !== active) return;
      if (session) {
        clearTimeout(session.timer);
        const wasDrag = session.dragging;
        const tap = !wasDrag && !session.moved && e.type === 'pointerup' && Date.now() - session.t < TAP_MS;
        session = null; active = null;
        if (wasDrag) { cur.style.filter = ''; fire('mouseup', gloveAt()); return; }
        if (tap) {
          clickAt(vx, vy);
          // the typed-chat button and the name box open the phone keyboard from the tap itself, so ask where the glove is, not the finger
          try { kbTap({ clientX: vx, clientY: vy }); armChain(); } catch (err) {}
        }
        return;
      }
      active = null; last = e;
      const wait = Math.max(0, downPlanned + MIN_HOLD - Date.now());
      setTimeout(() => { press(); pressed = false; fire('mouseup', e); }, wait);
    };
    document.addEventListener('pointerup', up, true);
    document.addEventListener('pointercancel', up, true);
    document.addEventListener('touchstart', (e) => { if (isGame(e.target)) e.preventDefault(); }, { capture: true, passive: false });   // no second, browser-made set of mouse events
  })();
  // The page's own start-up code resizes the drawing surface when the window changes, without telling the game, so the game can end up
  // drawing into a smaller area than the surface (a grey strip at the edge). If the game agrees with the size we asked for but the surface
  // does not, put the surface right.
  let fixes = 0;
  setInterval(() => {
    if (kbHold || hud.style.display === 'none') return;
    const c = document.querySelector('canvas.emscripten'); if (!c) return;
    const w = +T.winW, h = +T.winH;
    if (w > 0 && h > 0 && +T.pw === w && +T.ph === h && (c.width !== w || c.height !== h)) {
      c.width = w; c.height = h; fixes++;
      if (fixes <= 5) plog('JS| env fixcanvas #' + fixes + ' set ' + w + 'x' + h);
    }
  }, 400);
  // No zooming: Safari ignores user-scalable=no, so a quick double tap or a pinch zooms the whole page in. Stop both.
  ['gesturestart', 'gesturechange', 'gestureend'].forEach((t) => document.addEventListener(t, (e) => e.preventDefault(), { passive: false }));
  (function () {
    let last = 0;
    document.addEventListener('touchend', (e) => {
      const now = Date.now();
      const tg = e.target;
      const typing = tg && tg.closest && tg.closest('input, textarea, select, [contenteditable]');
      if (now - last < 350 && !typing) e.preventDefault();      // the second tap of a double tap
      last = now;
    }, { passive: false });
  })();
  // developer channel (only on the local test server, port 8001): run Python source from debug_code.py in the game
  if (location.port === '8001' || location.port === '8002') {
    let lastCode = '';
    setInterval(async () => {
      try { const t = await (await fetch('/__code?' + Date.now(), { cache: 'no-store' })).text(); if (t && t !== lastCode) { lastCode = t; T.pycode = t; } } catch (e) {}
    }, 2000);
  }
})();
