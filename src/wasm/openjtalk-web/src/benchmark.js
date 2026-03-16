/**
 * BenchmarkRunner & RegressionDetector
 * Phase 1: ベンチマーク基盤
 */

export class BenchmarkRunner {
  constructor() {
    this._entries = [];
  }

  /**
   * Measure execution time of an async function.
   * @param {string} name - Stage name
   * @param {Function} asyncFn - Async function to measure
   * @returns {*} The return value of asyncFn
   */
  async measureAsync(name, asyncFn) {
    const start = performance.now();
    const result = await asyncFn();
    const end = performance.now();
    this._entries.push({ name, duration: end - start });
    return result;
  }

  /**
   * Get summary of all measurements.
   * @returns {Array<{name: string, duration: string}>}
   */
  getSummary() {
    return this._entries.map(e => ({
      name: e.name,
      duration: `${e.duration.toFixed(2)}ms`,
    }));
  }

  /**
   * Clear all measurement entries.
   */
  reset() {
    this._entries = [];
  }
}

/**
 * Metric-specific regression thresholds (percentage).
 */
const THRESHOLDS = {
  'Inference': 10,
  'WASM Load': 5,
};
const DEFAULT_THRESHOLD = 5;

export class RegressionDetector {
  constructor() {}

  /**
   * Detect performance regressions between baseline and current measurements.
   * @param {Object} baseline - { metricName: msValue }
   * @param {Object} current  - { metricName: msValue }
   * @returns {Array<{metric: string, severity: string, delta: number, percentage: number}>}
   */
  detect(baseline, current) {
    const regressions = [];

    for (const metric of Object.keys(baseline)) {
      if (!(metric in current)) continue;

      const base = baseline[metric];
      const curr = current[metric];
      const delta = curr - base;

      // Only positive delta (slower) counts as regression
      if (delta <= 0) continue;

      // Skip metrics with zero baseline to avoid division by zero
      if (base === 0) continue;

      const percentage = (delta / base) * 100;
      const threshold = THRESHOLDS[metric] ?? DEFAULT_THRESHOLD;

      if (percentage > threshold) {
        const severity = percentage > 20 ? 'critical' : 'high';
        regressions.push({ metric, severity, delta, percentage });
      }
    }

    return regressions;
  }
}
