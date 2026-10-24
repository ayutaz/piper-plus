/**
 * Chinese G2P tests
 *
 * Validates character-based Chinese G2P, WASM fallback error visibility,
 * mode detection, and prosody structure.
 *
 * Run: node --test src/wasm/g2p/test/test-chinese.js
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import {
    ChineseG2P,
    createPinyinDictionary,
    isPinyinDictionaryLoaded,
    loadPinyinDictionary,
} from '../src/zh/index.js';
import { G2P } from '../src/index.js';

const PKG_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');

// ---------------------------------------------------------------------------
// Basic character-based phonemization (fallback mode)
// ---------------------------------------------------------------------------

describe('ChineseG2P — fallback phonemization', () => {
    it('should phonemize Chinese characters with phonemeIdMap', () => {
        const g2p = new ChineseG2P({
            phonemeIdMap: { '\u4F60': [10], '\u597D': [20] }, // 你, 好
        });
        const result = g2p.phonemize('\u4F60\u597D');
        assert.deepStrictEqual(result.tokens, ['\u4F60', '\u597D']);
        assert.equal(result.prosody.length, 2);
    });

    it('should pass through unknown characters', () => {
        const g2p = new ChineseG2P({ phonemeIdMap: { '\u4F60': [10] } });
        const result = g2p.phonemize('\u4F60X');
        assert.deepStrictEqual(result.tokens, ['\u4F60', 'X']);
    });

    it('should handle empty text', () => {
        const g2p = new ChineseG2P();
        const result = g2p.phonemize('');
        assert.deepStrictEqual(result.tokens, []);
        assert.deepStrictEqual(result.prosody, []);
    });

    it('should return empty arrays for null input', () => {
        const g2p = new ChineseG2P();
        const result = g2p.phonemize(null);
        assert.deepStrictEqual(result.tokens, []);
        assert.deepStrictEqual(result.prosody, []);
    });

    it('should return empty arrays for undefined input', () => {
        const g2p = new ChineseG2P();
        const result = g2p.phonemize(undefined);
        assert.deepStrictEqual(result.tokens, []);
        assert.deepStrictEqual(result.prosody, []);
    });

    it('should work without phonemeIdMap', () => {
        const g2p = new ChineseG2P();
        const result = g2p.phonemize('\u4F60\u597D');
        assert.deepStrictEqual(result.tokens, ['\u4F60', '\u597D']);
    });

    it('phonemize() returns null prosody values', () => {
        const g2p = new ChineseG2P({ phonemeIdMap: { '\u4F60': [10] } });
        const result = g2p.phonemize('\u4F60');
        assert.equal(result.prosody.length, 1);
        assert.strictEqual(result.prosody[0], null);
    });
});

// ---------------------------------------------------------------------------
// phonemizeWithProsody — returns { a1, a2, a3 } objects
// ---------------------------------------------------------------------------

describe('ChineseG2P — phonemizeWithProsody', () => {
    it('should return prosody objects with a1/a2/a3 keys', () => {
        const g2p = new ChineseG2P({ phonemeIdMap: { '\u4F60': [10], '\u597D': [20] } });
        const result = g2p.phonemizeWithProsody('\u4F60\u597D');
        assert.equal(result.prosody.length, 2);
        for (const p of result.prosody) {
            assert.deepStrictEqual(p, { a1: 0, a2: 0, a3: 0 });
        }
    });

    it('should return same tokens as phonemize()', () => {
        const g2p = new ChineseG2P({ phonemeIdMap: { '\u4F60': [10] } });
        const plain = g2p.phonemize('\u4F60');
        const withProsody = g2p.phonemizeWithProsody('\u4F60');
        assert.deepStrictEqual(plain.tokens, withProsody.tokens);
    });

    it('should handle empty text', () => {
        const g2p = new ChineseG2P();
        const result = g2p.phonemizeWithProsody('');
        assert.deepStrictEqual(result.tokens, []);
        assert.deepStrictEqual(result.prosody, []);
    });
});

// ---------------------------------------------------------------------------
// lastError property
// ---------------------------------------------------------------------------

describe('ChineseG2P — lastError', () => {
    it('should be null initially', () => {
        const g2p = new ChineseG2P();
        assert.strictEqual(g2p.lastError, null);
    });

    it('should be null after successful WASM mock call', () => {
        const mockWasm = {
            phonemize: (_text, _lang) => ({
                tokens: ['\u4F60', '\u597D'],
                prosody: [],
            }),
        };
        const g2p = new ChineseG2P({ wasmPhonemizer: mockWasm });
        g2p.phonemize('\u4F60\u597D');
        assert.strictEqual(g2p.lastError, null);
    });

    it('should be set when WASM mock throws', () => {
        const mockWasm = {
            phonemize: () => {
                throw new Error('test WASM failure');
            },
        };
        const g2p = new ChineseG2P({
            wasmPhonemizer: mockWasm,
            phonemeIdMap: { '\u4F60': [10] },
        });
        const result = g2p.phonemize('\u4F60');
        // Should have fallen back
        assert.deepStrictEqual(result.tokens, ['\u4F60']);
        // Error should be recorded
        assert.ok(g2p.lastError);
        assert.ok(g2p.lastError.includes('WASM phonemize failed'));
        assert.ok(g2p.lastError.includes('test WASM failure'));
    });

    it('should clear after a subsequent successful call', () => {
        let shouldFail = true;
        const mockWasm = {
            phonemize: (_text, _lang) => {
                if (shouldFail) throw new Error('fail');
                return { tokens: ['a'], prosody: [] };
            },
        };
        const g2p = new ChineseG2P({ wasmPhonemizer: mockWasm });
        g2p.phonemize('a');
        assert.ok(g2p.lastError, 'error should be set after failure');

        shouldFail = false;
        g2p.phonemize('a');
        assert.strictEqual(g2p.lastError, null, 'error should be cleared after success');
    });

    it('should handle WASM throwing non-Error values', () => {
        const mockWasm = {
            phonemize: () => {
                throw 'string error';
            },
        };
        const g2p = new ChineseG2P({ wasmPhonemizer: mockWasm });
        g2p.phonemize('x');
        assert.ok(g2p.lastError);
        assert.ok(g2p.lastError.includes('string error'));
    });
});

// ---------------------------------------------------------------------------
// mode property
// ---------------------------------------------------------------------------

describe('ChineseG2P — mode', () => {
    it('should return "fallback" without WASM', () => {
        const g2p = new ChineseG2P();
        assert.equal(g2p.mode, 'fallback');
    });

    it('should return "wasm" with WASM mock', () => {
        const mockWasm = { phonemize: () => ({ tokens: [], prosody: [] }) };
        const g2p = new ChineseG2P({ wasmPhonemizer: mockWasm });
        assert.equal(g2p.mode, 'wasm');
    });

    it('should change mode after setWasmPhonemizer()', () => {
        const g2p = new ChineseG2P();
        assert.equal(g2p.mode, 'fallback');

        const mockWasm = { phonemize: () => ({ tokens: [], prosody: [] }) };
        g2p.setWasmPhonemizer(mockWasm);
        assert.equal(g2p.mode, 'wasm');

        g2p.setWasmPhonemizer(null);
        assert.equal(g2p.mode, 'fallback');
    });
});

// ---------------------------------------------------------------------------
// WASM mock integration
// ---------------------------------------------------------------------------

describe('ChineseG2P — WASM integration', () => {
    it('should use WASM result when available', () => {
        const mockWasm = {
            phonemize: (_text, _lang) => ({
                tokens: ['ni', 'hao'],
                prosody: [],
            }),
        };
        const g2p = new ChineseG2P({ wasmPhonemizer: mockWasm });
        const result = g2p.phonemize('\u4F60\u597D');
        assert.deepStrictEqual(result.tokens, ['ni', 'hao']);
    });

    it('should fall back to character passthrough on WASM error', () => {
        const mockWasm = {
            phonemize: () => {
                throw new Error('WASM broke');
            },
        };
        const g2p = new ChineseG2P({
            wasmPhonemizer: mockWasm,
            phonemeIdMap: { '\u4F60': [10], '\u597D': [20] },
        });
        const result = g2p.phonemize('\u4F60\u597D');
        // Fallback: each character as a token
        assert.deepStrictEqual(result.tokens, ['\u4F60', '\u597D']);
    });

    it('should pass language hint to WASM', () => {
        let receivedLang = null;
        const mockWasm = {
            phonemize: (_text, lang) => {
                receivedLang = lang;
                return { tokens: ['a'], prosody: [] };
            },
        };
        const g2p = new ChineseG2P({ wasmPhonemizer: mockWasm });
        g2p.phonemize('a');
        assert.equal(receivedLang, 'zh');
    });

    it('setWasmPhonemizer should clear lastError', () => {
        const failWasm = { phonemize: () => { throw new Error('fail'); } };
        const g2p = new ChineseG2P({ wasmPhonemizer: failWasm });
        g2p.phonemize('x');
        assert.ok(g2p.lastError);

        const okWasm = { phonemize: () => ({ tokens: [], prosody: [] }) };
        g2p.setWasmPhonemizer(okWasm);
        assert.strictEqual(g2p.lastError, null, 'setWasmPhonemizer should clear lastError');
    });
});

// ---------------------------------------------------------------------------
// Dictionary loading workflow (setChineseDictionary mock)
// ---------------------------------------------------------------------------

describe('ChineseG2P — dictionary loading workflow', () => {
    it('should accept a mock WASM phonemizer with setChineseDictionary method', () => {
        const mockWasm = {
            phonemize: (_text, _lang) => ({ tokens: ['ni3', 'hao3'], prosody: [] }),
            setChineseDictionary: (_single, _phrase) => {},
        };
        const g2p = new ChineseG2P();
        g2p.setWasmPhonemizer(mockWasm);
        assert.equal(g2p.mode, 'wasm');
    });

    it('should use WASM path (not fallback) after setting dictionary-capable phonemizer', () => {
        let wasmCalled = false;
        const mockWasm = {
            phonemize: (_text, _lang) => {
                wasmCalled = true;
                return { tokens: ['ni3', 'hao3'], prosody: [] };
            },
            setChineseDictionary: (_single, _phrase) => {},
        };
        const g2p = new ChineseG2P({
            phonemeIdMap: { '\u4F60': [10], '\u597D': [20] },
        });
        // Before setting WASM, phonemize uses fallback
        const fallbackResult = g2p.phonemize('\u4F60\u597D');
        assert.deepStrictEqual(fallbackResult.tokens, ['\u4F60', '\u597D']);
        assert.equal(wasmCalled, false);

        // After setting WASM, phonemize uses WASM path
        g2p.setWasmPhonemizer(mockWasm);
        const wasmResult = g2p.phonemize('\u4F60\u597D');
        assert.deepStrictEqual(wasmResult.tokens, ['ni3', 'hao3']);
        assert.equal(wasmCalled, true);
    });

    it('should change mode to "wasm" after setWasmPhonemizer with dictionary-capable mock', () => {
        const g2p = new ChineseG2P();
        assert.equal(g2p.mode, 'fallback');

        const mockWasm = {
            phonemize: () => ({ tokens: [], prosody: [] }),
            setChineseDictionary: () => {},
        };
        g2p.setWasmPhonemizer(mockWasm);
        assert.equal(g2p.mode, 'wasm');
    });

    it('should use pinyin tokens from WASM after dictionary is loaded', () => {
        // Simulate the full workflow: create phonemizer, load dict, then phonemize
        const mockWasm = {
            _dictLoaded: false,
            setChineseDictionary(_single, _phrase) {
                this._dictLoaded = true;
            },
            phonemize(_text, _lang) {
                if (!this._dictLoaded) {
                    return { tokens: Array.from(_text), prosody: [] };
                }
                // After dict loaded, return pinyin tokens
                return { tokens: ['ni3', 'hao3'], prosody: [] };
            },
        };

        const g2p = new ChineseG2P({ wasmPhonemizer: mockWasm });

        // Before dictionary loading -- returns raw characters
        const beforeDict = g2p.phonemize('\u4F60\u597D');
        assert.deepStrictEqual(beforeDict.tokens, ['\u4F60', '\u597D']);

        // Load dictionary
        mockWasm.setChineseDictionary(new Uint8Array([]), new Uint8Array([]));

        // After dictionary loading -- returns pinyin tokens
        const afterDict = g2p.phonemize('\u4F60\u597D');
        assert.deepStrictEqual(afterDict.tokens, ['ni3', 'hao3']);
    });
});

// ---------------------------------------------------------------------------
// setChineseDictionary error cases
// ---------------------------------------------------------------------------

describe('ChineseG2P — setChineseDictionary error cases', () => {
    it('should handle setChineseDictionary throwing on invalid JSON', () => {
        const mockWasm = {
            phonemize: (_text, _lang) => ({ tokens: Array.from(_text), prosody: [] }),
            setChineseDictionary: () => {
                throw new Error('CONFIG_PARSE_ERROR: invalid JSON');
            },
        };

        const g2p = new ChineseG2P({ wasmPhonemizer: mockWasm });

        // Dictionary loading fails
        assert.throws(
            () => mockWasm.setChineseDictionary(new Uint8Array([]), new Uint8Array([])),
            { message: 'CONFIG_PARSE_ERROR: invalid JSON' },
        );

        // Phonemize should still work (WASM phonemizer itself is not broken)
        const result = g2p.phonemize('\u4F60');
        assert.deepStrictEqual(result.tokens, ['\u4F60']);
        assert.strictEqual(g2p.lastError, null);
    });

    it('should set lastError when WASM phonemizer throws during phonemization', () => {
        const mockWasm = {
            phonemize: () => {
                throw new Error('dict not loaded');
            },
            setChineseDictionary: () => {},
        };

        const g2p = new ChineseG2P({
            wasmPhonemizer: mockWasm,
            phonemeIdMap: { '\u4F60': [10] },
        });

        const result = g2p.phonemize('\u4F60');
        // Falls back to character passthrough
        assert.deepStrictEqual(result.tokens, ['\u4F60']);
        // Error is recorded
        assert.ok(g2p.lastError);
        assert.ok(g2p.lastError.includes('WASM phonemize failed'));
        assert.ok(g2p.lastError.includes('dict not loaded'));
    });

    it('should recover after replacing a broken phonemizer with a working one', () => {
        // Step 1: set a broken WASM phonemizer
        const brokenWasm = {
            phonemize: () => { throw new Error('broken'); },
            setChineseDictionary: () => {},
        };
        const g2p = new ChineseG2P({
            wasmPhonemizer: brokenWasm,
            phonemeIdMap: { '\u4F60': [10], '\u597D': [20] },
        });

        g2p.phonemize('\u4F60');
        assert.ok(g2p.lastError, 'lastError should be set after broken WASM call');

        // Step 2: replace with a working phonemizer
        const workingWasm = {
            phonemize: (_text, _lang) => ({ tokens: ['ni3', 'hao3'], prosody: [] }),
            setChineseDictionary: () => {},
        };
        g2p.setWasmPhonemizer(workingWasm);
        assert.strictEqual(g2p.lastError, null, 'lastError should be cleared by setWasmPhonemizer');

        // Step 3: phonemize succeeds with the new phonemizer
        const result = g2p.phonemize('\u4F60\u597D');
        assert.deepStrictEqual(result.tokens, ['ni3', 'hao3']);
        assert.strictEqual(g2p.lastError, null, 'lastError should remain null after success');
    });

    it('should keep lastError from phonemize failure even if setChineseDictionary works', () => {
        let callCount = 0;
        const mockWasm = {
            phonemize: () => {
                callCount++;
                if (callCount === 1) throw new Error('first call fails');
                return { tokens: ['ok'], prosody: [] };
            },
            setChineseDictionary: () => {
                // Dictionary loading succeeds -- but this does not clear lastError
            },
        };

        const g2p = new ChineseG2P({ wasmPhonemizer: mockWasm });

        // First call fails
        g2p.phonemize('\u4F60');
        assert.ok(g2p.lastError, 'lastError should be set');

        // Loading dictionary succeeds but does not touch lastError
        mockWasm.setChineseDictionary(new Uint8Array([]), new Uint8Array([]));
        assert.ok(g2p.lastError, 'lastError should still be set after dictionary load');

        // Second phonemize call succeeds and clears lastError
        g2p.phonemize('\u4F60');
        assert.strictEqual(g2p.lastError, null, 'lastError should be cleared after successful phonemize');
    });

    it('should handle setChineseDictionary throwing non-Error values', () => {
        const mockWasm = {
            phonemize: () => ({ tokens: [], prosody: [] }),
            setChineseDictionary: () => {
                throw 'raw string error from WASM';
            },
        };

        const g2p = new ChineseG2P({ wasmPhonemizer: mockWasm });

        assert.throws(
            () => mockWasm.setChineseDictionary(null, null),
            (err) => err === 'raw string error from WASM',
        );

        // Phonemizer still works
        const result = g2p.phonemize('test');
        assert.deepStrictEqual(result.tokens, []);
        assert.strictEqual(g2p.lastError, null);
    });
});

// ---------------------------------------------------------------------------
// Pinyin dictionary mode (Issue #829)
//
// The bundled pinyin_single.json / pinyin_phrases.json are the dictionaries
// the Rust ChinesePhonemizer reads (src/rust/piper-plus-g2p/data/). Expected
// tokens are spelled out like the Python golden (the Encoder maps them to PUA).
// ---------------------------------------------------------------------------

/** Codepoint key used by pinyin_single.json. */
function cp(ch) {
    return String(ch.codePointAt(0));
}

