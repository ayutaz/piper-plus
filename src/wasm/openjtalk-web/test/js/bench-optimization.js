/**
 * WebGPU最適化ベンチマーク
 *
 * Node.jsで計測可能な最適化コンポーネントのパフォーマンスを測定
 */

import { BenchmarkRunner } from '../../src/benchmark.js';
import { SimpleResampler } from '../../src/resampler.js';
import { TypedArrayPool } from '../../src/memory-pool.js';
import { CacheManager } from '../../src/cache-manager.js';
import { TextChunker, StreamingTTSPipeline, ChunkCrossfader } from '../../src/streaming-pipeline.js';

// performance polyfill
if (typeof performance === 'undefined') {
  const { performance: perf } = await import('perf_hooks');
  globalThis.performance = perf;
}

const runner = new BenchmarkRunner();

// ============================================================
// MockIndexedDB for CacheManager
// ============================================================
import { MockIndexedDB } from '../helpers/mock-indexeddb.js';

console.log('='.repeat(60));
console.log('  WebGPU最適化ベンチマーク');
console.log('='.repeat(60));
console.log();

// ============================================================
// 1. Resampler: 22050Hz → 48000Hz
// ============================================================
console.log('■ 1. Resampler (22050Hz → 48000Hz)');
console.log('-'.repeat(40));

const resampler = new SimpleResampler(22050, 48000);

// テスト用の正弦波を生成
function generateSineWave(sampleRate, durationSec, freq = 440) {
  const len = Math.round(sampleRate * durationSec);
  const buf = new Float32Array(len);
  for (let i = 0; i < len; i++) {
    buf[i] = Math.sin(2 * Math.PI * freq * i / sampleRate);
  }
  return buf;
}

for (const duration of [0.5, 1.0, 3.0, 5.0, 10.0]) {
  const input = generateSineWave(22050, duration);
  const iterations = 10;
  let totalMs = 0;
  for (let i = 0; i < iterations; i++) {
    const start = performance.now();
    resampler.resample(input);
    totalMs += performance.now() - start;
  }
  const avgMs = totalMs / iterations;
  const inputSamples = input.length;
  const outputSamples = Math.round(inputSamples * 48000 / 22050);
  console.log(`  ${duration}s (${inputSamples}→${outputSamples}サンプル): ${avgMs.toFixed(2)}ms (平均${iterations}回)`);
}
console.log();

// ============================================================
// 2. TypedArrayPool: プール有/無の比較
// ============================================================
console.log('■ 2. TypedArrayPool 効果測定');
console.log('-'.repeat(40));

const pool = new TypedArrayPool();
const ALLOC_ITERATIONS = 10000;
const ARRAY_SIZE = 48000; // 1秒分@48kHz

// プールなし: 毎回new Float32Array
{
  const start = performance.now();
  for (let i = 0; i < ALLOC_ITERATIONS; i++) {
    const arr = new Float32Array(ARRAY_SIZE);
    arr[0] = 1.0; // 使用をシミュレート
  }
  const elapsed = performance.now() - start;
  console.log(`  プールなし (${ALLOC_ITERATIONS}回 new Float32Array(${ARRAY_SIZE})): ${elapsed.toFixed(2)}ms`);
}

// プールあり: get/return サイクル
{
  const start = performance.now();
  for (let i = 0; i < ALLOC_ITERATIONS; i++) {
    const arr = pool.getArray('float32', ARRAY_SIZE);
    arr[0] = 1.0;
    pool.returnArray('float32', ARRAY_SIZE, arr);
  }
  const elapsed = performance.now() - start;
  const stats = pool.getStats();
  console.log(`  プールあり (${ALLOC_ITERATIONS}回 get+return): ${elapsed.toFixed(2)}ms`);
  console.log(`    hits: ${stats.hits}, misses: ${stats.misses}, hit率: ${(stats.hits / (stats.hits + stats.misses) * 100).toFixed(1)}%`);
}
console.log();

// ============================================================
// 3. TextChunker: 文分割パフォーマンス
// ============================================================
console.log('■ 3. TextChunker 文分割');
console.log('-'.repeat(40));

