/**
 * PUA (Private Use Area) mapping tests
 *
 * Validates the forward/reverse PUA mapping table and the mapToken/unmapToken
 * helper functions used by the Encoder.
 *
 * Run: node --test src/wasm/g2p/test/test-pua-map.js
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { PUA_MAP, mapToken, unmapToken } from '../src/pua-map.js';

// ---------------------------------------------------------------------------
// PUA_MAP table integrity
// ---------------------------------------------------------------------------

describe('PUA_MAP table', () => {
    it('should have exactly 96 entries', () => {
        assert.equal(Object.keys(PUA_MAP).length, 96);
    });

    it('should have unique PUA codepoints (no duplicates)', () => {
        const values = Object.values(PUA_MAP);
        const uniqueValues = new Set(values);
        assert.equal(values.length, uniqueValues.size,
            'Duplicate PUA codepoints detected');
    });

    it('should map all values to PUA range U+E000..U+E061', () => {
        for (const [token, puaChar] of Object.entries(PUA_MAP)) {
            const code = puaChar.codePointAt(0);
            assert.ok(
                code >= 0xE000 && code <= 0xE061,
                `Token "${token}" maps to U+${code.toString(16).toUpperCase()}, ` +
                `outside expected range U+E000..U+E061`
            );
        }
    });

    it('should contain Japanese tokens', () => {
        assert.ok('ch' in PUA_MAP, 'Missing "ch"');
        assert.ok('sh' in PUA_MAP, 'Missing "sh"');
        assert.ok('ts' in PUA_MAP, 'Missing "ts"');
        assert.ok('ky' in PUA_MAP, 'Missing "ky"');
        assert.ok('cl' in PUA_MAP, 'Missing "cl"');
        assert.ok('N_m' in PUA_MAP, 'Missing "N_m"');
        assert.ok('N_n' in PUA_MAP, 'Missing "N_n"');
        assert.ok('N_ng' in PUA_MAP, 'Missing "N_ng"');
        assert.ok('N_uvular' in PUA_MAP, 'Missing "N_uvular"');
    });

    it('should contain Chinese tone markers', () => {
        for (let i = 1; i <= 5; i++) {
            assert.ok(`tone${i}` in PUA_MAP, `Missing "tone${i}"`);
        }
    });

    it('should contain question markers', () => {
        assert.ok('?!' in PUA_MAP, 'Missing "?!"');
        assert.ok('?.' in PUA_MAP, 'Missing "?."');
        assert.ok('?~' in PUA_MAP, 'Missing "?~"');
    });
});

// ---------------------------------------------------------------------------
// mapToken()
// ---------------------------------------------------------------------------

describe('mapToken', () => {
    it('should map known multi-char token to PUA character', () => {
        assert.equal(mapToken('ch'), '\uE00E');
    });

    it('should map N_m to PUA character', () => {
        assert.equal(mapToken('N_m'), '\uE019');
    });

    it('should map N_n to PUA character', () => {
        assert.equal(mapToken('N_n'), '\uE01A');
    });

    it('should map N_ng to PUA character', () => {
        assert.equal(mapToken('N_ng'), '\uE01B');
    });

    it('should map N_uvular to PUA character', () => {
        assert.equal(mapToken('N_uvular'), '\uE01C');
    });

    it('should map long vowels', () => {
        assert.equal(mapToken('a:'), '\uE000');
        assert.equal(mapToken('i:'), '\uE001');
        assert.equal(mapToken('u:'), '\uE002');
        assert.equal(mapToken('e:'), '\uE003');
        assert.equal(mapToken('o:'), '\uE004');
    });

    it('should pass through single characters unchanged', () => {
        assert.equal(mapToken('k'), 'k');
        assert.equal(mapToken('a'), 'a');
        assert.equal(mapToken('o'), 'o');
    });

    it('should pass through unknown multi-char tokens unchanged', () => {
        assert.equal(mapToken('xyz'), 'xyz');
        assert.equal(mapToken('unknown'), 'unknown');
    });

    it('should pass through structural markers unchanged', () => {
        assert.equal(mapToken('^'), '^');
        assert.equal(mapToken('$'), '$');
        assert.equal(mapToken('_'), '_');
        assert.equal(mapToken('#'), '#');
        assert.equal(mapToken('['), '[');
        assert.equal(mapToken(']'), ']');
    });
});

// ---------------------------------------------------------------------------
// unmapToken()
// ---------------------------------------------------------------------------

describe('unmapToken', () => {
    it('should reverse PUA character to original token', () => {
        assert.equal(unmapToken('\uE00E'), 'ch');
    });

    it('should reverse N variant PUA characters', () => {
        assert.equal(unmapToken('\uE019'), 'N_m');
        assert.equal(unmapToken('\uE01A'), 'N_n');
        assert.equal(unmapToken('\uE01B'), 'N_ng');
        assert.equal(unmapToken('\uE01C'), 'N_uvular');
    });

    it('should pass through non-PUA characters unchanged', () => {
        assert.equal(unmapToken('k'), 'k');
        assert.equal(unmapToken('a'), 'a');
    });

    it('should pass through unknown PUA characters unchanged', () => {
        // U+E100 is not in our map
        assert.equal(unmapToken('\uE100'), '\uE100');
    });
});

// ---------------------------------------------------------------------------
// Round-trip (mapToken -> unmapToken)
// ---------------------------------------------------------------------------

describe('PUA round-trip', () => {
    it('should round-trip all 96 entries correctly', () => {
        for (const [token, puaChar] of Object.entries(PUA_MAP)) {
            const mapped = mapToken(token);
            assert.equal(mapped, puaChar,
                `mapToken("${token}") should return PUA char`);

            const unmapped = unmapToken(mapped);
            assert.equal(unmapped, token,
                `unmapToken(mapToken("${token}")) should return original token`);
        }
    });
});
