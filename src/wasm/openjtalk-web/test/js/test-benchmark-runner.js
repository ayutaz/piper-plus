/**
 * TDD Tests for BenchmarkRunner & RegressionDetector
 * Phase 1: ベンチマーク基盤
 *
 * テスト対象: src/wasm/openjtalk-web/src/benchmark.js (未実装)
 */

import { strict as assert } from 'assert';
import { describe, it, beforeEach } from 'node:test';

// Node.js環境での performance API ポリフィル
if (typeof performance === 'undefined') {
  const { performance: perf } = await import('perf_hooks');
  globalThis.performance = perf;
}

let BenchmarkRunner, RegressionDetector;
try {
  const mod = await import('../../src/benchmark.js');
  BenchmarkRunner = mod.BenchmarkRunner;
  RegressionDetector = mod.RegressionDetector;
} catch {
  BenchmarkRunner = null;
  RegressionDetector = null;
}

const skip = BenchmarkRunner === null;

// --- BenchmarkRunner ---

describe('BenchmarkRunner', { skip }, () => {
  let runner;

  beforeEach(() => {
    runner = new BenchmarkRunner();
  });

  it('measureAsync()で非同期関数の実行時間を計測できる', async () => {
    const result = await runner.measureAsync('test-stage', async () => {
      await new Promise(r => setTimeout(r, 50));
      return 42;
    });
    assert.equal(result, 42);
    const summary = runner.getSummary();
    const entry = summary.find(e => e.name === 'test-stage');
    assert.ok(entry);
    assert.ok(parseFloat(entry.duration) >= 30, `Duration ${entry.duration} should be >= 30ms`);
  });

  it('複数ステージを順番に計測できる', async () => {
    await runner.measureAsync('stage-1', async () => 'a');
    await runner.measureAsync('stage-2', async () => 'b');
    const summary = runner.getSummary();
    assert.equal(summary.length, 2);
    assert.equal(summary[0].name, 'stage-1');
    assert.equal(summary[1].name, 'stage-2');
  });

  it('getSummary()はdurationをms文字列で返す', async () => {
    await runner.measureAsync('fast', async () => {});
    const summary = runner.getSummary();
    assert.ok(summary[0].duration.endsWith('ms'));
  });

  it('reset()で計測データをクリアできる', async () => {
    await runner.measureAsync('x', async () => {});
    runner.reset();
    assert.equal(runner.getSummary().length, 0);
  });
});

// --- RegressionDetector ---

describe('RegressionDetector', { skip: RegressionDetector === null }, () => {
  let detector;

  beforeEach(() => {
    detector = new RegressionDetector();
  });

  describe('基本検知', () => {
    it('しきい値内の変動はリグレッションとして検出しない', () => {
      const baseline = { 'Inference': 300 };
      const current = { 'Inference': 310 }; // +10ms (3.3%) — しきい値10%以内
      const regressions = detector.detect(baseline, current);
      assert.equal(regressions.length, 0);
    });

    it('しきい値を超える劣化をリグレッションとして検出する', () => {
      const baseline = { 'Inference': 300 };
      const current = { 'Inference': 400 }; // +100ms (33%) — しきい値10%超過
      const regressions = detector.detect(baseline, current);
      assert.equal(regressions.length, 1);
      assert.equal(regressions[0].metric, 'Inference');
    });

    it('改善 (負のdelta) はリグレッションとして検出しない', () => {
      const baseline = { 'Inference': 300 };
      const current = { 'Inference': 200 }; // -100ms (改善)
      const regressions = detector.detect(baseline, current);
      assert.equal(regressions.length, 0);
    });
  });

  describe('メトリック別しきい値', () => {
    it('Inference: 10%超過で検出', () => {
      const baseline = { 'Inference': 300 };
      const current = { 'Inference': 335 }; // +35ms (11.7%)
      const regressions = detector.detect(baseline, current);
      assert.equal(regressions.length, 1);
    });

    it('WASM Load: 5%超過で検出', () => {
      const baseline = { 'WASM Load': 200 };
      const current = { 'WASM Load': 260 }; // +60ms (30%) > 5%
      const regressions = detector.detect(baseline, current);
      assert.equal(regressions.length, 1);
    });

    it('未知メトリックはデフォルトしきい値 (5%, 50ms) を使用', () => {
      const baseline = { 'Custom Metric': 1000 };
      const current = { 'Custom Metric': 1040 }; // +40ms (4%) — 5%以内
      const regressions = detector.detect(baseline, current);
      assert.equal(regressions.length, 0);
    });
  });

  describe('重要度判定', () => {
    it('20%超過はcritical', () => {
      const baseline = { 'Inference': 300 };
      const current = { 'Inference': 400 }; // +33%
      const regressions = detector.detect(baseline, current);
      assert.equal(regressions[0].severity, 'critical');
    });

    it('20%以下の超過はhigh', () => {
      const baseline = { 'Inference': 300 };
      const current = { 'Inference': 345 }; // +15%
      const regressions = detector.detect(baseline, current);
      assert.equal(regressions[0].severity, 'high');
    });
  });
});