/** A ChineseG2P on a small hand-written dictionary (no phrase entries unless given). */
function smallDict(single, phrases = {}) {
    const singleByCp = {};
    for (const [ch, py] of Object.entries(single)) {
        singleByCp[cp(ch)] = py;
    }
    return new ChineseG2P({ pinyinDict: { single: singleByCp, phrases } });
}

describe('ChineseG2P — dictionary loading', () => {
    it('loads nothing until asked, and stays in fallback mode without a dictionary', () => {
        // A fresh process: other tests in this file load the dictionary.
        const script = [
            "import { G2P, isPinyinDictionaryLoaded, ChineseG2P } from './src/index.js';",
            "const g2p = await G2P.create({ languages: ['en', 'es'] });",
            "g2p.phonemize('hello', { language: 'en' });",
            'const zh = new ChineseG2P();',
            "const out = { loaded: isPinyinDictionaryLoaded(), mode: zh.mode, tokens: zh.phonemize('你好').tokens };",
            'console.log(JSON.stringify(out));',
        ].join('\n');
        const stdout = execFileSync(process.execPath, ['--input-type=module', '-e', script], {
            cwd: PKG_ROOT,
            encoding: 'utf-8',
        });
        assert.deepEqual(JSON.parse(stdout.trim().split('\n').pop()), {
            loaded: false,
            mode: 'fallback',
            tokens: ['你', '好'],
        });
    });

    it('initialize() loads the bundled dictionary and switches to dictionary mode', async () => {
        const zh = new ChineseG2P();
        assert.equal(zh.mode, 'fallback');
        const returned = await zh.initialize();
        assert.equal(returned, zh);
        assert.equal(zh.mode, 'dictionary');
        assert.equal(isPinyinDictionaryLoaded(), true);
        assert.deepEqual(zh.phonemize('你好').tokens, ['n', 'i', 'tone2', 'x', 'aʊ', 'tone3']);
    });

    it('loadPinyinDictionary() returns the same shared instance every time', async () => {
        const a = await loadPinyinDictionary();
        const b = await loadPinyinDictionary();
        assert.strictEqual(a, b);
    });

    it('G2P.create() with zh loads the dictionary before resolving', async () => {
        const g2p = await G2P.create({ languages: ['zh'] });
        assert.deepEqual(g2p.phonemize('谢谢', { language: 'zh' }).tokens, [
            'ɕ', 'iɛ', 'tone4', 'ɕ', 'iɛ', 'tone4',
        ]);
    });

    it('G2P.create() uses a pinyinDict passed in instead of the bundled one', async () => {
        const g2p = await G2P.create({
            languages: ['zh'],
            pinyinDict: { single: { [cp('你')]: 'ma1' }, phrases: {} },
        });
        assert.deepEqual(g2p.phonemize('你', { language: 'zh' }).tokens, ['m', 'a', 'tone1']);
    });

    it('rejects a pinyinDict that is not two JSON objects', () => {
        assert.throws(() => createPinyinDictionary({ single: {} }), TypeError);
        assert.throws(() => createPinyinDictionary({ single: [], phrases: {} }), TypeError);
        assert.throws(() => new ChineseG2P({ pinyinDict: { single: null, phrases: {} } }), TypeError);
    });

    it('accepts the dictionaries as JSON text', () => {
        const dict = createPinyinDictionary({
            single: JSON.stringify({ [cp('好')]: 'hao3,hao4' }),
            phrases: '{}',
        });
        const zh = new ChineseG2P({ pinyinDict: dict });
        assert.deepEqual(zh.phonemize('好').tokens, ['x', 'aʊ', 'tone3']);
    });
});

