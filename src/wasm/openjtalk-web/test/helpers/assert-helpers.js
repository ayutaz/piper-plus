/**
 * Shared assertion helpers for openjtalk-web tests.
 *
 * Reusable utilities that address recurring test patterns:
 * - Float32 approximate comparison (ONNX scales tensors)
 * - WAV header structural validation
 * - Unordered array containment checks
 * - Async error assertion
 * - mock.fn() call argument verification
 *
 * All helpers use node:assert/strict internally and produce
 * descriptive error messages on failure. No external dependencies.
 *
 * @module test/helpers/assert-helpers
 */

import assert from 'node:assert/strict';

/**
 * Float32 近似比較。ONNX の scales テンソルは Float32 で精度が落ちるため、
 * assert.equal ではなく epsilon 範囲での比較が必要。
 *
 * @param {number} actual   - 実測値
 * @param {number} expected - 期待値
 * @param {string} [message] - 失敗時のカスタムメッセージ
 * @param {number} [epsilon=1e-3] - 許容誤差 (デフォルト: 0.001)
 */
export function assertCloseTo(actual, expected, message, epsilon = 1e-3) {
  const diff = Math.abs(actual - expected);
  if (diff > epsilon) {
    const detail = message
      ? `${message}: `
      : '';
    assert.fail(
      `${detail}expected ${actual} to be close to ${expected} ` +
      `(epsilon=${epsilon}, actual diff=${diff})`,
    );
  }
}

/**
 * DataView から ASCII 文字列を読み取る内部ヘルパー。
 *
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
 * WAV ヘッダーの基本構造を検証する。
 * 44 バイトの PCM WAV ヘッダーが正しいかを一括チェック。
 *
 * 検証項目:
 * - RIFF / WAVE / fmt / data マーカー
 * - PCM format (audioFormat = 1)
 * - チャンネル数 (デフォルト: 1 = モノラル)
 * - サンプルレート
 * - ビット深度 (16-bit)
 * - data チャンクサイズ = numSamples * 2
 * - 総ファイルサイズ = 44 + numSamples * 2
 * - RIFF チャンクサイズ = ファイルサイズ - 8
 *
 * @param {ArrayBuffer} wav      - WAV ファイルの ArrayBuffer
 * @param {object}      expected - 期待値
 * @param {number}      expected.sampleRate   - サンプルレート (Hz)
 * @param {number}      expected.numSamples   - サンプル数
 * @param {number}      [expected.numChannels=1] - チャンネル数 (デフォルト: 1)
 */
export function assertValidWavHeader(wav, expected) {
  const { sampleRate, numSamples, numChannels = 1 } = expected;

  assert.ok(
    wav instanceof ArrayBuffer,
    'assertValidWavHeader: wav must be an ArrayBuffer',
  );
  assert.ok(
    wav.byteLength >= 44,
    `assertValidWavHeader: WAV must be at least 44 bytes, got ${wav.byteLength}`,
  );

  const view = new DataView(wav);

  // Chunk markers
  assert.equal(
    readString(view, 0, 4), 'RIFF',
    'WAV header: expected "RIFF" at offset 0',
  );
  assert.equal(
    readString(view, 8, 4), 'WAVE',
    'WAV header: expected "WAVE" at offset 8',
  );
  assert.equal(
    readString(view, 12, 4), 'fmt ',
    'WAV header: expected "fmt " at offset 12',
  );
  assert.equal(
    readString(view, 36, 4), 'data',
    'WAV header: expected "data" at offset 36',
  );

  // Audio format: PCM = 1
  assert.equal(
    view.getUint16(20, true), 1,
    'WAV header: audioFormat must be 1 (PCM)',
  );

  // Number of channels
  assert.equal(
    view.getUint16(22, true), numChannels,
    `WAV header: expected ${numChannels} channel(s), got ${view.getUint16(22, true)}`,
  );

  // Sample rate
  assert.equal(
    view.getUint32(24, true), sampleRate,
    `WAV header: expected sampleRate=${sampleRate}, got ${view.getUint32(24, true)}`,
  );

  // Bits per sample: 16
  assert.equal(
    view.getUint16(34, true), 16,
    'WAV header: bitsPerSample must be 16',
  );

  // Data chunk size = numSamples * numChannels * 2 (16-bit = 2 bytes)
  const expectedDataSize = numSamples * numChannels * 2;
  assert.equal(
    view.getUint32(40, true), expectedDataSize,
    `WAV header: data chunk size expected ${expectedDataSize}, ` +
    `got ${view.getUint32(40, true)}`,
  );

  // Total file size = 44 (header) + data size
  const expectedFileSize = 44 + expectedDataSize;
  assert.equal(
    wav.byteLength, expectedFileSize,
    `WAV file size expected ${expectedFileSize}, got ${wav.byteLength}`,
  );

  // RIFF chunk size = file size - 8
  assert.equal(
    view.getUint32(4, true), wav.byteLength - 8,
    `WAV header: RIFF chunk size expected ${wav.byteLength - 8}, ` +
    `got ${view.getUint32(4, true)}`,
  );
}

