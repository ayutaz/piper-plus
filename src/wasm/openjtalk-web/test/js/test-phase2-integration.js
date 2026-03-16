/**
 * Phase 2 Integration Tests — M3-M7 component interactions
 *
 * Verifies that BenchmarkRunner, CacheManager, SimpleResampler,
 * WebGPUSessionManager, StreamingTTSPipeline, TextChunker, and
 * TypedArrayPool work correctly together.
 */

import { strict as assert } from 'assert';
import { describe, it, beforeEach } from 'node:test';

// Node.js環境での performance API ポリフィル
if (typeof performance === 'undefined') {
  const { performance: perf } = await import('perf_hooks');
  globalThis.performance = perf;
}

let BenchmarkRunner, CacheManager, SimpleResampler, WebGPUSessionManager, StreamingTTSPipeline, TextChunker, TypedArrayPool;
let allAvailable = true;
try {
  BenchmarkRunner = (await import('../../src/benchmark.js')).BenchmarkRunner;
  CacheManager = (await import('../../src/cache-manager.js')).CacheManager;
  SimpleResampler = (await import('../../src/resampler.js')).SimpleResampler;
  WebGPUSessionManager = (await import('../../src/webgpu-session-manager.js')).WebGPUSessionManager;
  const streaming = await import('../../src/streaming-pipeline.js');
  StreamingTTSPipeline = streaming.StreamingTTSPipeline;
  TextChunker = streaming.TextChunker;
  TypedArrayPool = (await import('../../src/memory-pool.js')).TypedArrayPool;
} catch {
  allAvailable = false;
}
const skip = !allAvailable;

// --- Mock helpers ---

import { MockIndexedDB } from '../helpers/mock-indexeddb.js';

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

// --- Integration Tests ---

describe('Phase 2 Integration: BenchmarkRunner + Resampler', { skip }, () => {
  it('measureAsyncでresampler.resample()の実行時間を計測できる', async () => {
    const runner = new BenchmarkRunner();
    const resampler = new SimpleResampler(22050, 48000);
    const input = new Float32Array(22050); // 1秒分
    for (let i = 0; i < input.length; i++) {
      input[i] = Math.sin(2 * Math.PI * 440 * i / 22050);
    }

    const output = await runner.measureAsync('resample', async () => {
      return resampler.resample(input);
    });

    assert.equal(output.length, 48000);
    const summary = runner.getSummary();
    assert.equal(summary.length, 1);
    assert.equal(summary[0].name, 'resample');
    assert.ok(summary[0].duration.endsWith('ms'));
  });
});

describe('Phase 2 Integration: CacheManager + getOrFetch', { skip }, () => {
  it('キャッシュミス→fetch→キャッシュヒットのサイクルが正しく動作する', async () => {
    const cache = new CacheManager({ dbFactory: () => new MockIndexedDB() });
    let fetchCount = 0;
    const fetcher = async () => {
      fetchCount++;
      return new ArrayBuffer(512);
    };

    // 1回目: キャッシュミス → fetcherが呼ばれる
    const data1 = await cache.getOrFetch('model.onnx', 'v1.0', fetcher);
    assert.equal(fetchCount, 1);
    assert.ok(data1);

    // 2回目: キャッシュヒット → fetcherは呼ばれない
    const data2 = await cache.getOrFetch('model.onnx', 'v1.0', fetcher);
    assert.equal(fetchCount, 1);
    assert.ok(data2);

    // 3回目: キャッシュに存在することを直接確認
    const valid = await cache.isValid('model.onnx', 'v1.0');
    assert.equal(valid, true);
  });
});

describe('Phase 2 Integration: Resampler + Streaming', { skip }, () => {
  it('TextChunkerで分割した各チャンクの推論結果をresamplerで処理できる', async () => {
    const chunks = TextChunker.split('今日は良い天気です。明日も晴れるでしょう。', 'ja');
    assert.equal(chunks.length, 2);

    const resampler = new SimpleResampler(22050, 48000);
    const resampledOutputs = [];

    for (const chunk of chunks) {
      // シミュレート: 各チャンクの推論結果として22050Hzの音声を生成
      const rawAudio = new Float32Array(2205); // 0.1秒分 @22050Hz
      for (let i = 0; i < rawAudio.length; i++) {
        rawAudio[i] = Math.sin(2 * Math.PI * 440 * i / 22050) * 0.5;
      }
      const resampled = resampler.resample(rawAudio);
      resampledOutputs.push(resampled);
    }

    assert.equal(resampledOutputs.length, 2);
    // 各出力は48000Hzにリサンプリングされた長さ
    const expectedLen = Math.round(2205 * 48000 / 22050);
    for (const out of resampledOutputs) {
      assert.equal(out.length, expectedLen);
    }
  });
});

