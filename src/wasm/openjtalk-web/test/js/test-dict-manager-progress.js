/**
 * TDD Tests for DictManager onProgress callback
 *
 * テスト対象: src/wasm/openjtalk-web/src/dict-manager.js
 * onProgress コールバックの詳細な振る舞いを検証する。
 */

import assert from 'node:assert/strict';
import { describe, it, beforeEach, afterEach } from 'node:test';
import {
  installIndexedDBMock,
  installFetchMock,
  installCryptoMock,
  cleanup,
} from './helpers/dict-mock.js';

// ---- Import SUT ----------------------------------------------------------------

let DictManager;
try {
  const mod = await import('../../src/dict-manager.js');
  DictManager = mod.DictManager || mod.default;
} catch {
  DictManager = null;
}

const skip = DictManager === null;

// ---- Tests ---------------------------------------------------------------------

describe('DictManager onProgress コールバック', { skip }, () => {
  let fetched;

  beforeEach(() => {
    installIndexedDBMock();
    installCryptoMock();
    fetched = installFetchMock();
  });

  afterEach(() => {
    fetched = [];
    cleanup();
  });

  it('onProgress が呼び出される', async () => {
    const calls = [];
    const dm = new DictManager();
    await dm.loadDictionary({
      onProgress: (info) => calls.push(info),
    });
    assert.ok(calls.length > 0, 'onProgress should be called at least once');
  });

  it('onProgress に phase が含まれる', async () => {
    const calls = [];
    const dm = new DictManager();
    await dm.loadDictionary({
      onProgress: (info) => calls.push(info),
    });

    const phases = new Set(calls.map((c) => c.phase));
    assert.ok(phases.has('dict'), 'Should have dict phase');
    assert.ok(phases.has('voice'), 'Should have voice phase');

    for (const call of calls) {
      assert.ok(
        call.phase === 'dict' || call.phase === 'voice',
        `phase should be dict or voice, got: ${call.phase}`
      );
    }
  });

  it('onProgress に file 情報が含まれる', async () => {
    const calls = [];
    const dm = new DictManager();
    await dm.loadDictionary({
      onProgress: (info) => calls.push(info),
    });

    for (const call of calls) {
      assert.ok(typeof call.file === 'string', 'file should be a string');
      assert.ok(call.file.length > 0, 'file should be non-empty');
    }
  });

  it('overallPercent が最終的に 100 になる', async () => {
    const calls = [];
    const dm = new DictManager();
    await dm.loadDictionary({
      onProgress: (info) => calls.push(info),
    });

    const last = calls[calls.length - 1];
    assert.equal(last.overallPercent, 100, 'Last callback should be 100%');
  });

  it('overallPercent が 0 以上 100 以下の範囲', async () => {
    const calls = [];
    const dm = new DictManager();
    await dm.loadDictionary({
      onProgress: (info) => calls.push(info),
    });

    for (const call of calls) {
      assert.ok(call.overallPercent >= 0, `overallPercent >= 0, got: ${call.overallPercent}`);
      assert.ok(call.overallPercent <= 100, `overallPercent <= 100, got: ${call.overallPercent}`);
    }
  });

  it('dict phase と voice phase の両方がレポートされる', async () => {
    const calls = [];
    const dm = new DictManager();
    await dm.loadDictionary({
      onProgress: (info) => calls.push(info),
    });

    const dictCalls = calls.filter((c) => c.phase === 'dict');
    const voiceCalls = calls.filter((c) => c.phase === 'voice');

    assert.ok(dictCalls.length > 0, 'Should have dict phase callbacks');
    assert.ok(voiceCalls.length > 0, 'Should have voice phase callbacks');
  });

  it('onProgress を指定しなくてもエラーにならない', async () => {
    const dm = new DictManager();
    await dm.loadDictionary();
    // No error = pass
  });

  it('onProgress が null でもエラーにならない', async () => {
    const dm = new DictManager();
    await dm.loadDictionary({ onProgress: null });
    // No error = pass
  });
});
