/**
 * Spanish G2P tests
 *
 * Validates rule-based Spanish G2P (ported from Rust spanish.rs).
 * Tests: seseo, affricates, yeismo, trill, allophony, stress,
 * function words, digraphs, punctuation, NFD normalization, prosody.
 *
 * Run: node --test src/wasm/g2p/test/test-spanish.js
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { SpanishG2P } from '../src/es/index.js';

// ---------------------------------------------------------------------------
// IPA / PUA constants -- must match pua-map.js / Rust spanish.rs
// ---------------------------------------------------------------------------

const IPA_BETA         = '\u03B2'; // voiced bilabial fricative (allophone of /b/)
const IPA_ETH          = '\u00F0'; // voiced dental fricative (allophone of /d/)
const IPA_G            = '\u0261'; // voiced velar stop (IPA)
const IPA_GAMMA        = '\u0263'; // voiced velar fricative (allophone of /g/)
const IPA_PALATAL_NASAL = '\u0272'; // palatal nasal (n-tilde)
const IPA_TAP          = '\u027E'; // alveolar tap (single r)
const IPA_PALATAL_FRIC = '\u029D'; // voiced palatal fricative (y, ll)
const IPA_STRESS       = '\u02C8'; // primary stress marker

const PUA_RR  = '\uE01D'; // alveolar trill (rr, word-initial r)
const PUA_TCH = '\uE054'; // voiceless postalveolar affricate (ch)

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function hasToken(tokens, token) {
    return tokens.includes(token);
}

// ===========================================================================
// Basic API structure
// ===========================================================================

describe('SpanishG2P -- API structure', () => {
    it('should return { tokens, prosody } from phonemize()', () => {
        const es = new SpanishG2P();
        const result = es.phonemize('hola');
        assert.ok(Array.isArray(result.tokens), 'tokens should be an array');
        assert.ok(Array.isArray(result.prosody), 'prosody should be an array');
        assert.equal(result.tokens.length, result.prosody.length,
            'tokens and prosody should have same length');
    });

    it('should return all-null prosody from phonemize()', () => {
        const es = new SpanishG2P();
        const { prosody } = es.phonemize('hola');
        assert.ok(prosody.every(p => p === null), 'phonemize prosody should be all null');
    });

    it('should return { tokens, prosody } from phonemizeWithProsody()', () => {
        const es = new SpanishG2P();
        const result = es.phonemizeWithProsody('hola');
        assert.ok(Array.isArray(result.tokens));
        assert.ok(Array.isArray(result.prosody));
        assert.equal(result.tokens.length, result.prosody.length);
    });

    it('should return prosody objects with a1/a2/a3 from phonemizeWithProsody()', () => {
        const es = new SpanishG2P();
        const { prosody } = es.phonemizeWithProsody('hola');
        for (const p of prosody) {
            assert.ok(p !== null, 'prosody entries should not be null');
            assert.ok('a1' in p, 'prosody should have a1');
            assert.ok('a2' in p, 'prosody should have a2');
            assert.ok('a3' in p, 'prosody should have a3');
        }
    });

    it('should have languageCode "es"', () => {
        const es = new SpanishG2P();
        assert.equal(es.languageCode, 'es');
    });

    it('should handle empty string', () => {
        const es = new SpanishG2P();
        const r1 = es.phonemize('');
        assert.deepEqual(r1.tokens, []);
        const r2 = es.phonemizeWithProsody('');
        assert.deepEqual(r2.tokens, []);
    });

    it('should handle null/undefined input', () => {
        const es = new SpanishG2P();
        const r1 = es.phonemize(null);
        assert.deepEqual(r1.tokens, []);
        const r2 = es.phonemize(undefined);
        assert.deepEqual(r2.tokens, []);
    });
});

// ===========================================================================
// Golden fixture: "hola" -> exact match
// ===========================================================================

describe('SpanishG2P -- golden fixture', () => {
    const es = new SpanishG2P();

    it('"hola" -> exactly ["\\u02C8", "o", "l", "a"]', () => {
        const { tokens } = es.phonemize('hola');
        assert.deepEqual(tokens, [IPA_STRESS, 'o', 'l', 'a']);
    });
});

// ===========================================================================
// Basic G2P rules
// ===========================================================================

describe('SpanishG2P -- basic rules', () => {
    const es = new SpanishG2P();

    it('h is silent in "hola"', () => {
        const { tokens } = es.phonemize('hola');
        assert.ok(!hasToken(tokens, 'h'), `h should be silent: ${JSON.stringify(tokens)}`);
    });

    it('"hola" contains stress, o, l, a', () => {
        const { tokens } = es.phonemize('hola');
        assert.ok(hasToken(tokens, IPA_STRESS));
        assert.ok(hasToken(tokens, 'o'));
        assert.ok(hasToken(tokens, 'l'));
        assert.ok(hasToken(tokens, 'a'));
    });
});

// ===========================================================================
// Seseo: c before e/i and z -> s
// ===========================================================================

describe('SpanishG2P -- seseo', () => {
    const es = new SpanishG2P();

    it('"cena" -> c before e -> s', () => {
        const { tokens } = es.phonemize('cena');
        assert.ok(hasToken(tokens, 's'), `c before e -> s: ${JSON.stringify(tokens)}`);
    });

    it('"zapato" -> z -> s, no z in output', () => {
        const { tokens } = es.phonemize('zapato');
        assert.ok(hasToken(tokens, 's'), `z -> s: ${JSON.stringify(tokens)}`);
        assert.ok(!hasToken(tokens, 'z'), `z should not appear: ${JSON.stringify(tokens)}`);
    });

    it('"ce" -> s e (seseo)', () => {
        const { tokens } = es.phonemize('ce');
        assert.ok(hasToken(tokens, 's'));
    });
});

// ===========================================================================
// Affricate: ch -> PUA_TCH
// ===========================================================================

describe('SpanishG2P -- affricate ch', () => {
    const es = new SpanishG2P();

    it('"chico" -> contains PUA tsh', () => {
        const { tokens } = es.phonemize('chico');
        assert.ok(hasToken(tokens, PUA_TCH), `ch -> PUA_TCH: ${JSON.stringify(tokens)}`);
    });
});

// ===========================================================================
// Yeismo: ll -> palatal fricative
// ===========================================================================

describe('SpanishG2P -- yeismo', () => {
    const es = new SpanishG2P();

    it('"calle" -> ll -> palatal fricative', () => {
        const { tokens } = es.phonemize('calle');
        assert.ok(hasToken(tokens, IPA_PALATAL_FRIC), `ll -> \\u029D: ${JSON.stringify(tokens)}`);
    });
});

// ===========================================================================
// Trill: rr and word-initial r
// ===========================================================================

describe('SpanishG2P -- trill', () => {
    const es = new SpanishG2P();

    it('"perro" -> rr -> PUA_RR', () => {
        const { tokens } = es.phonemize('perro');
        assert.ok(hasToken(tokens, PUA_RR), `rr -> PUA_RR: ${JSON.stringify(tokens)}`);
    });

    it('"rosa" -> word-initial r -> PUA_RR', () => {
        const { tokens } = es.phonemize('rosa');
        assert.ok(hasToken(tokens, PUA_RR), `word-initial r -> PUA_RR: ${JSON.stringify(tokens)}`);
    });

    it('"pero" -> intervocalic single r -> tap', () => {
        const { tokens } = es.phonemize('pero');
        assert.ok(hasToken(tokens, IPA_TAP), `single r -> tap: ${JSON.stringify(tokens)}`);
    });
});

// ===========================================================================
// Palatal nasal: n-tilde
// ===========================================================================

describe('SpanishG2P -- palatal nasal', () => {
    const es = new SpanishG2P();

    it('"ni\\u00F1o" -> \\u00F1 -> palatal nasal', () => {
        const { tokens } = es.phonemize('ni\u00F1o');
        assert.ok(hasToken(tokens, IPA_PALATAL_NASAL), `\\u00F1 -> \\u0272: ${JSON.stringify(tokens)}`);
    });
});

// ===========================================================================
// Allophony: b/d/g spirantization
// ===========================================================================

describe('SpanishG2P -- allophony (spirantization)', () => {
    const es = new SpanishG2P();

    it('"lobo" -> intervocalic b -> beta', () => {
        const { tokens } = es.phonemize('lobo');
        assert.ok(hasToken(tokens, IPA_BETA), `intervocalic b -> \\u03B2: ${JSON.stringify(tokens)}`);
    });

    it('"todo" -> intervocalic d -> eth', () => {
        const { tokens } = es.phonemize('todo');
        assert.ok(hasToken(tokens, IPA_ETH), `intervocalic d -> \\u00F0: ${JSON.stringify(tokens)}`);
    });

    it('"lago" -> intervocalic g -> gamma', () => {
        const { tokens } = es.phonemize('lago');
        assert.ok(hasToken(tokens, IPA_GAMMA), `intervocalic g -> \\u0263: ${JSON.stringify(tokens)}`);
    });
});

// ===========================================================================
// Stop after nasal
// ===========================================================================

describe('SpanishG2P -- stop after nasal', () => {
    const es = new SpanishG2P();

    it('"amba" -> b after nasal -> stop b (not beta)', () => {
        const { tokens } = es.phonemize('amba');
        assert.ok(hasToken(tokens, 'b'), `b after nasal -> stop: ${JSON.stringify(tokens)}`);
        assert.ok(!hasToken(tokens, IPA_BETA), `b after nasal NOT beta: ${JSON.stringify(tokens)}`);
    });

    it('"hambre" -> b after m -> stop b', () => {
        const { tokens } = es.phonemize('hambre');
        assert.ok(hasToken(tokens, 'b'), `b after m -> stop: ${JSON.stringify(tokens)}`);
    });
});

// ===========================================================================
// Stop after l
// ===========================================================================

describe('SpanishG2P -- stop after l', () => {
    const es = new SpanishG2P();

    it('"alba" -> b after l -> stop b (not beta)', () => {
        const { tokens } = es.phonemize('alba');
        assert.ok(hasToken(tokens, 'b'), `b after l -> stop: ${JSON.stringify(tokens)}`);
        assert.ok(!hasToken(tokens, IPA_BETA), `b after l NOT beta: ${JSON.stringify(tokens)}`);
    });

    it('"falda" -> d after l -> stop d (not eth)', () => {
        const { tokens } = es.phonemize('falda');
        assert.ok(hasToken(tokens, 'd'), `d after l -> stop: ${JSON.stringify(tokens)}`);
    });

    it('"algo" -> g after l -> stop g (not gamma)', () => {
        const { tokens } = es.phonemize('algo');
        assert.ok(hasToken(tokens, IPA_G), `g after l -> stop: ${JSON.stringify(tokens)}`);
        assert.ok(!hasToken(tokens, IPA_GAMMA), `g after l NOT gamma: ${JSON.stringify(tokens)}`);
    });
});

// ===========================================================================
// Stress rules
// ===========================================================================

describe('SpanishG2P -- stress', () => {
    const es = new SpanishG2P();

    it('"casa" -> ends in vowel -> penultimate stress', () => {
        const { tokens } = es.phonemize('casa');
        assert.ok(hasToken(tokens, IPA_STRESS), `penultimate stress for casa: ${JSON.stringify(tokens)}`);
    });

    it('"ciudad" -> ends in d -> final stress', () => {
        const { tokens } = es.phonemize('ciudad');
        assert.ok(hasToken(tokens, IPA_STRESS), `final stress for ciudad: ${JSON.stringify(tokens)}`);
    });

    it('"tel\\u00E9fono" -> accent mark -> stress on accented syllable', () => {
        const { tokens } = es.phonemize('tel\u00E9fono');
        assert.ok(hasToken(tokens, IPA_STRESS), `accent mark stress for tel\\u00E9fono: ${JSON.stringify(tokens)}`);
    });

    it('"sol" -> single syllable content word has stress', () => {
        const { tokens } = es.phonemize('sol');
        assert.ok(hasToken(tokens, IPA_STRESS), `content word "sol" has stress: ${JSON.stringify(tokens)}`);
    });
});

// ===========================================================================
// Function words -- no stress
// ===========================================================================

describe('SpanishG2P -- function words', () => {
    const es = new SpanishG2P();

    it('"el" -> no stress marker', () => {
        const { tokens } = es.phonemize('el');
        assert.ok(!hasToken(tokens, IPA_STRESS), `function word "el" no stress: ${JSON.stringify(tokens)}`);
    });

    it('"de" -> no stress marker', () => {
        const { tokens } = es.phonemize('de');
        assert.ok(!hasToken(tokens, IPA_STRESS), `function word "de" no stress: ${JSON.stringify(tokens)}`);
    });

    it('"la" -> no stress marker', () => {
        const { tokens } = es.phonemize('la');
        assert.ok(!hasToken(tokens, IPA_STRESS), `function word "la" no stress: ${JSON.stringify(tokens)}`);
    });
});

// ===========================================================================
// qu / gu digraphs
// ===========================================================================

describe('SpanishG2P -- qu/gu digraphs', () => {
    const es = new SpanishG2P();

    it('"queso" -> qu -> k', () => {
        const { tokens } = es.phonemize('queso');
        assert.ok(hasToken(tokens, 'k'), `qu -> k: ${JSON.stringify(tokens)}`);
    });

    it('"guerra" -> gu before e -> g (u silent)', () => {
        const { tokens } = es.phonemize('guerra');
        assert.ok(hasToken(tokens, IPA_G), `gu before e -> g: ${JSON.stringify(tokens)}`);
    });
});

// ===========================================================================
// gu-diaeresis
// ===========================================================================

describe('SpanishG2P -- gu-diaeresis', () => {
    const es = new SpanishG2P();

    it('"ping\\u00FCino" -> g\\u00FC -> g + w', () => {
        const { tokens } = es.phonemize('ping\u00FCino');
        assert.ok(hasToken(tokens, IPA_G), `g\\u00FC -> g: ${JSON.stringify(tokens)}`);
        assert.ok(hasToken(tokens, 'w'), `g\\u00FC -> w: ${JSON.stringify(tokens)}`);
    });
});

// ===========================================================================
// j and g+e/i -> x (velar fricative)
// ===========================================================================

describe('SpanishG2P -- j/g+ei -> x', () => {
    const es = new SpanishG2P();

    it('"jota" -> j -> x', () => {
        const { tokens } = es.phonemize('jota');
        assert.ok(hasToken(tokens, 'x'), `j -> x: ${JSON.stringify(tokens)}`);
    });

    it('"gente" -> g before e -> x', () => {
        const { tokens } = es.phonemize('gente');
        assert.ok(hasToken(tokens, 'x'), `g before e -> x: ${JSON.stringify(tokens)}`);
    });

    it('"jard\\u00EDn" -> j -> x', () => {
        const { tokens } = es.phonemize('jard\u00EDn');
        assert.ok(hasToken(tokens, 'x'), `j -> x: ${JSON.stringify(tokens)}`);
    });
});

// ===========================================================================
// h silent
// ===========================================================================

describe('SpanishG2P -- h silent', () => {
    const es = new SpanishG2P();

    it('"hola" -> no h in output', () => {
        const { tokens } = es.phonemize('hola');
        assert.ok(!hasToken(tokens, 'h'), `h should be silent: ${JSON.stringify(tokens)}`);
    });
});

// ===========================================================================
// r after l/n/s -> trill
// ===========================================================================

describe('SpanishG2P -- r after l/n/s -> trill', () => {
    const es = new SpanishG2P();

    it('"enrique" -> r after n -> PUA_RR', () => {
        const { tokens } = es.phonemize('enrique');
        assert.ok(hasToken(tokens, PUA_RR), `r after n -> trill: ${JSON.stringify(tokens)}`);
    });

    it('"honra" -> r after n -> PUA_RR', () => {
        const { tokens } = es.phonemize('honra');
        assert.ok(hasToken(tokens, PUA_RR), `r after n -> trill: ${JSON.stringify(tokens)}`);
    });
});

// ===========================================================================
// Word-final y -> i (vowel)
// ===========================================================================

describe('SpanishG2P -- word-final y', () => {
    const es = new SpanishG2P();

    it('"hoy" -> ends with i (word-final y -> vowel)', () => {
        const { tokens } = es.phonemize('hoy');
        assert.ok(hasToken(tokens, 'i'), `word-final y -> i: ${JSON.stringify(tokens)}`);
    });
});

// ===========================================================================
// x -> ks
// ===========================================================================

describe('SpanishG2P -- x', () => {
    const es = new SpanishG2P();

    it('"examen" -> x -> k + s', () => {
        const { tokens } = es.phonemize('examen');
        assert.ok(hasToken(tokens, 'k'), `x -> k: ${JSON.stringify(tokens)}`);
        assert.ok(hasToken(tokens, 's'), `x -> s: ${JSON.stringify(tokens)}`);
    });
});

// ===========================================================================
// v same as b (betacismo)
// ===========================================================================

describe('SpanishG2P -- v/b betacismo', () => {
    const es = new SpanishG2P();

    it('"vino" -> word-initial v -> b', () => {
        const { tokens } = es.phonemize('vino');
        assert.ok(hasToken(tokens, 'b'), `word-initial v -> b: ${JSON.stringify(tokens)}`);
    });
});

// ===========================================================================
// NFD normalization / uppercase
// ===========================================================================

describe('SpanishG2P -- normalization', () => {
    const es = new SpanishG2P();

    it('"HOLA" produces same tokens as "hola"', () => {
        const upper = es.phonemize('HOLA');
        const lower = es.phonemize('hola');
        assert.deepEqual(upper.tokens, lower.tokens, 'uppercase normalizes to lowercase');
    });
});

// ===========================================================================
// Punctuation preserved
// ===========================================================================

describe('SpanishG2P -- punctuation', () => {
    const es = new SpanishG2P();

    it('"\\u00A1hola!" -> preserves \\u00A1 and !', () => {
        const { tokens } = es.phonemize('\u00A1hola!');
        assert.ok(hasToken(tokens, '\u00A1'), `\\u00A1 preserved: ${JSON.stringify(tokens)}`);
        assert.ok(hasToken(tokens, '!'), `! preserved: ${JSON.stringify(tokens)}`);
    });

    it('"\\u00BFC\\u00F3mo est\\u00E1s?" -> preserves \\u00BF and ?', () => {
        const { tokens } = es.phonemize('\u00BFC\u00F3mo est\u00E1s?');
        assert.ok(hasToken(tokens, '\u00BF'), `\\u00BF preserved: ${JSON.stringify(tokens)}`);
        assert.ok(hasToken(tokens, '?'), `? preserved: ${JSON.stringify(tokens)}`);
    });
});

// ===========================================================================
// Multi-word
// ===========================================================================

describe('SpanishG2P -- multi-word', () => {
    const es = new SpanishG2P();

    it('"el sol" -> has space between words', () => {
        const { tokens } = es.phonemize('el sol');
        assert.ok(hasToken(tokens, ' '), `space between words: ${JSON.stringify(tokens)}`);
    });

    it('"buenos dias amigo" -> multiple stress markers', () => {
        const { tokens } = es.phonemize('buenos dias amigo');
        const stressCount = tokens.filter(t => t === IPA_STRESS).length;
        assert.ok(stressCount >= 2, `multiple content words have stress (${stressCount}): ${JSON.stringify(tokens)}`);
    });

    it('"hola, como estas" -> multiple content words have stress', () => {
        const { tokens } = es.phonemize('hola, como estas');
        const stressCount = tokens.filter(t => t === IPA_STRESS).length;
        assert.ok(stressCount >= 2, `multiple content words stressed: ${JSON.stringify(tokens)}`);
    });
});

// ===========================================================================
// Empty string
// ===========================================================================

describe('SpanishG2P -- empty/edge cases', () => {
    const es = new SpanishG2P();

    it('"" -> empty tokens', () => {
        const { tokens } = es.phonemize('');
        assert.deepEqual(tokens, []);
    });

    it('digits and unknown chars are skipped', () => {
        const { tokens } = es.phonemize('123');
        assert.deepEqual(tokens, []);
    });
});

// ===========================================================================
// Prosody: tokens.length === prosody.length
// ===========================================================================

describe('SpanishG2P -- prosody alignment', () => {
    const es = new SpanishG2P();

    it('"hola mundo" -> tokens.length === prosody.length (phonemize)', () => {
        const result = es.phonemize('hola mundo');
        assert.equal(result.tokens.length, result.prosody.length);
    });

    it('"hola mundo" -> tokens.length === prosody.length (phonemizeWithProsody)', () => {
        const result = es.phonemizeWithProsody('hola mundo');
        assert.equal(result.tokens.length, result.prosody.length);
    });
});

// ===========================================================================
// sc before e/i -> single s
// ===========================================================================

describe('SpanishG2P -- sc before e/i', () => {
    const es = new SpanishG2P();

    it('"escena" -> sc before e -> single s', () => {
        const { tokens } = es.phonemize('escena');
        assert.ok(hasToken(tokens, 's'), `sc before e -> s: ${JSON.stringify(tokens)}`);
    });
});

// ===========================================================================
// Detailed prosody: a2 stress positions, a3 word phoneme count
// ===========================================================================

describe('SpanishG2P -- phonemizeWithProsody detailed', () => {
    const es = new SpanishG2P();

    // -----------------------------------------------------------------------
    // 1. a2=2 at stress positions
    // -----------------------------------------------------------------------

    it('"hola" -> stress marker and following vowel have a2=2, others a2=0', () => {
        const { tokens, prosody } = es.phonemizeWithProsody('hola');
        const stressIdx = tokens.indexOf(IPA_STRESS);
        assert.ok(stressIdx >= 0, `"hola" should have a stress marker: ${JSON.stringify(tokens)}`);

        // Stress marker itself has a2=2
        assert.equal(prosody[stressIdx].a2, 2,
            'stress marker token should have a2=2');

        // The vowel immediately after the stress marker should also have a2=2
        assert.ok(stressIdx + 1 < tokens.length,
            'there should be a token after the stress marker');
        assert.equal(prosody[stressIdx + 1].a2, 2,
            `vowel after stress marker ("${tokens[stressIdx + 1]}") should have a2=2`);

        // All other tokens should have a2=0
        for (let i = 0; i < tokens.length; i++) {
            if (i !== stressIdx && i !== stressIdx + 1) {
                assert.equal(prosody[i].a2, 0,
                    `token "${tokens[i]}" at index ${i} should have a2=0`);
            }
        }
    });

    // -----------------------------------------------------------------------
    // 2. a3 word phoneme count
    // -----------------------------------------------------------------------

    it('"hola" -> all word tokens have a3 = phoneme count (excluding stress marker)', () => {
        const { tokens, prosody } = es.phonemizeWithProsody('hola');
        // "hola" -> [IPA_STRESS, 'o', 'l', 'a'] -- 3 phonemes excl. stress
        const wordPhonemeCount = tokens.filter(t => t !== IPA_STRESS).length;
        assert.ok(wordPhonemeCount > 0, 'should have at least one phoneme');

        for (let i = 0; i < tokens.length; i++) {
            assert.equal(prosody[i].a3, wordPhonemeCount,
                `token "${tokens[i]}" at index ${i} should have a3=${wordPhonemeCount}, got ${prosody[i].a3}`);
        }
    });

    // -----------------------------------------------------------------------
    // 3. Multi-word a3 reset
    // -----------------------------------------------------------------------

    it('"hola mundo" -> each word has independent a3, space has a3=0', () => {
        const { tokens, prosody } = es.phonemizeWithProsody('hola mundo');
        const spaceIdx = tokens.indexOf(' ');
        assert.ok(spaceIdx > 0, `should have a space separator: ${JSON.stringify(tokens)}`);

        // Space token has a3=0
        assert.equal(prosody[spaceIdx].a3, 0,
            'space token should have a3=0');

        // Word 1 ("hola"): tokens before the space
        const word1Tokens = tokens.slice(0, spaceIdx);
        const word1PhCount = word1Tokens.filter(t => t !== IPA_STRESS).length;
        assert.ok(word1PhCount > 0, 'word 1 should have phonemes');
        for (let i = 0; i < spaceIdx; i++) {
            assert.equal(prosody[i].a3, word1PhCount,
                `word1 token "${tokens[i]}" at index ${i} should have a3=${word1PhCount}`);
        }

        // Word 2 ("mundo"): tokens after the space
        const word2Tokens = tokens.slice(spaceIdx + 1);
        const word2PhCount = word2Tokens.filter(t => t !== IPA_STRESS).length;
        assert.ok(word2PhCount > 0, 'word 2 should have phonemes');
        for (let i = spaceIdx + 1; i < tokens.length; i++) {
            assert.equal(prosody[i].a3, word2PhCount,
                `word2 token "${tokens[i]}" at index ${i} should have a3=${word2PhCount}`);
        }

        // The two words have different lengths, so a3 should differ
        assert.notEqual(word1PhCount, word2PhCount,
            `"hola" (${word1PhCount} phonemes) and "mundo" (${word2PhCount} phonemes) should have different a3`);
    });

    // -----------------------------------------------------------------------
    // 4. Function word prosody
    // -----------------------------------------------------------------------

    it('"el gato" -> "el" has no stress marker; "gato" has stress', () => {
        const { tokens, prosody } = es.phonemizeWithProsody('el gato');
        const spaceIdx = tokens.indexOf(' ');
        assert.ok(spaceIdx > 0, `should have a space separator: ${JSON.stringify(tokens)}`);

        // "el" is a function word -> no stress marker in word 1
        const word1Tokens = tokens.slice(0, spaceIdx);
        assert.ok(!word1Tokens.includes(IPA_STRESS),
            `function word "el" should have no stress marker: ${JSON.stringify(word1Tokens)}`);

        // "gato" is a content word -> should have a stress marker
        const word2Tokens = tokens.slice(spaceIdx + 1);
        assert.ok(word2Tokens.includes(IPA_STRESS),
            `content word "gato" should have a stress marker: ${JSON.stringify(word2Tokens)}`);

        // Verify a2 values: no a2=2 in "el" tokens
        for (let i = 0; i < spaceIdx; i++) {
            assert.equal(prosody[i].a2, 0,
                `function word token "${tokens[i]}" at index ${i} should have a2=0`);
        }

        // "gato" should have a2=2 at stress marker and following vowel
        const gatoStressIdx = tokens.indexOf(IPA_STRESS, spaceIdx + 1);
        assert.ok(gatoStressIdx >= 0, '"gato" should have a stress marker');
        assert.equal(prosody[gatoStressIdx].a2, 2,
            'stress marker in "gato" should have a2=2');
        assert.equal(prosody[gatoStressIdx + 1].a2, 2,
            `vowel after stress marker in "gato" ("${tokens[gatoStressIdx + 1]}") should have a2=2`);
    });

    // -----------------------------------------------------------------------
    // 5. Punctuation prosody
    // -----------------------------------------------------------------------

    it('"hola." -> punctuation token has a1=0, a2=0, a3=0', () => {
        const { tokens, prosody } = es.phonemizeWithProsody('hola.');
        const dotIdx = tokens.indexOf('.');
        assert.ok(dotIdx >= 0, `should have a "." token: ${JSON.stringify(tokens)}`);

        assert.equal(prosody[dotIdx].a1, 0,
            'punctuation "." should have a1=0');
        assert.equal(prosody[dotIdx].a2, 0,
            'punctuation "." should have a2=0');
        assert.equal(prosody[dotIdx].a3, 0,
            'punctuation "." should have a3=0');
    });

    // -----------------------------------------------------------------------
    // 6. Empty string
    // -----------------------------------------------------------------------

    it('phonemizeWithProsody("") -> empty arrays', () => {
        const { tokens, prosody } = es.phonemizeWithProsody('');
        assert.deepEqual(tokens, [], 'tokens should be empty for empty input');
        assert.deepEqual(prosody, [], 'prosody should be empty for empty input');
    });
});
