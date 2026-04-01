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
