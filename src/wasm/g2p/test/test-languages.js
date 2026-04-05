/**
 * ZH/ES/FR/PT language G2P API tests
 *
 * Validates API structure and basic behavior for Chinese, Spanish, French,
 * and Portuguese G2P implementations.
 *
 * - ZH: character-based fallback (WASM required for full IPA)
 * - ES/FR/PT: rule-based IPA (ported from Rust)
 *
 * Run: node --test src/wasm/g2p/test/test-languages.js
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { ChineseG2P } from '../src/zh/index.js';
import { SpanishG2P } from '../src/es/index.js';
import { FrenchG2P } from '../src/fr/index.js';
import { PortugueseG2P } from '../src/pt/index.js';

// ===========================================================================
// Chinese (ZH) — character-based fallback
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

        it('should produce one token per character (fallback mode)', () => {
            const zh = new ChineseG2P();
            const { tokens } = zh.phonemize('你好');
            assert.equal(tokens.length, 2);
            assert.equal(tokens[0], '你');
            assert.equal(tokens[1], '好');
        });

        it('should handle empty string', () => {
            const zh = new ChineseG2P();
            const { tokens } = zh.phonemize('');
            assert.deepEqual(tokens, []);
        });
    });

    describe('prosody', () => {
        it('should return all-null prosody from phonemize()', () => {
            const zh = new ChineseG2P();
            const { prosody } = zh.phonemize('你好世界');
            assert.ok(prosody.every(p => p === null));
        });
    });

    describe('phonemizeWithProsody', () => {
        it('should return prosody objects with a1/a2/a3', () => {
            const zh = new ChineseG2P();
            const { tokens, prosody } = zh.phonemizeWithProsody('你好');
            assert.equal(tokens.length, prosody.length);
            for (const p of prosody) {
                assert.equal(typeof p.a1, 'number');
                assert.equal(typeof p.a2, 'number');
                assert.equal(typeof p.a3, 'number');
            }
        });
    });

    describe('multi-character input', () => {
        it('should produce one token per character for a sentence', () => {
            const zh = new ChineseG2P();
            const input = '北京欢迎你';
            const { tokens } = zh.phonemize(input);
            assert.equal(tokens.length, 5);
        });

        it('should include punctuation characters as tokens', () => {
            const zh = new ChineseG2P();
            const { tokens } = zh.phonemize('我是学生。');
            assert.ok(tokens.length >= 5);
            assert.ok(tokens.includes('。'));
        });
    });

    describe('error visibility', () => {
        it('mode should be fallback without WASM', () => {
            const zh = new ChineseG2P();
            assert.equal(zh.mode, 'fallback');
        });

        it('lastError should be null initially', () => {
            const zh = new ChineseG2P();
            assert.equal(zh.lastError, null);
        });
    });
});

// ===========================================================================
// Spanish (ES) — rule-based IPA
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

        it('should produce IPA tokens (not character passthrough)', () => {
            const es = new SpanishG2P();
            const { tokens } = es.phonemize('hola');
            // h is silent in Spanish, so it should NOT appear in output
            assert.ok(!tokens.includes('h'), 'h should be silent in Spanish');
            assert.deepStrictEqual(tokens, ['\u02C8', 'o', 'l', 'a']);
        });

        it('should handle empty string', () => {
            const es = new SpanishG2P();
            const { tokens } = es.phonemize('');
            assert.deepEqual(tokens, []);
        });
    });

    describe('prosody', () => {
        it('should return all-null prosody from phonemize()', () => {
            const es = new SpanishG2P();
            const { prosody } = es.phonemize('hola');
            assert.ok(prosody.every(p => p === null));
        });
    });

    describe('phonemizeWithProsody', () => {
        it('should return prosody objects with a1/a2/a3', () => {
            const es = new SpanishG2P();
            const { tokens, prosody } = es.phonemizeWithProsody('hola');
            assert.equal(tokens.length, prosody.length);
            for (const p of prosody) {
                assert.equal(typeof p.a1, 'number');
                assert.equal(typeof p.a2, 'number');
                assert.equal(typeof p.a3, 'number');
            }
        });
    });
});

// ===========================================================================
// French (FR) — rule-based IPA
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

        it('should produce IPA tokens (not character passthrough)', () => {
            const fr = new FrenchG2P();
            const { tokens } = fr.phonemize('bonjour');
            // FR should contain IPA tokens like b, ʁ, etc.
            assert.ok(tokens.includes('b'), 'should contain b');
            assert.ok(tokens.length >= 3, 'should have multiple IPA tokens');
        });

        it('should handle empty string', () => {
            const fr = new FrenchG2P();
            const { tokens } = fr.phonemize('');
            assert.deepEqual(tokens, []);
        });
    });

    describe('prosody', () => {
        it('should return all-null prosody from phonemize()', () => {
            const fr = new FrenchG2P();
            const { prosody } = fr.phonemize('bonjour');
            assert.ok(prosody.every(p => p === null));
        });
    });

    describe('phonemizeWithProsody', () => {
        it('should return prosody objects with a1/a2/a3', () => {
            const fr = new FrenchG2P();
            const { tokens, prosody } = fr.phonemizeWithProsody('bonjour');
            assert.equal(tokens.length, prosody.length);
            for (const p of prosody) {
                assert.equal(typeof p.a1, 'number');
                assert.equal(typeof p.a2, 'number');
                assert.equal(typeof p.a3, 'number');
            }
        });
    });
});

// ===========================================================================
// Portuguese (PT) — rule-based IPA (BR dialect)
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

        it('should produce IPA tokens (not character passthrough)', () => {
            const pt = new PortugueseG2P();
            const { tokens } = pt.phonemize('ola');
            // PT should produce IPA tokens
            assert.ok(tokens.includes('o'), 'should contain o');
            assert.ok(tokens.length >= 3, 'should have multiple IPA tokens');
        });

        it('should handle empty string', () => {
            const pt = new PortugueseG2P();
            const { tokens } = pt.phonemize('');
            assert.deepEqual(tokens, []);
        });
    });

    describe('prosody', () => {
        it('should return all-null prosody from phonemize()', () => {
            const pt = new PortugueseG2P();
            const { prosody } = pt.phonemize('ola');
            assert.ok(prosody.every(p => p === null));
        });
    });

    describe('phonemizeWithProsody', () => {
        it('should return prosody objects with a1/a2/a3', () => {
            const pt = new PortugueseG2P();
            const { tokens, prosody } = pt.phonemizeWithProsody('ola');
            assert.equal(tokens.length, prosody.length);
            for (const p of prosody) {
                assert.equal(typeof p.a1, 'number');
                assert.equal(typeof p.a2, 'number');
                assert.equal(typeof p.a3, 'number');
            }
        });
    });
});

// ===========================================================================
// Cross-language API consistency
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

        it(`${lang}: phonemizeWithProsody() prosody should be objects`, () => {
            const { prosody } = g2p.phonemizeWithProsody('abc');
            for (const p of prosody) {
                assert.equal(typeof p, 'object');
                assert.ok(p !== null);
                assert.equal(typeof p.a1, 'number');
            }
        });
    }
});