describe('ChineseG2P — pinyin readings', () => {
    const zh = new ChineseG2P();

    it('setup', async () => {
        await zh.initialize();
    });

    const cases = [
        // Polyphonic characters read by the phrase dictionary.
        ['银行', ['in', 'tone2', 'x', 'aŋ', 'tone2']],
        ['行走', ['ɕ', 'iŋ', 'tone2', 'ts', 'oʊ', 'tone3']],
        ['长城', ['tʂʰ', 'aŋ', 'tone2', 'tʂʰ', 'əŋ', 'tone2']],
        ['长大', ['tʂ', 'aŋ', 'tone3', 't', 'a', 'tone4']],
        ['重庆', ['tʂʰ', 'uŋ', 'tone2', 'tɕʰ', 'iŋ', 'tone4']],
        ['重要', ['tʂ', 'uŋ', 'tone4', 'iaʊ', 'tone4']],
        // Single characters take the first reading.
        ['行', ['ɕ', 'iŋ', 'tone2']],
        ['我', ['uo', 'tone3']],
        ['是', ['ʂ', 'ɻ̩', 'tone4']],
        ['四', ['s', 'ɨ', 'tone4']],
        ['六', ['l', 'iou', 'tone4']],
        ['日本', ['ɻ', 'ɻ̩', 'tone4', 'p', 'ən', 'tone3']],
        ['学生', ['ɕ', 'yɛ', 'tone2', 'ʂ', 'əŋ', 'tone1']],
        // Neutral tone.
        ['我们', ['uo', 'tone3', 'm', 'ən', 'tone5']],
        // Tone sandhi: T3 + T3 -> T2 + T3 (no phrase entry for 很好).
        ['很好', ['x', 'ən', 'tone2', 'x', 'aʊ', 'tone3']],
        // 一 before tone 4 -> tone 2, before tone 1 -> tone 4 (no phrase entries).
        ['一万', ['i', 'tone2', 'uan', 'tone4']],
        ['一千', ['i', 'tone4', 'tɕʰ', 'iɛn', 'tone1']],
        // Punctuation is mapped to ASCII, whitespace kept, digits passed through.
        ['我是学生。', ['uo', 'tone3', 'ʂ', 'ɻ̩', 'tone4', 'ɕ', 'yɛ', 'tone2', 'ʂ', 'əŋ', 'tone1', '.']],
        [
            '你好，再见！',
            ['n', 'i', 'tone2', 'x', 'aʊ', 'tone3', ',', 'ts', 'aɪ', 'tone4', 'tɕ', 'iɛn', 'tone4', '!'],
        ],
        ['我 有3个', ['uo', 'tone3', ' ', 'iou', 'tone3', '3', 'k', 'ɤ', 'tone4']],
    ];
    for (const [input, expected] of cases) {
        it(`reads ${input}`, () => {
            assert.deepEqual(zh.phonemize(input).tokens, expected);
        });
    }

    it('gives prosody a1 = tone, a2 = position, a3 = length of the Chinese run', () => {
        const { tokens, prosody } = zh.phonemizeWithProsody('你好。');
        assert.deepEqual(tokens, ['n', 'i', 'tone2', 'x', 'aʊ', 'tone3', '.']);
        assert.deepEqual(prosody, [
            { a1: 2, a2: 1, a3: 2 },
            { a1: 2, a2: 1, a3: 2 },
            { a1: 2, a2: 1, a3: 2 },
            { a1: 3, a2: 2, a3: 2 },
            { a1: 3, a2: 2, a3: 2 },
            { a1: 3, a2: 2, a3: 2 },
            null,
        ]);
    });

    it('phonemize() keeps null prosody in dictionary mode', () => {
        const { tokens, prosody } = zh.phonemize('你好');
        assert.equal(prosody.length, tokens.length);
        assert.ok(prosody.every((p) => p === null));
    });
});

