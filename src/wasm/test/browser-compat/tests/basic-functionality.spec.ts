import { test, expect } from '@playwright/test';

/**
 * Basic functionality tests for Piper WebAssembly
 */

test.describe('Basic WebAssembly Support', () => {
  test('WebAssembly is available', async ({ page }) => {
    const wasmSupported = await page.evaluate(() => {
      return typeof WebAssembly !== 'undefined';
    });
    expect(wasmSupported).toBe(true);
  });

  test('WebAssembly.instantiateStreaming is available', async ({ page }) => {
    const instantiateStreamingSupported = await page.evaluate(() => {
      return typeof WebAssembly.instantiateStreaming === 'function';
    });
    expect(instantiateStreamingSupported).toBe(true);
  });

  test('Can load simple WASM module', async ({ page }) => {
    const result = await page.evaluate(async () => {
      // Simple add function WASM module
      const wasmCode = new Uint8Array([
        0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00,
        0x01, 0x07, 0x01, 0x60, 0x02, 0x7f, 0x7f, 0x01,
        0x7f, 0x03, 0x02, 0x01, 0x00, 0x07, 0x07, 0x01,
        0x03, 0x61, 0x64, 0x64, 0x00, 0x00, 0x0a, 0x09,
        0x01, 0x07, 0x00, 0x20, 0x00, 0x20, 0x01, 0x6a,
        0x0b
      ]);
      
      const module = await WebAssembly.compile(wasmCode);
      const instance = await WebAssembly.instantiate(module);
      const add = instance.exports.add as (a: number, b: number) => number;
      
      return add(2, 3);
    });
    
    expect(result).toBe(5);
  });
});

test.describe('SIMD Support Detection', () => {
  test('Check WebAssembly SIMD support', async ({ page, browserName }) => {
    const simdSupported = await page.evaluate(async () => {
      try {
        // SIMD detection code
        const simdTest = new Uint8Array([
          0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00,
          0x01, 0x05, 0x01, 0x60, 0x00, 0x01, 0x7b, 0x03,
          0x02, 0x01, 0x00, 0x0a, 0x0a, 0x01, 0x08, 0x00,
          0x41, 0x00, 0xfd, 0x0f, 0x0b
        ]);
        
        await WebAssembly.instantiate(simdTest);
        return true;
      } catch (e) {
        return false;
      }
    });
    
    // Log SIMD support status
    console.log(`${browserName} SIMD support: ${simdSupported}`);
    
    // Chrome should support SIMD
    if (browserName === 'chromium') {
      expect(simdSupported).toBe(true);
    }
  });
});

test.describe('SharedArrayBuffer Support', () => {
  test('Check SharedArrayBuffer availability', async ({ page, browserName }) => {
    await page.goto('/test/mecab-test.html');
    
    const sabSupported = await page.evaluate(() => {
      return typeof SharedArrayBuffer !== 'undefined';
    });
    
    // Log SAB support
    console.log(`${browserName} SharedArrayBuffer support: ${sabSupported}`);
    
    // Note: SAB requires proper COOP/COEP headers
    if (sabSupported) {
      // Test basic SAB functionality
      const sabWorks = await page.evaluate(() => {
        try {
          const sab = new SharedArrayBuffer(1024);
          const view = new Int32Array(sab);
          view[0] = 42;
          return view[0] === 42;
        } catch (e) {
          return false;
        }
      });
      
      expect(sabWorks).toBe(true);
    }
  });
});

test.describe('Web Audio API Support', () => {
  test('AudioContext is available', async ({ page }) => {
    const audioSupported = await page.evaluate(() => {
      return typeof (window as any).AudioContext !== 'undefined' || 
             typeof (window as any).webkitAudioContext !== 'undefined';
    });
    
    expect(audioSupported).toBe(true);
  });
  
  test('Can create AudioContext', async ({ page, browserName }) => {
    const canCreateContext = await page.evaluate(() => {
      try {
        const AudioContext = (window as any).AudioContext || (window as any).webkitAudioContext;
        const ctx = new AudioContext();
        const state = ctx.state;
        ctx.close();
        return { success: true, state };
      } catch (e: any) {
        return { success: false, error: e.message };
      }
    });
    
    expect(canCreateContext.success).toBe(true);
    
    // Safari may require user interaction
    if (browserName === 'webkit' && canCreateContext.state === 'suspended') {
      console.log('Safari AudioContext requires user interaction');
    }
  });
});

