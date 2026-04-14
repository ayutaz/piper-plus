/**
 * Unit tests for the phoneme timing module.
 *
 * テスト対象: src/wasm/openjtalk-web/src/timing.js
 *
 * Verifies frame -> millisecond conversion, error handling, and serializers
 * (JSON / TSV / SRT) for byte-for-byte parity with the Rust/Go/Python
 * implementations.
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  DEFAULT_HOP_LENGTH,
  durationsToTiming,
  timingToJson,
  timingToJsonCompact,
  timingToTsv,
  timingToSrt,
} from '../../src/timing.js';

// Frame time at 22050 Hz with 256 hop length: (256 / 22050) * 1000 ≈ 11.60998 ms
const FRAME_TIME_22050_256 = (256 / 22050) * 1000;
const EPS = 0.1;

const approxEqual = (actual, expected, eps = EPS) =>
  Math.abs(actual - expected) < eps;

describe('durationsToTiming - basic conversion', () => {
  it('converts three phonemes correctly at 22050 Hz / 256 hop', () => {
    const result = durationsToTiming([10, 20, 15], 22050);

    assert.strictEqual(result.phonemes.length, 3);
    assert.strictEqual(result.sample_rate, 22050);

    // First phoneme starts at 0, lasts 10 frames * 11.60998 ≈ 116.09977
    assert.strictEqual(result.phonemes[0].start_ms, 0);
    assert.ok(
      approxEqual(result.phonemes[0].duration_ms, 116.09977),
      `duration_ms[0] = ${result.phonemes[0].duration_ms}, expected ≈ 116.09977`,
    );

    // Second phoneme starts where first ended ≈ 116.09977
    assert.ok(
      approxEqual(result.phonemes[1].start_ms, 116.09977),
      `start_ms[1] = ${result.phonemes[1].start_ms}, expected ≈ 116.09977`,
    );

    // Total = 45 frames * 11.60998 ≈ 522.449
    assert.ok(
      approxEqual(result.total_duration_ms, 522.449),
      `total_duration_ms = ${result.total_duration_ms}, expected ≈ 522.449`,
    );
  });
});

describe('durationsToTiming - DEFAULT_HOP_LENGTH', () => {
  it('exports DEFAULT_HOP_LENGTH equal to 256', () => {
    assert.strictEqual(DEFAULT_HOP_LENGTH, 256);
  });

  it('uses DEFAULT_HOP_LENGTH when hopLength argument is omitted', () => {
    const a = durationsToTiming([5, 5], 22050);
    const b = durationsToTiming([5, 5], 22050, DEFAULT_HOP_LENGTH);
    assert.deepStrictEqual(a, b);
  });
});

describe('durationsToTiming - edge cases', () => {
  it('handles all-zero durations', () => {
    const result = durationsToTiming([0, 0, 0], 22050);
    assert.strictEqual(result.phonemes.length, 3);
    for (const p of result.phonemes) {
      assert.strictEqual(p.start_ms, 0);
      assert.strictEqual(p.end_ms, 0);
      assert.strictEqual(p.duration_ms, 0);
    }
    assert.strictEqual(result.total_duration_ms, 0);
  });

  it('clamps negative durations to zero without throwing', () => {
    // Suppress the warning emitted for the negative entry to keep test output clean.
    const originalWarn = console.warn;
    console.warn = () => {};
    try {
      const result = durationsToTiming([-5, 10], 22050);
      assert.strictEqual(result.phonemes.length, 2);
      assert.strictEqual(result.phonemes[0].duration_ms, 0);
      assert.strictEqual(result.phonemes[0].start_ms, 0);
      assert.strictEqual(result.phonemes[0].end_ms, 0);
      // Second phoneme should still progress normally, starting at 0.
      assert.strictEqual(result.phonemes[1].start_ms, 0);
      assert.ok(
        approxEqual(result.phonemes[1].duration_ms, 10 * FRAME_TIME_22050_256),
        `duration_ms[1] = ${result.phonemes[1].duration_ms}`,
      );
    } finally {
      console.warn = originalWarn;
    }
  });

  it('returns empty result for empty input array', () => {
    const result = durationsToTiming([], 22050);
    assert.deepStrictEqual(result.phonemes, []);
    assert.strictEqual(result.total_duration_ms, 0);
    assert.strictEqual(result.sample_rate, 22050);
  });
});

describe('durationsToTiming - validation errors', () => {
  it('throws when phonemeTokens length mismatches durations length', () => {
    assert.throws(
      () => durationsToTiming([10, 20, 15], 22050, 256, ['a', 'b']),
      /length mismatch/,
    );
  });

  it('throws when sampleRate is zero', () => {
    assert.throws(() => durationsToTiming([10], 0), /sampleRate must be positive/);
  });

  it('throws when sampleRate is negative', () => {
    assert.throws(
      () => durationsToTiming([10], -22050),
      /sampleRate must be positive/,
    );
  });

  it('throws when hopLength is zero', () => {
    assert.throws(
      () => durationsToTiming([10], 22050, 0),
      /hopLength must be positive/,
    );
  });

  it('throws when hopLength is negative', () => {
    assert.throws(
      () => durationsToTiming([10], 22050, -256),
      /hopLength must be positive/,
    );
  });
});

describe('durationsToTiming - timing structure invariants', () => {
  it('maintains continuity: phonemes[i].end_ms === phonemes[i+1].start_ms', () => {
    const result = durationsToTiming([7, 13, 3, 25, 1], 22050);
    for (let i = 0; i < result.phonemes.length - 1; i++) {
      assert.strictEqual(
        result.phonemes[i].end_ms,
        result.phonemes[i + 1].start_ms,
        `gap between phoneme ${i} and ${i + 1}`,
      );
    }
  });

  it('first phoneme always starts at zero', () => {
    const result = durationsToTiming([42, 17, 8], 22050);
    assert.strictEqual(result.phonemes[0].start_ms, 0);
  });

  it('total_duration_ms equals last phoneme end_ms', () => {
    const result = durationsToTiming([10, 20, 15, 8], 22050);
    const last = result.phonemes[result.phonemes.length - 1];
    assert.strictEqual(result.total_duration_ms, last.end_ms);
  });
});

describe('durationsToTiming - sample rate variations', () => {
  it('produces different timings for different sample rates', () => {
    const at22050 = durationsToTiming([10, 20, 15], 22050);
    const at16000 = durationsToTiming([10, 20, 15], 16000);

    // 16000 Hz frame time = 256/16000 * 1000 = 16ms (slower clock -> longer durations)
    // 22050 Hz frame time ≈ 11.60998ms
    assert.notStrictEqual(at22050.total_duration_ms, at16000.total_duration_ms);
    assert.ok(at16000.total_duration_ms > at22050.total_duration_ms);

    // Verify exact 16000 Hz value: 45 frames * (256/16000)*1000 = 720ms
    assert.ok(
      approxEqual(at16000.total_duration_ms, 720),
      `16000Hz total = ${at16000.total_duration_ms}, expected ≈ 720`,
    );
  });
});

describe('durationsToTiming - phoneme tokens', () => {
  it('uses provided phoneme tokens when given', () => {
    const result = durationsToTiming([10, 20, 15], 22050, 256, ['a', 'b', 'c']);
    assert.strictEqual(result.phonemes[0].phoneme, 'a');
    assert.strictEqual(result.phonemes[1].phoneme, 'b');
    assert.strictEqual(result.phonemes[2].phoneme, 'c');
  });

  it('falls back to ph_${i} format when tokens are not provided', () => {
    const result = durationsToTiming([10, 20, 15], 22050);
    assert.strictEqual(result.phonemes[0].phoneme, 'ph_0');
    assert.strictEqual(result.phonemes[1].phoneme, 'ph_1');
    assert.strictEqual(result.phonemes[2].phoneme, 'ph_2');
  });
});

describe('durationsToTiming - input types', () => {
  it('accepts Float32Array input', () => {
    const result = durationsToTiming(new Float32Array([10, 20, 15]), 22050);
    assert.strictEqual(result.phonemes.length, 3);
    assert.ok(approxEqual(result.total_duration_ms, 522.449));
  });

  it('produces identical results for Float32Array and plain array', () => {
    const arr = durationsToTiming([10, 20, 15], 22050);
    const f32 = durationsToTiming(new Float32Array([10, 20, 15]), 22050);
    assert.deepStrictEqual(arr, f32);
  });
});

describe('timingToJson', () => {
  it('returns valid JSON parseable as TimingResult', () => {
    const result = durationsToTiming([10, 20, 15], 22050, 256, ['a', 'b', 'c']);
    const json = timingToJson(result);
    const parsed = JSON.parse(json);

    assert.ok(Array.isArray(parsed.phonemes));
    assert.strictEqual(parsed.phonemes.length, 3);
    assert.ok('total_duration_ms' in parsed);
    assert.ok('sample_rate' in parsed);
    assert.strictEqual(parsed.sample_rate, 22050);
  });

  it('produces pretty-printed (indented) JSON with newlines', () => {
    const result = durationsToTiming([10, 20], 22050);
    const json = timingToJson(result);
    assert.ok(json.includes('\n'), 'pretty-printed JSON should contain newlines');
  });
});

describe('timingToJsonCompact', () => {
  it('produces single-line JSON without newlines', () => {
    const result = durationsToTiming([10, 20, 15], 22050);
    const json = timingToJsonCompact(result);
    assert.strictEqual(json.includes('\n'), false);
  });

  it('produces parseable JSON with the same data as pretty form', () => {
    const result = durationsToTiming([10, 20, 15], 22050, 256, ['a', 'b', 'c']);
    const compact = JSON.parse(timingToJsonCompact(result));
    const pretty = JSON.parse(timingToJson(result));
    assert.deepStrictEqual(compact, pretty);
  });
});

describe('timingToTsv', () => {
  it('starts with the exact header line', () => {
    const result = durationsToTiming([10, 20, 15], 22050);
    const tsv = timingToTsv(result);
    const firstLine = tsv.split('\n')[0];
    assert.strictEqual(firstLine, 'start_ms\tend_ms\tduration_ms\tphoneme');
  });

  it('contains one data row per phoneme', () => {
    const result = durationsToTiming([10, 20, 15, 8], 22050);
    const tsv = timingToTsv(result);
    const lines = tsv.split('\n').filter((l) => l.length > 0);
    // header + 4 data rows
    assert.strictEqual(lines.length, 5);
  });

  it('each data row has 4 tab-separated fields', () => {
    const result = durationsToTiming([10, 20, 15], 22050, 256, ['a', 'b', 'c']);
    const tsv = timingToTsv(result);
    const dataLines = tsv.split('\n').slice(1).filter((l) => l.length > 0);
    for (const line of dataLines) {
      assert.strictEqual(line.split('\t').length, 4);
    }
  });
});

describe('timingToSrt', () => {
  it('contains sequential cue numbers (1, 2, 3, ...)', () => {
    const result = durationsToTiming([10, 20, 15], 22050, 256, ['a', 'b', 'c']);
    const srt = timingToSrt(result);
    assert.ok(srt.includes('1\n'), 'should contain cue 1');
    assert.ok(srt.includes('2\n'), 'should contain cue 2');
    assert.ok(srt.includes('3\n'), 'should contain cue 3');
  });

  it('uses --> as timestamp separator and , as ms separator', () => {
    const result = durationsToTiming([10, 20], 22050);
    const srt = timingToSrt(result);
    assert.ok(srt.includes('-->'), 'should contain --> separator');
    assert.ok(srt.includes(','), 'should contain , for milliseconds');
  });

  it('separates entries with blank lines (\\n\\n)', () => {
    const result = durationsToTiming([10, 20, 15], 22050);
    const srt = timingToSrt(result);
    assert.ok(srt.includes('\n\n'), 'should contain blank line separators');
  });

  it('uses provided phoneme tokens in the cue text', () => {
    const result = durationsToTiming([10, 20, 15], 22050, 256, ['a', 'b', 'c']);
    const srt = timingToSrt(result);
    assert.ok(srt.includes('a'), 'cue should contain phoneme "a"');
    assert.ok(srt.includes('b'), 'cue should contain phoneme "b"');
    assert.ok(srt.includes('c'), 'cue should contain phoneme "c"');
  });
});


// ---------------------------------------------------------------------------
// Extended invariants and extreme values (P0/P1 from review)
// ---------------------------------------------------------------------------

describe('durationsToTiming - extended invariants', () => {
  it('all start_ms, end_ms, duration_ms are non-negative', () => {
    const result = durationsToTiming([0, 5, 10, 3], 22050);
    for (const p of result.phonemes) {
      assert.ok(p.start_ms >= 0, `start_ms should be >= 0, got ${p.start_ms}`);
      assert.ok(p.end_ms >= 0, `end_ms should be >= 0, got ${p.end_ms}`);
      assert.ok(p.duration_ms >= 0, `duration_ms should be >= 0, got ${p.duration_ms}`);
    }
  });

  it('timestamps are monotonically non-decreasing', () => {
    const result = durationsToTiming([5, 10, 8, 12, 3], 22050);
    for (let i = 0; i < result.phonemes.length - 1; i++) {
      assert.ok(
        result.phonemes[i].start_ms <= result.phonemes[i + 1].start_ms,
        `start_ms[${i}]=${result.phonemes[i].start_ms} should be <= start_ms[${i + 1}]=${result.phonemes[i + 1].start_ms}`
      );
      assert.ok(
        result.phonemes[i].end_ms <= result.phonemes[i + 1].end_ms,
        `end_ms[${i}]=${result.phonemes[i].end_ms} should be <= end_ms[${i + 1}]=${result.phonemes[i + 1].end_ms}`
      );
    }
  });

  it('total_duration_ms equals sum of individual duration_ms', () => {
    const result = durationsToTiming([7, 13, 3, 25, 1], 22050);
    const sum = result.phonemes.reduce((acc, p) => acc + p.duration_ms, 0);
    assert.ok(
      Math.abs(result.total_duration_ms - sum) < 1e-6,
      `total ${result.total_duration_ms} should equal sum ${sum}`
    );
  });
});

// ---------------------------------------------------------------------------
// Extreme values
// ---------------------------------------------------------------------------

describe('durationsToTiming - extreme values', () => {
  it('handles very large duration values (1,000,000 frames)', () => {
    const result = durationsToTiming([1_000_000], 22050);
    const expected = 1_000_000 * (256 / 22050) * 1000; // ≈ 11,609,977 ms
    assert.ok(
      Math.abs(result.phonemes[0].duration_ms - expected) < 1.0,
      `expected ~${expected}, got ${result.phonemes[0].duration_ms}`
    );
    assert.ok(result.total_duration_ms > 40_000, 'total should exceed 40 seconds');
  });

  it('handles very small sample rates (100 Hz, hop=10)', () => {
    const result = durationsToTiming([1], 100, 10);
    // 1 frame * (10/100) * 1000 = 100 ms
    assert.ok(
      Math.abs(result.phonemes[0].duration_ms - 100.0) < 1e-6,
      `expected 100.0, got ${result.phonemes[0].duration_ms}`
    );
  });

  it('handles 8000 Hz sample rate', () => {
    const result = durationsToTiming([10], 8000);
    // 10 * (256/8000) * 1000 = 320 ms
    assert.ok(Math.abs(result.phonemes[0].duration_ms - 320.0) < 0.01);
  });

  it('handles 48000 Hz sample rate', () => {
    const result = durationsToTiming([10], 48000);
    // 10 * (256/48000) * 1000 ≈ 53.333 ms
    const expected = 10 * (256 / 48000) * 1000;
    assert.ok(Math.abs(result.phonemes[0].duration_ms - expected) < 0.01);
  });
});

// ---------------------------------------------------------------------------
// JSON roundtrip and TSV numeric parseability
// ---------------------------------------------------------------------------

describe('timingToJson - roundtrip', () => {
  it('JSON roundtrip preserves all fields', () => {
    const result = durationsToTiming([4, 8, 6], 22050, 256, ['s', 't', 'u']);
    const json = timingToJson(result);
    const parsed = JSON.parse(json);

    assert.strictEqual(parsed.sample_rate, 22050);
    assert.strictEqual(parsed.phonemes.length, 3);

    // Verify sum invariant survived roundtrip
    const sum = parsed.phonemes.reduce((acc, p) => acc + p.duration_ms, 0);
    assert.ok(
      Math.abs(parsed.total_duration_ms - sum) < 0.01,
      `total should equal sum of durations: ${parsed.total_duration_ms} vs ${sum}`
    );

    // Verify phoneme names preserved in order
    const names = parsed.phonemes.map((p) => p.phoneme);
    assert.deepStrictEqual(names, ['s', 't', 'u']);
  });
});

describe('timingToTsv - numeric parseability', () => {
  it('all TSV numeric columns parse as valid finite numbers', () => {
    const result = durationsToTiming([10, 20], 22050, 256, ['a', 'b']);
    const tsv = timingToTsv(result);
    const lines = tsv.split('\n').filter((l) => l.length > 0);

    // Skip header, verify data rows
    for (let i = 1; i < lines.length; i++) {
      const cols = lines[i].split('\t');
      assert.strictEqual(cols.length, 4);

      const start = parseFloat(cols[0]);
      const end = parseFloat(cols[1]);
      const dur = parseFloat(cols[2]);

      assert.ok(Number.isFinite(start), `start_ms should parse: ${cols[0]}`);
      assert.ok(Number.isFinite(end), `end_ms should parse: ${cols[1]}`);
      assert.ok(Number.isFinite(dur), `duration_ms should parse: ${cols[2]}`);

      assert.ok(start >= 0, 'start_ms must be non-negative');
      assert.ok(end >= start, 'end_ms must be >= start_ms');
      assert.ok(dur >= 0, 'duration_ms must be non-negative');
    }
  });
});
