/**
 * Unit Tests for AudioResult.timing / AudioResult.hasTimingInfo
 * npm パッケージ: TTS 出力オーディオラッパー (タイミング情報)
 *
 * テスト対象: src/wasm/openjtalk-web/src/audio-result.js
 *
 * AudioResult は新たに以下の機能を持つ:
 *   - constructor(samples, sampleRate = 22050, timing = null)
 *   - get timing      -> TimingResult | null
 *   - get hasTimingInfo -> boolean
 *
 * 既存の samples / sampleRate / duration / toWav() がタイミング引数の有無で
 * 影響を受けないことも併せて検証する。
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { AudioResult } from '../../src/audio-result.js';

// -----------------------------------------------------------
// Sample TimingResult-like object used across tests.
// -----------------------------------------------------------
function makeSampleTiming() {
  return {
    phonemes: [
      { phoneme: 'ph_0', start_ms: 0, end_ms: 58, duration_ms: 58 },
      { phoneme: 'ph_1', start_ms: 58, end_ms: 150.8, duration_ms: 92.8 },
    ],
    total_duration_ms: 150.8,
    sample_rate: 22050,
  };
}

describe('AudioResult.timing / hasTimingInfo', () => {
  // -------------------------------------------------------
  // 1. constructor without timing
  // -------------------------------------------------------
  it('constructor without timing -> timing === null, hasTimingInfo === false', () => {
    const samples = new Float32Array([0.1, 0.2, 0.3]);
    const result = new AudioResult(samples, 22050);
    assert.strictEqual(result.timing, null);
    assert.strictEqual(result.hasTimingInfo, false);
  });

  // -------------------------------------------------------
  // 2. constructor with explicit null timing
  // -------------------------------------------------------
  it('constructor with explicit null timing -> timing === null, hasTimingInfo === false', () => {
    const samples = new Float32Array([0.1, 0.2, 0.3]);
    const result = new AudioResult(samples, 22050, null);
    assert.strictEqual(result.timing, null);
    assert.strictEqual(result.hasTimingInfo, false);
  });

  // -------------------------------------------------------
  // 3. constructor with timing object
  // -------------------------------------------------------
  it('constructor with timing object -> getter returns the same object', () => {
    const samples = new Float32Array([0.1, 0.2, 0.3]);
    const timing = makeSampleTiming();
    const result = new AudioResult(samples, 22050, timing);
    assert.strictEqual(result.timing, timing);
    assert.deepStrictEqual(result.timing, makeSampleTiming());
  });

  // -------------------------------------------------------
  // 4. hasTimingInfo true when timing is provided
  // -------------------------------------------------------
  it('hasTimingInfo === true when timing is provided', () => {
    const samples = new Float32Array([0.1, 0.2, 0.3]);
    const timing = makeSampleTiming();
    const result = new AudioResult(samples, 22050, timing);
    assert.strictEqual(result.hasTimingInfo, true);
  });

  // -------------------------------------------------------
  // 5. hasTimingInfo false with explicit null
  // -------------------------------------------------------
  it('hasTimingInfo === false when timing is explicit null', () => {
    const samples = new Float32Array([0.1, 0.2, 0.3]);
    const result = new AudioResult(samples, 22050, null);
    assert.strictEqual(result.hasTimingInfo, false);
  });

  // -------------------------------------------------------
  // 6. hasTimingInfo false with undefined
  // -------------------------------------------------------
  it('hasTimingInfo === false when timing is undefined', () => {
    const samples = new Float32Array([0.1, 0.2, 0.3]);
    // Passing undefined should fall back to the constructor default (null)
    // and therefore behave identically to omitting the argument.
    const result = new AudioResult(samples, 22050, undefined);
    assert.strictEqual(result.timing, null);
    assert.strictEqual(result.hasTimingInfo, false);
  });

  // -------------------------------------------------------
  // 7. timing getter returns the same reference for repeated calls
  // -------------------------------------------------------
  it('timing getter returns the same reference for repeated calls', () => {
    const samples = new Float32Array([0.1, 0.2, 0.3]);
    const timing = makeSampleTiming();
    const result = new AudioResult(samples, 22050, timing);
    const first = result.timing;
    const second = result.timing;
    assert.strictEqual(first, second);
    assert.strictEqual(first, timing);
  });

  // -------------------------------------------------------
  // 8. backward compatibility: omitting the timing argument
  // -------------------------------------------------------
  it('backward compatibility: omitting the timing argument defaults to null', () => {
    const samples = new Float32Array([0.1, 0.2, 0.3]);
    // Two-argument form (samples, sampleRate) used by all pre-timing callers.
    const result = new AudioResult(samples, 22050);
    assert.strictEqual(result.timing, null);
    assert.strictEqual(result.hasTimingInfo, false);
    // Single-argument form (samples) using the default sampleRate.
    const resultDefault = new AudioResult(samples);
    assert.strictEqual(resultDefault.timing, null);
    assert.strictEqual(resultDefault.hasTimingInfo, false);
    assert.strictEqual(resultDefault.sampleRate, 22050);
  });

  // -------------------------------------------------------
  // 9. samples getter still works with timing
  // -------------------------------------------------------
  it('samples getter is unaffected by timing', () => {
    const samples = new Float32Array([0.5, -0.5, 0.0, 0.25]);
    const timing = makeSampleTiming();
    const result = new AudioResult(samples, 22050, timing);
    assert.strictEqual(result.samples, samples);
    assert.strictEqual(result.samples.length, 4);
  });

  // -------------------------------------------------------
  // 10. sampleRate getter still works with timing
  // -------------------------------------------------------
  it('sampleRate getter is unaffected by timing', () => {
    const samples = new Float32Array(100);
    const timing = makeSampleTiming();
    const result = new AudioResult(samples, 44100, timing);
    assert.strictEqual(result.sampleRate, 44100);
  });

  // -------------------------------------------------------
  // 11. duration getter still works with timing
  // -------------------------------------------------------
  it('duration getter is unaffected by timing', () => {
    // 22050 samples / 22050 Hz = 1.0 second.
    const samples = new Float32Array(22050);
    const timing = makeSampleTiming();
    const result = new AudioResult(samples, 22050, timing);
    assert.strictEqual(result.duration, 1.0);
  });

  // -------------------------------------------------------
  // 12. toWav() still works with timing
  // -------------------------------------------------------
  it('toWav() returns a valid ArrayBuffer when timing is provided', () => {
    const samples = new Float32Array(100);
    const timing = makeSampleTiming();
    const result = new AudioResult(samples, 22050, timing);
    const wav = result.toWav();
    assert.ok(wav instanceof ArrayBuffer);
    // Sanity check: 44 byte WAV header + 100 samples * 2 bytes (PCM 16-bit, mono).
    assert.strictEqual(wav.byteLength, 44 + 100 * 2);
  });
});