describe('Phase 2 Integration: WebGPU + Benchmark', { skip }, () => {
  it('BenchmarkRunnerでセッション作成時間を計測できる', async () => {
    const runner = new BenchmarkRunner();
    const mgr = new WebGPUSessionManager({
      ort: createMockOrt({ supportedProviders: ['wasm'] }),
      gpu: createMockGPU(false),
    });

    const session = await runner.measureAsync('session-create', async () => {
      return mgr.createSession('model.onnx');
    });

    assert.ok(session);
    assert.equal(mgr.currentProvider, 'wasm');
    const summary = runner.getSummary();
    assert.equal(summary.length, 1);
    assert.equal(summary[0].name, 'session-create');
    assert.ok(parseFloat(summary[0].duration) >= 0);
  });
});

describe('Phase 2 Integration: TypedArrayPool + Resampler', { skip }, () => {
  it('プールから取得した配列をリサンプリングに使用し、返却できる', () => {
    const pool = new TypedArrayPool();
    const resampler = new SimpleResampler(22050, 48000);

    // プールからFloat32Arrayを取得
    const input = pool.getArray('float32', 1000);
    assert.equal(input.length, 1000);

    // 入力データを設定（DC信号）
    input.fill(0.5);

    // リサンプリング実行
    const output = resampler.resample(input);
    const expectedLen = Math.round(1000 * 48000 / 22050);
    assert.equal(output.length, expectedLen);

    // 出力が正しい値か確認（DC信号なので0.5のまま）
    for (let i = 0; i < output.length; i++) {
      assert.ok(Math.abs(output[i] - 0.5) < 1e-6, `sample ${i}: ${output[i]}`);
    }

    // 入力配列をプールに返却
    pool.returnArray('float32', 1000, input);

    // 返却後にゼロクリアされている
    assert.equal(input[0], 0);

    // 再取得するとプールからヒットする
    const reused = pool.getArray('float32', 1000);
    assert.equal(reused.length, 1000);
    const stats = pool.getStats();
    assert.equal(stats.hits, 1);
    assert.equal(stats.misses, 1);
  });
});

describe('Phase 2 Integration: Full pipeline', { skip }, () => {
  it('TextChunker→音素化→推論→resampler→onAudioChunkの全フロー', async () => {
    const resampler = new SimpleResampler(22050, 48000);
    const receivedChunks = [];

    const pipeline = new StreamingTTSPipeline({
      phonemize: async (text) => {
        // モック音素化: テキスト長に応じたID列を返す
        return Array.from({ length: text.length }, (_, i) => i + 1);
      },
      synthesize: async (ids) => {
        // モック推論: ID数に応じた22050Hz音声を生成
        const samples = ids.length * 100;
        const audio = new Float32Array(samples);
        for (let i = 0; i < samples; i++) {
          audio[i] = Math.sin(2 * Math.PI * 440 * i / 22050) * 0.3;
        }
        return audio;
      },
      onAudioChunk: (audio) => {
        // リサンプリングしてから格納
        const resampled = resampler.resample(audio);
        receivedChunks.push(resampled);
      },
    });

    await pipeline.synthesizeAndPlay('テスト。確認。', 'ja');

    // 2文に分割されるので2チャンク受信
    assert.equal(receivedChunks.length, 2);
    // 各チャンクは48000Hzにリサンプリングされている
    for (const chunk of receivedChunks) {
      assert.ok(chunk instanceof Float32Array);
      assert.ok(chunk.length > 0);
    }
  });
});

