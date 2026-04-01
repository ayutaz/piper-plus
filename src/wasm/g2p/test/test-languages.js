/**
 * ZH/ES/FR/PT language G2P tests
 *
 * Validates character-based G2P for Chinese, Spanish, French, and Portuguese.
 * These languages use simple character-by-character lookup in the phoneme_id_map.
 *
 * Run: node --test src/wasm/g2p/test/test-languages.js
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { ChineseG2P } from '../src/zh/index.js';
import { SpanishG2P } from '../src/es/index.js';
import { FrenchG2P } from '../src/fr/index.js';
import { PortugueseG2P } from '../src/pt/index.js';

// ---------------------------------------------------------------------------
// Shared phoneme_id_map for testing
// ---------------------------------------------------------------------------

const TEST_MAP = {
    'a': [10], 'b': [11], 'c': [12], 'd': [13], 'e': [14],
    'h': [15], 'i': [16], 'l': [17], 'o': [18], 'n': [19],
    'r': [20], 's': [21], 't': [22], 'u': [23],
    ' ': [24],
    // Chinese chars
    '\u4F60': [30],  // 你
    '\u597D': [31],  // 好
    '\u4E16': [32],  // 世
    '\u754C': [33],  // 界
    // Accented characters for romance languages
    '\u00E9': [40],  // e with acute
    '\u00E1': [41],  // a with acute
    '\u00E3': [42],  // a with tilde
    '\u00E7': [43],  // c with cedilla
};

// ===========================================================================
// Chinese (ZH)
// ===========================================================================

describe('ChineseG2P', () => {
    describe('phonemize - basic', () => {
        it('should return { tokens, prosody } structure', () => {
            const zh = new ChineseG2P();
            const result = zh.phonemize('你好');
            assert.ok(Array.isArray(result.tokens));
            assert.ok(Array.isArray(result.prosody));
            assert.equal(result.tokens.length, result.prosody.length);
        });

        it('should produce one token per character', () => {
            const zh = new ChineseG2P();
            const { tokens } = zh.phonemize('你好');
            assert.equal(tokens.length, 2);
            assert.equal(tokens[0], '你');
            assert.equal(tokens[1], '好');
        });

        it('should pass through characters not in phonemeIdMap', () => {
            const zh = new ChineseG2P({ phonemeIdMap: TEST_MAP });
            const { tokens } = zh.phonemize('你好X');
            assert.equal(tokens.length, 3);
            assert.equal(tokens[2], 'X');
        });

        it('should handle empty string', () => {
            const zh = new ChineseG2P();
            const { tokens } = zh.phonemize('');
            assert.deepEqual(tokens, []);
        });
    });

    describe('phonemize - with phonemeIdMap', () => {
        it('should accept phonemeIdMap via constructor', () => {
            const zh = new ChineseG2P({ phonemeIdMap: TEST_MAP });
            const { tokens } = zh.phonemize('你好');
            assert.equal(tokens.length, 2);
        });

        it('should accept phonemeIdMap via setPhonemeIdMap', () => {
            const zh = new ChineseG2P();
            zh.setPhonemeIdMap(TEST_MAP);
            const { tokens } = zh.phonemize('你好');
            assert.equal(tokens.length, 2);
        });
    });

    describe('prosody', () => {
        it('should return all-null prosody', () => {
            const zh = new ChineseG2P();
            const { prosody } = zh.phonemize('你好世界');
            assert.ok(prosody.every(p => p === null));
        });
    });

    describe('phonemizeWithProsody', () => {
        it('should return same result as phonemize', () => {
            const zh = new ChineseG2P();
            const r1 = zh.phonemize('你好');
            const r2 = zh.phonemizeWithProsody('你好');
            assert.deepEqual(r1.tokens, r2.tokens);
            assert.deepEqual(r1.prosody, r2.prosody);
        });
    });
});

// ===========================================================================
// Spanish (ES)
// ===========================================================================

describe('SpanishG2P', () => {
    describe('phonemize - basic', () => {
        it('should return { tokens, prosody } structure', () => {
            const es = new SpanishG2P();
            const result = es.phonemize('hola');
            assert.ok(Array.isArray(result.tokens));
            assert.ok(Array.isArray(result.prosody));
            assert.equal(result.tokens.length, result.prosody.length);
        });

        it('should lowercase input text', () => {
            const es = new SpanishG2P({ phonemeIdMap: TEST_MAP });
            const { tokens } = es.phonemize('HOLA');
            // All tokens should be lowercase
            assert.ok(tokens.every(t => t === t.toLowerCase()),
                'tokens should be lowercased');
        });

        it('should produce one token per character (lowercase)', () => {
            const es = new SpanishG2P({ phonemeIdMap: TEST_MAP });
            const { tokens } = es.phonemize('hola');
            assert.equal(tokens.length, 4);
            assert.deepEqual(tokens, ['h', 'o', 'l', 'a']);
        });

        it('should handle space characters', () => {
            const es = new SpanishG2P({ phonemeIdMap: TEST_MAP });
            const { tokens } = es.phonemize('hola hola');
            assert.ok(tokens.includes(' '));
        });

        it('should handle empty string', () => {
            const es = new SpanishG2P();
            const { tokens } = es.phonemize('');
            assert.deepEqual(tokens, []);
        });
    });

    describe('prosody', () => {
        it('should return all-null prosody', () => {
            const es = new SpanishG2P();
            const { prosody } = es.phonemize('hola');
            assert.ok(prosody.every(p => p === null));
        });
    });

    describe('phonemizeWithProsody', () => {
        it('should return same result as phonemize', () => {
            const es = new SpanishG2P();
            const r1 = es.phonemize('hola');
            const r2 = es.phonemizeWithProsody('hola');
            assert.deepEqual(r1.tokens, r2.tokens);
        });
    });
});

// ===========================================================================
// French (FR)
// ===========================================================================

describe('FrenchG2P', () => {
    describe('phonemize - basic', () => {
        it('should return { tokens, prosody } structure', () => {
            const fr = new FrenchG2P();
            const result = fr.phonemize('bonjour');
            assert.ok(Array.isArray(result.tokens));
            assert.ok(Array.isArray(result.prosody));
            assert.equal(result.tokens.length, result.prosody.length);
        });

        it('should lowercase input text', () => {
            const fr = new FrenchG2P({ phonemeIdMap: TEST_MAP });
            const { tokens } = fr.phonemize('BONJOUR');
            assert.ok(tokens.every(t => t === t.toLowerCase()));
        });

        it('should produce one token per character (lowercase)', () => {
            const fr = new FrenchG2P({ phonemeIdMap: TEST_MAP });
            const { tokens } = fr.phonemize('bon');
            assert.equal(tokens.length, 3);
            assert.deepEqual(tokens, ['b', 'o', 'n']);
        });

        it('should handle space characters', () => {
            const fr = new FrenchG2P({ phonemeIdMap: TEST_MAP });
            const { tokens } = fr.phonemize('le chat');
            assert.ok(tokens.includes(' '));
        });

        it('should handle empty string', () => {
            const fr = new FrenchG2P();
            const { tokens } = fr.phonemize('');
            assert.deepEqual(tokens, []);
        });
    });

    describe('prosody', () => {
        it('should return all-null prosody', () => {
            const fr = new FrenchG2P();
            const { prosody } = fr.phonemize('bonjour');
            assert.ok(prosody.every(p => p === null));
        });
    });

    describe('phonemizeWithProsody', () => {
        it('should return same result as phonemize', () => {
            const fr = new FrenchG2P();
            const r1 = fr.phonemize('bonjour');
            const r2 = fr.phonemizeWithProsody('bonjour');
            assert.deepEqual(r1.tokens, r2.tokens);
        });
    });
});

// ===========================================================================
// Portuguese (PT)
// ===========================================================================

describe('PortugueseG2P', () => {
    describe('phonemize - basic', () => {
        it('should return { tokens, prosody } structure', () => {
            const pt = new PortugueseG2P();
            const result = pt.phonemize('ola');
            assert.ok(Array.isArray(result.tokens));
            assert.ok(Array.isArray(result.prosody));
            assert.equal(result.tokens.length, result.prosody.length);
        });

        it('should lowercase input text', () => {
            const pt = new PortugueseG2P({ phonemeIdMap: TEST_MAP });
            const { tokens } = pt.phonemize('OLA');
            assert.ok(tokens.every(t => t === t.toLowerCase()));
        });

        it('should produce one token per character (lowercase)', () => {
            const pt = new PortugueseG2P({ phonemeIdMap: TEST_MAP });
            const { tokens } = pt.phonemize('ola');
            assert.equal(tokens.length, 3);
            assert.deepEqual(tokens, ['o', 'l', 'a']);
        });

        it('should handle space characters', () => {
            const pt = new PortugueseG2P({ phonemeIdMap: TEST_MAP });
            const { tokens } = pt.phonemize('o sol');
            assert.ok(tokens.includes(' '));
        });

        it('should handle empty string', () => {
            const pt = new PortugueseG2P();
            const { tokens } = pt.phonemize('');
            assert.deepEqual(tokens, []);
        });
    });

    describe('prosody', () => {
        it('should return all-null prosody', () => {
            const pt = new PortugueseG2P();
            const { prosody } = pt.phonemize('ola');
            assert.ok(prosody.every(p => p === null));
        });
    });

    describe('phonemizeWithProsody', () => {
        it('should return same result as phonemize', () => {
            const pt = new PortugueseG2P();
            const r1 = pt.phonemize('ola');
            const r2 = pt.phonemizeWithProsody('ola');
            assert.deepEqual(r1.tokens, r2.tokens);
        });
    });
});

// ===========================================================================
// Cross-language consistency
// ===========================================================================

describe('Cross-language API consistency', () => {
    const instances = {
        zh: new ChineseG2P(),
        es: new SpanishG2P(),
        fr: new FrenchG2P(),
        pt: new PortugueseG2P(),
    };

    for (const [lang, g2p] of Object.entries(instances)) {
        it(`${lang}: phonemize() should return { tokens, prosody }`, () => {
            const result = g2p.phonemize('test');
            assert.ok('tokens' in result, `${lang} missing tokens`);
            assert.ok('prosody' in result, `${lang} missing prosody`);
        });

        it(`${lang}: phonemizeWithProsody() should exist`, () => {
            assert.equal(typeof g2p.phonemizeWithProsody, 'function');
        });

        it(`${lang}: setPhonemeIdMap() should exist`, () => {
            assert.equal(typeof g2p.setPhonemeIdMap, 'function');
        });

        it(`${lang}: prosody length should match tokens length`, () => {
            const { tokens, prosody } = g2p.phonemize('abc');
            assert.equal(tokens.length, prosody.length);
        });
    }
});
