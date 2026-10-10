/* Service Worker — منصة أخبار النصر
   استراتيجية:
   - التنقّل (الصفحات): الشبكة أولًا ثم الكاش، ومع انقطاع الاتصال تظهر صفحة «غير متصل».
   - ملفات /static/: الكاش أولًا مع تحديث في الخلفية (سريعة جدًا).
   - صفحات الإدارة/التحرير/الدخول: لا تُخزَّن مطلقًا.
*/
const VERSION = 'v1';
const STATIC_CACHE = `nassr-static-${VERSION}`;
const PAGE_CACHE = `nassr-pages-${VERSION}`;
const OFFLINE_URL = '/offline.html';
const NO_CACHE_PREFIXES = ['/editor', '/tasks', '/admin', '/auth'];

const PRECACHE = [
  OFFLINE_URL,
  '/manifest.webmanifest',
  '/static/img/icons/icon-192.png',
  '/static/img/icons/icon-512.png',
  '/static/img/icons/maskable-192.png',
  '/static/img/icons/maskable-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(STATIC_CACHE);
    await Promise.all(
      PRECACHE.map((u) => cache.add(new Request(u, { cache: 'reload' })).catch(() => {}))
    );
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((k) => !k.endsWith(VERSION)).map((k) => caches.delete(k)));
    await self.clients.claim();
  })());
});

function isNoCache(pathname) {
  return NO_CACHE_PREFIXES.some((p) => pathname === p || pathname.startsWith(p + '/') || pathname.startsWith(p));
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  if (req.mode === 'navigate') {
    event.respondWith(handleNavigate(req));
    return;
  }
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(cacheFirst(req, STATIC_CACHE));
    return;
  }
  if (isNoCache(url.pathname)) return;
  event.respondWith(networkFirst(req, PAGE_CACHE));
});

async function handleNavigate(req) {
  const url = new URL(req.url);
  const cacheable = !isNoCache(url.pathname);
  try {
    const fresh = await fetch(req);
    if (fresh && fresh.ok && cacheable) {
      const cache = await caches.open(PAGE_CACHE);
      cache.put(req, fresh.clone());
    }
    return fresh;
  } catch (err) {
    const cache = await caches.open(PAGE_CACHE);
    const cached = await cache.match(req);
    if (cached) return cached;
    const staticCache = await caches.open(STATIC_CACHE);
    const offline = await staticCache.match(OFFLINE_URL);
    if (offline) return offline;
    return new Response('لا يوجد اتصال بالإنترنت.', {
      status: 503,
      headers: { 'Content-Type': 'text/plain; charset=utf-8' },
    });
  }
}

async function cacheFirst(req, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(req);
  if (cached) {
    fetch(req).then((res) => { if (res && res.ok) cache.put(req, res.clone()); }).catch(() => {});
    return cached;
  }
  const res = await fetch(req);
  if (res && res.ok) cache.put(req, res.clone());
  return res;
}

async function networkFirst(req, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const res = await fetch(req);
    if (res && res.ok) cache.put(req, res.clone());
    return res;
  } catch (err) {
    const cached = await cache.match(req);
    if (cached) return cached;
    throw err;
  }
}
