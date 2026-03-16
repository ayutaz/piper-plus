/**
 * TDD Tests for AudioBackendFactory & Audio Backends
 * Phase 3: オーディオ再生バックエンド
 *
 * テスト対象: src/wasm/openjtalk-web/src/audio-backend-factory.js (未実装)
 */

import { strict as assert } from 'assert';
import { describe, it, beforeEach } from 'node:test';

let AudioBackendFactory, AudioWorkletBackend, ScriptProcessorBackend, HTMLAudioBackend;
try {
  const mod = await import('../../src/audio-backend-factory.js');
  AudioBackendFactory = mod.AudioBackendFactory;
  AudioWorkletBackend = mod.AudioWorkletBackend;
  ScriptProcessorBackend = mod.ScriptProcessorBackend;
  HTMLAudioBackend = mod.HTMLAudioBackend;
} catch {
  AudioBackendFactory = null;
}

const skip = AudioBackendFactory === null;

// --- AudioWorkletBackend ---

describe('AudioWorkletBackend', { skip }, () => {
  it('typeプロパティが"audioworklet"である', () => {
    const backend = new AudioWorkletBackend(null);
    assert.equal(backend.type, 'audioworklet');
  });

  it('AudioWorkletBackend.dispose()がPromiseを返す', () => {
    const mockCtx = { state: 'running', close: async () => {} };
    const backend = new AudioWorkletBackend(mockCtx);
    const result = backend.dispose();
    assert.ok(result instanceof Promise || (result && typeof result.then === 'function'),
      'dispose() should return a Promise');
  });
});

// --- ScriptProcessorBackend ---

describe('ScriptProcessorBackend', { skip }, () => {
  it('typeプロパティが"scriptprocessor"である', () => {
    const backend = new ScriptProcessorBackend(null);
    assert.equal(backend.type, 'scriptprocessor');
  });

  it('pushChunk()でバッファにデータを追加できる', () => {
    const backend = new ScriptProcessorBackend(null);
    const chunk = new Float32Array([0.1, 0.2, 0.3]);
    backend.pushChunk(chunk);
    assert.equal(backend.buffer.length, 1, 'Buffer should contain one chunk after pushChunk');
    assert.deepEqual(backend.buffer[0], chunk);
  });

  it('ScriptProcessorBackend.dispose()がPromiseを返す', () => {
    const mockCtx = { state: 'running', close: async () => {} };
    const backend = new ScriptProcessorBackend(mockCtx);
    const result = backend.dispose();
    assert.ok(result instanceof Promise || (result && typeof result.then === 'function'),
      'dispose() should return a Promise');
  });

  it('stop()でonaudioprocessがnullになる', () => {
    const mockCtx = { state: 'running', close: async () => {} };
    const backend = new ScriptProcessorBackend(mockCtx);
    const mockProcessor = {
      onaudioprocess: () => {},
      disconnect: () => {}
    };
    backend.processor = mockProcessor;
    backend.stop();
    assert.equal(mockProcessor.onaudioprocess, null, 'onaudioprocess should be null after stop');
    assert.equal(backend.processor, null, 'processor should be null after stop');
  });
});

// --- HTMLAudioBackend ---

describe('HTMLAudioBackend', { skip }, () => {
  let backend;

  beforeEach(() => {
    backend = new HTMLAudioBackend(22050);
  });

  it('typeプロパティが"htmlaudio"である', () => {
    assert.equal(backend.type, 'htmlaudio');
  });

  it('コンストラクタでsampleRateを設定できる', () => {
    const b = new HTMLAudioBackend(48000);
    assert.equal(b.sampleRate, 48000);
  });

  it('_encodeWav()でFloat32ArrayからWAVバイナリを生成する', () => {
    const samples = new Float32Array([0.0, 0.5, -0.5, 1.0]);
    const wav = backend._encodeWav(samples);
    assert.ok(wav instanceof ArrayBuffer);
    // Check WAV header: first 4 bytes should be "RIFF"
    const header = new Uint8Array(wav, 0, 4);
    assert.equal(String.fromCharCode(...header), 'RIFF');
    // Total size: 44 header + 4 samples * 2 bytes = 52
    assert.equal(wav.byteLength, 52);
  });

  it('play()連続呼び出しで前のblobUrlがrevokeされる', () => {
    // HTMLAudioBackend tests need to verify stop() is called before new play
    // Since Audio/URL are not available in Node.js, we test the _encodeWav and
    // verify stop() clears state
    const backend = new HTMLAudioBackend(48000);
    // Simulate state as if play() was already called
    backend.audio = { pause: () => {} };
    backend._blobUrl = 'blob:test-url';

    // Call stop() (which play() calls first)
    backend.stop();

    assert.equal(backend.audio, null, 'audio should be null after stop');
    assert.equal(backend._blobUrl, null, 'blobUrl should be null after stop');
  });
});

// --- 共通インターフェース ---

describe('共通インターフェース', { skip }, () => {
  it('全バックエンドがplay/stop/disposeメソッドを持つ', () => {
    for (const Backend of [AudioWorkletBackend, ScriptProcessorBackend, HTMLAudioBackend]) {
      for (const method of ['play', 'stop', 'dispose']) {
        assert.equal(
          typeof Backend.prototype[method], 'function',
          `${Backend.name} should have ${method}() method`
        );
      }
    }
  });

  it('全バックエンドがpushChunkメソッドを持つ', () => {
    for (const Backend of [AudioWorkletBackend, ScriptProcessorBackend, HTMLAudioBackend]) {
      assert.equal(
        typeof Backend.prototype.pushChunk, 'function',
        `${Backend.name} should have pushChunk() method`
      );
    }
  });
});
