/**
 * TDD Tests for SimpleResampler
 * Phase 2a: AudioWorklet移行 — サンプルレート変換
 *
 * テスト対象: src/wasm/openjtalk-web/src/resampler.js (未実装)
 */

import { strict as assert } from 'assert';
import { describe, it } from 'node:test';

let SimpleResampler;
try {
  const mod = await import('../../src/resampler.js');
  SimpleResampler = mod.SimpleResampler || mod.default;
} catch {
  SimpleResampler = null;
}

const skip = SimpleResampler === null;

describe('SimpleResampler', { skip }, () => {
  describe('アップサンプリング (22050Hz → 48000Hz)', () => {
    it('出力長が正しい (ratio ≈ 2.177)', () => {
      const resampler = new SimpleResampler(22050, 48000);
      const input = new Float32Array(22050); // 1秒分
      const output = resampler.resample(input);
      assert.equal(output.length, 48000);
    });

    it('無音入力には無音が出力される', () => {
      const resampler = new SimpleResampler(22050, 48000);
      const input = new Float32Array(1000); // ゼロ埋め
      const output = resampler.resample(input);
      const maxAbs = Math.max(...output.map(Math.abs));
      assert.equal(maxAbs, 0);
    });

    it('DC信号 (定数) は変換後も同じ値', () => {
      const resampler = new SimpleResampler(22050, 48000);
      const input = new Float32Array(1000).fill(0.5);
      const output = resampler.resample(input);
      // 線形補間なので定数は保持される
      for (let i = 0; i < output.length; i++) {
        assert.ok(Math.abs(output[i] - 0.5) < 1e-6, `sample ${i}: ${output[i]}`);
      }
    });

    it('出力値が-1.0〜1.0の範囲内', () => {
      const resampler = new SimpleResampler(22050, 48000);
      const input = new Float32Array(1000);
      // 正弦波 (440Hz)
      for (let i = 0; i < input.length; i++) {
        input[i] = Math.sin(2 * Math.PI * 440 * i / 22050);
      }
      const output = resampler.resample(input);
      for (let i = 0; i < output.length; i++) {
        assert.ok(output[i] >= -1.0 && output[i] <= 1.0, `sample ${i} out of range: ${output[i]}`);
      }
    });
  });

  describe('ダウンサンプリング (48000Hz → 22050Hz)', () => {
    it('出力長が正しい', () => {
      const resampler = new SimpleResampler(48000, 22050);
      const input = new Float32Array(48000);
      const output = resampler.resample(input);
      assert.equal(output.length, 22050);
    });
  });

  describe('同一レート (22050Hz → 22050Hz)', () => {
    it('入力と同じデータが出力される', () => {
      const resampler = new SimpleResampler(22050, 22050);
      const input = new Float32Array([0.1, 0.2, 0.3, 0.4, 0.5]);
      const output = resampler.resample(input);
      assert.equal(output.length, input.length);
      for (let i = 0; i < input.length; i++) {
        assert.ok(Math.abs(output[i] - input[i]) < 1e-6);
      }
    });
  });

  describe('エッジケース', () => {
    it('空の入力には空の出力', () => {
      const resampler = new SimpleResampler(22050, 48000);
      const output = resampler.resample(new Float32Array(0));
      assert.equal(output.length, 0);
    });

    it('1サンプル入力', () => {
      const resampler = new SimpleResampler(22050, 48000);
      const output = resampler.resample(new Float32Array([0.7]));
      assert.ok(output.length >= 1);
    });
  });
});
