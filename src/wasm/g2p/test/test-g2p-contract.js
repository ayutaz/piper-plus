/**
 * G2P language class contract tests
 *
 * Verifies that every language G2P class implements the interface methods
 * expected by the unified G2P orchestrator (index.js). This catches bugs
 * like JapaneseG2P.create() not existing — the exact kind of mismatch
 * between caller and callee that caused the production TypeError.
 *
 * Run: node --test test/test-g2p-contract.js
 */

import { strict as assert } from 'node:assert';
import { describe, it } from 'node:test';

import {
  JapaneseG2P,
  EnglishG2P,
  ChineseG2P,
  KoreanG2P,
  SpanishG2P,
  FrenchG2P,
  PortugueseG2P,
  SwedishG2P,
} from '../src/index.js';

// ---------------------------------------------------------------------------
// All language G2P classes and their categories
// ---------------------------------------------------------------------------

/** Languages whose G2P is instantiated via LANGUAGE_FACTORIES (sync). */
const RULE_BASED_CLASSES = [
  { name: 'EnglishG2P', Class: EnglishG2P },
  { name: 'ChineseG2P', Class: ChineseG2P },
  { name: 'KoreanG2P', Class: KoreanG2P },
  { name: 'SpanishG2P', Class: SpanishG2P },
  { name: 'FrenchG2P', Class: FrenchG2P },
  { name: 'PortugueseG2P', Class: PortugueseG2P },
  { name: 'SwedishG2P', Class: SwedishG2P },
];

// ---------------------------------------------------------------------------
// Contract: required methods on all language G2P instances
// ---------------------------------------------------------------------------

/**
 * G2P.phonemize() calls g2p.phonemize(text) on every language instance.
 * This is the only REQUIRED method — all others are guarded by typeof checks.
 */
const REQUIRED_METHODS = ['phonemize'];

/**
 * Optional methods called with typeof guards.
 * Missing is OK (won't crash), but we document expectations.
 */
const OPTIONAL_METHODS = ['phonemizeWithProsody', 'dispose', 'setCustomDicts'];

// ---------------------------------------------------------------------------
// Tests: rule-based languages (sync, no WASM)
// ---------------------------------------------------------------------------

describe('G2P contract: rule-based languages', () => {
  for (const { name, Class } of RULE_BASED_CLASSES) {
    describe(name, () => {
      it('is constructible with no arguments', () => {
        const instance = new Class();
        assert.ok(instance, `${name} constructor returned falsy`);
      });

      for (const method of REQUIRED_METHODS) {
        it(`implements required method: ${method}()`, () => {
          const instance = new Class();
          assert.equal(
            typeof instance[method],
            'function',
            `${name}.${method} must be a function — G2P.phonemize() calls it unconditionally`
          );
        });
      }

      it('phonemize() returns { tokens, prosody } with correct shape', () => {
        const instance = new Class();
        // Use a simple ASCII text that all rule-based G2Ps can handle
        const result = instance.phonemize('hello');
        assert.ok(Array.isArray(result.tokens), `${name}.phonemize().tokens must be an array`);
        assert.ok('prosody' in result, `${name}.phonemize() must return a prosody field`);
      });
    });
  }
});

// ---------------------------------------------------------------------------
// Tests: JapaneseG2P (async, requires WASM for full init)
// ---------------------------------------------------------------------------

describe('G2P contract: JapaneseG2P', () => {
  it('is constructible with options object', () => {
    const instance = new JapaneseG2P({});
    assert.ok(instance);
  });

  it('is constructible with no arguments', () => {
    const instance = new JapaneseG2P();
    assert.ok(instance);
  });

  for (const method of REQUIRED_METHODS) {
    it(`implements required method: ${method}()`, () => {
      const instance = new JapaneseG2P();
      assert.equal(
        typeof instance[method],
        'function',
        `JapaneseG2P.${method} must be a function`
      );
    });
  }

  it('implements initialize() (async factory pattern)', () => {
    const instance = new JapaneseG2P();
    assert.equal(
      typeof instance.initialize,
      'function',
      'JapaneseG2P.initialize must be a function — G2P.create() calls it'
    );
  });

  it('does NOT have a static create() method', () => {
    // Regression: G2P.create() previously called JapaneseG2P.create()
    // which didn't exist. JapaneseG2P uses constructor + initialize() pattern.
    // If someone adds create(), that's fine, but this documents the current API.
    assert.equal(
      typeof JapaneseG2P.create,
      'undefined',
      'JapaneseG2P uses constructor + initialize(), not a static create() factory'
    );
  });
});

// ---------------------------------------------------------------------------
// Tests: G2P.create() factory integration (with mocked JapaneseG2P)
// ---------------------------------------------------------------------------

