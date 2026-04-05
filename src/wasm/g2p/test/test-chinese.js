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