const jaText = 'これは長いテキストです。音声合成では文ごとに区切って処理します。そうすることで、最初の文の音声を再生しながら、次の文を並列で処理できます。これにより体感レイテンシが大幅に低下します。ストリーミング再生の基盤技術です。';
const enText = 'This is a long text for benchmarking. Speech synthesis processes text sentence by sentence. This allows playing the first sentence while processing the next one in parallel. Mr. Smith noted that this reduces perceived latency significantly. Dr. Johnson agreed with the assessment.';

{
  const iterations = 10000;
  const start = performance.now();
  for (let i = 0; i < iterations; i++) {
    TextChunker.split(jaText, 'ja');
  }
  const elapsed = performance.now() - start;
  const chunks = TextChunker.split(jaText, 'ja');
  console.log(`  日本語 (${jaText.length}文字→${chunks.length}チャンク): ${(elapsed / iterations * 1000).toFixed(1)}μs/回 (${iterations}回)`);
}

{
  const iterations = 10000;
  const start = performance.now();
  for (let i = 0; i < iterations; i++) {
    TextChunker.split(enText, 'en');
  }
  const elapsed = performance.now() - start;
  const chunks = TextChunker.split(enText, 'en');
  console.log(`  英語 (${enText.length}文字→${chunks.length}チャンク): ${(elapsed / iterations * 1000).toFixed(1)}μs/回 (${iterations}回)`);
}
console.log();

// ============================================================
// 4. CacheManager: キャッシュヒット/ミス比較
// ============================================================
console.log('■ 4. CacheManager キャッシュ効果');
console.log('-'.repeat(40));

const cache = new CacheManager({ dbFactory: () => new MockIndexedDB() });

// 模擬辞書データ (8ファイル, 実際のsys.dicは約20MB)
const DICT_FILES = ['char.bin', 'matrix.bin', 'sys.dic', 'unk.dic', 'left-id.def', 'pos-id.def', 'rewrite.def', 'right-id.def'];
const MOCK_DICT_SIZE = 1024 * 1024; // 1MB/ファイル (実際は合計23MB)

// キャッシュミス (初回fetch): ネットワーク遅延シミュレート
{
  const start = performance.now();
  for (const file of DICT_FILES) {
    await cache.getOrFetch(`dict/${file}`, 'v1.0', async () => {
      // fetchのシミュレーション (実際は50-200ms/ファイル)
      return new ArrayBuffer(MOCK_DICT_SIZE);
    });
  }
  const elapsed = performance.now() - start;
  console.log(`  初回ロード (キャッシュミス, ${DICT_FILES.length}ファイル): ${elapsed.toFixed(2)}ms`);
}

// キャッシュヒット (2回目): IndexedDBから
{
  const start = performance.now();
  for (const file of DICT_FILES) {
    await cache.getOrFetch(`dict/${file}`, 'v1.0', async () => {
      throw new Error('Should not fetch!');
    });
  }
  const elapsed = performance.now() - start;
  console.log(`  2回目ロード (キャッシュヒット, ${DICT_FILES.length}ファイル): ${elapsed.toFixed(2)}ms`);
}

// 実環境のネットワーク遅延込み推定
console.log();
console.log('  【実環境推定 (辞書23MB, 50Mbps)】');
console.log('    初回: ネットワーク ~3.7s + IndexedDB書込 ~100ms = ~3.8s');
console.log('    2回目: IndexedDB読込 ~50ms (95%以上削減)');
console.log();

// ============================================================
// 5. StreamingPipeline: シーケンシャル vs パイプライン
// ============================================================
console.log('■ 5. StreamingTTSPipeline パイプライン並列化効果');
console.log('-'.repeat(40));

const PHONEMIZE_MS = 20;  // 音素化 20ms/文
const SYNTHESIZE_MS = 100; // 推論 100ms/文
const testText = '今日は良い天気です。明日も晴れるでしょう。来週は雨かもしれません。気温は20度くらいです。過ごしやすい日が続きます。';
const chunks = TextChunker.split(testText, 'ja');
const numChunks = chunks.length;