describe('Phase 2 Integration: CacheManager + version check', { skip }, () => {
  it('バージョン変更後にisValidがfalseを返す', async () => {
    const cache = new CacheManager({ dbFactory: () => new MockIndexedDB() });

    await cache.set('dict/sys.dic', new ArrayBuffer(1024), { version: 'v1.0' });

    // 同じバージョンならtrue
    const valid1 = await cache.isValid('dict/sys.dic', 'v1.0');
    assert.equal(valid1, true);

    // バージョンを更新
    await cache.set('dict/sys.dic', new ArrayBuffer(2048), { version: 'v2.0' });

    // 古いバージョンではfalse
    const valid2 = await cache.isValid('dict/sys.dic', 'v1.0');
    assert.equal(valid2, false);

    // 新しいバージョンではtrue
    const valid3 = await cache.isValid('dict/sys.dic', 'v2.0');
    assert.equal(valid3, true);
  });
});

describe('Phase 2 Integration: Resampler identity in pipeline', { skip }, () => {
  it('22050→22050のリサンプリングがパイプライン内で正しく動作する', async () => {
    const resampler = new SimpleResampler(22050, 22050);
    const receivedChunks = [];

    const pipeline = new StreamingTTSPipeline({
      phonemize: async (text) => [1, 2, 3],
      synthesize: async (ids) => {
        const audio = new Float32Array(5);
        audio[0] = 0.1; audio[1] = 0.2; audio[2] = 0.3; audio[3] = 0.4; audio[4] = 0.5;
        return audio;
      },
      onAudioChunk: (audio) => {
        const resampled = resampler.resample(audio);
        receivedChunks.push(resampled);
      },
    });

    await pipeline.synthesizeAndPlay('テスト。', 'ja');

    assert.equal(receivedChunks.length, 1);
    const output = receivedChunks[0];
    assert.equal(output.length, 5);
    // 同一レートなので値が保持される
    assert.ok(Math.abs(output[0] - 0.1) < 1e-6);
    assert.ok(Math.abs(output[1] - 0.2) < 1e-6);
    assert.ok(Math.abs(output[2] - 0.3) < 1e-6);
    assert.ok(Math.abs(output[3] - 0.4) < 1e-6);
    assert.ok(Math.abs(output[4] - 0.5) < 1e-6);
  });
});

describe('Phase 2 Integration: Pool stats after pipeline', { skip }, () => {
  it('パイプライン実行後にプールのhits/missesが正しく追跡される', async () => {
    const pool = new TypedArrayPool();
    const resampler = new SimpleResampler(22050, 48000);
    const audioLen = 1000;

    const pipeline = new StreamingTTSPipeline({
      phonemize: async (text) => [1, 2, 3],
      synthesize: async (ids) => {
        // プールからバッファを取得して推論結果を格納
        const buf = pool.getArray('float32', audioLen);
        buf.fill(0.25);
        return buf;
      },
      onAudioChunk: (audio) => {
        const resampled = resampler.resample(audio);
        // 使い終わった入力バッファをプールに返却
        pool.returnArray('float32', audioLen, audio);
      },
    });

    // 3文 = 3チャンク
    await pipeline.synthesizeAndPlay('文1。文2。文3。', 'ja');

    const stats = pool.getStats();
    // 3回getArray (miss) → 3回returnArray → プールに3つ蓄積
    // ただし、推論は順次実行されるため、返却後に次のgetArrayでhitする場合がある
    assert.equal(stats.misses + stats.hits, 3, `Total gets should be 3, got misses=${stats.misses} hits=${stats.hits}`);
    assert.ok(stats.misses >= 1, 'At least 1 miss (first allocation)');
    assert.equal(typeof stats.evictions, 'number');
  });
});

describe('Phase 2 Integration: Error resilience', { skip }, () => {
  it('synthesize失敗時にパイプラインがエラーを適切に伝播する', async () => {
    const receivedChunks = [];

    const pipeline = new StreamingTTSPipeline({
      phonemize: async (text) => [1, 2, 3],
      synthesize: async (ids) => {
        throw new Error('GPU out of memory');
      },
      onAudioChunk: (audio) => {
        receivedChunks.push(audio);
      },
    });

    await assert.rejects(
      () => pipeline.synthesizeAndPlay('テスト。', 'ja'),
      { message: /GPU out of memory/ }
    );

    // エラー発生時はonAudioChunkが呼ばれない
    assert.equal(receivedChunks.length, 0);
  });
});
