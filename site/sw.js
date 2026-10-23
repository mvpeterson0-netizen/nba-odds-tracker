// Dime service worker: makes the site installable and lets it open offline.
// Network first for everything, so data and code are always fresh when online;
// the last good copy is served only when the network fails.
const CACHE = "dime-v1";
const SHELL = ["./", "index.html", "style.css", "mobile.css", "app.js", "props.js", "manifest.webmanifest",
  "icons/dime-180.png", "icons/dime-192.png", "icons/dime-512.png", "icons/dime-64.png", "icons/dime-32.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {}).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;   // GitHub API etc.: browser default
  // Cache key ignores ?t= / ?v= cache-busters so the offline copy is found.
  const key = new Request(url.origin + url.pathname);
  e.respondWith(
    fetch(req).then((res) => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(key, copy)); }
      return res;
    }).catch(() => caches.match(key).then((hit) => hit || caches.match("index.html")))
  );
});
