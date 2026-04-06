/**
 * TDD Tests for WebGPUSessionManager
 * Phase 2b: WebGPU バックエンド
 *
 * テスト対象: src/wasm/openjtalk-web/src/webgpu-session-manager.js (未実装)
 */

import { strict as assert } from 'assert';
import { describe, it, beforeEach } from 'node:test';

// --- モック定義 ---

function createMockOrt({ supportedProviders = ['wasm'] } = {}) {
  return {
    InferenceSession: {
      create: async (path, options) => {
        const provider = (options.executionProviders || ['wasm'])[0];
        const providerName = typeof provider === 'string' ? provider : provider.name;
        if (!supportedProviders.includes(providerName)) {
          throw new Error(`EP ${providerName} not available`);
        }
        return {
          inputNames: ['input', 'input_lengths', 'scales'],
          outputNames: ['output'],
          currentProvider: providerName,
          run: async () => ({ output: { data: new Float32Array(100), dims: [1, 100] } }),
          release: () => {},
        };
      },
    },
    Tensor: class { constructor(t, d, s) { this.type = t; this.data = d; this.dims = s; } },
  };
}

function createMockGPU(available = true) {
  if (!available) return undefined;
  return {
    requestAdapter: async () => ({
      requestDevice: async () => ({
        limits: {
          maxBufferSize: 256 * 1024 * 1024,
          maxStorageBufferBindingSize: 128 * 1024 * 1024,
        },
        destroy: () => {},
      }),
    }),
  };
}

let WebGPUSessionManager;
try {
  const mod = await import('../../src/webgpu-session-manager.js');
  WebGPUSessionManager = mod.WebGPUSessionManager || mod.default;
} catch {
  WebGPUSessionManager = null;
}

const skip = WebGPUSessionManager === null;

