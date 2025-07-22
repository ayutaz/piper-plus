import { test, expect } from '@playwright/test';

/**
 * Browser-specific compatibility tests
 */

test.describe('Chrome-specific Features', () => {
  test.skip(({ browserName }) => browserName !== 'chromium', 'Chrome only');
  
  test('WebGPU support in Chrome', async ({ page }) => {
    const webgpuSupported = await page.evaluate(async () => {
      if (!navigator.gpu) return false;
      
      try {
        const adapter = await navigator.gpu.requestAdapter();
        return !!adapter;
      } catch (e) {
        return false;
      }
    });
    
    console.log('Chrome WebGPU support:', webgpuSupported);
    // WebGPU may not be available in all Chrome versions
  });
  
  test('Chrome memory pressure API', async ({ page }) => {
    const memoryPressureSupported = await page.evaluate(() => {
      return 'memory' in performance;
    });
    
    expect(memoryPressureSupported).toBe(true);
  });
  
  test('OffscreenCanvas support', async ({ page }) => {
    const offscreenSupported = await page.evaluate(() => {
      return typeof OffscreenCanvas !== 'undefined';
    });
    
    expect(offscreenSupported).toBe(true);
  });
});

test.describe('Firefox-specific Features', () => {
  test.skip(({ browserName }) => browserName !== 'firefox', 'Firefox only');
  
  test('Firefox SharedArrayBuffer handling', async ({ page }) => {
    await page.goto('/test/mecab-test.html');
    
    const sabHandling = await page.evaluate(() => {
      // Firefox-specific SAB behavior
      const sabAvailable = typeof SharedArrayBuffer !== 'undefined';
      const coopCoepRequired = !sabAvailable && 'crossOriginIsolated' in window;
      
      return {
        sabAvailable,
        coopCoepRequired,
        crossOriginIsolated: (window as any).crossOriginIsolated || false
      };
    });
    
    console.log('Firefox SAB handling:', sabHandling);
  });
  
  test('Firefox WebAssembly streaming', async ({ page }) => {
    const streamingWorks = await page.evaluate(async () => {
      try {
        // Test with a minimal WASM module
        const response = new Response(new Uint8Array([
          0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00
        ]), {
          headers: { 'Content-Type': 'application/wasm' }
        });
        
        const module = await WebAssembly.instantiateStreaming(response);
        return true;
      } catch (e) {
        // Firefox may require proper MIME type
        return false;
      }
    });
    
    console.log('Firefox WASM streaming:', streamingWorks);
  });
});

test.describe('Safari/WebKit-specific Features', () => {
  test.skip(({ browserName }) => browserName !== 'webkit', 'Safari only');
  
  test('Safari Web Audio autoplay policy', async ({ page }) => {
    const audioPolicy = await page.evaluate(async () => {
      const AudioContext = (window as any).AudioContext || (window as any).webkitAudioContext;
      const ctx = new AudioContext();
      
      const initialState = ctx.state;
      
      // Try to resume (Safari may require user gesture)
      let resumeResult = 'not_needed';
      if (ctx.state === 'suspended') {
        try {
          await ctx.resume();
          resumeResult = 'resumed';
        } catch (e) {
          resumeResult = 'failed';
        }
      }
      
      const finalState = ctx.state;
      ctx.close();
      
      return {
        initialState,
        finalState,
        resumeResult,
        requiresUserGesture: initialState === 'suspended'
      };
    });
    
    console.log('Safari audio policy:', audioPolicy);
    
    // Safari typically requires user interaction
    if (audioPolicy.requiresUserGesture) {
      expect(audioPolicy.initialState).toBe('suspended');
    }
  });
  
  test('Safari WebAssembly memory limits', async ({ page }) => {
    const memoryTest = await page.evaluate(async () => {
      try {
        // Try to allocate large WASM memory
        const memory = new WebAssembly.Memory({
          initial: 256, // 256 * 64KB = 16MB
          maximum: 4096 // 4096 * 64KB = 256MB
        });
        
        return {
          success: true,
          buffer: memory.buffer.byteLength
        };
      } catch (e: any) {
        return {
          success: false,
          error: e.message
        };
      }
    });
    
    console.log('Safari WASM memory test:', memoryTest);
    expect(memoryTest.success).toBe(true);
  });
  
  test('Safari CORS handling', async ({ page }) => {
    // Safari has stricter CORS policies
    const corsTest = await page.evaluate(async () => {
      try {
        // Test fetch with CORS
        const response = await fetch('https://cdn.jsdelivr.net/npm/onnxruntime-web@1.18.0/package.json');
        return {
          ok: response.ok,
          corsMode: response.type
        };
      } catch (e: any) {
        return {
          ok: false,
          error: e.message
        };
      }
    });
    
    console.log('Safari CORS test:', corsTest);
  });
});

