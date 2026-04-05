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
import { ChineseG2P } from '../src/zh/index.js';

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
