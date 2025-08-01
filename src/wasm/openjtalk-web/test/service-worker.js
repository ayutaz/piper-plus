// Service Worker for caching TTS resources
const CACHE_NAME = 'openjtalk-piper-tts-v1';
const urlsToCache = [
    // HTML files
    './',
    './index.html',
    './production-audio-test.html',
    './production-audio-test-optimized.html',
    
    // JavaScript files
    './test/js/openjtalk-piper-integration.js',
    './test/js/openjtalk-piper-integration-optimized.js',
    
    // WebAssembly files
    './dist/openjtalk.js',
    './dist/openjtalk.wasm',
    
    // Dictionary files (large, cache after first load)
    './assets/dict/char.bin',
    './assets/dict/matrix.bin',
    './assets/dict/sys.dic',
    './assets/dict/unk.dic',
    './assets/dict/left-id.def',
    './assets/dict/pos-id.def',
    './assets/dict/rewrite.def',
    './assets/dict/right-id.def',
    
    // Voice file
    './assets/voice/mei_normal.htsvoice',
    
    // ONNX model files (large, cache after first load)
    './models/ja_JP-test-medium.onnx',
    './models/ja_JP-test-medium.onnx.json',
    
    // External dependencies (ONNX Runtime)
    'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.16.3/dist/ort.min.js'
];

// Install event - cache resources
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => {
                console.log('Opened cache');
                // Cache only essential files during install
                const essentialUrls = [
                    './',
                    './index.html',
                    './test/js/openjtalk-piper-integration.js',
                    './test/js/openjtalk-piper-integration-optimized.js'
                ];
                return cache.addAll(essentialUrls);
            })
            .then(() => self.skipWaiting())
    );
});

// Fetch event - serve from cache when available
self.addEventListener('fetch', event => {
    event.respondWith(
        caches.match(event.request)
            .then(response => {
                // Cache hit - return response
                if (response) {
                    console.log('Serving from cache:', event.request.url);
                    return response;
                }

                // Clone the request
                const fetchRequest = event.request.clone();

                return fetch(fetchRequest).then(response => {
                    // Check if valid response
                    if (!response || response.status !== 200 || response.type === 'error') {
                        return response;
                    }

                    // Clone the response
                    const responseToCache = response.clone();

                    // Cache large files after first successful fetch
                    const url = event.request.url;
                    if (url.includes('.bin') || url.includes('.dic') || 
                        url.includes('.onnx') || url.includes('.wasm') ||
                        url.includes('.htsvoice')) {
                        caches.open(CACHE_NAME)
                            .then(cache => {
                                console.log('Caching large file:', url);
                                cache.put(event.request, responseToCache);
                            });
                    }

                    return response;
                });
            })
    );
});

// Activate event - clean up old caches
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cacheName => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('Deleting old cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

// Message event - handle cache control messages
self.addEventListener('message', event => {
    if (event.data.action === 'clearCache') {
        caches.delete(CACHE_NAME).then(() => {
            console.log('Cache cleared');
            event.ports[0].postMessage({ status: 'Cache cleared' });
        });
    } else if (event.data.action === 'getCacheSize') {
        caches.open(CACHE_NAME).then(cache => {
            return cache.keys();
        }).then(keys => {
            event.ports[0].postMessage({ 
                status: 'success', 
                count: keys.length,
                urls: keys.map(request => request.url)
            });
        });
    }
});