// シーケンシャル実行 (最適化なし)
{
  const start = performance.now();
  for (let i = 0; i < numChunks; i++) {
    await new Promise(r => setTimeout(r, PHONEMIZE_MS));
    await new Promise(r => setTimeout(r, SYNTHESIZE_MS));
  }
  const sequential = performance.now() - start;
  console.log(`  シーケンシャル (${numChunks}文): ${sequential.toFixed(0)}ms`);
  console.log(`    = ${numChunks} × (${PHONEMIZE_MS}ms音素化 + ${SYNTHESIZE_MS}ms推論)`);

  // パイプライン実行 (StreamingTTSPipeline)
  const audioChunks = [];
  const pipeline = new StreamingTTSPipeline({
    phonemize: async (text) => {
      await new Promise(r => setTimeout(r, PHONEMIZE_MS));
      return [1, 2, 3];
    },
    synthesize: async (ids) => {
      await new Promise(r => setTimeout(r, SYNTHESIZE_MS));
      return new Float32Array(22050);
    },
    onAudioChunk: (audio) => audioChunks.push(audio),
  });

  const pipelineStart = performance.now();
  await pipeline.synthesizeAndPlay(testText, 'ja');
  const pipelined = performance.now() - pipelineStart;

  const improvement = ((sequential - pipelined) / sequential * 100).toFixed(1);
  console.log(`  パイプライン (${numChunks}文): ${pipelined.toFixed(0)}ms`);
  console.log(`    → ${improvement}% 高速化`);
  console.log(`    TTFB (最初の音声まで): ~${PHONEMIZE_MS + SYNTHESIZE_MS}ms`);
}
console.log();

// ============================================================
// 6. ChunkCrossfader: オーバーヘッド
// ============================================================
console.log('■ 6. ChunkCrossfader オーバーヘッド');
console.log('-'.repeat(40));

const crossfader = new ChunkCrossfader(50, 22050);
const chunkSize = 22050; // 1秒分
{
  const iterations = 100;
  const start = performance.now();
  for (let i = 0; i < iterations; i++) {
    const chunk = new Float32Array(chunkSize).fill(Math.random());
    crossfader.addChunk(chunk);
  }
  const elapsed = performance.now() - start;
  console.log(`  50msクロスフェード (${chunkSize}サンプル/チャンク × ${iterations}回): ${elapsed.toFixed(2)}ms`);
  console.log(`  = ${(elapsed / iterations).toFixed(3)}ms/チャンク (リアルタイム比 ${(elapsed / iterations / (chunkSize / 22050 * 1000) * 100).toFixed(2)}%)`);
}
console.log();

// ============================================================
// 7. BenchmarkRunner でまとめ
// ============================================================
console.log('■ 7. 総合ベンチマーク (BenchmarkRunner)');
console.log('-'.repeat(40));

const summaryRunner = new BenchmarkRunner();

await summaryRunner.measureAsync('Resampler 1s (22050→48000)', async () => {
  const input = generateSineWave(22050, 1.0);
  resampler.resample(input);
});

await summaryRunner.measureAsync('TextChunker 日本語 1000回', async () => {
  for (let i = 0; i < 1000; i++) TextChunker.split(jaText, 'ja');
});

await summaryRunner.measureAsync('CacheManager get (ヒット)', async () => {
  for (const file of DICT_FILES) {
    await cache.getOrFetch(`dict/${file}`, 'v1.0', async () => new ArrayBuffer(0));
  }
});

await summaryRunner.measureAsync('MemoryPool 1000回 get+return', async () => {
  const p = new TypedArrayPool();
  for (let i = 0; i < 1000; i++) {
    const arr = p.getArray('float32', 4096);
    p.returnArray('float32', 4096, arr);
  }
});

await summaryRunner.measureAsync('Crossfade 50ms (22050サンプル)', async () => {
  const cf = new ChunkCrossfader(50, 22050);
  for (let i = 0; i < 10; i++) {
    cf.addChunk(new Float32Array(22050).fill(0.5));
  }
});

console.log();
const summary = summaryRunner.getSummary();
for (const entry of summary) {
  console.log(`  ${entry.name}: ${entry.duration}`);
}

console.log();
console.log('='.repeat(60));
console.log('  ベンチマーク完了');
console.log('='.repeat(60));
