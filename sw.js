const CACHE = 'azs-piter-v1';

const SHELL = [
  './',
  './index.html',
  './lib/leaflet.js',
  './lib/leaflet.css',
  './lib/leaflet.markercluster.js',
  './lib/MarkerCluster.css',
  './lib/MarkerCluster.Default.css',
];

const DATA = ['stations.json', 'prices.json', 'station_prices.json'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(SHELL).catch(() => {}))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(k => k !== CACHE).map(k => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const { request } = e;
  const url = new URL(request.url);

  if (request.method !== 'GET') return;
  if (url.origin !== self.location.origin) return;

  const filename = url.pathname.split('/').pop();

  if (DATA.includes(filename)) {
    e.respondWith(staleWhileRevalidate(request, filename));
  } else {
    e.respondWith(
      caches.match(request).then(cached => cached || fetch(request))
    );
  }
});

// Показываем кэш сразу, обновляем в фоне
async function staleWhileRevalidate(request, filename) {
  const cache = await caches.open(CACHE);
  const cacheKey = `./${filename}`;
  const cached = await cache.match(cacheKey);

  const networkFetch = fetch(request)
    .then(r => { if (r.ok) cache.put(cacheKey, r.clone()); return r; })
    .catch(() => null);

  return cached || await networkFetch;
}
