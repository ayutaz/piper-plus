/**
 * WAV 生成エッジケーステスト for AudioResult
 *
 * テスト対象: src/wasm/openjtalk-web/src/audio-result.js
 * 0サンプル/1サンプル/大量サンプル、各種サンプルレート、
 * チャンクサイズ検証、極値サンプルデータ、正弦波整合性。
 */

import { strict as assert } from 'assert';
import { describe, it } from 'node:test';

let AudioResult;
try {
  const mod = await import('../../src/audio-result.js');
  AudioResult = mod.AudioResult || mod.default;
} catch {
  AudioResult = null;
}

const skip = AudioResult === null;

/**
 * DataView から ASCII 文字列を読み取るヘルパー。
 * @param {DataView} view
 * @param {number}   offset
 * @param {number}   length
 * @returns {string}
 */
function readString(view, offset, length) {
  let str = '';
  for (let i = 0; i < length; i++) {
    str += String.fromCharCode(view.getUint8(offset + i));
  }
  return str;
}

/**
 * WAV データ領域から指定インデックスの Int16 サンプル値を読み取る。
 * @param {ArrayBuffer} wav        WAV ArrayBuffer
 * @param {number}      sampleIndex サンプルインデックス (0-based)
 * @returns {number}    Int16 値 (-32768 ~ 32767)
 */
function readInt16(wav, sampleIndex) {
  return new DataView(wav).getInt16(44 + sampleIndex * 2, true);
}

