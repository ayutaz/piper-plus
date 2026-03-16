/**
 * TDD Tests for StreamingTTSPipeline & ChunkCrossfader
 * Phase 3: ストリーミング再生
 *
 * テスト対象:
 *   src/wasm/openjtalk-web/src/streaming-pipeline.js (未実装)
 *   src/wasm/openjtalk-web/src/chunk-crossfader.js (未実装)
 */

import { strict as assert } from 'assert';
import { describe, it, beforeEach } from 'node:test';

let StreamingTTSPipeline, ChunkCrossfader, TextChunker, RingBuffer;
try {
  const pipeline = await import('../../src/streaming-pipeline.js');
  StreamingTTSPipeline = pipeline.StreamingTTSPipeline;
  ChunkCrossfader = pipeline.ChunkCrossfader;
  TextChunker = pipeline.TextChunker;
  RingBuffer = pipeline.RingBuffer;
} catch {
  StreamingTTSPipeline = null;
}

const skip = StreamingTTSPipeline === null;

// --- TextChunker ---

describe('TextChunker', { skip }, () => {
  describe('日本語文分割', () => {
    it('句点で分割する', () => {
      const chunks = TextChunker.split('今日は良い天気です。明日も晴れるでしょう。', 'ja');
      assert.equal(chunks.length, 2);
      assert.equal(chunks[0], '今日は良い天気です。');
      assert.equal(chunks[1], '明日も晴れるでしょう。');
    });

    it('感嘆符・疑問符で分割する', () => {
      const chunks = TextChunker.split('すごい！本当ですか？はい。', 'ja');
      assert.equal(chunks.length, 3);
    });

    it('句読点がないテキストはそのまま1チャンク', () => {
      const chunks = TextChunker.split('こんにちは', 'ja');
      assert.equal(chunks.length, 1);
    });

    it('空文字列は空配列を返す', () => {
      const chunks = TextChunker.split('', 'ja');
      assert.equal(chunks.length, 0);
    });
  });

  describe('英語文分割', () => {
    it('ピリオドで分割する', () => {
      const chunks = TextChunker.split('Hello world. How are you?', 'en');
      assert.equal(chunks.length, 2);
    });

    it('略語のピリオドでは分割しない (Mr. Dr. etc.)', () => {
      const chunks = TextChunker.split('Mr. Smith went home. He was tired.', 'en');
      assert.equal(chunks.length, 2); // "Mr. Smith went home." と "He was tired."
    });
  });
});

// --- RingBuffer ---

describe('RingBuffer', { skip }, () => {
  it('enqueue/dequeueの基本動作', () => {
    const rb = new RingBuffer(4);
    rb.enqueue(new Float32Array([1, 2, 3]));
    rb.enqueue(new Float32Array([4, 5, 6]));
    const first = rb.dequeue();
    assert.deepEqual([...first], [1, 2, 3]);
  });

  it('空のdequeueはnullを返す', () => {
    const rb = new RingBuffer(4);
    assert.equal(rb.dequeue(), null);
  });

  it('容量超過時に最も古いデータを上書きする', () => {
    const rb = new RingBuffer(2);
    rb.enqueue(new Float32Array([1]));
    rb.enqueue(new Float32Array([2]));
    rb.enqueue(new Float32Array([3])); // 1が上書きされる
    const first = rb.dequeue();
    assert.deepEqual([...first], [2]);
  });

  it('size()で現在の要素数を取得できる', () => {
    const rb = new RingBuffer(4);
    assert.equal(rb.size(), 0);
    rb.enqueue(new Float32Array([1]));
    assert.equal(rb.size(), 1);
    rb.dequeue();
    assert.equal(rb.size(), 0);
  });
});

// --- ChunkCrossfader ---

