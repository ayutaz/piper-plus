/**
 * Encoder tests
 *
 * Validates phoneme token -> ID conversion with BOS/PAD/EOS insertion
 * and prosody feature alignment.
 *
 * Run: node --test src/wasm/g2p/test/test-encode.js
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { Encoder } from '../src/encode.js';

// ---------------------------------------------------------------------------
// Minimal phoneme_id_map for testing
// ---------------------------------------------------------------------------

const TEST_MAP = {
    '^': [1],         // BOS
    '$': [2],         // EOS
    '_': [0],         // PAD
    'k': [10],
    'o': [11],
    'n': [12],
    'i': [13],
    'a': [14],
    ' ': [15],
    '#': [16],
    // Multi-ID token (some tokens map to multiple IDs)
    '\uE00E': [30, 31],  // PUA for 'ch'
};

// ---------------------------------------------------------------------------
// Korean phoneme_id_map for testing
// Includes tense consonants (PUA), unreleased finals (PUA), and basic IPA
// ---------------------------------------------------------------------------

const KO_MAP = {
    '^': [1],         // BOS
    '$': [2],         // EOS
    '_': [0],         // PAD
    'k': [10],
    'a': [11],
    'm': [12],
    's': [13],
    'h': [14],
    'i': [15],
    ' ': [16],
    '\u014B': [17],        // ŋ  velar nasal
    '\u027E': [18],        // ɾ  alveolar flap
    '\uE04B': [40, 41],   // PUA p͈  tense bilabial stop
    '\uE04D': [42, 43],   // PUA k͈  tense velar stop
    '\uE04E': [44, 45],   // PUA s͈  tense sibilant fricative
    '\uE050': [46, 47],   // PUA k̚  unreleased velar stop
    '\uE051': [48, 49],   // PUA t̚  unreleased alveolar stop
};

// ---------------------------------------------------------------------------
// Swedish phoneme_id_map for testing
// Includes long vowel PUA tokens and basic IPA consonants
// ---------------------------------------------------------------------------

const SV_MAP = {
    '^': [1],         // BOS
    '$': [2],         // EOS
    '_': [0],         // PAD
    'h': [10],
    'j': [11],
    'k': [12],
    'l': [13],
    'n': [14],
    't': [15],
    ' ': [16],
    '\u02C8': [17],        // ˈ  primary stress
    '\uE059': [50, 51],   // PUA iː  long close front unrounded vowel
    '\uE05B': [52, 53],   // PUA eː  long close-mid front unrounded vowel
    '\uE05E': [54, 55],   // PUA ɑː  long open back unrounded vowel
    '\uE05F': [56, 57],   // PUA oː  long close-mid back rounded vowel
    '\uE060': [58, 59],   // PUA uː  long close back rounded vowel
    '\u026A': [60],        // ɪ  short vowel (lax close front)
};

// ---------------------------------------------------------------------------
// Constructor validation
// ---------------------------------------------------------------------------

describe('Encoder constructor', () => {
    it('should throw if phonemeIdMap is null', () => {
        assert.throws(
            () => new Encoder(null),
            /phonemeIdMap is required/
        );
    });

    it('should throw if phonemeIdMap is not an object', () => {
        assert.throws(
            () => new Encoder('bad'),
            /phonemeIdMap is required/
        );
    });

    it('should throw if BOS (^) is missing', () => {
        assert.throws(
            () => new Encoder({ '$': [2], '_': [0] }),
            /missing required '\^' \(BOS\)/
        );
    });

    it('should throw if EOS ($) is missing', () => {
        assert.throws(
            () => new Encoder({ '^': [1], '_': [0] }),
            /missing required '\$' \(EOS\)/
        );
    });

    it('should throw if PAD (_) is missing', () => {
        assert.throws(
            () => new Encoder({ '^': [1], '$': [2] }),
            /missing required '_' \(PAD\)/
        );
    });

    it('should succeed with valid map', () => {
        const enc = new Encoder(TEST_MAP);
        assert.ok(enc);
    });
});

// ---------------------------------------------------------------------------
// encode()
// ---------------------------------------------------------------------------

describe('Encoder.encode', () => {
    const encoder = new Encoder(TEST_MAP);

    it('should wrap empty tokens with BOS + PAD + EOS', () => {
        const { phonemeIds } = encoder.encode([]);
        // BOS + EOS (no PAD between because no tokens)
        assert.deepEqual(phonemeIds, [1, 2]);
    });

    it('should encode single token with BOS, token IDs, PAD, EOS', () => {
        const { phonemeIds } = encoder.encode(['k']);
        // BOS + k(10) + PAD + EOS
        assert.deepEqual(phonemeIds, [1, 10, 0, 2]);
    });

    it('should insert PAD between tokens', () => {
        const { phonemeIds } = encoder.encode(['k', 'o']);
        // BOS + k(10) + PAD + o(11) + PAD + EOS
        assert.deepEqual(phonemeIds, [1, 10, 0, 11, 0, 2]);
    });

    it('should encode multiple tokens correctly', () => {
        const { phonemeIds } = encoder.encode(['k', 'o', 'n']);
        // BOS + k(10) + PAD + o(11) + PAD + n(12) + PAD + EOS
        assert.deepEqual(phonemeIds, [1, 10, 0, 11, 0, 12, 0, 2]);
    });

    it('should handle multi-ID tokens (PUA)', () => {
        // ch -> PUA \uE00E -> [30, 31]
        const { phonemeIds } = encoder.encode(['\uE00E']);
        // BOS + 30 + 31 + PAD + EOS
        assert.deepEqual(phonemeIds, [1, 30, 31, 0, 2]);
    });

    it('should apply PUA mapping for multi-char tokens', () => {
        // 'ch' should be PUA-mapped to \uE00E then looked up
        const { phonemeIds } = encoder.encode(['ch']);
        // BOS + 30 + 31 + PAD + EOS
        assert.deepEqual(phonemeIds, [1, 30, 31, 0, 2]);
    });

    it('should skip unknown tokens but still insert PAD', () => {
        // 'xyz' is not in the map
        const { phonemeIds } = encoder.encode(['k', 'xyz', 'o']);
        // BOS + k(10) + PAD + (xyz skipped) + PAD + o(11) + PAD + EOS
        assert.deepEqual(phonemeIds, [1, 10, 0, 0, 11, 0, 2]);
    });

    it('should handle prosody markers like #', () => {
        const { phonemeIds } = encoder.encode(['k', '#', 'o']);
        // BOS + k(10) + PAD + #(16) + PAD + o(11) + PAD + EOS
        assert.deepEqual(phonemeIds, [1, 10, 0, 16, 0, 11, 0, 2]);
    });
});

// ---------------------------------------------------------------------------
// encodeWithProsody()
// ---------------------------------------------------------------------------

describe('Encoder.encodeWithProsody', () => {
    const encoder = new Encoder(TEST_MAP);

    it('should return null prosodyFlat when prosody is null', () => {
        const { phonemeIds, prosodyFlat } = encoder.encodeWithProsody(['k', 'o'], null);
        assert.deepEqual(phonemeIds, [1, 10, 0, 11, 0, 2]);
        assert.equal(prosodyFlat, null);
    });

    it('should throw when prosody length does not match tokens', () => {
        assert.throws(
            () => encoder.encodeWithProsody(['k', 'o'], [null]),
            /prosody length.*must match tokens length/
        );
    });

    it('should align prosody with phoneme IDs', () => {
        const tokens = ['k', 'o'];
        const prosody = [
            { a1: -3, a2: 1, a3: 5 },
            { a1: -2, a2: 2, a3: 5 },
        ];
        const { phonemeIds, prosodyFlat } = encoder.encodeWithProsody(tokens, prosody);

        // BOS + k(10) + PAD + o(11) + PAD + EOS
        assert.deepEqual(phonemeIds, [1, 10, 0, 11, 0, 2]);

        // prosodyFlat: BOS(0,0,0) + k(-3,1,5) + PAD(0,0,0) + o(-2,2,5) + PAD(0,0,0) + EOS(0,0,0)
        assert.deepEqual(prosodyFlat, [
            0, 0, 0,    // BOS
            -3, 1, 5,   // k
            0, 0, 0,    // PAD
            -2, 2, 5,   // o
            0, 0, 0,    // PAD
            0, 0, 0,    // EOS
        ]);
    });

    it('should use zeros for null prosody entries', () => {
        const tokens = ['k', 'o'];
        const prosody = [null, { a1: 1, a2: 2, a3: 3 }];
        const { prosodyFlat } = encoder.encodeWithProsody(tokens, prosody);

        // BOS(0,0,0) + k(0,0,0) + PAD(0,0,0) + o(1,2,3) + PAD(0,0,0) + EOS(0,0,0)
        assert.deepEqual(prosodyFlat, [
            0, 0, 0,
            0, 0, 0,
            0, 0, 0,
            1, 2, 3,
            0, 0, 0,
            0, 0, 0,
        ]);
    });

    it('should have prosodyFlat length = phonemeIds.length * 3', () => {
        const tokens = ['k', 'o', 'n'];
        const prosody = [
            { a1: 1, a2: 1, a3: 3 },
            { a1: 2, a2: 2, a3: 3 },
            { a1: 3, a2: 3, a3: 3 },
        ];
        const { phonemeIds, prosodyFlat } = encoder.encodeWithProsody(tokens, prosody);
        assert.equal(prosodyFlat.length, phonemeIds.length * 3);
    });

    it('should duplicate prosody for multi-ID tokens', () => {
        // \uE00E maps to [30, 31] -- both should get the same prosody
        const tokens = ['\uE00E'];
        const prosody = [{ a1: 5, a2: 6, a3: 7 }];
        const { phonemeIds, prosodyFlat } = encoder.encodeWithProsody(tokens, prosody);

        // BOS + 30 + 31 + PAD + EOS
        assert.deepEqual(phonemeIds, [1, 30, 31, 0, 2]);
        assert.deepEqual(prosodyFlat, [
            0, 0, 0,    // BOS
            5, 6, 7,    // id 30
            5, 6, 7,    // id 31
            0, 0, 0,    // PAD
            0, 0, 0,    // EOS
        ]);
    });

    it('should handle empty tokens with prosody', () => {
        const { phonemeIds, prosodyFlat } = encoder.encodeWithProsody([], []);
        assert.deepEqual(phonemeIds, [1, 2]);
        assert.deepEqual(prosodyFlat, [0, 0, 0, 0, 0, 0]);
    });
});

// ---------------------------------------------------------------------------
// Korean token encoding
// ---------------------------------------------------------------------------

describe('Encoder.encode -- Korean tokens', () => {
    const encoder = new Encoder(KO_MAP);

    it('should encode basic Korean IPA tokens (감)', () => {
        // 감 (gam) -> k, a, m
        const { phonemeIds } = encoder.encode(['k', 'a', 'm']);
        // BOS + k(10) + PAD + a(11) + PAD + m(12) + PAD + EOS
        assert.deepEqual(phonemeIds, [1, 10, 0, 11, 0, 12, 0, 2]);
    });

    it('should encode Korean tense consonant PUA tokens', () => {
        // ㅃ (tense bilabial) -> PUA \uE04B -> [40, 41]
        const { phonemeIds } = encoder.encode(['\uE04B', 'a']);
        // BOS + 40 + 41 + PAD + a(11) + PAD + EOS
        assert.deepEqual(phonemeIds, [1, 40, 41, 0, 11, 0, 2]);
    });

    it('should encode Korean unreleased final PUA tokens', () => {
        // k̚ (unreleased velar) -> PUA \uE050 -> [46, 47]
        const { phonemeIds } = encoder.encode(['a', '\uE050']);
        // BOS + a(11) + PAD + 46 + 47 + PAD + EOS
        assert.deepEqual(phonemeIds, [1, 11, 0, 46, 47, 0, 2]);
    });

    it('should encode a Korean syllable with tense + unreleased (ㅆ + k̚)', () => {
        // s͈ (tense sibilant) + a + k̚ (unreleased velar)
        const { phonemeIds } = encoder.encode(['\uE04E', 'a', '\uE050']);
        // BOS + 44,45 + PAD + a(11) + PAD + 46,47 + PAD + EOS
        assert.deepEqual(phonemeIds, [1, 44, 45, 0, 11, 0, 46, 47, 0, 2]);
    });

    it('should encode Korean tokens with space separator', () => {
        // "감사" -> k a m + space + s a
        const { phonemeIds } = encoder.encode(['k', 'a', 'm', ' ', 's', 'a']);
        assert.deepEqual(phonemeIds, [
            1,              // BOS
            10, 0,          // k + PAD
            11, 0,          // a + PAD
            12, 0,          // m + PAD
            16, 0,          // space + PAD
            13, 0,          // s + PAD
            11, 0,          // a + PAD
            2,              // EOS
        ]);
    });

    it('should have correct BOS/EOS/PAD for Korean tokens', () => {
        const { phonemeIds } = encoder.encode(['\uE04D']);
        // BOS + k͈(42,43) + PAD + EOS
        assert.equal(phonemeIds[0], 1, 'first ID should be BOS');
        assert.equal(phonemeIds[phonemeIds.length - 1], 2, 'last ID should be EOS');
        // PAD before EOS
        assert.equal(phonemeIds[phonemeIds.length - 2], 0, 'PAD before EOS');
    });
});

// ---------------------------------------------------------------------------
// Swedish token encoding
// ---------------------------------------------------------------------------

describe('Encoder.encode -- Swedish tokens', () => {
    const encoder = new Encoder(SV_MAP);

    it('should encode basic Swedish IPA tokens (hej)', () => {
        // hej -> h, e (short), j -- but we use tokens in SV_MAP
        const { phonemeIds } = encoder.encode(['h', '\u026A', 'j']);
        // BOS + h(10) + PAD + ɪ(60) + PAD + j(11) + PAD + EOS
        assert.deepEqual(phonemeIds, [1, 10, 0, 60, 0, 11, 0, 2]);
    });

    it('should encode Swedish long vowel PUA tokens (iː)', () => {
        // iː -> PUA \uE059 -> [50, 51]
        const { phonemeIds } = encoder.encode(['\uE059']);
        // BOS + 50 + 51 + PAD + EOS
        assert.deepEqual(phonemeIds, [1, 50, 51, 0, 2]);
    });

    it('should encode Swedish long vowel eː (PUA)', () => {
        // eː -> PUA \uE05B -> [52, 53]
        const { phonemeIds } = encoder.encode(['h', '\uE05B', 't']);
        // BOS + h(10) + PAD + 52,53 + PAD + t(15) + PAD + EOS
        assert.deepEqual(phonemeIds, [1, 10, 0, 52, 53, 0, 15, 0, 2]);
    });

    it('should encode Swedish long vowel ɑː (PUA)', () => {
        // ɑː -> PUA \uE05E -> [54, 55]
        const { phonemeIds } = encoder.encode(['\uE05E']);
        // BOS + 54 + 55 + PAD + EOS
        assert.deepEqual(phonemeIds, [1, 54, 55, 0, 2]);
    });

    it('should encode Swedish long vowel oː (PUA)', () => {
        // oː -> PUA \uE05F -> [56, 57]
        const { phonemeIds } = encoder.encode(['k', '\uE05F', 'l']);
        // BOS + k(12) + PAD + 56,57 + PAD + l(13) + PAD + EOS
        assert.deepEqual(phonemeIds, [1, 12, 0, 56, 57, 0, 13, 0, 2]);
    });

    it('should encode Swedish long vowel uː (PUA)', () => {
        // uː -> PUA \uE060 -> [58, 59]
        const { phonemeIds } = encoder.encode(['\uE060']);
        // BOS + 58 + 59 + PAD + EOS
        assert.deepEqual(phonemeIds, [1, 58, 59, 0, 2]);
    });

    it('should encode mixed short and long Swedish vowels', () => {
        // Short ɪ + space + long iː
        const { phonemeIds } = encoder.encode(['\u026A', ' ', '\uE059']);
        // BOS + ɪ(60) + PAD + space(16) + PAD + 50,51 + PAD + EOS
        assert.deepEqual(phonemeIds, [1, 60, 0, 16, 0, 50, 51, 0, 2]);
    });

    it('should have correct BOS/EOS/PAD for Swedish tokens', () => {
        const { phonemeIds } = encoder.encode(['\uE05E', 'k']);
        // BOS + ɑː(54,55) + PAD + k(12) + PAD + EOS
        assert.equal(phonemeIds[0], 1, 'first ID should be BOS');
        assert.equal(phonemeIds[phonemeIds.length - 1], 2, 'last ID should be EOS');
        assert.equal(phonemeIds[phonemeIds.length - 2], 0, 'PAD before EOS');
    });
});