describe('ChineseG2P — tone sandhi rules on a small dictionary', () => {
    it('bu4 before tone 4 becomes bu2', () => {
        const zh = smallDict({ 不: 'bu4', 去: 'qu4' });
        assert.deepEqual(zh.phonemize('不去').tokens, ['p', 'u', 'tone2', 'tɕʰ', 'y_vowel', 'tone4']);
    });

    it('bu4 before other tones stays', () => {
        const zh = smallDict({ 不: 'bu4', 来: 'lai2' });
        assert.deepEqual(zh.phonemize('不来').tokens, ['p', 'u', 'tone4', 'l', 'aɪ', 'tone2']);
    });

    it('a run of tone-3 syllables: each one before a tone 3 becomes tone 2', () => {
        const zh = smallDict({ 我: 'wo3', 很: 'hen3', 好: 'hao3' });
        assert.deepEqual(zh.phonemize('我很好').tokens, [
            'uo', 'tone2', 'x', 'ən', 'tone2', 'x', 'aʊ', 'tone3',
        ]);
    });

    it('does not apply sandhi across punctuation', () => {
        const zh = smallDict({ 你: 'ni3', 好: 'hao3' });
        assert.deepEqual(zh.phonemize('你，好').tokens, ['n', 'i', 'tone3', ',', 'x', 'aʊ', 'tone3']);
    });

    it('the phrase dictionary wins over single characters', () => {
        const zh = smallDict({ 行: 'xing2', 银: 'yin2' }, { 银行: [['yin2'], ['hang2']] });
        assert.deepEqual(zh.phonemize('银行').tokens, ['in', 'tone2', 'x', 'aŋ', 'tone2']);
    });

    it('erhua puts ɚ before the tone', () => {
        const zh = smallDict({ 花: 'huar1' });
        assert.deepEqual(zh.phonemize('花').tokens, ['x', 'ua', 'ɚ', 'tone1']);
    });

    it('passes an unknown CJK character through', () => {
        const zh = smallDict({ 你: 'ni3' });
        assert.deepEqual(zh.phonemize('你丂').tokens, ['n', 'i', 'tone3', '丂']);
    });
});

