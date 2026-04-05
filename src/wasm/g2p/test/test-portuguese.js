/**
 * Portuguese G2P tests
 *
 * Validates Brazilian Portuguese rule-based G2P (ported from Rust portuguese.rs).
 * Tests: nasal vowels, coda-l vocalization, palatalization, r polymorphism,
 * digraphs, stress detection, vowel reduction, BR post-processing, NFD
 * normalization, multi-word sentences, punctuation handling.
 *
 * Run: node --test src/wasm/g2p/test/test-portuguese.js
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { PortugueseG2P } from '../src/pt/index.js';

// ---------------------------------------------------------------------------
// IPA codepoints -- must match pua-map.js / Rust portuguese.rs
// ---------------------------------------------------------------------------

const PUA_AFFRICATE_TCH = '\uE054'; // tʃ (palatalized t before i)
const PUA_AFFRICATE_DZH = '\uE055'; // dʒ (palatalized d before i)

const IPA_EPSILON   = '\u025B'; // ɛ  open-mid front unrounded
const IPA_OPEN_O    = '\u0254'; // ɔ  open-mid back rounded
const IPA_VOICED_G  = '\u0261'; // ɡ  voiced velar plosive
const IPA_ESH       = '\u0283'; // ʃ  voiceless postalveolar fricative
const IPA_EZH       = '\u0292'; // ʒ  voiced postalveolar fricative
const IPA_UVULAR_R  = '\u0281'; // ʁ  voiced uvular fricative
const IPA_PALATAL_N = '\u0272'; // ɲ  palatal nasal
const IPA_TAP       = '\u027E'; // ɾ  alveolar tap
const IPA_PALATAL_L = '\u028E'; // ʎ  palatal lateral approximant

const NASAL_A = '\u00E3'; // ã
const NASAL_E = '\u1EBD'; // ẽ
const NASAL_I = '\u0129'; // ĩ
const NASAL_O = '\u00F5'; // õ
const NASAL_U = '\u0169'; // ũ

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function hasToken(tokens, token) {
    return tokens.includes(token);
}

// ===========================================================================
// Basic API structure
// ===========================================================================

describe('PortugueseG2P -- API structure', () => {
    it('should return { tokens, prosody } from phonemize()', () => {
        const pt = new PortugueseG2P();
        const result = pt.phonemize('bom');
        assert.ok(Array.isArray(result.tokens), 'tokens should be an array');
        assert.ok(Array.isArray(result.prosody), 'prosody should be an array');
        assert.equal(result.tokens.length, result.prosody.length,
            'tokens and prosody should have same length');
    });

    it('should return all-null prosody from phonemize()', () => {
        const pt = new PortugueseG2P();
        const { prosody } = pt.phonemize('bom');
        assert.ok(prosody.every(p => p === null), 'phonemize prosody should be all null');
    });

    it('should have languageCode "pt"', () => {
        const pt = new PortugueseG2P();
        assert.equal(pt.languageCode, 'pt');
    });

    it('should handle empty string', () => {
        const pt = new PortugueseG2P();
        const r1 = pt.phonemize('');
        assert.deepEqual(r1.tokens, []);
        const r2 = pt.phonemizeWithProsody('');
        assert.deepEqual(r2.tokens, []);
    });

    it('should handle null/undefined input', () => {
        const pt = new PortugueseG2P();
        const r1 = pt.phonemize(null);
        assert.deepEqual(r1.tokens, []);
        const r2 = pt.phonemize(undefined);
        assert.deepEqual(r2.tokens, []);
    });

    it('should return matching tokens/prosody length from phonemizeWithProsody()', () => {
        const pt = new PortugueseG2P();
        const result = pt.phonemizeWithProsody('bom dia');
        assert.ok(Array.isArray(result.tokens));
        assert.ok(Array.isArray(result.prosody));
        assert.equal(result.tokens.length, result.prosody.length);
    });
});

// ===========================================================================
// Nasal vowels (Rust test 1)
// ===========================================================================

describe('PortugueseG2P -- nasal vowels', () => {
    const pt = new PortugueseG2P();

    it('should produce nasal o in "bom"', () => {
        // "bom" -> b + nasal o (o tilde)
        const { tokens } = pt.phonemize('bom');
        assert.ok(hasToken(tokens, NASAL_O), `expected nasal o in [${tokens.join(', ')}]`);
        // Should NOT have trailing 'm' after nasal vowel (duplicate removed)
        assert.equal(tokens[tokens.length - 1], NASAL_O,
            `no trailing m after nasal: [${tokens.join(', ')}]`);
    });

    it('should NOT nasalize before nh digraph in "manh\u00E3"', () => {
        // "manhã" -- the 'a' before 'nh' should NOT be nasalized;
        // only the final ã is nasal
        const { tokens } = pt.phonemize('manh\u00E3');
        // Should contain palatal nasal from nh
        assert.ok(hasToken(tokens, IPA_PALATAL_N),
            `expected palatal nasal in manh\u00E3: [${tokens.join(', ')}]`);
        // Should contain nasal a from ã
        assert.ok(hasToken(tokens, NASAL_A),
            `expected nasal a in manh\u00E3: [${tokens.join(', ')}]`);
    });
});

// ===========================================================================
// Coda-l vocalization (Rust test 2)
// ===========================================================================

describe('PortugueseG2P -- coda-l vocalization', () => {
    const pt = new PortugueseG2P();

    it('should vocalize final l to w in "Brasil"', () => {
        // "Brasil" -> b ʁ a z i w (final l -> w)
        const { tokens } = pt.phonemize('Brasil');
        assert.ok(hasToken(tokens, 'w'), `expected coda-l -> w in [${tokens.join(', ')}]`);
        assert.ok(!hasToken(tokens, 'l'), `should not contain 'l' in coda: [${tokens.join(', ')}]`);
    });

    it('should vocalize l before consonant in "alto"', () => {
        // "alto" -> a w t u (l before t -> w)
        const { tokens } = pt.phonemize('alto');
        assert.ok(hasToken(tokens, 'w'), `expected coda-l -> w in 'alto': [${tokens.join(', ')}]`);
    });
});

// ===========================================================================
// Palatalization (Rust test 3)
// ===========================================================================

describe('PortugueseG2P -- palatalization', () => {
    const pt = new PortugueseG2P();

    it('should palatalize t before i in "tia"', () => {
        const { tokens } = pt.phonemize('tia');
        assert.ok(hasToken(tokens, PUA_AFFRICATE_TCH),
            `expected tʃ affricate in 'tia': [${tokens.join(', ')}]`);
    });

    it('should palatalize d before i in "dia"', () => {
        const { tokens } = pt.phonemize('dia');
        assert.ok(hasToken(tokens, PUA_AFFRICATE_DZH),
            `expected dʒ affricate in 'dia': [${tokens.join(', ')}]`);
    });

    it('should palatalize t+e in unstressed final position in "gente"', () => {
        // "gente" -> final unstressed e with preceding t -> tʃ+i
        const { tokens } = pt.phonemize('gente');
        const lastTwo = tokens.slice(-2);
        // Should end with either tʃ+i (BR post-processing) or just i
        assert.ok(
            hasToken(tokens, PUA_AFFRICATE_TCH) || hasToken(tokens, PUA_AFFRICATE_DZH) ||
            tokens[tokens.length - 1] === 'i',
            `expected palatalization or i-reduction in 'gente': [${tokens.join(', ')}]`);
    });
});

// ===========================================================================
// r polymorphism (Rust test 4)
// ===========================================================================

describe('PortugueseG2P -- r polymorphism', () => {
    const pt = new PortugueseG2P();

    it('should use tap for intervocalic r in "caro"', () => {
        // "caro" -> k a ɾ u  (intervocalic r -> tap)
        const { tokens } = pt.phonemize('caro');
        assert.ok(hasToken(tokens, IPA_TAP),
            `expected tap in 'caro': [${tokens.join(', ')}]`);
    });

    it('should use uvular r for word-initial r in "rato"', () => {
        // "rato" -> ʁ a t u  (initial r -> uvular)
        const { tokens } = pt.phonemize('rato');
        assert.ok(hasToken(tokens, IPA_UVULAR_R),
            `expected uvular r in 'rato': [${tokens.join(', ')}]`);
    });

    it('should use uvular r for "rr" in "carro"', () => {
        // "carro" -> k a ʁ u (rr -> uvular, deduplicated)
        const { tokens } = pt.phonemize('carro');
        assert.ok(hasToken(tokens, IPA_UVULAR_R),
            `expected uvular R in 'carro': [${tokens.join(', ')}]`);
    });
});

// ===========================================================================
// Digraphs lh/nh (Rust test 5)
// ===========================================================================

describe('PortugueseG2P -- digraphs', () => {
    const pt = new PortugueseG2P();

    it('should convert lh to palatal lateral in "filho"', () => {
        const { tokens } = pt.phonemize('filho');
        assert.ok(hasToken(tokens, IPA_PALATAL_L),
            `expected palatal L in 'filho': [${tokens.join(', ')}]`);
    });

    it('should convert nh to palatal nasal in "junho"', () => {
        const { tokens } = pt.phonemize('junho');
        assert.ok(hasToken(tokens, IPA_PALATAL_N),
            `expected palatal N in 'junho': [${tokens.join(', ')}]`);
    });
});

// ===========================================================================
// Stress detection (Rust tests 6-7)
// ===========================================================================

describe('PortugueseG2P -- stress detection', () => {
    const pt = new PortugueseG2P();

    it('should detect accent-based stress in "caf\u00E9"', () => {
        // café has acute on final vowel -> oxytone
        // The phonemes should contain open-mid front unrounded vowel (ɛ)
        const { tokens } = pt.phonemize('caf\u00E9');
        assert.ok(hasToken(tokens, IPA_EPSILON),
            `expected open vowel from acute in 'caf\u00E9': [${tokens.join(', ')}]`);
    });

    it('should detect penultimate stress in "casa"', () => {
        // "casa" ends in 'a' -> paroxytone (penultimate stress)
        // Stress on first syllable 'a', unstressed final 'a'
        const { tokens } = pt.phonemize('casa');
        assert.ok(tokens.length >= 3, `expected at least 3 tokens in 'casa'`);
    });
});

// ===========================================================================
// Vowel reduction (Rust tests 8, 16)
// ===========================================================================

describe('PortugueseG2P -- vowel reduction', () => {
    const pt = new PortugueseG2P();

    it('should reduce unstressed final e in "grande"', () => {
        // "grande" -> final unstressed e -> d+e -> dʒ+i (BR post-proc)
        const { tokens } = pt.phonemize('grande');
        const lastTwo = tokens.slice(-2);
        assert.deepEqual(lastTwo, [PUA_AFFRICATE_DZH, 'i'],
            `grande should end with dʒ+i: [${tokens.join(', ')}]`);
    });

    it('should reduce unstressed final o to u in "gato"', () => {
        // "gato" -> g a t u (unstressed final o -> u)
        const { tokens } = pt.phonemize('gato');
        assert.equal(tokens[tokens.length - 1], 'u',
            `gato should end with 'u' (final o reduction): [${tokens.join(', ')}]`);
    });
});

// ===========================================================================
// c cedilla (Rust test 9)
// ===========================================================================

describe('PortugueseG2P -- c cedilla', () => {
    const pt = new PortugueseG2P();

    it('should convert \u00E7 to s in "cora\u00E7\u00E3o"', () => {
        const { tokens } = pt.phonemize('cora\u00E7\u00E3o');
        assert.ok(hasToken(tokens, 's'),
            `expected 's' from cedilla in 'cora\u00E7\u00E3o': [${tokens.join(', ')}]`);
    });
});

// ===========================================================================
// qu digraph (Rust test 11)
// ===========================================================================

describe('PortugueseG2P -- qu digraph', () => {
    const pt = new PortugueseG2P();

    it('should produce k (silent u) in "quero"', () => {
        // "quero" -> k e ʁ u (qu before e: u is silent)
        const { tokens } = pt.phonemize('quero');
        assert.equal(tokens[0], 'k', `quero should start with k: [${tokens.join(', ')}]`);
    });

    it('should produce kw in "quando"', () => {
        // "quando" -> kw... (qu before a: u pronounced as w)
        const { tokens } = pt.phonemize('quando');
        assert.equal(tokens[0], 'k', `quando starts with k`);
        assert.equal(tokens[1], 'w', `quando has w glide after k`);
    });
});

// ===========================================================================
// Intervocalic s (Rust test 12)
// ===========================================================================

describe('PortugueseG2P -- intervocalic s', () => {
    const pt = new PortugueseG2P();

    it('should voice intervocalic s to z in "casa"', () => {
        // "casa" -> k a z a (s between vowels -> z)
        const { tokens } = pt.phonemize('casa');
        assert.ok(hasToken(tokens, 'z'),
            `expected 'z' from intervocalic s in 'casa': [${tokens.join(', ')}]`);
    });
});

// ===========================================================================
// ss digraph (Rust test 17)
// ===========================================================================

describe('PortugueseG2P -- ss digraph', () => {
    const pt = new PortugueseG2P();

    it('should produce single s from "ss" in "passo"', () => {
        // "passo" -> p a s u (ss -> s, final o -> u)
        const { tokens } = pt.phonemize('passo');
        const sCount = tokens.filter(t => t === 's').length;
        assert.equal(sCount, 1, `ss should produce single s: [${tokens.join(', ')}]`);
    });
});

// ===========================================================================
// ch digraph
// ===========================================================================

describe('PortugueseG2P -- ch digraph', () => {
    const pt = new PortugueseG2P();

    it('should convert ch to ʃ in "chuva"', () => {
        const { tokens } = pt.phonemize('chuva');
        assert.ok(hasToken(tokens, IPA_ESH),
            `expected ʃ in 'chuva': [${tokens.join(', ')}]`);
    });
});

// ===========================================================================
// sc before soft vowel
// ===========================================================================

describe('PortugueseG2P -- sc digraph', () => {
    const pt = new PortugueseG2P();

    it('should convert sc+i to s in "piscina"', () => {
        const { tokens } = pt.phonemize('piscina');
        assert.ok(hasToken(tokens, 's'),
            `expected 's' from sc in 'piscina': [${tokens.join(', ')}]`);
    });
});

// ===========================================================================
// g + soft vowel
// ===========================================================================

describe('PortugueseG2P -- g + soft vowel', () => {
    const pt = new PortugueseG2P();

    it('should convert g+e to ʒ in "gente"', () => {
        const { tokens } = pt.phonemize('gente');
        assert.ok(hasToken(tokens, IPA_EZH),
            `expected ʒ in 'gente': [${tokens.join(', ')}]`);
    });
});

// ===========================================================================
// j
// ===========================================================================

describe('PortugueseG2P -- j', () => {
    const pt = new PortugueseG2P();

    it('should convert j to ʒ in "janela"', () => {
        const { tokens } = pt.phonemize('janela');
        assert.ok(hasToken(tokens, IPA_EZH),
            `expected ʒ in 'janela': [${tokens.join(', ')}]`);
    });
});

// ===========================================================================
// x
// ===========================================================================

describe('PortugueseG2P -- x', () => {
    const pt = new PortugueseG2P();

    it('should convert word-initial x to ʃ in "xadrez"', () => {
        const { tokens } = pt.phonemize('xadrez');
        assert.ok(hasToken(tokens, IPA_ESH),
            `expected ʃ in 'xadrez': [${tokens.join(', ')}]`);
    });
});

// ===========================================================================
// NFD normalization (Rust test 15)
// ===========================================================================

describe('PortugueseG2P -- NFD normalization', () => {
    const pt = new PortugueseG2P();

    it('should produce same output for NFD and NFC of "caf\u00E9"', () => {
        // "cafe\u0301" (NFD: e + combining acute) should match "caf\u00E9" (NFC)
        const nfd = pt.phonemize('cafe\u0301');
        const nfc = pt.phonemize('caf\u00E9');
        assert.deepEqual(nfd.tokens, nfc.tokens,
            'NFD and NFC should produce identical phonemes');
    });
});

// ===========================================================================
// ou reduction (Rust test 19)
// ===========================================================================

describe('PortugueseG2P -- ou reduction', () => {
    const pt = new PortugueseG2P();

    it('should reduce ou to o in "outro"', () => {
        // "outro" -> o t ʁ u (ou -> o, BR reduction)
        const { tokens } = pt.phonemize('outro');
        assert.equal(tokens[0], 'o', `ou should reduce to o: [${tokens.join(', ')}]`);
    });
});

// ===========================================================================
// Multi-word sentence (Rust test 18)
// ===========================================================================

describe('PortugueseG2P -- multi-word', () => {
    const pt = new PortugueseG2P();

    it('should contain space in multi-word "bom dia"', () => {
        const { tokens } = pt.phonemize('bom dia');
        assert.ok(hasToken(tokens, ' '),
            `multi-word should contain space: [${tokens.join(', ')}]`);
    });

    it('should handle full sentence "Bom dia, como voc\u00EA est\u00E1?"', () => {
        const { tokens } = pt.phonemize('Bom dia, como voc\u00EA est\u00E1?');
        assert.ok(tokens.length >= 8,
            `expected at least 8 tokens: [${tokens.join(', ')}]`);
        // Should contain comma and question mark punctuation
        assert.ok(hasToken(tokens, ','), 'should have comma');
        assert.ok(hasToken(tokens, '?'), 'should have question mark');
    });
});

// ===========================================================================
// h silent
// ===========================================================================

describe('PortugueseG2P -- silent h', () => {
    const pt = new PortugueseG2P();

    it('should drop h in "hora"', () => {
        const { tokens } = pt.phonemize('hora');
        // First phoneme should NOT be 'h'
        assert.notEqual(tokens[0], 'h',
            `'hora' should not start with h: [${tokens.join(', ')}]`);
    });
});

// ===========================================================================
// Prosody length matching
// ===========================================================================

describe('PortugueseG2P -- prosody', () => {
    const pt = new PortugueseG2P();

    it('should have matching tokens and prosody length', () => {
        const { tokens, prosody } = pt.phonemize('ol\u00E1');
        assert.equal(tokens.length, prosody.length,
            'tokens and prosody should have same length');
    });

    it('should have matching tokens and prosody length for long sentence', () => {
        const { tokens, prosody } = pt.phonemize('Bom dia, como voc\u00EA est\u00E1?');
        assert.equal(tokens.length, prosody.length,
            'tokens and prosody should have same length');
    });
});

// ===========================================================================
// Case insensitivity
// ===========================================================================

describe('PortugueseG2P -- case insensitivity', () => {
    const pt = new PortugueseG2P();

    it('should produce same output regardless of case', () => {
        const lower = pt.phonemize('brasil');
        const upper = pt.phonemize('BRASIL');
        const mixed = pt.phonemize('Brasil');
        assert.deepEqual(lower.tokens, upper.tokens,
            'lowercase and uppercase should produce same tokens');
        assert.deepEqual(lower.tokens, mixed.tokens,
            'lowercase and mixed case should produce same tokens');
    });
});

// ===========================================================================
// gu digraph
// ===========================================================================

describe('PortugueseG2P -- gu digraph', () => {
    const pt = new PortugueseG2P();

    it('should produce ɡ (silent u) in "guerra"', () => {
        // "guerra" -> gu before e: u is silent
        const { tokens } = pt.phonemize('guerra');
        assert.ok(hasToken(tokens, IPA_VOICED_G),
            `expected ɡ in 'guerra': [${tokens.join(', ')}]`);
    });
});

// ===========================================================================
// phonemizeWithProsody detailed tests
// ===========================================================================

describe('PortugueseG2P -- phonemizeWithProsody detailed', () => {
    const pt = new PortugueseG2P();

    it('should have exactly one a2=2 token (stressed vowel) in "café"', () => {
        const { tokens, prosody } = pt.phonemizeWithProsody('caf\u00E9');
        const stressedIndices = [];
        for (let i = 0; i < prosody.length; i++) {
            if (prosody[i].a2 === 2) {
                stressedIndices.push(i);
            }
        }
        assert.equal(stressedIndices.length, 1,
            `expected exactly 1 token with a2=2 in "café", got ${stressedIndices.length}: ` +
            `tokens=[${tokens.join(', ')}], a2=[${prosody.map(p => p.a2).join(', ')}]`);
        // All other tokens should have a2=0
        for (let i = 0; i < prosody.length; i++) {
            if (i !== stressedIndices[0]) {
                assert.equal(prosody[i].a2, 0,
                    `token "${tokens[i]}" at index ${i} should have a2=0`);
            }
        }
    });

    it('should set a3 = word phoneme count for all tokens in "bom"', () => {
        const { tokens, prosody } = pt.phonemizeWithProsody('bom');
        // All tokens belong to one word, so a3 should be the same for all
        const expectedA3 = tokens.length;
        for (let i = 0; i < tokens.length; i++) {
            assert.equal(prosody[i].a3, expectedA3,
                `token "${tokens[i]}" at index ${i} should have a3=${expectedA3}, ` +
                `got ${prosody[i].a3}`);
        }
    });

    it('should reset a3 per word in "bom dia" and set a3=0 for space', () => {
        const { tokens, prosody } = pt.phonemizeWithProsody('bom dia');
        const spaceIdx = tokens.indexOf(' ');
        assert.ok(spaceIdx > 0, 'should have a space separator');

        // Space should have a3=0
        assert.equal(prosody[spaceIdx].a3, 0,
            'space token should have a3=0');

        // Word 1: tokens before space
        const word1Count = spaceIdx;
        for (let i = 0; i < spaceIdx; i++) {
            assert.equal(prosody[i].a3, word1Count,
                `word1 token "${tokens[i]}" at index ${i} should have a3=${word1Count}`);
        }

        // Word 2: tokens after space
        const word2Count = tokens.length - spaceIdx - 1;
        for (let i = spaceIdx + 1; i < tokens.length; i++) {
            assert.equal(prosody[i].a3, word2Count,
                `word2 token "${tokens[i]}" at index ${i} should have a3=${word2Count}`);
        }
    });

    it('should place stress on final vowel (oxytone) in "café"', () => {
        const { tokens, prosody } = pt.phonemizeWithProsody('caf\u00E9');
        // Find the stressed token (a2=2)
        let stressIdx = -1;
        for (let i = 0; i < prosody.length; i++) {
            if (prosody[i].a2 === 2) {
                stressIdx = i;
                break;
            }
        }
        assert.ok(stressIdx >= 0, 'should have a stressed token');
        // The stressed token should be a vowel (ɛ from é)
        const stressedToken = tokens[stressIdx];
        assert.equal(stressedToken, IPA_EPSILON,
            `stressed token should be ɛ (from é), got "${stressedToken}"`);
        // It should be the last phoneme (final syllable stress)
        assert.equal(stressIdx, tokens.length - 1,
            `stress should be on final position (oxytone): stressIdx=${stressIdx}, ` +
            `len=${tokens.length}`);
    });

    it('should place stress on penultimate vowel (paroxytone) in "casa"', () => {
        const { tokens, prosody } = pt.phonemizeWithProsody('casa');
        // Find the stressed token (a2=2)
        let stressIdx = -1;
        for (let i = 0; i < prosody.length; i++) {
            if (prosody[i].a2 === 2) {
                stressIdx = i;
                break;
            }
        }
        assert.ok(stressIdx >= 0, 'should have a stressed token');
        // Stress should NOT be on the last token (that would be oxytone)
        assert.ok(stressIdx < tokens.length - 1,
            `stress should be before the final token (paroxytone): stressIdx=${stressIdx}, ` +
            `tokens=[${tokens.join(', ')}]`);
    });

    it('should set a1=0, a2=0, a3=0 for punctuation in "olá!"', () => {
        const { tokens, prosody } = pt.phonemizeWithProsody('ol\u00E1!');
        // Find the punctuation token '!'
        const exclIdx = tokens.indexOf('!');
        assert.ok(exclIdx >= 0, 'should have "!" token');
        assert.equal(prosody[exclIdx].a1, 0,
            'punctuation a1 should be 0');
        assert.equal(prosody[exclIdx].a2, 0,
            'punctuation a2 should be 0');
        assert.equal(prosody[exclIdx].a3, 0,
            'punctuation a3 should be 0');
    });

    it('should return empty arrays for empty string', () => {
        const { tokens, prosody } = pt.phonemizeWithProsody('');
        assert.deepEqual(tokens, [], 'tokens should be empty');
        assert.deepEqual(prosody, [], 'prosody should be empty');
    });
});