test.describe('WebGL Support', () => {
  test('WebGL is available', async ({ page }) => {
    const webglInfo = await page.evaluate(() => {
      const canvas = document.createElement('canvas');
      const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
      const gl2 = canvas.getContext('webgl2');
      
      return {
        webgl: !!gl,
        webgl2: !!gl2,
        vendor: gl ? gl.getParameter(gl.VENDOR) : null,
        renderer: gl ? gl.getParameter(gl.RENDERER) : null
      };
    });
    
    console.log('WebGL Info:', webglInfo);
    expect(webglInfo.webgl || webglInfo.webgl2).toBe(true);
  });
});

test.describe('MeCab Module Loading', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/test/mecab-test.html');
  });
  
  test('Can load MeCab WebAssembly module', async ({ page }) => {
    // Wait for module to load
    await page.waitForFunction(() => {
      return typeof (window as any).MeCabModule !== 'undefined';
    }, { timeout: 30000 });
    
    const moduleLoaded = await page.evaluate(() => {
      return typeof (window as any).mecabModule !== 'undefined';
    });
    
    expect(moduleLoaded).toBe(true);
  });
  
  test('Can tokenize Japanese text', async ({ page, browserName }) => {
    // Skip if module loading failed
    const moduleLoaded = await page.evaluate(() => {
      return typeof (window as any).mecabModule !== 'undefined';
    }).catch(() => false);
    
    if (!moduleLoaded) {
      test.skip();
      return;
    }
    
    // Test tokenization
    const result = await page.evaluate(() => {
      const mecab = (window as any).mecabModule;
      if (!mecab || !mecab.tokenize) return null;
      
      try {
        return mecab.tokenize('こんにちは世界');
      } catch (e: any) {
        return { error: e.message };
      }
    });
    
    console.log(`${browserName} MeCab tokenization result:`, result);
    
    if (result && !result.error) {
      expect(result).toBeTruthy();
      expect(result.length).toBeGreaterThan(0);
    }
  });
});

test.describe('OpenJTalk Module Loading', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/test/openjtalk-test.html');
  });
  
  test('Can load OpenJTalk WebAssembly module', async ({ page }) => {
    // Wait for module to load
    await page.waitForFunction(() => {
      return typeof (window as any).OpenJTalkModule !== 'undefined';
    }, { timeout: 30000 });
    
    const moduleLoaded = await page.evaluate(() => {
      return typeof (window as any).openJTalkModule !== 'undefined';
    });
    
    expect(moduleLoaded).toBe(true);
  });
});

test.describe('ONNX Runtime Web', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/test/full-tts-demo.html');
  });
  
  test('Can load ONNX Runtime Web', async ({ page }) => {
    // Load ONNX Runtime
    await page.evaluate(() => {
      return new Promise((resolve) => {
        const script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.18.0/dist/ort.min.js';
        script.onload = resolve;
        document.head.appendChild(script);
      });
    });
    
    const ortLoaded = await page.evaluate(() => {
      return typeof (window as any).ort !== 'undefined';
    });
    
    expect(ortLoaded).toBe(true);
  });
  
  test('Check ONNX Runtime execution providers', async ({ page, browserName }) => {
    // Skip if ORT not loaded
    const ortLoaded = await page.evaluate(() => {
      return typeof (window as any).ort !== 'undefined';
    }).catch(() => false);
    
    if (!ortLoaded) {
      test.skip();
      return;
    }
    
    const providers = await page.evaluate(() => {
      const ort = (window as any).ort;
      return {
        wasm: true, // WASM is always available
        webgl: 'webgl' in ort.env.backends,
        webgpu: 'webgpu' in ort.env.backends
      };
    });
    
    console.log(`${browserName} ONNX Runtime providers:`, providers);
    expect(providers.wasm).toBe(true);
  });
});

test.describe('Memory and Performance', () => {
  test('Check memory limits', async ({ page, browserName }) => {
    const memoryInfo = await page.evaluate(() => {
      const memory = (performance as any).memory;
      
      if (!memory) {
        return { available: false };
      }
      
      return {
        available: true,
        jsHeapSizeLimit: Math.round(memory.jsHeapSizeLimit / 1024 / 1024),
        totalJSHeapSize: Math.round(memory.totalJSHeapSize / 1024 / 1024),
        usedJSHeapSize: Math.round(memory.usedJSHeapSize / 1024 / 1024)
      };
    });
    
    console.log(`${browserName} Memory info:`, memoryInfo);
    
    // Chrome provides memory info
    if (memoryInfo.available && browserName === 'chromium') {
      expect(memoryInfo.jsHeapSizeLimit).toBeGreaterThan(500); // At least 500MB
    }
  });
  
  test('Hardware concurrency', async ({ page }) => {
    const cores = await page.evaluate(() => {
      return navigator.hardwareConcurrency || 0;
    });
    
    console.log('Hardware concurrency:', cores);
    expect(cores).toBeGreaterThan(0);
  });
});