describe('ChineseG2P — embedded English (ZH-EN loanword, #384)', () => {
    const zh = new ChineseG2P();

    it('reads an acronym from the loanword dictionary', () => {
        assert.deepEqual(zh.phonemizeEmbeddedEnglish('GPS').tokens, [
            'tɕ', 'i', 'tone4', 'pʰ', 'i', 'tone4', 'aɪ', 'tone1', 's', 'ɨ', 'tone4',
        ]);
    });

    it('reads a case-sensitive loanword', () => {
        assert.deepEqual(zh.phonemizeEmbeddedEnglish('Python').tokens, [
            'pʰ', 'aɪ', 'tone4', 's', 'ən', 'tone1',
        ]);
    });

    it('spells an unknown word letter by letter and drops punctuation', () => {
        assert.deepEqual(zh.phonemizeEmbeddedEnglish('Hi, ').tokens, [
            'aɪ', 'tone1', 'tʂʰ', 'ɻ̩', 'tone4', 'aɪ', 'tone4',
        ]);
    });

    it('carries the tone in a1 with a2 = a3 = 1', () => {
        const { prosody } = zh.phonemizeEmbeddedEnglishWithProsody('AI');
        assert.deepEqual(prosody, [
            { a1: 1, a2: 1, a3: 1 },
            { a1: 1, a2: 1, a3: 1 },
            { a1: 4, a2: 1, a3: 1 },
            { a1: 4, a2: 1, a3: 1 },
        ]);
    });

    it('returns nothing for digits only', () => {
        assert.deepEqual(zh.phonemizeEmbeddedEnglish('123').tokens, []);
    });
});

