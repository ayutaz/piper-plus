/**
 * Swedish G2P tests
 *
 * Validates rule-based Swedish G2P (ported from Go swedish.go).
 * Tests: long/short vowels, soft/hard k/g, retroflex assimilation,
 * loanword suffixes, stress detection, prosody structure.
 *
 * Run: node --test src/wasm/g2p/test/test-swedish.js
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { SwedishG2P } from '../src/sv/index.js';
import { mapToken } from '../src/pua-map.js';

// ---------------------------------------------------------------------------
// Helper: check that a token array contains a specific phoneme
// ---------------------------------------------------------------------------

function hasToken(tokens, token) {
    return tokens.includes(token);
}

// ===========================================================================
// Basic API structure
// ===========================================================================

describe('SwedishG2P -- API structure', () => {
    it('should return { tokens, prosody } from phonemize()', () => {
        const sv = new SwedishG2P();
        const result = sv.phonemize('hej');
        assert.ok(Array.isArray(result.tokens), 'tokens should be an array');
        assert.ok(Array.isArray(result.prosody), 'prosody should be an array');
        assert.equal(result.tokens.length, result.prosody.length,
            'tokens and prosody should have same length');
    });

    it('should return all-null prosody from phonemize()', () => {
        const sv = new SwedishG2P();
        const { prosody } = sv.phonemize('hej');
        assert.ok(prosody.every(p => p === null), 'phonemize prosody should be all null');
    });

    it('should return { tokens, prosody } from phonemizeWithProsody()', () => {
        const sv = new SwedishG2P();
        const result = sv.phonemizeWithProsody('hej');
        assert.ok(Array.isArray(result.tokens));
        assert.ok(Array.isArray(result.prosody));
        assert.equal(result.tokens.length, result.prosody.length);
    });

    it('should return prosody objects with a1/a2/a3 from phonemizeWithProsody()', () => {
        const sv = new SwedishG2P();
        const { prosody } = sv.phonemizeWithProsody('hej');
        for (const p of prosody) {
            assert.ok(p !== null, 'prosody entries should not be null');
            assert.ok('a1' in p, 'prosody should have a1');
            assert.ok('a2' in p, 'prosody should have a2');
            assert.ok('a3' in p, 'prosody should have a3');
        }
    });

    it('should handle empty string', () => {
        const sv = new SwedishG2P();
        const r1 = sv.phonemize('');
        assert.deepEqual(r1.tokens, []);
        const r2 = sv.phonemizeWithProsody('');
        assert.deepEqual(r2.tokens, []);
    });

    it('should handle null/undefined input', () => {
        const sv = new SwedishG2P();
        const r1 = sv.phonemize(null);
        assert.deepEqual(r1.tokens, []);
        const r2 = sv.phonemize(undefined);
        assert.deepEqual(r2.tokens, []);
    });

    it('should have languageCode "sv"', () => {
        const sv = new SwedishG2P();
        assert.equal(sv.languageCode, 'sv');
    });
});

// ===========================================================================
// Long vowels
// ===========================================================================

describe('SwedishG2P -- long vowels', () => {
    const sv = new SwedishG2P();

    it('should produce long a (gata -> \u0251\u02d0)', () => {
        // gata: g-a-t-a, first 'a' before single 't' -> long
        const { tokens } = sv.phonemize('gata');
        assert.ok(hasToken(tokens, '\u0251\u02d0'), // ɑː
            `expected long a (\u0251\u02d0) in [${tokens.join(', ')}]`);
    });

    it('should produce long e (vet -> e\u02d0)', () => {
        // vet: v-e-t, 'e' before single 't' -> long
        const { tokens } = sv.phonemize('vet');
        assert.ok(hasToken(tokens, 'e\u02d0'), // eː
            `expected long e (e\u02d0) in [${tokens.join(', ')}]`);
    });

    it('should produce long i (fin -> i\u02d0)', () => {
        const { tokens } = sv.phonemize('fin');
        assert.ok(hasToken(tokens, 'i\u02d0'), // iː
            `expected long i (i\u02d0) in [${tokens.join(', ')}]`);
    });

    it('should produce long u (hus -> \u0289\u02d0)', () => {
        // hus: h-u-s, 'u' before single 's' -> long
        const { tokens } = sv.phonemize('hus');
        assert.ok(hasToken(tokens, '\u0289\u02d0'), // ʉː
            `expected long u (\u0289\u02d0) in [${tokens.join(', ')}]`);
    });

    it('should produce long y (ny -> y\u02d0)', () => {
        // ny: n-y, word-final vowel -> long
        const { tokens } = sv.phonemize('ny');
        assert.ok(hasToken(tokens, 'y\u02d0'), // yː
            `expected long y (y\u02d0) in [${tokens.join(', ')}]`);
    });

    it('should produce long \u00e5 (l\u00e5t -> o\u02d0)', () => {
        const { tokens } = sv.phonemize('l\u00e5t');
        assert.ok(hasToken(tokens, 'o\u02d0'), // oː
            `expected long \u00e5 (o\u02d0) in [${tokens.join(', ')}]`);
    });

    it('should produce long \u00e4 (l\u00e4sa -> \u025b\u02d0)', () => {
        const { tokens } = sv.phonemize('l\u00e4sa');
        assert.ok(hasToken(tokens, '\u025b\u02d0'), // ɛː
            `expected long \u00e4 (\u025b\u02d0) in [${tokens.join(', ')}]`);
    });

    it('should produce long \u00f6 (h\u00f6ra -> \u00f8\u02d0)', () => {
        const { tokens } = sv.phonemize('h\u00f6ra');
        assert.ok(hasToken(tokens, '\u00f8\u02d0'), // øː
            `expected long \u00f6 (\u00f8\u02d0) in [${tokens.join(', ')}]`);
    });

    it('should produce long o as u\u02d0 by default (sol)', () => {
        // sol: s-o-l, default 'o' -> uː
        const { tokens } = sv.phonemize('sol');
        assert.ok(hasToken(tokens, 'u\u02d0'), // uː
            `expected long o (u\u02d0) in [${tokens.join(', ')}]`);
    });

    it('should produce long o as o\u02d0 for O_LONG_AS_OO words (fot)', () => {
        // fot is in O_LONG_AS_OO -> oː
        const { tokens } = sv.phonemize('fot');
        assert.ok(hasToken(tokens, 'o\u02d0'), // oː
            `expected o\u02d0 in [${tokens.join(', ')}]`);
    });
});

// ===========================================================================
// Short vowels
// ===========================================================================

describe('SwedishG2P -- short vowels', () => {
    const sv = new SwedishG2P();

    it('should produce short a (katt -> a)', () => {
        // katt: k-a-t-t, 'a' before 2 consonants (tt) -> short
        const { tokens } = sv.phonemize('katt');
        assert.ok(hasToken(tokens, 'a'),
            `expected short a in [${tokens.join(', ')}]`);
    });

    it('should produce short e (fest -> \u025b)', () => {
        // fest: f-e-s-t, 'e' before 2 consonants -> short
        const { tokens } = sv.phonemize('fest');
        assert.ok(hasToken(tokens, '\u025b'), // ɛ
            `expected short e (\u025b) in [${tokens.join(', ')}]`);
    });

    it('should produce short i (mitt -> \u026a)', () => {
        const { tokens } = sv.phonemize('mitt');
        assert.ok(hasToken(tokens, '\u026a'), // ɪ
            `expected short i (\u026a) in [${tokens.join(', ')}]`);
    });

    it('should produce short o (bott -> \u0254)', () => {
        const { tokens } = sv.phonemize('bott');
        assert.ok(hasToken(tokens, '\u0254'), // ɔ
            `expected short o (\u0254) in [${tokens.join(', ')}]`);
    });

    it('should produce short u (full -> \u0275)', () => {
        const { tokens } = sv.phonemize('full');
        assert.ok(hasToken(tokens, '\u0275'), // ɵ
            `expected short u (\u0275) in [${tokens.join(', ')}]`);
    });

    it('should produce short y in cluster (bytt -> \u028f)', () => {
        const { tokens } = sv.phonemize('bytt');
        assert.ok(hasToken(tokens, '\u028f'), // ʏ
            `expected short y (\u028f) in [${tokens.join(', ')}]`);
    });
});

// ===========================================================================
// Soft k/g rules
// ===========================================================================

describe('SwedishG2P -- soft k/g', () => {
    const sv = new SwedishG2P();

    it('should produce soft k (\u0255) before front vowel (k\u00f6pa)', () => {
        // köpa: k before ö (front vowel) -> soft /ɕ/
        const { tokens } = sv.phonemize('k\u00f6pa');
        assert.ok(hasToken(tokens, '\u0255'), // ɕ
            `expected soft k (\u0255) in [${tokens.join(', ')}]`);
    });

    it('should produce hard k before back vowel (kall)', () => {
        const { tokens } = sv.phonemize('kall');
        assert.ok(hasToken(tokens, 'k'),
            `expected hard k in [${tokens.join(', ')}]`);
    });

    it('should produce hard k for exception word (keps)', () => {
        const { tokens } = sv.phonemize('keps');
        assert.ok(hasToken(tokens, 'k'),
            `expected hard k for keps in [${tokens.join(', ')}]`);
    });

    it('should produce soft g (j) before front vowel (g\u00f6ra)', () => {
        // göra: g before ö -> soft /j/
        const { tokens } = sv.phonemize('g\u00f6ra');
        assert.ok(hasToken(tokens, 'j'),
            `expected soft g (j) in [${tokens.join(', ')}]`);
    });

    it('should produce hard g (\u0261) for exception word (ge)', () => {
        // ge is in HARD_G_WORDS
        const { tokens } = sv.phonemize('ge');
        assert.ok(hasToken(tokens, '\u0261'), // ɡ
            `expected hard g (\u0261) for ge in [${tokens.join(', ')}]`);
    });

    it('should produce hard g (\u0261) before back vowel (gata)', () => {
        const { tokens } = sv.phonemize('gata');
        assert.ok(hasToken(tokens, '\u0261'), // ɡ
            `expected hard g (\u0261) in [${tokens.join(', ')}]`);
    });
});

// ===========================================================================
// Retroflex assimilation
// ===========================================================================

describe('SwedishG2P -- retroflex assimilation', () => {
    const sv = new SwedishG2P();

    it('should convert rt -> \u0288 (kort)', () => {
        const { tokens } = sv.phonemize('kort');
        assert.ok(hasToken(tokens, '\u0288'), // ʈ
            `expected retroflex \u0288 in [${tokens.join(', ')}]`);
    });

    it('should convert rd -> \u0256 (bord)', () => {
        const { tokens } = sv.phonemize('bord');
        assert.ok(hasToken(tokens, '\u0256'), // ɖ
            `expected retroflex \u0256 in [${tokens.join(', ')}]`);
    });

    it('should convert rs -> \u0282 (kors)', () => {
        const { tokens } = sv.phonemize('kors');
        assert.ok(hasToken(tokens, '\u0282'), // ʂ
            `expected retroflex \u0282 in [${tokens.join(', ')}]`);
    });

    it('should convert rn -> \u0273 (barn)', () => {
        const { tokens } = sv.phonemize('barn');
        assert.ok(hasToken(tokens, '\u0273'), // ɳ
            `expected retroflex \u0273 in [${tokens.join(', ')}]`);
    });

    it('should convert rl -> \u026d (Karl)', () => {
        const { tokens } = sv.phonemize('karl');
        assert.ok(hasToken(tokens, '\u026d'), // ɭ
            `expected retroflex \u026d in [${tokens.join(', ')}]`);
    });

    it('should not retrofit rr (geminate block)', () => {
        // 'barr' -> should have 'r' tokens, not retroflex
        const { tokens } = sv.phonemize('barr');
        assert.ok(!hasToken(tokens, '\u0288'), // no ʈ
            `should not have retroflex in barr [${tokens.join(', ')}]`);
        // Should have regular 'r' preserved
        assert.ok(hasToken(tokens, 'r'),
            `expected regular r in barr [${tokens.join(', ')}]`);
    });
});

// ===========================================================================
// Consonant digraphs
// ===========================================================================

describe('SwedishG2P -- consonant digraphs', () => {
    const sv = new SwedishG2P();

    it('should convert sj -> \u0267 (sj-sound)', () => {
        const { tokens } = sv.phonemize('sju');
        assert.ok(hasToken(tokens, '\u0267'), // ɧ
            `expected sj-sound (\u0267) in [${tokens.join(', ')}]`);
    });

    it('should convert tj -> \u0255 (tj-sound)', () => {
        const { tokens } = sv.phonemize('tjugo');
        assert.ok(hasToken(tokens, '\u0255'), // ɕ
            `expected tj-sound (\u0255) in [${tokens.join(', ')}]`);
    });

    it('should convert ng -> \u014b', () => {
        const { tokens } = sv.phonemize('ring');
        assert.ok(hasToken(tokens, '\u014b'), // ŋ
            `expected ng (\u014b) in [${tokens.join(', ')}]`);
    });

    it('should convert sk + front vowel -> \u0267 (sk\u00e4ra)', () => {
        const { tokens } = sv.phonemize('sk\u00e4ra');
        assert.ok(hasToken(tokens, '\u0267'), // ɧ
            `expected sj-sound for sk+front vowel in [${tokens.join(', ')}]`);
    });

    it('should keep sk before back vowel as s+k (ska)', () => {
        const { tokens } = sv.phonemize('ska');
        assert.ok(hasToken(tokens, 's') && hasToken(tokens, 'k'),
            `expected s+k in [${tokens.join(', ')}]`);
    });

    it('should convert och -> k (ch exception)', () => {
        const { tokens } = sv.phonemize('och');
        assert.ok(hasToken(tokens, 'k'),
            `expected k for och in [${tokens.join(', ')}]`);
    });
});

// ===========================================================================
// Loanword suffixes
// ===========================================================================

describe('SwedishG2P -- loanword suffixes', () => {
    const sv = new SwedishG2P();

    it('should handle -tion suffix (station)', () => {
        const { tokens } = sv.phonemize('station');
        // -tion -> ɧ uː n
        assert.ok(hasToken(tokens, '\u0267'), // ɧ
            `expected \u0267 for -tion in [${tokens.join(', ')}]`);
    });

    it('should handle -age suffix as French loan (garage)', () => {
        const { tokens } = sv.phonemize('garage');
        // -age (not native) -> ɑː ɧ
        assert.ok(hasToken(tokens, '\u0267'), // ɧ
            `expected \u0267 for -age loan in [${tokens.join(', ')}]`);
    });

    it('should treat native -age words normally (hage)', () => {
        // hage is in AGE_NATIVE_WORDS -> not treated as loanword
        const { tokens } = sv.phonemize('hage');
        // Should have regular Swedish vowel, not ɑː ɧ suffix
        // hage -> h + vowel + ɡ/j + vowel
        assert.ok(!tokens.includes('\u0267'),
            `should not have \u0267 for native hage in [${tokens.join(', ')}]`);
    });
});

// ===========================================================================
// Stress detection
// ===========================================================================

describe('SwedishG2P -- stress', () => {
    const sv = new SwedishG2P();

    it('should insert primary stress marker (\u02c8) for content words', () => {
        const { tokens } = sv.phonemize('huset');
        assert.ok(hasToken(tokens, '\u02c8'), // ˈ
            `expected stress marker in [${tokens.join(', ')}]`);
    });

    it('should not insert stress for function words (och)', () => {
        const { tokens } = sv.phonemize('och');
        assert.ok(!hasToken(tokens, '\u02c8'),
            `should not have stress for function word och in [${tokens.join(', ')}]`);
    });

    it('should stress first syllable by default (huset)', () => {
        const { tokens } = sv.phonemize('huset');
        const stressIdx = tokens.indexOf('\u02c8');
        assert.ok(stressIdx >= 0, 'stress marker should exist');
        assert.equal(stressIdx, 0, 'stress marker should be at position 0 for first syllable');
    });
});

// ===========================================================================
// Prosody structure
// ===========================================================================

describe('SwedishG2P -- prosody', () => {
    const sv = new SwedishG2P();

    it('should set a2=2 for stress markers in phonemizeWithProsody', () => {
        const { tokens, prosody } = sv.phonemizeWithProsody('huset');
        const stressIdx = tokens.indexOf('\u02c8');
        if (stressIdx >= 0) {
            assert.equal(prosody[stressIdx].a2, 2,
                'a2 should be 2 for stress marker');
        }
    });

    it('should set a1=0 for all tokens', () => {
        const { prosody } = sv.phonemizeWithProsody('huset');
        for (const p of prosody) {
            assert.equal(p.a1, 0, 'a1 should always be 0');
        }
    });

    it('should set a3 = word phoneme count (excluding stress markers)', () => {
        const { tokens, prosody } = sv.phonemizeWithProsody('hej');
        // 'hej' -> monosyllabic, some phonemes
        const nonStressTokens = tokens.filter(t => t !== '\u02c8' && t !== '\u02cc');
        const expectedA3 = nonStressTokens.length;
        // All tokens in the same word should share the same a3
        for (const p of prosody) {
            assert.equal(p.a3, expectedA3,
                `a3 should be ${expectedA3}, got ${p.a3}`);
        }
    });

    it('should have a2=2 only for stress marker and a2=0 for all others', () => {
        const { tokens, prosody } = sv.phonemizeWithProsody('huset');
        const stressIdx = tokens.indexOf('\u02c8');
        assert.ok(stressIdx >= 0, 'huset (content word) should have a stress marker');
        assert.equal(prosody[stressIdx].a2, 2,
            'stress marker token should have a2=2');
        for (let i = 0; i < tokens.length; i++) {
            if (i !== stressIdx) {
                assert.equal(prosody[i].a2, 0,
                    `non-stress token "${tokens[i]}" at index ${i} should have a2=0`);
            }
        }
    });

    it('should set a3 = phoneme count per word in multi-word sentence', () => {
        const { tokens, prosody } = sv.phonemizeWithProsody('hej du');
        // Find the space separator to split into two words
        const spaceIdx = tokens.indexOf(' ');
        assert.ok(spaceIdx > 0, 'should have a space separator');

        // Word 1: tokens before the space
        const word1Tokens = tokens.slice(0, spaceIdx);
        const word1PhCount = word1Tokens.filter(t => t !== '\u02c8' && t !== '\u02cc').length;
        for (let i = 0; i < spaceIdx; i++) {
            assert.equal(prosody[i].a3, word1PhCount,
                `word1 token "${tokens[i]}" should have a3=${word1PhCount}`);
        }

        // Word 2: tokens after the space
        const word2Tokens = tokens.slice(spaceIdx + 1);
        const word2PhCount = word2Tokens.filter(t => t !== '\u02c8' && t !== '\u02cc').length;
        for (let i = spaceIdx + 1; i < tokens.length; i++) {
            assert.equal(prosody[i].a3, word2PhCount,
                `word2 token "${tokens[i]}" should have a3=${word2PhCount}`);
        }
    });
});

// ===========================================================================
// Multi-word sentences
// ===========================================================================

describe('SwedishG2P -- sentences', () => {
    const sv = new SwedishG2P();

    it('should separate words with space tokens', () => {
        const { tokens } = sv.phonemize('hej du');
        assert.ok(tokens.includes(' '),
            `expected space separator in [${tokens.join(', ')}]`);
    });

    it('should handle punctuation as separate tokens', () => {
        const { tokens } = sv.phonemize('hej!');
        assert.ok(tokens.includes('!'),
            `expected ! in [${tokens.join(', ')}]`);
    });

    it('should normalize uppercase to lowercase', () => {
        const sv2 = new SwedishG2P();
        const r1 = sv2.phonemize('Hej');
        const r2 = sv2.phonemize('hej');
        assert.deepEqual(r1.tokens, r2.tokens,
            'uppercase and lowercase should produce same tokens');
    });
});

// ===========================================================================
// Word-initial digraphs
// ===========================================================================

describe('SwedishG2P -- word-initial digraphs', () => {
    const sv = new SwedishG2P();

    it('should convert initial dj -> j (djur)', () => {
        const { tokens } = sv.phonemize('djur');
        assert.equal(tokens.filter(t => t !== '\u02c8')[0], 'j',
            `expected initial j in djur, got [${tokens.join(', ')}]`);
    });

    it('should convert initial lj -> j (ljus)', () => {
        const { tokens } = sv.phonemize('ljus');
        assert.equal(tokens.filter(t => t !== '\u02c8')[0], 'j',
            `expected initial j in ljus, got [${tokens.join(', ')}]`);
    });

    it('should convert initial hj -> j (hj\u00e4lp)', () => {
        const { tokens } = sv.phonemize('hj\u00e4lp');
        assert.equal(tokens.filter(t => t !== '\u02c8')[0], 'j',
            `expected initial j in hj\u00e4lp, got [${tokens.join(', ')}]`);
    });
});

// ===========================================================================
// Single-character tokens (after PUA mapping)
// ===========================================================================

describe('SwedishG2P -- token format', () => {
    const sv = new SwedishG2P();

    it('should produce single-character tokens after PUA mapping', () => {
        // 'gata' produces long vowel ɑː which is multi-char before PUA mapping
        const { tokens } = sv.phonemize('gata');
        const mapped = tokens.map(t => mapToken(t));
        for (const t of mapped) {
            assert.equal(t.length, 1,
                `Expected single-char token after PUA mapping, got "${t}" (length ${t.length})`);
        }
    });

    it('should produce single-character tokens for short-vowel words', () => {
        // 'katt' has only short vowels and single-char consonants
        const { tokens } = sv.phonemize('katt');
        const mapped = tokens.map(t => mapToken(t));
        for (const t of mapped) {
            assert.equal(t.length, 1,
                `Expected single-char token after PUA mapping, got "${t}" (length ${t.length})`);
        }
    });

    it('should produce single-character tokens for multi-word input', () => {
        const { tokens } = sv.phonemize('hej du');
        const mapped = tokens.map(t => mapToken(t));
        for (const t of mapped) {
            assert.equal(t.length, 1,
                `Expected single-char token after PUA mapping, got "${t}" (length ${t.length})`);
        }
    });
});

// ===========================================================================
// Error handling / robustness
// ===========================================================================

describe('SwedishG2P -- error handling', () => {
    const sv = new SwedishG2P();

    it('should handle numeric-only input without crashing', () => {
        const { tokens } = sv.phonemize('12345');
        assert.ok(Array.isArray(tokens), 'should return an array');
    });

    it('should handle symbol-only input without crashing', () => {
        const { tokens } = sv.phonemize('@#$%^&*');
        assert.ok(Array.isArray(tokens), 'should return an array');
    });

    it('should handle very long input (1000+ characters) without crashing', () => {
        const longText = 'hej '.repeat(300); // 1200 characters
        const { tokens } = sv.phonemize(longText);
        assert.ok(Array.isArray(tokens), 'should return an array');
        assert.ok(tokens.length > 0, 'should produce tokens for valid long input');
    });

    it('should handle phonemizeWithProsody for numeric-only input', () => {
        const { tokens, prosody } = sv.phonemizeWithProsody('12345');
        assert.ok(Array.isArray(tokens), 'should return tokens array');
        assert.ok(Array.isArray(prosody), 'should return prosody array');
        assert.equal(tokens.length, prosody.length,
            'tokens and prosody should have same length');
    });

    it('should handle phonemizeWithProsody for symbol-only input', () => {
        const { tokens, prosody } = sv.phonemizeWithProsody('@#$%^&*');
        assert.ok(Array.isArray(tokens), 'should return tokens array');
        assert.ok(Array.isArray(prosody), 'should return prosody array');
        assert.equal(tokens.length, prosody.length,
            'tokens and prosody should have same length');
    });

    it('should handle phonemizeWithProsody for very long input', () => {
        const longText = 'huset '.repeat(250); // 1500 characters
        const { tokens, prosody } = sv.phonemizeWithProsody(longText);
        assert.ok(Array.isArray(tokens), 'should return tokens array');
        assert.ok(tokens.length > 0, 'should produce tokens');
        assert.equal(tokens.length, prosody.length,
            'tokens and prosody should have same length');
    });
});
