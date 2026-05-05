/**
 * PUA (Private Use Area) mapping tests
 *
 * Validates the forward/reverse PUA mapping table and the mapToken/unmapToken
 * helper functions used by the Encoder.
 *
 * Also validates all 99 PUA entries and spot-check codepoints against the
 * cross-platform fixture (tests/fixtures/g2p/phoneme_test_cases.json).
 *
 * Run: node --test src/wasm/g2p/test/test-pua-map.js
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join, dirname } from 'node:path';
import { PUA_MAP, mapToken, unmapToken, checkPuaCompat, PUA_COMPAT_VERSION } from '../src/pua-map.js';

// ---------------------------------------------------------------------------
// Fixture loading
// ---------------------------------------------------------------------------

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const FIXTURE_PATH = join(
    __dirname,
    '..', '..', '..', '..',
    'tests', 'fixtures', 'g2p', 'phoneme_test_cases.json'
);

const FIXTURE = JSON.parse(readFileSync(FIXTURE_PATH, 'utf-8'));

// ---------------------------------------------------------------------------
// PUA_MAP table integrity
// ---------------------------------------------------------------------------

describe('PUA_MAP table', () => {
    it('should have exactly 99 entries', () => {
        assert.equal(Object.keys(PUA_MAP).length, 99);
    });

    it('should have unique PUA codepoints (no duplicates)', () => {
        const values = Object.values(PUA_MAP);
        const uniqueValues = new Set(values);
        assert.equal(values.length, uniqueValues.size,
            'Duplicate PUA codepoints detected');
    });

    it('should map all values to PUA range U+E000..U+E064', () => {
        for (const [token, puaChar] of Object.entries(PUA_MAP)) {
            const code = puaChar.codePointAt(0);
            assert.ok(
                code >= 0xE000 && code <= 0xE064,
                `Token "${token}" maps to U+${code.toString(16).toUpperCase()}, ` +
                `outside expected range U+E000..U+E064`
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
    it('should round-trip all 99 entries correctly', () => {
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

// ---------------------------------------------------------------------------
// Fixture-based: pua_map_count validation
// ---------------------------------------------------------------------------

describe('PUA fixture: pua_map_count', () => {
    it(`should match fixture pua_map_count (${FIXTURE.pua_map_count})`, () => {
        assert.equal(
            Object.keys(PUA_MAP).length,
            FIXTURE.pua_map_count,
            `PUA_MAP entry count should match fixture pua_map_count`
        );
    });
});

// ---------------------------------------------------------------------------
// Fixture-based: pua_spot_checks -- individual codepoint verification
//
// Each entry in pua_spot_checks has { token, codepoint, description }.
// Verifies the JS PUA_MAP produces the exact same codepoint as the fixture.
// ---------------------------------------------------------------------------

describe('PUA fixture: pua_spot_checks', () => {
    const spotChecks = FIXTURE.pua_spot_checks;
    if (!spotChecks || spotChecks.length === 0) {
        it('SKIP: no pua_spot_checks in fixture', { skip: true }, () => {});
    } else {
        for (const check of spotChecks) {
            it(`${check.token} -> ${check.codepoint} (${check.description})`, () => {
                // Verify token exists in PUA_MAP
                assert.ok(
                    check.token in PUA_MAP,
                    `Token "${check.token}" is missing from PUA_MAP`
                );

                // Verify codepoint matches
                const expectedCodepoint = parseInt(check.codepoint, 16);
                const actualCodepoint = PUA_MAP[check.token].codePointAt(0);
                assert.equal(
                    actualCodepoint,
                    expectedCodepoint,
                    `Token "${check.token}" should map to U+${expectedCodepoint.toString(16).toUpperCase()}, ` +
                    `but got U+${actualCodepoint.toString(16).toUpperCase()}`
                );
            });
        }
    }
});

// ---------------------------------------------------------------------------
// Full 99-entry individual verification
//
// Checks every single entry in PUA_MAP:
// 1. mapToken(token) returns the correct PUA char
// 2. unmapToken(puaChar) returns the original token
// 3. The codepoint is within the valid PUA range
// ---------------------------------------------------------------------------

describe('PUA full 99-entry individual verification', () => {
    const entries = Object.entries(PUA_MAP);
    assert.equal(entries.length, 99, 'PUA_MAP should have exactly 99 entries');

    for (const [token, puaChar] of entries) {
        it(`mapToken("${token}") -> U+${puaChar.codePointAt(0).toString(16).toUpperCase()}`, () => {
            // Forward mapping
            const mapped = mapToken(token);
            assert.equal(mapped, puaChar,
                `mapToken("${token}") should return PUA char`);

            // Reverse mapping
            const unmapped = unmapToken(puaChar);
            assert.equal(unmapped, token,
                `unmapToken should return "${token}"`);

            // Codepoint range check
            const code = puaChar.codePointAt(0);
            assert.ok(
                code >= 0xE000 && code <= 0xE064,
                `Codepoint U+${code.toString(16).toUpperCase()} outside range U+E000..U+E064`
            );
        });
    }
});

// ---------------------------------------------------------------------------
// checkPuaCompat()
// ---------------------------------------------------------------------------

describe('checkPuaCompat', () => {
    it('should return compatible:true for matching version', () => {
        const result = checkPuaCompat(PUA_COMPAT_VERSION);
        assert.deepStrictEqual(result, { compatible: true });
    });

    it('should return compatible:false with message for mismatched version', () => {
        const result = checkPuaCompat(PUA_COMPAT_VERSION + 1);
        assert.equal(result.compatible, false);
        assert.equal(typeof result.message, 'string');
        assert.ok(result.message.length > 0, 'message should be non-empty');
    });

    it('should return compatible:true for undefined version', () => {
        const result = checkPuaCompat(undefined);
        assert.deepStrictEqual(result, { compatible: true });
    });

    it('should return compatible:true for null version', () => {
        const result = checkPuaCompat(null);
        assert.deepStrictEqual(result, { compatible: true });
    });

    it('should return compatible:false for zero version', () => {
        const result = checkPuaCompat(0);
        assert.equal(result.compatible, false);
        assert.equal(typeof result.message, 'string');
        assert.ok(result.message.length > 0, 'message should be non-empty');
    });
});