describe('G2P — Chinese text with English (language "zh")', () => {
    let g2p;

    it('setup', async () => {
        g2p = await G2P.create({ languages: ['en', 'zh'] });
    });

    it('reads English next to Chinese with the loanword dictionary', () => {
        assert.deepEqual(g2p.phonemize('我用 GPS 导航', { language: 'zh' }).tokens, [
            'uo', 'tone3', 'iuŋ', 'tone4', ' ',
            'tɕ', 'i', 'tone4', 'pʰ', 'i', 'tone4', 'aɪ', 'tone1', 's', 'ɨ', 'tone4',
            't', 'aʊ', 'tone3', 'x', 'aŋ', 'tone2',
        ]);
    });

    it('keeps the tone sandhi of the Chinese segment after English', () => {
        const { tokens } = g2p.phonemize('Hello你好', { language: 'zh' });
        assert.deepEqual(tokens.slice(-6), ['n', 'i', 'tone2', 'x', 'aʊ', 'tone3']);
    });

    it('reads English as English when ZH-EN dispatch is turned off', () => {
        const zh = g2p._phonemizers.get('zh');
        assert.equal(zh.isZhEnDispatchEnabled(), true);
        zh.setZhEnDispatch(false);
        try {
            const off = g2p.phonemize('Python 你好', { language: 'zh' }).tokens;
            const english = g2p.phonemize('Python ', { language: 'en' }).tokens;
            assert.deepEqual(off.slice(0, english.length), english);
        } finally {
            zh.setZhEnDispatch(true);
        }
    });

    it('carries the Chinese prosody to phonemizeWithProsody()', () => {
        const { prosody } = g2p.phonemizeWithProsody('你好', { language: 'zh' });
        assert.deepEqual(prosody[0], { a1: 2, a2: 1, a3: 2 });
    });
});