test.describe('Edge-specific Features', () => {
  test.skip(({ browserName }) => browserName !== 'edge' && browserName !== 'chromium', 'Edge only');
  
  test('Edge Chromium compatibility', async ({ page, browserName }) => {
    if (browserName !== 'edge') {
      test.skip();
      return;
    }
    
    const edgeFeatures = await page.evaluate(() => {
      return {
        userAgent: navigator.userAgent,
        isEdge: navigator.userAgent.includes('Edg/'),
        // Edge-specific APIs (if any)
      };
    });
    
    console.log('Edge features:', edgeFeatures);
    expect(edgeFeatures.isEdge).toBe(true);
  });
});

test.describe('Cross-Browser Feature Matrix', () => {
  test('Generate browser capability matrix', async ({ page, browserName }) => {
    await page.goto('/test/benchmark.html');
    
    const capabilities = await page.evaluate(async () => {
      // Comprehensive feature detection
      const features: any = {};
      
      // WebAssembly features
      features.wasm = typeof WebAssembly !== 'undefined';
      features.wasmStreaming = typeof WebAssembly.instantiateStreaming === 'function';
      
      // SIMD detection
      try {
        const simdTest = new Uint8Array([
          0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00,
          0x01, 0x05, 0x01, 0x60, 0x00, 0x01, 0x7b, 0x03,
          0x02, 0x01, 0x00, 0x0a, 0x0a, 0x01, 0x08, 0x00,
          0x41, 0x00, 0xfd, 0x0f, 0x0b
        ]);
        await WebAssembly.instantiate(simdTest);
        features.wasmSIMD = true;
      } catch {
        features.wasmSIMD = false;
      }
      
      // Threading
      features.sharedArrayBuffer = typeof SharedArrayBuffer !== 'undefined';
      features.atomics = typeof Atomics !== 'undefined';
      
      // Web Audio
      features.webAudio = !!(window as any).AudioContext || !!(window as any).webkitAudioContext;
      features.audioWorklet = !!(window as any).AudioWorkletNode;
      
      // WebGL
      const canvas = document.createElement('canvas');
      features.webgl = !!canvas.getContext('webgl');
      features.webgl2 = !!canvas.getContext('webgl2');
      
      // WebGPU
      features.webgpu = 'gpu' in navigator;
      
      // Performance APIs
      features.performanceMemory = 'memory' in performance;
      features.performanceObserver = typeof PerformanceObserver !== 'undefined';
      
      // Storage
      features.indexedDB = 'indexedDB' in window;
      features.cacheAPI = 'caches' in window;
      
      // Workers
      features.worker = typeof Worker !== 'undefined';
      features.sharedWorker = typeof SharedWorker !== 'undefined';
      features.serviceWorker = 'serviceWorker' in navigator;
      
      // Misc
      features.offscreenCanvas = typeof OffscreenCanvas !== 'undefined';
      features.bigInt = typeof BigInt !== 'undefined';
      features.textEncoder = typeof TextEncoder !== 'undefined';
      
      return features;
    });
    
    // Log capability matrix
    console.log(`\n=== ${browserName.toUpperCase()} Capability Matrix ===`);
    Object.entries(capabilities).forEach(([feature, supported]) => {
      console.log(`${feature}: ${supported ? '✓' : '✗'}`);
    });
    
    // Save results for later analysis
    await page.evaluate((data) => {
      localStorage.setItem(`piper-compat-${data.browser}`, JSON.stringify({
        timestamp: new Date().toISOString(),
        capabilities: data.capabilities,
        userAgent: navigator.userAgent
      }));
    }, { browser: browserName, capabilities });
    
    // Essential features that must be present
    expect(capabilities.wasm).toBe(true);
    expect(capabilities.webAudio).toBe(true);
    expect(capabilities.textEncoder).toBe(true);
  });
});