describe('AudioResult WAV 生成エッジケース', { skip }, () => {
  // -------------------------------------------------------
  // 1. 0サンプル / 1サンプル / 大量サンプルのファイルサイズ
  // -------------------------------------------------------
  describe('ファイルサイズ境界', () => {
    it('0サンプルの WAV は正確に 44 バイト', () => {
      // Arrange
      const audio = new AudioResult(new Float32Array(0), 22050);

      // Act
      const wav = audio.toWav();

      // Assert
      assert.equal(wav.byteLength, 44);
    });

    it('1サンプルの WAV は正確に 46 バイト', () => {
      // Arrange
      const audio = new AudioResult(new Float32Array([0.5]), 22050);

      // Act
      const wav = audio.toWav();

      // Assert
      assert.equal(wav.byteLength, 46);
    });

    it('大量サンプル (100000) の WAV ファイルサイズ', () => {
      // Arrange
      const numSamples = 100000;
      const audio = new AudioResult(new Float32Array(numSamples), 22050);

      // Act
      const wav = audio.toWav();

      // Assert
      assert.equal(wav.byteLength, 44 + numSamples * 2);
    });
  });

  // -------------------------------------------------------
  // 2. 0サンプル WAV ヘッダー検証
  // -------------------------------------------------------
  describe('0サンプル WAV ヘッダー', () => {
    it('0サンプル WAV のヘッダーが正しい', () => {
      // Arrange
      const audio = new AudioResult(new Float32Array(0), 22050);

      // Act
      const wav = audio.toWav();
      const view = new DataView(wav);

      // Assert — RIFF, WAVE, fmt, data チャンクすべてが有効
      assert.deepStrictEqual(
        [
          readString(view, 0, 4),
          readString(view, 8, 4),
          readString(view, 12, 4),
          readString(view, 36, 4),
        ],
        ['RIFF', 'WAVE', 'fmt ', 'data'],
      );
    });
  });

  // -------------------------------------------------------
  // 3. 各種サンプルレートの WAV ヘッダー
  // -------------------------------------------------------
  describe('サンプルレート別ヘッダー', () => {
    it('サンプルレート 8000Hz の WAV ヘッダー', () => {
      // Arrange
      const audio = new AudioResult(new Float32Array(10), 8000);

      // Act
      const wav = audio.toWav();
      const view = new DataView(wav);

      // Assert
      assert.equal(view.getUint32(24, true), 8000);
    });

    it('サンプルレート 16000Hz の WAV ヘッダー', () => {
      // Arrange
      const audio = new AudioResult(new Float32Array(10), 16000);

      // Act
      const wav = audio.toWav();
      const view = new DataView(wav);

      // Assert
      assert.equal(view.getUint32(24, true), 16000);
    });

    it('サンプルレート 44100Hz の WAV ヘッダー', () => {
      // Arrange
      const audio = new AudioResult(new Float32Array(10), 44100);

      // Act
      const wav = audio.toWav();
      const view = new DataView(wav);

      // Assert
      assert.equal(view.getUint32(24, true), 44100);
    });

    it('サンプルレート 48000Hz の WAV ヘッダー', () => {
      // Arrange
      const audio = new AudioResult(new Float32Array(10), 48000);

      // Act
      const wav = audio.toWav();
      const view = new DataView(wav);

      // Assert
      assert.equal(view.getUint32(24, true), 48000);
    });
  });

  // -------------------------------------------------------
  // 4. チャンクサイズ検証
  // -------------------------------------------------------
  describe('チャンクサイズ', () => {
    it('WAV の RIFF チャンクサイズが正しい', () => {
      // Arrange
      const numSamples = 256;
      const audio = new AudioResult(new Float32Array(numSamples), 22050);

      // Act
      const wav = audio.toWav();
      const view = new DataView(wav);

      // Assert — RIFF チャンクサイズ = ファイル全体 - 8
      assert.equal(view.getUint32(4, true), wav.byteLength - 8);
    });

    it('WAV の data チャンクサイズが正しい', () => {
      // Arrange
      const numSamples = 256;
      const audio = new AudioResult(new Float32Array(numSamples), 22050);

      // Act
      const wav = audio.toWav();
      const view = new DataView(wav);

      // Assert — data チャンクサイズ = numSamples * 2
      assert.equal(view.getUint32(40, true), numSamples * 2);
    });
  });

  // -------------------------------------------------------
  // 5. 極値サンプルデータ
  // -------------------------------------------------------
  describe('極値サンプルデータ', () => {
    it('全サンプルが 0.0 の場合の WAV データ', () => {
      // Arrange
      const numSamples = 8;
      const audio = new AudioResult(new Float32Array(numSamples), 22050);

      // Act
      const wav = audio.toWav();

      // Assert — 全 Int16 値が 0
      assert.ok(
        Array.from({ length: numSamples }, (_, i) => readInt16(wav, i))
          .every((v) => v === 0),
      );
    });

    it('全サンプルが 1.0 の場合の WAV データ', () => {
      // Arrange
      const numSamples = 8;
      const samples = new Float32Array(numSamples).fill(1.0);
      const audio = new AudioResult(samples, 22050);

      // Act
      const wav = audio.toWav();

      // Assert — 全 Int16 値が 32767
      assert.ok(
        Array.from({ length: numSamples }, (_, i) => readInt16(wav, i))
          .every((v) => v === 32767),
      );
    });

    it('全サンプルが -1.0 の場合の WAV データ', () => {
      // Arrange
      const numSamples = 8;
      const samples = new Float32Array(numSamples).fill(-1.0);
      const audio = new AudioResult(samples, 22050);

      // Act
      const wav = audio.toWav();

      // Assert — 全 Int16 値が -32768
      assert.ok(
        Array.from({ length: numSamples }, (_, i) => readInt16(wav, i))
          .every((v) => v === -32768),
      );
    });
  });

  // -------------------------------------------------------
  // 6. 正弦波データの WAV 変換整合性
  // -------------------------------------------------------
  describe('正弦波整合性', () => {
    it('正弦波データの WAV 変換整合性', () => {
      // Arrange — 440Hz 正弦波、1周期分
      const sampleRate = 22050;
      const freq = 440;
      const numSamples = Math.floor(sampleRate / freq);
      const samples = new Float32Array(numSamples);
      for (let i = 0; i < numSamples; i++) {
        samples[i] = Math.sin((2 * Math.PI * freq * i) / sampleRate);
      }
      const audio = new AudioResult(samples, sampleRate);

      // Act
      const wav = audio.toWav();

      // Assert — 正弦波にはゼロでないサンプルが含まれるはず
      assert.ok(
        Array.from({ length: numSamples }, (_, i) => readInt16(wav, i))
          .some((v) => v !== 0),
      );
    });
  });
});