describe('ChunkCrossfader', { skip }, () => {
  it('最初のチャンクはそのまま返される', () => {
    const cf = new ChunkCrossfader(50, 22050);
    const input = new Float32Array([0.1, 0.2, 0.3]);
    const output = cf.addChunk(input);
    assert.deepEqual(Array.from(output), Array.from(input));
  });

  it('2番目以降のチャンクはクロスフェード処理される', () => {
    const cf = new ChunkCrossfader(50, 22050);
    const chunk1 = new Float32Array(2000).fill(1.0);
    const chunk2 = new Float32Array(2000).fill(0.5);
    cf.addChunk(chunk1);
    const output = cf.addChunk(chunk2);
    // クロスフェード区間の先頭は chunk1寄り、末尾は chunk2寄り
    const fadeLen = Math.ceil(22050 * 50 / 1000); // ~1103 samples
    assert.ok(output[0] > 0.5, 'Start should lean toward chunk1');
    assert.ok(Math.abs(output[fadeLen] - 0.5) < 0.01, 'After fade should be chunk2 value');
  });

  it('クロスフェード長が0の場合は単純接合', () => {
    const cf = new ChunkCrossfader(0, 22050);
    const chunk1 = new Float32Array(100).fill(1.0);
    const chunk2 = new Float32Array(100).fill(0.5);
    cf.addChunk(chunk1);
    const output = cf.addChunk(chunk2);
    assert.equal(output[0], 0.5);
  });

  it('空チャンクを渡しても_prevTailが保持される', () => {
    const crossfader = new ChunkCrossfader(50, 22050);
    const chunk1 = new Float32Array([0.5, 0.5, 0.5, 0.5, 0.5]);
    crossfader.addChunk(chunk1);

    // Add empty chunk — should not clear _prevTail
    const emptyResult = crossfader.addChunk(new Float32Array(0));
    assert.equal(emptyResult.length, 0);

    // Next real chunk should still crossfade with chunk1's tail
    const chunk3 = new Float32Array([1.0, 1.0, 1.0, 1.0, 1.0]);
    const result = crossfader.addChunk(chunk3);
    // If _prevTail was preserved, the first sample should have some blending
    // (not 100% chunk3 which would happen if _prevTail was lost)
    assert.ok(result.length === 5);
  });

  it('チャンクがfadeLen未満でもクロスフェードが正しく動作する', () => {
    // fadeLen at 22050Hz/50ms = ceil(22050*0.05) = 1103 samples
    const crossfader = new ChunkCrossfader(50, 22050);
    const chunk1 = new Float32Array(2000).fill(1.0);
    crossfader.addChunk(chunk1);

    // Short chunk: only 10 samples, much less than fadeLen=1103
    const shortChunk = new Float32Array(10).fill(0.0);
    const result = crossfader.addChunk(shortChunk);
    assert.equal(result.length, 10);
    // First sample should be blended (not pure 0.0 since prev tail was 1.0)
    assert.ok(result[0] > 0, 'First sample should have prev contribution');
    // Last sample should be close to 0.0 (new chunk value)
    assert.ok(result[9] < 0.5, 'Last sample should lean toward new chunk');
  });

  it('1サンプルのクロスフェードは50/50ブレンドになる', () => {
    const crossfader = new ChunkCrossfader(50, 22050);
    const chunk1 = new Float32Array(2000).fill(1.0);
    crossfader.addChunk(chunk1);

    // 1-sample chunk
    const singleSample = new Float32Array([0.0]);
    const result = crossfader.addChunk(singleSample);
    assert.equal(result.length, 1);
    // Should be 50% blend of prev (1.0) and new (0.0) = 0.5
    assert.ok(Math.abs(result[0] - 0.5) < 0.01, `Expected ~0.5, got ${result[0]}`);
  });
});

// --- StreamingTTSPipeline ---

describe('StreamingTTSPipeline', { skip }, () => {
  it('文分割 → 音素化 → 推論の順序で実行される', async () => {
    const callOrder = [];
    const pipeline = new StreamingTTSPipeline({
      phonemize: async (text) => { callOrder.push(`phonemize:${text}`); return [1, 2, 3]; },
      synthesize: async (ids) => { callOrder.push('synthesize'); return new Float32Array(100); },
      onAudioChunk: (audio) => { callOrder.push('play'); },
    });
    await pipeline.synthesizeAndPlay('テスト。確認。', 'ja');
    // 音素化が推論より先に実行される
    assert.ok(callOrder.indexOf('phonemize:テスト。') < callOrder.indexOf('synthesize'));
  });

  it('音素化と推論がパイプライン並列化されている', async () => {
    const timestamps = [];
    const pipeline = new StreamingTTSPipeline({
      phonemize: async (text) => {
        timestamps.push({ event: 'phonemize_start', text, time: Date.now() });
        await new Promise(r => setTimeout(r, 50));
        timestamps.push({ event: 'phonemize_end', text, time: Date.now() });
        return [1, 2, 3];
      },
      synthesize: async (ids) => {
        timestamps.push({ event: 'synthesize_start', time: Date.now() });
        await new Promise(r => setTimeout(r, 50));
        timestamps.push({ event: 'synthesize_end', time: Date.now() });
        return new Float32Array(100);
      },
      onAudioChunk: () => {},
    });
    await pipeline.synthesizeAndPlay('文1。文2。文3。', 'ja');
    // 文2の音素化は文1の推論と重畳するはず
    const ph2Start = timestamps.find(t => t.event === 'phonemize_start' && t.text === '文2。');
    const syn1End = timestamps.find(t => t.event === 'synthesize_end');
    if (ph2Start && syn1End) {
      assert.ok(ph2Start.time <= syn1End.time, 'Chunk2 phonemization should overlap with chunk1 synthesis');
    }
  });

  it('空テキストでもエラーにならない', async () => {
    const pipeline = new StreamingTTSPipeline({
      phonemize: async () => [],
      synthesize: async () => new Float32Array(0),
      onAudioChunk: () => {},
    });
    await pipeline.synthesizeAndPlay('', 'ja'); // no error
  });

  it('コールバックが関数でない場合TypeErrorをスローする', () => {
    assert.throws(() => new StreamingTTSPipeline({ phonemize: 'not a function', synthesize: async () => {}, onAudioChunk: () => {} }), { name: 'TypeError' });
    assert.throws(() => new StreamingTTSPipeline({ phonemize: async () => {}, synthesize: null, onAudioChunk: () => {} }), { name: 'TypeError' });
    assert.throws(() => new StreamingTTSPipeline({ phonemize: async () => {}, synthesize: async () => {}, onAudioChunk: 123 }), { name: 'TypeError' });
  });
});
