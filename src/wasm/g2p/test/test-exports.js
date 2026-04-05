/**
 * Entry-point export verification tests.
 *
 * Ensures every public API symbol re-exported from ../src/index.js is
 * importable and has the expected type. This catches accidental removal
 * of re-exports during refactoring.
 *
 * Run: node --test src/wasm/g2p/test/test-exports.js
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

import {
    // Unified G2P class
    G2P,

    // Per-language G2P classes
    EnglishG2P,
    ChineseG2P,
    KoreanG2P,
    SpanishG2P,
    FrenchG2P,
    PortugueseG2P,
    SwedishG2P,
    JapaneseG2P,

    // Encoder
    Encoder,

    // Language detector
    UnicodeLanguageDetector,

    // PUA utilities
    PUA_MAP,
    PUA_COMPAT_VERSION,
    mapToken,
    unmapToken,
    checkPuaCompat,

    // JA utilities
    extractPhonemesFromLabels,
    applyNPhonemeRules,
    mapToPUA,

    // Other re-exports
    DictLoader,
    CustomDictionary,
} from '../src/index.js';

// ---------------------------------------------------------------------------
// Language G2P classes
// ---------------------------------------------------------------------------

describe('exports: language G2P classes', () => {
    it('G2P is a class with a static create() factory', () => {
        assert.equal(typeof G2P, 'function');
        assert.equal(typeof G2P.create, 'function');
    });

    it('EnglishG2P is a class', () => {
        assert.equal(typeof EnglishG2P, 'function');
    });

    it('ChineseG2P is a class', () => {
        assert.equal(typeof ChineseG2P, 'function');
    });

    it('KoreanG2P is a class', () => {
        assert.equal(typeof KoreanG2P, 'function');
    });

    it('SpanishG2P is a class', () => {
        assert.equal(typeof SpanishG2P, 'function');
    });

    it('FrenchG2P is a class', () => {
        assert.equal(typeof FrenchG2P, 'function');
    });

    it('PortugueseG2P is a class', () => {
        assert.equal(typeof PortugueseG2P, 'function');
    });

    it('SwedishG2P is a class', () => {
        assert.equal(typeof SwedishG2P, 'function');
    });

    it('JapaneseG2P is a class', () => {
        assert.equal(typeof JapaneseG2P, 'function');
    });
});

// ---------------------------------------------------------------------------
// Encoder
// ---------------------------------------------------------------------------

describe('exports: Encoder', () => {
    it('Encoder is importable and constructible', () => {
        assert.equal(typeof Encoder, 'function');
        const enc = new Encoder({ '^': [1], '$': [2], '_': [0] });
        assert.ok(enc);
    });
});

// ---------------------------------------------------------------------------
// UnicodeLanguageDetector
// ---------------------------------------------------------------------------

describe('exports: UnicodeLanguageDetector', () => {
    it('UnicodeLanguageDetector is importable and constructible', () => {
        assert.equal(typeof UnicodeLanguageDetector, 'function');
        const det = new UnicodeLanguageDetector(['en']);
        assert.ok(det);
    });
});

// ---------------------------------------------------------------------------
// PUA utilities
// ---------------------------------------------------------------------------

describe('exports: PUA utilities', () => {
    it('PUA_MAP is a non-empty object', () => {
        assert.equal(typeof PUA_MAP, 'object');
        assert.ok(PUA_MAP !== null);
        assert.ok(Object.keys(PUA_MAP).length > 0, 'PUA_MAP should have entries');
    });

    it('PUA_COMPAT_VERSION is a number', () => {
        assert.equal(typeof PUA_COMPAT_VERSION, 'number');
    });

    it('mapToken is a function', () => {
        assert.equal(typeof mapToken, 'function');
    });

    it('unmapToken is a function', () => {
        assert.equal(typeof unmapToken, 'function');
    });

    it('mapToken maps a multi-char token to a PUA codepoint', () => {
        const pua = mapToken('ch');
        assert.equal(pua.length, 1, 'PUA char should be a single codepoint');
        assert.notEqual(pua, 'ch', 'should differ from original token');
    });

    it('unmapToken(mapToken(token)) round-trips correctly', () => {
        const original = 'ch';
        const mapped = mapToken(original);
        const restored = unmapToken(mapped);
        assert.equal(restored, original);
    });

    it('mapToken returns the token unchanged when not in PUA_MAP', () => {
        assert.equal(mapToken('a'), 'a');
    });

    it('unmapToken returns the char unchanged when not in reverse map', () => {
        assert.equal(unmapToken('x'), 'x');
    });
});

// ---------------------------------------------------------------------------
// checkPuaCompat
// ---------------------------------------------------------------------------

describe('exports: checkPuaCompat', () => {
    it('checkPuaCompat is a function', () => {
        assert.equal(typeof checkPuaCompat, 'function');
    });

    it('returns { compatible: true } for matching version', () => {
        const result = checkPuaCompat(PUA_COMPAT_VERSION);
        assert.deepEqual(result, { compatible: true });
    });

    it('returns { compatible: true } for undefined version', () => {
        const result = checkPuaCompat(undefined);
        assert.deepEqual(result, { compatible: true });
    });

    it('returns { compatible: false, message } for mismatched version', () => {
        const result = checkPuaCompat(PUA_COMPAT_VERSION + 999);
        assert.equal(result.compatible, false);
        assert.equal(typeof result.message, 'string');
    });
});

// ---------------------------------------------------------------------------
// JA utilities
// ---------------------------------------------------------------------------

describe('exports: JA utilities', () => {
    it('extractPhonemesFromLabels is a function', () => {
        assert.equal(typeof extractPhonemesFromLabels, 'function');
    });

    it('applyNPhonemeRules is a function', () => {
        assert.equal(typeof applyNPhonemeRules, 'function');
    });

    it('mapToPUA is a function', () => {
        assert.equal(typeof mapToPUA, 'function');
    });

    it('applyNPhonemeRules replaces N before bilabial with N_m', () => {
        const result = applyNPhonemeRules(['a', 'N', 'b', 'a']);
        assert.ok(result.includes('N_m'), 'N before "b" should become N_m');
        assert.ok(!result.includes('N'), 'bare N should be replaced');
    });

    it('mapToPUA maps multi-char tokens to PUA codepoints', () => {
        const result = mapToPUA(['a', 'ch', 'o']);
        assert.equal(result[0], 'a');
        assert.notEqual(result[1], 'ch', 'ch should be PUA-mapped');
        assert.equal(result[1].length, 1, 'PUA char should be single codepoint');
        assert.equal(result[2], 'o');
    });
});

// ---------------------------------------------------------------------------
// Other re-exports
// ---------------------------------------------------------------------------

describe('exports: other re-exports', () => {
    it('DictLoader is a class', () => {
        assert.equal(typeof DictLoader, 'function');
    });

    it('CustomDictionary is a class', () => {
        assert.equal(typeof CustomDictionary, 'function');
    });
});