describe('G2P.create() factory with Japanese (mocked)', () => {
  it('should initialize JapaneseG2P via new + initialize(), not create()', async () => {
    // Import G2P to test the factory. We can't fully run G2P.create with 'ja'
    // without WASM, but we verify the error comes from initialize() (missing
    // openjtalkModule), NOT from "create is not a function".
    const { G2P } = await import('../src/index.js');

    try {
      await G2P.create({ languages: ['ja'] });
      assert.fail('Expected G2P.create() to throw (no openjtalkModule provided)');
    } catch (err) {
      // The error should be about missing openjtalkModule, NOT about
      // "JapaneseG2P.create is not a function"
      assert.ok(
        !err.message.includes('is not a function'),
        `G2P.create() threw a "not a function" error — indicates API mismatch: ${err.message}`
      );
      assert.ok(
        err.message.includes('openjtalkModule'),
        `Expected error about missing openjtalkModule, got: ${err.message}`
      );
    }
  });

  it('should not crash with mixed languages including ja', async () => {
    const { G2P } = await import('../src/index.js');

    try {
      await G2P.create({ languages: ['ja', 'en', 'zh'] });
      assert.fail('Expected G2P.create() to throw (no openjtalkModule provided)');
    } catch (err) {
      // Should fail gracefully at JapaneseG2P.initialize, not at construction
      assert.ok(
        !err.message.includes('is not a function'),
        `API mismatch error: ${err.message}`
      );
    }
  });
});

// ---------------------------------------------------------------------------
// Tests: voice-free initialization (M4 — HTS voice dependency removed)
// ---------------------------------------------------------------------------

describe('G2P contract: voice-free initialization (M4)', () => {
  it('should accept jaDict with dictFiles (canonical field name)', () => {
    const DICT_FILES = [
        'char.bin', 'matrix.bin', 'sys.dic', 'unk.dic',
        'left-id.def', 'pos-id.def', 'rewrite.def', 'right-id.def',
    ];
    const mockDict = {
        dictFiles: Object.fromEntries(
            DICT_FILES.map(f => [f, new ArrayBuffer(10)])
        ),
    };
    const ja = new JapaneseG2P({ jaDict: mockDict });
    assert.ok(ja, 'JapaneseG2P should initialize with dictFiles');
  });

  it('should accept jaDict with legacy dictData field (backward compat)', () => {
    const DICT_FILES = [
        'char.bin', 'matrix.bin', 'sys.dic', 'unk.dic',
        'left-id.def', 'pos-id.def', 'rewrite.def', 'right-id.def',
    ];
    const mockDict = {
        dictData: Object.fromEntries(
            DICT_FILES.map(f => [f, new ArrayBuffer(10)])
        ),
    };
    const ja = new JapaneseG2P({ jaDict: mockDict });
    assert.ok(ja, 'JapaneseG2P should still accept legacy dictData');
  });

  it('should throw when dictFiles is missing from jaDict', () => {
    const ja = new JapaneseG2P({ jaDict: {} });
    ja._openjtalkModule = {
        FS: { mkdir: () => {}, writeFile: () => {} },
        allocateUTF8: () => 1,
        _free: () => {},
        _openjtalk_initialize: () => 0,
    };
    assert.throws(
        () => ja._loadDict({}),
        (err) => err.message.includes('dictFiles'),
        '_loadDict({}) must throw an error mentioning dictFiles'
    );
  });

  it('DictLoader.loadJaDict should not include voiceData in its contract', async () => {
    const { DictLoader } = await import('../src/dict-loader.js');
    const loader = new DictLoader();

    // Primary: API contract verification
    assert.equal(typeof loader.loadJaDict, 'function',
        'DictLoader must have loadJaDict method');
    assert.strictEqual(
        loader.loadJaDict.length <= 1, true,
        'loadJaDict should accept at most 1 parameter (options without includeVoice)'
    );
  });

  it('dict-loader.js source should not reference voice concepts (defense-in-depth)', async () => {
    // NOTE: This is a defense-in-depth static check, not a behavioral test.
    // If this breaks due to refactoring (e.g., variable rename), it is safe to
    // update the assertions — the behavioral tests above are authoritative.
    const { default: fs } = await import('node:fs');
    const src = fs.readFileSync(
        new URL('../src/dict-loader.js', import.meta.url), 'utf-8'
    );
    assert.ok(
        !src.includes('VOICE_CACHE_KEY'),
        'dict-loader.js must not contain VOICE_CACHE_KEY after M2 cleanup'
    );
    assert.ok(
        !src.includes('includeVoice'),
        'dict-loader.js must not contain includeVoice option after M2 cleanup'
    );
  });
});
