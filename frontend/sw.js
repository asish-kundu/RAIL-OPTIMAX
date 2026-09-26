const CACHE='rail-optimax-v27';
const ASSETS=['./','./index.html','./src/style.css','./src/components.css','./src/dashboard.css','./src/map.css','./js/map.js?v=25','./js/demo-runtime.js','./js/dashboard.js?v=25','./js/app.js?v=25','./js/maintenance.js','./assets/uploaded-corridor-map.svg'];
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS)).then(()=>self.skipWaiting())));
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('rail-optimax-')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',e=>{const u=new URL(e.request.url);if(e.request.method!=='GET'||u.pathname.includes('/trains/live')||u.pathname.includes('/health')||u.pathname.includes('/ai/'))return;e.respondWith(fetch(e.request).then(r=>{const copy=r.clone();caches.open(CACHE).then(c=>c.put(e.request,copy));return r;}).catch(()=>caches.match(e.request)));});