/**
 * 配列に指定された全要素が含まれることを検証する。
 * 順序は問わない。厳密等価 (===) で比較する。
 *
 * @param {Array} actual   - 実際の配列
 * @param {Array} expected - 含まれるべき要素の配列
 * @param {string} [message] - 失敗時のカスタムメッセージ
 */
export function assertContainsAll(actual, expected, message) {
  assert.ok(
    Array.isArray(actual),
    'assertContainsAll: actual must be an Array',
  );
  assert.ok(
    Array.isArray(expected),
    'assertContainsAll: expected must be an Array',
  );

  const missing = expected.filter((item) => !actual.includes(item));
  if (missing.length > 0) {
    const prefix = message ? `${message}: ` : '';
    assert.fail(
      `${prefix}missing ${missing.length} element(s) from actual array: ` +
      `${JSON.stringify(missing)}\n` +
      `  actual:   ${JSON.stringify(actual)}\n` +
      `  expected to contain: ${JSON.stringify(expected)}`,
    );
  }
}

/**
 * async 関数が指定された型のエラーをスローすることを検証する。
 *
 * node:assert の assert.rejects は存在するが、エラー型 + メッセージパターンの
 * 同時検証には冗長な記述が必要。このヘルパーは簡潔な API を提供する。
 *
 * @param {Function} asyncFn        - テスト対象の async 関数
 * @param {Function} errorType      - 期待されるエラーの型 (e.g., TypeError, Error)
 * @param {string|RegExp} [messagePattern] - エラーメッセージのパターン (省略可)
 */
export async function assertAsyncThrows(asyncFn, errorType, messagePattern) {
  let threw = false;
  let caughtError;

  try {
    await asyncFn();
  } catch (err) {
    threw = true;
    caughtError = err;
  }

  if (!threw) {
    assert.fail(
      `Expected async function to throw ${errorType.name}, but it did not throw`,
    );
  }

  assert.ok(
    caughtError instanceof errorType,
    `Expected error to be instance of ${errorType.name}, ` +
    `but got ${caughtError.constructor.name}: ${caughtError.message}`,
  );

  if (messagePattern !== undefined) {
    if (typeof messagePattern === 'string') {
      assert.ok(
        caughtError.message.includes(messagePattern),
        `Expected error message to include "${messagePattern}", ` +
        `but got: "${caughtError.message}"`,
      );
    } else if (messagePattern instanceof RegExp) {
      assert.match(
        caughtError.message,
        messagePattern,
        `Expected error message to match ${messagePattern}, ` +
        `but got: "${caughtError.message}"`,
      );
    }
  }
}

/**
 * mock.fn() の呼び出し引数を検証するヘルパー。
 *
 * node:test の mock.fn() は calls プロパティに呼び出し履歴を記録する。
 * このヘルパーは指定インデックスの呼び出しが存在し、引数が期待通りであることを
 * 一括検証する。
 *
 * @param {object} mockFn       - node:test の mock.fn() が返すモック関数
 * @param {number} callIndex    - 検証対象の呼び出しインデックス (0-based)
 * @param {Array}  expectedArgs - 期待される引数の配列
 */
export function assertCalledWith(mockFn, callIndex, expectedArgs) {
  assert.ok(
    mockFn && mockFn.mock && Array.isArray(mockFn.mock.calls),
    'assertCalledWith: first argument must be a node:test mock function',
  );

  const { calls } = mockFn.mock;

  assert.ok(
    callIndex < calls.length,
    `assertCalledWith: expected at least ${callIndex + 1} call(s), ` +
    `but mock was called ${calls.length} time(s)`,
  );

  const actualArgs = calls[callIndex].arguments;
  assert.deepStrictEqual(
    actualArgs,
    expectedArgs,
    `assertCalledWith: call[${callIndex}] arguments mismatch\n` +
    `  actual:   ${JSON.stringify(actualArgs)}\n` +
    `  expected: ${JSON.stringify(expectedArgs)}`,
  );
}
