/**
 * French G2P tests
 *
 * Validates rule-based French G2P (ported from Rust french.rs).
 * Tests: nasal vowels, silent finals, digraphs, vowel combinations,
 * intervocalic s, -er endings, -tion, -ille, normalization, prosody.
 *
 * Run: node --test src/wasm/g2p/test/test-french.js
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { FrenchG2P } from '../src/fr/index.js';

// ---------------------------------------------------------------------------
// PUA codepoints -- must match pua-map.js / Rust french.rs
// ---------------------------------------------------------------------------

const PUA_Y_VOWEL   = '\uE01E'; // y_vowel [y]
const PUA_NASAL_EIN = '\uE056'; // nasal open-mid front (vin, pain)
const PUA_NASAL_AN  = '\uE057'; // nasal open back (dans, vent)
const PUA_NASAL_ON  = '\uE058'; // nasal open-mid back (bon, mont)

// Single IPA codepoints
const IPA_OPEN_E    = '\u025B'; // open-mid front unrounded
const IPA_OPEN_O    = '\u0254'; // open-mid back rounded
const IPA_SCHWA     = '\u0259'; // schwa
const IPA_VOICED_G  = '\u0261'; // voiced velar plosive
const IPA_ESH       = '\u0283'; // voiceless postalveolar fricative
const IPA_EZH       = '\u0292'; // voiced postalveolar fricative
const IPA_UVULAR_R  = '\u0281'; // voiced uvular fricative
const IPA_PALATAL_N = '\u0272'; // palatal nasal
const IPA_TURNED_H  = '\u0265'; // labial-palatal approximant
const IPA_SLASHED_O = '\u00F8'; // close-mid front rounded
const IPA_OE_LIG    = '\u0153'; // open-mid front rounded

// ---------------------------------------------------------------------------
// Helper: join tokens for easier comparison
// ---------------------------------------------------------------------------

function tokStr(text) {
    const fr = new FrenchG2P();
    return fr.phonemize(text).tokens.join('');
}

function hasToken(tokens, token) {
    return tokens.includes(token);
}

// ===========================================================================
// Basic API structure
// ===========================================================================

describe('FrenchG2P -- API structure', () => {
    it('should return { tokens, prosody } from phonemize()', () => {
        const fr = new FrenchG2P();
        const result = fr.phonemize('bonjour');
        assert.ok(Array.isArray(result.tokens), 'tokens should be an array');
        assert.ok(Array.isArray(result.prosody), 'prosody should be an array');
        assert.equal(result.tokens.length, result.prosody.length,
            'tokens and prosody should have same length');
    });

    it('should return all-null prosody from phonemize()', () => {
        const fr = new FrenchG2P();
        const { prosody } = fr.phonemize('bonjour');
        assert.ok(prosody.every(p => p === null), 'phonemize prosody should be all null');
    });

    it('should return { tokens, prosody } from phonemizeWithProsody()', () => {
        const fr = new FrenchG2P();
        const result = fr.phonemizeWithProsody('bonjour');
        assert.ok(Array.isArray(result.tokens));
        assert.ok(Array.isArray(result.prosody));
        assert.equal(result.tokens.length, result.prosody.length);
    });

    it('should return prosody objects with a1/a2/a3 from phonemizeWithProsody()', () => {
        const fr = new FrenchG2P();
        const { prosody } = fr.phonemizeWithProsody('bonjour');
        for (const p of prosody) {
            assert.ok(p !== null, 'prosody entries should not be null');
            assert.ok('a1' in p, 'prosody should have a1');
            assert.ok('a2' in p, 'prosody should have a2');
            assert.ok('a3' in p, 'prosody should have a3');
        }
    });

    it('should have languageCode === "fr"', () => {
        const fr = new FrenchG2P();
        assert.equal(fr.languageCode, 'fr');
    });

    it('should handle empty string', () => {
        const fr = new FrenchG2P();
        const r1 = fr.phonemize('');
        assert.deepEqual(r1.tokens, []);
        assert.deepEqual(r1.prosody, []);
        const r2 = fr.phonemizeWithProsody('');
        assert.deepEqual(r2.tokens, []);
        assert.deepEqual(r2.prosody, []);
    });

    it('should handle null/undefined input', () => {
        const fr = new FrenchG2P();
        const r1 = fr.phonemize(null);
        assert.deepEqual(r1.tokens, []);
        const r2 = fr.phonemize(undefined);
        assert.deepEqual(r2.tokens, []);
    });
});

// ===========================================================================
// Nasal vowels
// ===========================================================================

describe('FrenchG2P -- Nasal vowels', () => {
    it('nasal on: "bon" -> contains PUA nasal-on', () => {
        const fr = new FrenchG2P();
        const { tokens } = fr.phonemize('bon');
        assert.ok(hasToken(tokens, PUA_NASAL_ON),
            `"bon" should contain nasal-on PUA: [${tokens.join(', ')}]`);
        assert.equal(tokStr('bon'), `b${PUA_NASAL_ON}`);
    });

    it('nasal on: "bonjour" -> contains PUA nasal-on', () => {
        const fr = new FrenchG2P();
        const { tokens } = fr.phonemize('bonjour');
        assert.ok(hasToken(tokens, PUA_NASAL_ON),
            `"bonjour" should contain nasal-on: [${tokens.join(', ')}]`);
    });

    it('nasal an: "france" -> contains PUA nasal-an', () => {
        const fr = new FrenchG2P();
        const { tokens } = fr.phonemize('france');
        assert.ok(hasToken(tokens, PUA_NASAL_AN),
            `"france" should contain nasal-an: [${tokens.join(', ')}]`);
    });

    it('nasal an: "francais" -> contains PUA nasal-an', () => {
        const fr = new FrenchG2P();
        // fran\u00E7ais has cedilla
        const { tokens } = fr.phonemize('fran\u00E7ais');
        assert.ok(hasToken(tokens, PUA_NASAL_AN),
            `"fran\u00E7ais" should contain nasal-an: [${tokens.join(', ')}]`);
    });

    it('nasal ein: "vin" -> contains PUA nasal-ein', () => {
        const fr = new FrenchG2P();
        const { tokens } = fr.phonemize('vin');
        assert.ok(hasToken(tokens, PUA_NASAL_EIN),
            `"vin" should contain nasal-ein: [${tokens.join(', ')}]`);
        assert.equal(tokStr('vin'), `v${PUA_NASAL_EIN}`);
    });

    it('nasal guard: "bonne" -> NO nasalization (doubled nn)', () => {
        const result = tokStr('bonne');
        assert.ok(!result.includes(PUA_NASAL_ON),
            `"bonne" should NOT contain nasal-on (doubled nn): ${result}`);
    });

    it('nasal guard: "anime" -> NO nasalization of "an" (next char is vowel)', () => {
        const result = tokStr('anime');
        assert.ok(!result.includes(PUA_NASAL_AN),
            `"anime" should NOT contain nasal-an (vowel follows): ${result}`);
    });

    it('oin nasal: "loin" -> w + nasal-ein', () => {
        const result = tokStr('loin');
        assert.ok(result.includes('w'), `"loin" oin -> w: ${result}`);
        assert.ok(result.includes(PUA_NASAL_EIN), `"loin" oin -> nasal-ein: ${result}`);
    });

    it('ien nasal: "bien" -> j + nasal-ein', () => {
        const result = tokStr('bien');
        assert.ok(result.includes('j'), `"bien" ien -> j: ${result}`);
        assert.ok(result.includes(PUA_NASAL_EIN), `"bien" ien -> nasal-ein: ${result}`);
    });

    it('ain nasal: "pain" -> nasal-ein', () => {
        const fr = new FrenchG2P();
        const { tokens } = fr.phonemize('pain');
        assert.ok(hasToken(tokens, PUA_NASAL_EIN),
            `"pain" ain -> nasal-ein: [${tokens.join(', ')}]`);
    });

    it('un nasal: "un" -> nasal-ein (modern French merger)', () => {
        const fr = new FrenchG2P();
        const { tokens } = fr.phonemize('un');
        assert.ok(hasToken(tokens, PUA_NASAL_EIN),
            `"un" un -> nasal-ein: [${tokens.join(', ')}]`);
    });
});

// ===========================================================================
// Silent final consonants
// ===========================================================================

describe('FrenchG2P -- Silent final consonants', () => {
    it('"petit" -> no final t', () => {
        const result = tokStr('petit');
        assert.ok(!result.endsWith('t'),
            `"petit" should not end with t: ${result}`);
    });

    it('"chat" -> no final t, has esh', () => {
        const result = tokStr('chat');
        assert.ok(result.includes(IPA_ESH), `"chat" should contain esh: ${result}`);
        assert.ok(!result.endsWith('t'), `"chat" final t should be silent: ${result}`);
    });

    it('"dans" -> no final s', () => {
        const result = tokStr('dans');
        // "dans" = d + nasal-an (n consumed by nasal), s is final silent
        assert.ok(!result.endsWith('s'),
            `"dans" should not end with s: ${result}`);
    });

    it('"porte" -> t IS pronounced (not final)', () => {
        const result = tokStr('porte');
        // "porte" -> p + open-o + uvular-r + t (e is silent at end)
        assert.ok(result.includes('t'),
            `"porte" should have pronounced t: ${result}`);
    });
});

// ===========================================================================
// -er verb ending
// ===========================================================================

describe('FrenchG2P -- -er verb ending', () => {
    it('"parler" -> ends with /e/', () => {
        const result = tokStr('parler');
        assert.ok(result.endsWith('e'),
            `polysyllabic -er should end /e/: ${result}`);
    });

    it('"hiver" (exception) -> has uvular-R', () => {
        const result = tokStr('hiver');
        assert.ok(result.includes(IPA_UVULAR_R),
            `"hiver" should have uvular-R: ${result}`);
    });

    it('"fer" (exception) -> has uvular-R', () => {
        const result = tokStr('fer');
        assert.ok(result.includes(IPA_UVULAR_R),
            `"fer" should have uvular-R: ${result}`);
    });

    it('"mer" -> has uvular-R (monosyllabic, vc < 2)', () => {
        const result = tokStr('mer');
        assert.ok(result.includes(IPA_UVULAR_R),
            `"mer" should have uvular-R (monosyllabic): ${result}`);
    });
});

// ===========================================================================
// Consonant digraphs
// ===========================================================================

describe('FrenchG2P -- Consonant digraphs', () => {
    it('ch: "chambre" -> contains esh', () => {
        const result = tokStr('chambre');
        assert.ok(result.includes(IPA_ESH),
            `"chambre" ch -> esh: ${result}`);
    });

    it('gn: "montagne" -> contains palatal-n', () => {
        const result = tokStr('montagne');
        assert.ok(result.includes(IPA_PALATAL_N),
            `"montagne" gn -> palatal-n: ${result}`);
    });

    it('ph: "photo" -> starts with f', () => {
        const result = tokStr('photo');
        assert.ok(result.startsWith('f'),
            `"photo" ph -> f: ${result}`);
    });

    it('th: "the" -> starts with t (not th)', () => {
        const result = tokStr('the');
        assert.ok(result.startsWith('t'),
            `"the" th -> t: ${result}`);
    });

    it('qu: "que" -> k', () => {
        assert.equal(tokStr('que'), 'k');
    });

    it('gu + front vowel: "guerre" -> voiced-g (silent u)', () => {
        const result = tokStr('guerre');
        assert.ok(result.includes(IPA_VOICED_G),
            `"guerre" gu+e -> voiced-g: ${result}`);
    });
});

// ===========================================================================
// Vowel digraphs and combinations
// ===========================================================================

describe('FrenchG2P -- Vowel digraphs', () => {
    it('oi: "trois" -> wa', () => {
        const result = tokStr('trois');
        assert.ok(result.includes('w'), `"trois" oi -> w: ${result}`);
        assert.ok(result.includes('a'), `"trois" oi -> a: ${result}`);
    });

    it('ou: "vous" -> u', () => {
        const result = tokStr('vous');
        assert.ok(result.includes('u'), `"vous" ou -> u: ${result}`);
    });

    it('au: "beau" -> o', () => {
        assert.equal(tokStr('beau'), 'bo');
    });

    it('eau: "eau" -> o', () => {
        assert.equal(tokStr('eau'), 'o');
    });

    it('ai: "fait" -> open-e', () => {
        const result = tokStr('fait');
        assert.ok(result.includes(IPA_OPEN_E),
            `"fait" ai -> open-e: ${result}`);
    });

    it('ei: "seize" -> open-e', () => {
        const result = tokStr('seize');
        assert.ok(result.includes(IPA_OPEN_E),
            `"seize" ei -> open-e: ${result}`);
    });

    it('oi: "moi" -> wa', () => {
        assert.equal(tokStr('moi'), 'mwa');
    });

    it('eu closed: "jeu" -> slashed-o', () => {
        const result = tokStr('jeu');
        assert.ok(result.includes(IPA_SLASHED_O),
            `"jeu" eu at end -> closed (slashed-o): ${result}`);
    });

    it('eu open: "fleur" -> oe-ligature', () => {
        const result = tokStr('fleur');
        assert.ok(result.includes(IPA_OE_LIG),
            `"fleur" eu before r -> open (oe-lig): ${result}`);
    });
});

// ===========================================================================
// -tion suffix
// ===========================================================================

describe('FrenchG2P -- -tion suffix', () => {
    it('"nation" -> s + j + nasal-on', () => {
        const result = tokStr('nation');
        assert.ok(result.includes('s'), `"nation" -tion -> s: ${result}`);
        assert.ok(result.includes('j'), `"nation" -tion -> j: ${result}`);
        assert.ok(result.includes(PUA_NASAL_ON), `"nation" -tion -> nasal-on: ${result}`);
    });
});

// ===========================================================================
// -ille
// ===========================================================================

describe('FrenchG2P -- -ille', () => {
    it('"fille" -> ij (default)', () => {
        const result = tokStr('fille');
        assert.ok(result.includes('j'), `"fille" should have j: ${result}`);
        assert.ok(!result.includes('l'), `"fille" should NOT have l: ${result}`);
    });

    it('"ville" (exception) -> il', () => {
        const result = tokStr('ville');
        assert.ok(result.includes('l'), `"ville" should have l: ${result}`);
    });

    it('"mille" (exception) -> il', () => {
        const result = tokStr('mille');
        assert.ok(result.includes('l'), `"mille" should have l: ${result}`);
    });

    it('"tranquille" (exception) -> il', () => {
        const result = tokStr('tranquille');
        assert.ok(result.includes('l'), `"tranquille" should have l: ${result}`);
    });
});

// ===========================================================================
// Intervocalic s
// ===========================================================================

describe('FrenchG2P -- Intervocalic s', () => {
    it('"maison" -> contains z (intervocalic s)', () => {
        const result = tokStr('maison');
        assert.ok(result.includes('z'),
            `"maison" intervocalic s -> z: ${result}`);
    });
});

// ===========================================================================
// y_vowel (PUA E01E)
// ===========================================================================

describe('FrenchG2P -- y_vowel', () => {
    it('"tu" -> PUA y_vowel', () => {
        const fr = new FrenchG2P();
        const { tokens } = fr.phonemize('tu');
        assert.ok(hasToken(tokens, PUA_Y_VOWEL),
            `"tu" -> PUA y_vowel: [${tokens.join(', ')}]`);
    });

    it('"lune" -> contains PUA y_vowel', () => {
        const fr = new FrenchG2P();
        const { tokens } = fr.phonemize('lune');
        assert.ok(hasToken(tokens, PUA_Y_VOWEL),
            `"lune" -> PUA y_vowel: [${tokens.join(', ')}]`);
    });
});

// ===========================================================================
// Semi-vowels
// ===========================================================================

describe('FrenchG2P -- Semi-vowels', () => {
    it('u + i: "lui" -> turned-h', () => {
        const result = tokStr('lui');
        assert.ok(result.includes(IPA_TURNED_H),
            `"lui" u before i -> turned-h: ${result}`);
    });
});

// ===========================================================================
// C/G softening
// ===========================================================================

describe('FrenchG2P -- C/G softening', () => {
    it('c + e: "cent" -> s', () => {
        const result = tokStr('cent');
        // "cent" -> s + nasal-an (e+n -> nasal)
        assert.ok(result.startsWith('s'),
            `"cent" c before e -> s: ${result}`);
    });

    it('c + i: "ciel" -> s', () => {
        const result = tokStr('ciel');
        assert.ok(result.startsWith('s'),
            `"ciel" c before i -> s: ${result}`);
    });

    it('g + e: "gens" -> ezh', () => {
        const result = tokStr('gens');
        assert.ok(result.includes(IPA_EZH),
            `"gens" g before e -> ezh: ${result}`);
    });

    it('g + e: "gel" -> starts with ezh', () => {
        const result = tokStr('gel');
        assert.ok(result.startsWith(IPA_EZH),
            `"gel" g before e -> ezh: ${result}`);
    });

    it('c-cedilla: "ca" (from garcon cedilla) -> s', () => {
        const result = tokStr('\u00E7a');
        assert.ok(result.startsWith('s'),
            `c-cedilla -> s: ${result}`);
    });
});

// ===========================================================================
// j consonant
// ===========================================================================

describe('FrenchG2P -- j consonant', () => {
    it('"jour" -> starts with ezh', () => {
        const result = tokStr('jour');
        assert.ok(result.includes(IPA_EZH),
            `"jour" j -> ezh: ${result}`);
    });
});

// ===========================================================================
// Silent h
// ===========================================================================

describe('FrenchG2P -- Silent h', () => {
    it('"homme" -> no h in output', () => {
        const result = tokStr('homme');
        assert.ok(!result.includes('h'),
            `"homme" h should be silent: ${result}`);
    });
});

// ===========================================================================
// x (context-dependent)
// ===========================================================================

describe('FrenchG2P -- x', () => {
    it('word-final x: "voix" -> no final x', () => {
        const result = tokStr('voix');
        assert.ok(!result.includes('x'),
            `"voix" final x should be silent: ${result}`);
    });
});

// ===========================================================================
// Doubled consonants
// ===========================================================================

describe('FrenchG2P -- Doubled consonants', () => {
    it('"belle" -> single l', () => {
        const result = tokStr('belle');
        const lCount = [...result].filter(c => c === 'l').length;
        assert.equal(lCount, 1, `doubled l -> single l in belle: ${result}`);
    });

    it('"terre" -> single uvular-R', () => {
        const result = tokStr('terre');
        const rCount = [...result].filter(c => c === IPA_UVULAR_R).length;
        assert.equal(rCount, 1, `doubled r -> single R in terre: ${result}`);
    });
});

// ===========================================================================
// Normalization
// ===========================================================================

describe('FrenchG2P -- Normalization', () => {
    it('uppercase: "BONJOUR" -> same as "bonjour"', () => {
        const upper = tokStr('BONJOUR');
        const lower = tokStr('bonjour');
        assert.equal(upper, lower,
            `uppercase and lowercase should produce same output: ${upper} vs ${lower}`);
    });

    it('NFD e-acute: "e\\u0301" -> treated as e-acute', () => {
        const nfd = tokStr('e\u0301t\u00E9');  // NFD "ete" (summer)
        const nfc = tokStr('\u00E9t\u00E9');    // NFC
        assert.equal(nfd, nfc,
            `NFD and NFC should produce same output: ${nfd} vs ${nfc}`);
    });
});

// ===========================================================================
// Eille pattern
// ===========================================================================

describe('FrenchG2P -- eille pattern', () => {
    it('"abeille" -> open-e + j', () => {
        const result = tokStr('abeille');
        assert.ok(result.includes(IPA_OPEN_E), `"abeille" eille -> open-e: ${result}`);
        assert.ok(result.includes('j'), `"abeille" eille -> j: ${result}`);
    });
});

// ===========================================================================
// Full sentences / multi-word
// ===========================================================================

describe('FrenchG2P -- Full sentence', () => {
    it('"Comment allez-vous?" -> non-empty with punctuation', () => {
        const fr = new FrenchG2P();
        const { tokens, prosody } = fr.phonemizeWithProsody('Comment allez-vous?');
        assert.ok(tokens.length > 0, 'should produce tokens');
        assert.equal(tokens.length, prosody.length, 'tokens and prosody same length');
        assert.ok(tokens.includes('?'), 'should contain ?');
    });

    it('"Bonjour, comment allez-vous?" -> has comma and question mark', () => {
        const fr = new FrenchG2P();
        const { tokens } = fr.phonemize('Bonjour, comment allez-vous?');
        assert.ok(tokens.includes(','), 'should contain comma');
        assert.ok(tokens.includes('?'), 'should contain question mark');
    });

    it('apostrophe elision: "l\'homme" -> l + homme phonemes', () => {
        const result = tokStr("l'homme");
        assert.ok(result.includes('l'), `"l'homme" -> should have l: ${result}`);
        // homme -> o + m (h silent, final e silent)
        assert.ok(result.includes('o'), `"l'homme" -> should have o from homme: ${result}`);
    });
});

// ===========================================================================
// Prosody stress
// ===========================================================================

describe('FrenchG2P -- Prosody', () => {
    it('"bonjour" -> has stressed phoneme (a2=2)', () => {
        const fr = new FrenchG2P();
        const { prosody } = fr.phonemizeWithProsody('bonjour');
        const stressed = prosody.filter(p => p && p.a2 === 2);
        assert.ok(stressed.length > 0, 'should have at least one stressed phoneme');
    });

    it('tokens.length === prosody.length', () => {
        const fr = new FrenchG2P();
        const words = ['bonjour', 'parler', 'maison', 'Comment allez-vous?'];
        for (const w of words) {
            const r = fr.phonemize(w);
            assert.equal(r.tokens.length, r.prosody.length,
                `tokens/prosody length mismatch for "${w}"`);
        }
    });

    it('a3 = word phoneme count', () => {
        const fr = new FrenchG2P();
        const { prosody } = fr.phonemizeWithProsody('bon');
        // "bon" -> b + nasal-on = 2 phonemes
        const wordProsody = prosody.filter(p => p && p.a3 > 0);
        assert.ok(wordProsody.length > 0, 'should have non-zero a3');
        assert.equal(wordProsody[0].a3, 2, '"bon" should have a3=2');
    });
});

// ===========================================================================
// Cedilla
// ===========================================================================

describe('FrenchG2P -- Cedilla', () => {
    it('"garcon" with cedilla -> contains s', () => {
        const result = tokStr('gar\u00E7on');
        assert.ok(result.includes('s'), `c-cedilla -> s: ${result}`);
    });
});

// ===========================================================================
// Aille / Ouille patterns
// ===========================================================================

describe('FrenchG2P -- aille/ouille', () => {
    it('"aille" suffix: "bataille" -> aj', () => {
        const result = tokStr('bataille');
        assert.ok(result.includes('a'), `"bataille" aille -> a: ${result}`);
        assert.ok(result.includes('j'), `"bataille" aille -> j: ${result}`);
    });
});

// ===========================================================================
// Additional Rust #[test] cases ported
// ===========================================================================

describe('FrenchG2P -- Rust test cases', () => {
    it('cher -> contains esh', () => {
        const result = tokStr('cher');
        assert.ok(result.includes(IPA_ESH), `"cher" ch -> esh: ${result}`);
    });

    it('ligne -> contains palatal-n', () => {
        const result = tokStr('ligne');
        assert.ok(result.includes(IPA_PALATAL_N), `"ligne" gn -> palatal-n: ${result}`);
    });

    it('photo -> starts with f', () => {
        const result = tokStr('photo');
        assert.ok(result.startsWith('f'), `"photo" ph -> f: ${result}`);
    });

    it('lui -> contains turned-h', () => {
        const result = tokStr('lui');
        assert.ok(result.includes(IPA_TURNED_H), `"lui" u+i -> turned-h: ${result}`);
    });

    it('ciel -> starts with s', () => {
        const result = tokStr('ciel');
        assert.ok(result.startsWith('s'), `"ciel" c+i -> s: ${result}`);
    });
});

// ===========================================================================
// phonemizeWithProsody detailed
// ===========================================================================

describe('FrenchG2P -- phonemizeWithProsody detailed', () => {
    const fr = new FrenchG2P();

    it('a2=2 uniqueness per word: "bon" has exactly one token with a2=2', () => {
        const { tokens, prosody } = fr.phonemizeWithProsody('bon');
        const stressed = prosody.filter(p => p.a2 === 2);
        assert.equal(stressed.length, 1,
            `"bon" should have exactly 1 stressed token (a2=2), got ${stressed.length}: [${tokens.join(', ')}]`);
        const unstressed = prosody.filter(p => p.a2 === 0);
        assert.equal(unstressed.length, tokens.length - 1,
            'all other tokens should have a2=0');
    });

    it('a2=2 at last vowel, not consonants: "bonjour" stress on last vowel phoneme', () => {
        const { tokens, prosody } = fr.phonemizeWithProsody('bonjour');
        // Find the index where a2=2
        const stressIdx = prosody.findIndex(p => p.a2 === 2);
        assert.ok(stressIdx >= 0, '"bonjour" should have a stressed phoneme');

        // The stressed token must be a vowel phoneme
        const stressedToken = tokens[stressIdx];
        const vowelPhonemes = new Set([
            'a', 'e', 'i', 'o', 'u',
            '\u025B', '\u0254', '\u0259',   // open-e, open-o, schwa
            '\u00F8', '\u0153',             // slashed-o, oe-ligature
            '\uE01E',                       // PUA y_vowel
            '\uE056', '\uE057', '\uE058',   // PUA nasals
        ]);
        assert.ok(vowelPhonemes.has(stressedToken),
            `stressed token "${stressedToken}" at index ${stressIdx} should be a vowel phoneme`);

        // No vowel phoneme AFTER the stressed index (it should be the last vowel)
        for (let i = stressIdx + 1; i < tokens.length; i++) {
            assert.ok(!vowelPhonemes.has(tokens[i]),
                `token "${tokens[i]}" at index ${i} is a vowel after the stress position -- stress should be on last vowel`);
        }

        // Trailing consonant phonemes should have a2=0
        for (let i = stressIdx + 1; i < tokens.length; i++) {
            assert.equal(prosody[i].a2, 0,
                `trailing token "${tokens[i]}" at index ${i} should have a2=0`);
        }
    });

    it('multi-word a3 independence: "bon jour" has independent a3 per word', () => {
        const { tokens, prosody } = fr.phonemizeWithProsody('bon jour');
        // Find the space separator
        const spaceIdx = tokens.indexOf(' ');
        assert.ok(spaceIdx > 0, '"bon jour" should have a space separator');

        // Space token should have a3=0
        assert.equal(prosody[spaceIdx].a3, 0,
            'space token should have a3=0');
        assert.equal(prosody[spaceIdx].a2, 0,
            'space token should have a2=0');
        assert.equal(prosody[spaceIdx].a1, 0,
            'space token should have a1=0');

        // Word 1 ("bon"): all tokens before the space share the same a3
        const word1A3 = prosody[0].a3;
        assert.ok(word1A3 > 0, 'word 1 a3 should be > 0');
        for (let i = 0; i < spaceIdx; i++) {
            assert.equal(prosody[i].a3, word1A3,
                `word1 token "${tokens[i]}" at index ${i} should have a3=${word1A3}`);
        }

        // Word 2 ("jour"): all tokens after the space share the same a3
        const word2A3 = prosody[spaceIdx + 1].a3;
        assert.ok(word2A3 > 0, 'word 2 a3 should be > 0');
        for (let i = spaceIdx + 1; i < tokens.length; i++) {
            assert.equal(prosody[i].a3, word2A3,
                `word2 token "${tokens[i]}" at index ${i} should have a3=${word2A3}`);
        }
    });

    it('a3 count accuracy: "bon" a3 matches number of phonemes in the word', () => {
        const { tokens, prosody } = fr.phonemizeWithProsody('bon');
        // "bon" is a single word -- all tokens are word phonemes, no spaces
        const phonemeCount = tokens.length;
        for (let i = 0; i < tokens.length; i++) {
            assert.equal(prosody[i].a3, phonemeCount,
                `"bon" token "${tokens[i]}" at index ${i} should have a3=${phonemeCount}`);
        }
    });

    it('nasal vowel stress: "bon" nasal vowel is the stressed position (a2=2)', () => {
        const { tokens, prosody } = fr.phonemizeWithProsody('bon');
        // "bon" -> b + PUA_NASAL_ON; the nasal vowel should be stressed
        const nasalIdx = tokens.indexOf('\uE058'); // PUA_NASAL_ON
        assert.ok(nasalIdx >= 0, '"bon" should contain nasal-on PUA token');
        assert.equal(prosody[nasalIdx].a2, 2,
            'nasal vowel in "bon" should have a2=2 (stressed)');

        // The consonant 'b' should NOT be stressed
        const bIdx = tokens.indexOf('b');
        assert.ok(bIdx >= 0, '"bon" should contain "b"');
        assert.equal(prosody[bIdx].a2, 0,
            'consonant "b" in "bon" should have a2=0');
    });

    it('punctuation prosody: "bonjour!" punctuation has a1=0, a2=0, a3=0', () => {
        const { tokens, prosody } = fr.phonemizeWithProsody('bonjour!');
        // Find the exclamation mark
        const exclIdx = tokens.indexOf('!');
        assert.ok(exclIdx >= 0, '"bonjour!" should contain "!"');
        assert.equal(prosody[exclIdx].a1, 0, 'punctuation a1 should be 0');
        assert.equal(prosody[exclIdx].a2, 0, 'punctuation a2 should be 0');
        assert.equal(prosody[exclIdx].a3, 0, 'punctuation a3 should be 0');

        // Non-punctuation tokens should have a3 > 0
        for (let i = 0; i < exclIdx; i++) {
            assert.ok(prosody[i].a3 > 0,
                `word token "${tokens[i]}" at index ${i} should have a3 > 0`);
        }
    });

    it('empty string: phonemizeWithProsody("") returns empty arrays', () => {
        const { tokens, prosody } = fr.phonemizeWithProsody('');
        assert.deepEqual(tokens, [], 'tokens should be empty for empty input');
        assert.deepEqual(prosody, [], 'prosody should be empty for empty input');
    });
});