describe('WebGPUSessionManager', { skip }, () => {
  describe('フォールバック順序', () => {
    it('WebGPU対応環境ではwebgpuプロバイダーを選択する', async () => {
      const mgr = new WebGPUSessionManager({
        ort: createMockOrt({ supportedProviders: ['webgpu', 'wasm'] }),
        gpu: createMockGPU(true),
      });
      const session = await mgr.createSession('model.onnx');
      assert.equal(mgr.currentProvider, 'webgpu');
    });

    it('WebGPU非対応時はwasmにフォールバックする', async () => {
      const mgr = new WebGPUSessionManager({
        ort: createMockOrt({ supportedProviders: ['wasm'] }),
        gpu: createMockGPU(false),
      });
      const session = await mgr.createSession('model.onnx');
      assert.equal(mgr.currentProvider, 'wasm');
    });

    it('全プロバイダー失敗時はエラーをスローする', async () => {
      const mgr = new WebGPUSessionManager({
        ort: createMockOrt({ supportedProviders: [] }),
        gpu: createMockGPU(false),
      });
      await assert.rejects(
        () => mgr.createSession('model.onnx'),
        { message: /All execution providers failed/ }
      );
    });

    it('フォールバック順序は webgpu → wasm (WebGL含まない)', async () => {
      const tried = [];
      const mgr = new WebGPUSessionManager({
        ort: {
          InferenceSession: {
            create: async (path, opts) => {
              const p = opts.executionProviders[0];
              const name = typeof p === 'string' ? p : p.name;
              tried.push(name);
              throw new Error('fail');
            },
          },
        },
        gpu: createMockGPU(true),
      });
      try { await mgr.createSession('model.onnx'); } catch {}
      assert.ok(!tried.includes('webgl'), 'WebGL should not be in fallback chain');
      assert.deepEqual(tried, ['webgpu', 'wasm']);
    });
  });

  describe('GPU容量チェック', () => {
    it('モデルサイズがGPU容量内ならtrueを返す', async () => {
      const mgr = new WebGPUSessionManager({
        ort: createMockOrt(),
        gpu: createMockGPU(true), // maxBufferSize=256MB
      });
      const ok = await mgr.checkGPUCapacity(26 * 1024 * 1024); // 26MB
      assert.equal(ok, true);
    });

    it('モデルサイズがGPU容量を超えるとfalseを返す', async () => {
      const mgr = new WebGPUSessionManager({
        ort: createMockOrt(),
        gpu: {
          requestAdapter: async () => ({
            requestDevice: async () => ({
              limits: { maxBufferSize: 50 * 1024 * 1024, maxStorageBufferBindingSize: 50 * 1024 * 1024 },
              destroy: () => {},
            }),
          }),
        },
      });
      // maxBufferSize=50MB, modelSize=100MB → false
      const ok = await mgr.checkGPUCapacity(100 * 1024 * 1024);
      assert.equal(ok, false);
    });

    it('maxStorageBufferBindingSizeが不足するとfalseを返す', async () => {
      const mgr = new WebGPUSessionManager({
        ort: createMockOrt(),
        gpu: {
          requestAdapter: async () => ({
            requestDevice: async () => ({
              limits: {
                maxBufferSize: 256 * 1024 * 1024,           // 256MB — enough
                maxStorageBufferBindingSize: 50 * 1024 * 1024, // 50MB — too small
              },
              destroy: () => {},
            }),
          }),
        },
      });
      const ok = await mgr.checkGPUCapacity(100 * 1024 * 1024); // 100MB
      assert.equal(ok, false);
    });

    it('GPU非対応時はfalseを返す', async () => {
      const mgr = new WebGPUSessionManager({
        ort: createMockOrt(),
        gpu: undefined,
      });
      const ok = await mgr.checkGPUCapacity(26 * 1024 * 1024);
      assert.equal(ok, false);
    });

    it('requestAdapterがnullを返した場合はfalseを返す', async () => {
      const mgr = new WebGPUSessionManager({
        ort: createMockOrt(),
        gpu: { requestAdapter: async () => null },
      });
      const ok = await mgr.checkGPUCapacity(26 * 1024 * 1024);
      assert.equal(ok, false);
    });
  });

  describe('int64 フォールバック', () => {
    it('int64入力を持つモデルではWebGPUをスキップしWASMにフォールバックする', async () => {
      const mgr = new WebGPUSessionManager({
        ort: {
          InferenceSession: {
            create: async (path, opts) => {
              const provider = (opts.executionProviders || ['wasm'])[0];
              return {
                inputNames: ['input', 'input_lengths', 'scales', 'lid'],
                outputNames: ['output'],
                inputMetadata: {
                  input: { dataType: 'int64' },
                  input_lengths: { dataType: 'int64' },
                  scales: { dataType: 'float32' },
                  lid: { dataType: 'int64' },
                },
                currentProvider: provider,
                run: async () => ({ output: { data: new Float32Array(100), dims: [1, 100] } }),
                release: () => {},
              };
            },
          },
        },
        gpu: createMockGPU(true),
      });
      const session = await mgr.createSession('model.onnx');
      assert.equal(mgr.currentProvider, 'wasm',
        'Should fall back to wasm when model uses int64 inputs');
    });

    it('float32のみのモデルではWebGPUが選択される', async () => {
      const mgr = new WebGPUSessionManager({
        ort: {
          InferenceSession: {
            create: async (path, opts) => {
              const provider = (opts.executionProviders || ['wasm'])[0];
              return {
                inputNames: ['x', 'y'],
                outputNames: ['output'],
                inputMetadata: {
                  x: { dataType: 'float32' },
                  y: { dataType: 'float32' },
                },
                currentProvider: provider,
                run: async () => ({ output: { data: new Float32Array(100), dims: [1, 100] } }),
                release: () => {},
              };
            },
          },
        },
        gpu: createMockGPU(true),
      });
      const session = await mgr.createSession('model.onnx');
      assert.equal(mgr.currentProvider, 'webgpu',
        'Should use webgpu when model has no int64 inputs');
    });

    it('inputMetadata未提供時はWebGPUを許可する (後方互換)', async () => {
      const mgr = new WebGPUSessionManager({
        ort: createMockOrt({ supportedProviders: ['webgpu', 'wasm'] }),
        gpu: createMockGPU(true),
      });
      const session = await mgr.createSession('model.onnx');
      assert.equal(mgr.currentProvider, 'webgpu',
        'Should allow webgpu when metadata is unavailable');
    });
  });

  describe('セッション設定', () => {
    it('graphOptimizationLevelがextendedに設定される', async () => {
      let capturedOptions;
      const mgr = new WebGPUSessionManager({
        ort: {
          InferenceSession: {
            create: async (path, opts) => {
              capturedOptions = opts;
              return { inputNames: [], outputNames: [], run: async () => ({}), release: () => {} };
            },
          },
        },
        gpu: createMockGPU(false),
      });
      await mgr.createSession('model.onnx');
      assert.equal(capturedOptions.graphOptimizationLevel, 'extended');
    });

    it('enableMemPatternがtrueに設定される', async () => {
      let capturedOptions;
      const mgr = new WebGPUSessionManager({
        ort: {
          InferenceSession: {
            create: async (path, opts) => {
              capturedOptions = opts;
              return { inputNames: [], outputNames: [], run: async () => ({}), release: () => {} };
            },
          },
        },
        gpu: createMockGPU(false),
      });
      await mgr.createSession('model.onnx');
      assert.equal(capturedOptions.enableMemPattern, true);
    });

    it('intraOpNumThreadsが設定されない (WASM非対応)', async () => {
      let capturedOptions;
      const mgr = new WebGPUSessionManager({
        ort: {
          InferenceSession: {
            create: async (path, opts) => {
              capturedOptions = opts;
              return { inputNames: [], outputNames: [], run: async () => ({}), release: () => {} };
            },
          },
        },
        gpu: createMockGPU(false),
      });
      await mgr.createSession('model.onnx');
      assert.equal(capturedOptions.intraOpNumThreads, undefined);
    });
  });
});
