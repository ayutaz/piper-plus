/**
 * Chinese G2P tests
 *
 * Validates the ChineseG2P class: API structure, fallback (character-level)
 * mode for Node.js, and mock WASM integration path.
 *
 * Note: Full pinyin-to-IPA WASM phonemization requires a browser environment
 * with the Rust WASM module loaded.  These tests exercise the fallback path
 * and the WASM integration via a mock object.
 *
 * Run: node --test src/wasm/g2p/test/test-chinese.js
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { ChineseG2P } from '../src/zh/index.js';

// ===========================================================================
// API structure
// ===========================================================================

describe('ChineseG2P -- API structure', () => {
    it('languageCode returns zh', () => {
        const g2p = new ChineseG2P();
        assert.equal(g2p.languageCode, 'zh');
    });

    it('phonemize returns tokens and prosody', () => {
        const g2p = new ChineseG2P();
        const result = g2p.phonemize('\u4F60\u597D');
        assert.ok(Array.isArray(result.tokens));
        assert.ok(Array.isArray(result.prosody));
        assert.equal(result.tokens.length, result.prosody.length);
    });

    it('phonemizeWithProsody returns same structure as phonemize', () => {
        const g2p = new ChineseG2P();
        const r1 = g2p.phonemize('\u4F60\u597D');
        const r2 = g2p.phonemizeWithProsody('\u4F60\u597D');
        assert.deepEqual(r1.tokens, r2.tokens);
        assert.deepEqual(r1.prosody, r2.prosody);
    });

    it('isWasmInitialized is false by default', () => {
        const g2p = new ChineseG2P();
        assert.equal(g2p.isWasmInitialized, false);
    });

    it('setPhonemeIdMap stores the map', () => {
        const g2p = new ChineseG2P();
        const map = { '\u4F60': [10], '\u597D': [11] };
        g2p.setPhonemeIdMap(map);
        assert.deepEqual(g2p.phonemeIdMap, map);
    });
});

// ===========================================================================
// Fallback mode (no WASM)
// ===========================================================================

describe('ChineseG2P -- fallback mode (no WASM)', () => {
    const g2p = new ChineseG2P();

    it('produces tokens for Chinese text', () => {
        const { tokens } = g2p.phonemize('\u4F60\u597D');
        assert.ok(tokens.length > 0);
    });

    it('handles punctuation', () => {
        const { tokens } = g2p.phonemize('\u4F60\u597D\u3002');
        assert.ok(tokens.length > 0);
    });

    it('handles empty string', () => {
        const { tokens } = g2p.phonemize('');
        assert.equal(tokens.length, 0);
    });

    it('handles null input', () => {
        const { tokens } = g2p.phonemize(null);
        assert.equal(tokens.length, 0);
    });

    it('handles undefined input', () => {
        const { tokens } = g2p.phonemize(undefined);
        assert.equal(tokens.length, 0);
    });

    it('handles whitespace', () => {
        const { tokens } = g2p.phonemize('\u4F60 \u597D');
        assert.ok(tokens.includes(' '));
    });

    it('handles mixed CJK and Latin', () => {
        const { tokens } = g2p.phonemize('Hello\u4F60\u597D');
        assert.ok(tokens.length > 0);
    });

    it('prosody matches token count', () => {
        const { tokens, prosody } = g2p.phonemize('\u5317\u4EAC\u6B22\u8FCE\u4F60');
        assert.equal(tokens.length, prosody.length);
    });

    it('produces one token per character in fallback mode', () => {
        const { tokens } = g2p.phonemize('\u4F60\u597D');
        // Fallback: each character -> one token
        assert.equal(tokens.length, 2);
        assert.equal(tokens[0], '\u4F60');
        assert.equal(tokens[1], '\u597D');
    });

    it('prosody is all null in fallback mode', () => {
        const { prosody } = g2p.phonemize('\u4F60\u597D');
        assert.ok(prosody.every(p => p === null));
    });
});

// ===========================================================================
// WASM integration (mock)
// ===========================================================================

describe('ChineseG2P -- WASM integration (mock)', () => {
    it('uses wasmPhonemizer when provided', () => {
        let called = false;
        const mockWasm = {
            phonemize: (text, lang) => {
                called = true;
                assert.equal(lang, 'zh');
                return {
                    tokens: ['n', 'i', 'tone3', 'x', 'a', 'u', 'tone3'],
                    prosody: new Array(7).fill(null),
                };
            },
        };
        const g2p = new ChineseG2P({ wasmPhonemizer: mockWasm });
        assert.equal(g2p.isWasmInitialized, true);
        const { tokens } = g2p.phonemize('\u4F60\u597D');
        assert.ok(called);
        assert.ok(tokens.length > 0);
    });

    it('returns tokens from WASM result', () => {
        const expectedTokens = ['p', 'a', 'tone1'];
        const mockWasm = {
            phonemize: () => ({
                tokens: expectedTokens,
                prosody: new Array(expectedTokens.length).fill(null),
            }),
        };
        const g2p = new ChineseG2P({ wasmPhonemizer: mockWasm });
        const { tokens } = g2p.phonemize('\u7238');
        assert.deepEqual(tokens, expectedTokens);
    });

    it('handles WASM returning empty arrays', () => {
        const mockWasm = {
            phonemize: () => ({ tokens: [], prosody: [] }),
        };
        const g2p = new ChineseG2P({ wasmPhonemizer: mockWasm });
        const { tokens, prosody } = g2p.phonemize('\u4F60');
        assert.equal(tokens.length, 0);
        assert.equal(prosody.length, 0);
    });

    it('handles WASM returning undefined fields gracefully', () => {
        const mockWasm = {
            phonemize: () => ({}),
        };
        const g2p = new ChineseG2P({ wasmPhonemizer: mockWasm });
        const { tokens, prosody } = g2p.phonemize('\u4F60');
        assert.deepEqual(tokens, []);
        assert.deepEqual(prosody, []);
    });
});
