/**
 * Unit Tests for AudioResult
 * npm パッケージ: TTS 出力オーディオラッパー
 *
 * テスト対象: src/wasm/openjtalk-web/src/audio-result.js
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

describe('AudioResult', { skip }, () => {
  // -------------------------------------------------------
  // 1. 構築テスト
  // -------------------------------------------------------
  describe('構築', () => {
    it('Float32Array と sampleRate から構築できる', () => {
      const samples = new Float32Array([0.1, 0.2, 0.3]);
      const result = new AudioResult(samples, 44100);
      assert.ok(result instanceof AudioResult);
    });

    it('デフォルト sampleRate は 22050', () => {
      const samples = new Float32Array(10);
      const result = new AudioResult(samples);
      assert.equal(result.sampleRate, 22050);
    });

    it('samples プロパティが元の Float32Array を返す', () => {
      const samples = new Float32Array([0.5, -0.5, 0.0]);
      const result = new AudioResult(samples);
      assert.equal(result.samples, samples);
    });

    it('Float32Array 以外を渡すと TypeError', () => {
      assert.throws(() => new AudioResult([1, 2, 3]), TypeError);
    });

    it('sampleRate が正の数でない場合に TypeError', () => {
      const samples = new Float32Array(1);
      assert.throws(() => new AudioResult(samples, 0), TypeError);
      assert.throws(() => new AudioResult(samples, -1), TypeError);
      assert.throws(() => new AudioResult(samples, 'abc'), TypeError);
    });
  });

  // -------------------------------------------------------
  // 2. duration 計算
  // -------------------------------------------------------
  describe('duration 計算', () => {
    it('22050 サンプル / 22050Hz = 1.0 秒', () => {
      const result = new AudioResult(new Float32Array(22050), 22050);
      assert.equal(result.duration, 1.0);
    });

    it('44100 サンプル / 22050Hz = 2.0 秒', () => {
      const result = new AudioResult(new Float32Array(44100), 22050);
      assert.equal(result.duration, 2.0);
    });

    it('0 サンプル = 0.0 秒', () => {
      const result = new AudioResult(new Float32Array(0), 22050);
      assert.equal(result.duration, 0.0);
    });
  });

  // -------------------------------------------------------
  // 3. toWav() テスト
  // -------------------------------------------------------
  describe('toWav()', () => {
    it('ArrayBuffer を返す', () => {
      const result = new AudioResult(new Float32Array(100), 22050);
      const wav = result.toWav();
      assert.ok(wav instanceof ArrayBuffer);
    });

    it('WAV ヘッダーの先頭 4 バイトが "RIFF"', () => {
      const result = new AudioResult(new Float32Array(100), 22050);
      const wav = result.toWav();
      const view = new DataView(wav);
      assert.equal(readString(view, 0, 4), 'RIFF');
    });

    it('offset 8 に "WAVE" がある', () => {
      const result = new AudioResult(new Float32Array(100), 22050);
      const wav = result.toWav();
      const view = new DataView(wav);
      assert.equal(readString(view, 8, 4), 'WAVE');
    });

    it('fmt チャンク (offset 12) に "fmt " がある', () => {
      const result = new AudioResult(new Float32Array(100), 22050);
      const wav = result.toWav();
      const view = new DataView(wav);
      assert.equal(readString(view, 12, 4), 'fmt ');
    });

    it('サンプルレートが正しくエンコードされている (offset 24)', () => {
      const sampleRate = 22050;
      const result = new AudioResult(new Float32Array(100), sampleRate);
      const wav = result.toWav();
      const view = new DataView(wav);
      assert.equal(view.getUint32(24, true), sampleRate);
    });

    it('非デフォルト sampleRate (48000) も正しくエンコードされる', () => {
      const sampleRate = 48000;
      const result = new AudioResult(new Float32Array(100), sampleRate);
      const wav = result.toWav();
      const view = new DataView(wav);
      assert.equal(view.getUint32(24, true), sampleRate);
    });

    it('チャンネル数が 1 (モノラル) (offset 22)', () => {
      const result = new AudioResult(new Float32Array(100), 22050);
      const wav = result.toWav();
      const view = new DataView(wav);
      assert.equal(view.getUint16(22, true), 1);
    });

    it('ビット深度が 16 (offset 34)', () => {
      const result = new AudioResult(new Float32Array(100), 22050);
      const wav = result.toWav();
      const view = new DataView(wav);
      assert.equal(view.getUint16(34, true), 16);
    });

    it('オーディオフォーマットが PCM (1) (offset 20)', () => {
      const result = new AudioResult(new Float32Array(100), 22050);
      const wav = result.toWav();
      const view = new DataView(wav);
      assert.equal(view.getUint16(20, true), 1);
    });

    it('data チャンク (offset 36) に "data" がある', () => {
      const result = new AudioResult(new Float32Array(100), 22050);
      const wav = result.toWav();
      const view = new DataView(wav);
      assert.equal(readString(view, 36, 4), 'data');
    });

    it('ファイルサイズが正しい (44 ヘッダー + サンプル数 * 2)', () => {
      const numSamples = 100;
      const result = new AudioResult(new Float32Array(numSamples), 22050);
      const wav = result.toWav();
      assert.equal(wav.byteLength, 44 + numSamples * 2);
    });

    it('RIFF チャンクサイズ (offset 4) が fileSize - 8', () => {
      const numSamples = 100;
      const result = new AudioResult(new Float32Array(numSamples), 22050);
      const wav = result.toWav();
      const view = new DataView(wav);
      assert.equal(view.getUint32(4, true), wav.byteLength - 8);
    });

    it('data チャンクサイズ (offset 40) が サンプル数 * 2', () => {
      const numSamples = 100;
      const result = new AudioResult(new Float32Array(numSamples), 22050);
      const wav = result.toWav();
      const view = new DataView(wav);
      assert.equal(view.getUint32(40, true), numSamples * 2);
    });
  });

  // -------------------------------------------------------
  // 4. toBlob() テスト
  // -------------------------------------------------------
  describe('toBlob()', () => {
    // Node.js 18+ では globalThis.Blob が利用可能
    const hasBlob = typeof globalThis.Blob !== 'undefined';

    it('Blob を返す', { skip: !hasBlob }, () => {
      const result = new AudioResult(new Float32Array(100), 22050);
      const blob = result.toBlob();
      assert.ok(blob instanceof Blob);
    });

    it('type が "audio/wav"', { skip: !hasBlob }, () => {
      const result = new AudioResult(new Float32Array(100), 22050);
      const blob = result.toBlob();
      assert.equal(blob.type, 'audio/wav');
    });

    it('Blob サイズが toWav() の byteLength と一致', { skip: !hasBlob }, () => {
      const result = new AudioResult(new Float32Array(100), 22050);
      const blob = result.toBlob();
      const wav = result.toWav();
      assert.equal(blob.size, wav.byteLength);
    });
  });

  // -------------------------------------------------------
  // 5. サンプル値の変換テスト
  // -------------------------------------------------------
  describe('サンプル値の Float32 -> Int16 変換', () => {
    /**
     * toWav() の PCM データ領域から指定インデックスの Int16 値を読み取る。
     * @param {ArrayBuffer} wav
     * @param {number}      index  サンプルインデックス (0-based)
     * @returns {number}     Int16 値 (-32768 ~ 32767)
     */
    function readSampleInt16(wav, index) {
      const view = new DataView(wav);
      return view.getInt16(44 + index * 2, true);
    }

    it('Float32 0.0 -> Int16 0', () => {
      const result = new AudioResult(new Float32Array([0.0]), 22050);
      const wav = result.toWav();
      assert.equal(readSampleInt16(wav, 0), 0);
    });

    it('Float32 1.0 -> Int16 32767', () => {
      const result = new AudioResult(new Float32Array([1.0]), 22050);
      const wav = result.toWav();
      assert.equal(readSampleInt16(wav, 0), 32767);
    });

    it('Float32 -1.0 -> Int16 -32768', () => {
      const result = new AudioResult(new Float32Array([-1.0]), 22050);
      const wav = result.toWav();
      assert.equal(readSampleInt16(wav, 0), -32768);
    });

    it('クリッピング: Float32 1.5 -> Int16 32767', () => {
      const result = new AudioResult(new Float32Array([1.5]), 22050);
      const wav = result.toWav();
      assert.equal(readSampleInt16(wav, 0), 32767);
    });

    it('クリッピング: Float32 -1.5 -> Int16 -32768', () => {
      const result = new AudioResult(new Float32Array([-1.5]), 22050);
      const wav = result.toWav();
      assert.equal(readSampleInt16(wav, 0), -32768);
    });

    it('Float32 0.5 -> 正の Int16 中間値', () => {
      const result = new AudioResult(new Float32Array([0.5]), 22050);
      const wav = result.toWav();
      const value = readSampleInt16(wav, 0);
      // 0.5 * 0x7FFF = 16383.5 -> 切り捨てで 16383
      assert.equal(value, Math.floor(0.5 * 0x7FFF));
    });

    it('Float32 -0.5 -> 負の Int16 中間値', () => {
      const result = new AudioResult(new Float32Array([-0.5]), 22050);
      const wav = result.toWav();
      const value = readSampleInt16(wav, 0);
      // -0.5 * 0x8000 = -16384
      assert.equal(value, Math.floor(-0.5 * 0x8000));
    });

    it('複数サンプルが正しく変換される', () => {
      const input = new Float32Array([0.0, 1.0, -1.0, 0.5]);
      const result = new AudioResult(input, 22050);
      const wav = result.toWav();
      assert.equal(readSampleInt16(wav, 0), 0);
      assert.equal(readSampleInt16(wav, 1), 32767);
      assert.equal(readSampleInt16(wav, 2), -32768);
      assert.equal(readSampleInt16(wav, 3), Math.floor(0.5 * 0x7FFF));
    });
  });
});
