/* Toontown: Anywhere: shows the notifications the server sends (events, announcements) and opens the game when one is tapped.
   There is no offline cache here on purpose: the game's own files are loaded and cached by the page itself. */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

self.addEventListener('push', (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (err) { d = { body: e.data ? e.data.text() : '' }; }
  // every push has to show something (Safari revokes the permission otherwise)
  e.waitUntil(self.registration.showNotification(String(d.title || 'Toontown: Anywhere').slice(0, 80), {
    body: String(d.body || '').slice(0, 240),
    icon: 'icon-192.png',
    badge: 'icon-192.png',
    data: { url: typeof d.url === 'string' && d.url.charAt(0) === '/' ? d.url : '/play/' },
  }));
});

self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  const target = new URL((e.notification.data && e.notification.data.url) || '/play/', self.location.origin).href;
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
    for (const c of list) if (c.url.indexOf(self.registration.scope) === 0 && 'focus' in c) return c.focus();
    return self.clients.openWindow(target);
  }));
});
