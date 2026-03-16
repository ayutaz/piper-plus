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
