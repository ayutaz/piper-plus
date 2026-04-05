/**
 * Cross-platform G2P golden test (JS)
 *
 * Loads `tests/fixtures/g2p/phoneme_test_cases.json` and runs assertions
 * against each language G2P. Shares the same fixture with Python/Rust to
 * guarantee output consistency across all three platforms.
 *
 * ## JS platform notes
 *
 * The JS G2P is a lightweight browser-optimised implementation, so some
 * differences from the Python/Rust output are expected:
 * - ZH: character-based tokeniser (no rule-based IPA conversion yet)
 * - EN: dictionary + fallback rules (IPA output, expected_contains checked)
 * - ES/FR/KO/SV: rule-based (expected_contains checked)
 *
 * This test performs `expected_token_count_min` and `expected_contains`
 * checks. Exact token match (`expected_tokens`) is performed when the
 * fixture provides it (e.g. ES). JA is skipped because it requires
 * the OpenJTalk WASM runtime.
 *
 * Additionally, `encode_test_cases` from the fixture are validated against
 * the Encoder class to verify BOS/PAD/EOS insertion and PUA mapping.
 *
 * Run: node --test test/test-g2p-golden.js
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join, dirname } from 'node:path';

import { EnglishG2P } from '../src/en/index.js';
import { SpanishG2P } from '../src/es/index.js';
import { FrenchG2P } from '../src/fr/index.js';
import { PortugueseG2P } from '../src/pt/index.js';
import { SwedishG2P } from '../src/sv/index.js';
import { KoreanG2P } from '../src/ko/index.js';
import { ChineseG2P } from '../src/zh/index.js';
import { Encoder } from '../src/encode.js';
import { PUA_MAP, mapToken } from '../src/pua-map.js';

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

function casesFor(lang) {
    return FIXTURE.test_cases.filter(c => c.language === lang);
}

// Languages where the JS G2P produces IPA tokens (rule-based or dictionary).
// For character-based languages (ZH), expected_contains from the
// fixture refers to IPA tokens that the JS implementation does not produce,
// so those checks are skipped.
const IPA_OUTPUT_LANGUAGES = new Set(['en', 'es', 'fr', 'ko', 'pt', 'sv']);

// ---------------------------------------------------------------------------
// Helper: structural assertion (token count only -- JS may differ from Py/Rust)
// ---------------------------------------------------------------------------

function assertTokenCountMin(tokens, testCase) {
    if (testCase.expected_token_count_min === undefined) return;
    const desc = testCase.description ?? testCase.input;
    assert.ok(
        tokens.length >= testCase.expected_token_count_min,
        `${testCase.language} token count ${tokens.length} < ${testCase.expected_token_count_min} for ${JSON.stringify(desc)}: [${tokens.join(', ')}]`
    );
}

// ---------------------------------------------------------------------------
// Helper: expected_contains assertion
//
// Checks that every token in expected_contains appears in the output.
// Also checks PUA-mapped forms: if expected_contains has "ch", we accept
// either "ch" or its PUA character \uE00E in the output.
// ---------------------------------------------------------------------------

function assertExpectedContains(tokens, testCase) {
    if (!testCase.expected_contains) return;
    if (!IPA_OUTPUT_LANGUAGES.has(testCase.language)) return;

    const tokenSet = new Set(tokens);
    for (const expected of testCase.expected_contains) {
        const puaMapped = mapToken(expected);
        const found = tokenSet.has(expected) || tokenSet.has(puaMapped);
        assert.ok(
            found,
            `${testCase.language} output missing ${JSON.stringify(expected)} ` +
            `(or PUA ${JSON.stringify(puaMapped)}) for ${JSON.stringify(testCase.input)}: ` +
            `[${tokens.join(', ')}]`
        );
    }
}

// ---------------------------------------------------------------------------
// English (dictionary + fallback rules)
// ---------------------------------------------------------------------------

describe('G2P golden: English', () => {
    const g2p = new EnglishG2P();
    for (const c of casesFor('en')) {
        it(c.description ?? c.input, () => {
            const { tokens } = g2p.phonemize(c.input);
            assertTokenCountMin(tokens, c);
            assertExpectedContains(tokens, c);
        });
    }
});

// ---------------------------------------------------------------------------
// Spanish (rule-based IPA)
// ---------------------------------------------------------------------------

describe('G2P golden: Spanish', () => {
    const g2p = new SpanishG2P();
    for (const c of casesFor('es')) {
        it(c.description ?? c.input, () => {
            const { tokens } = g2p.phonemize(c.input);
            // Exact token match when fixture specifies expected_tokens
            if (c.expected_tokens) {
                assert.deepEqual(tokens, c.expected_tokens,
                    `ES exact token mismatch for ${JSON.stringify(c.input)}`);
            }
            assertTokenCountMin(tokens, c);
            assertExpectedContains(tokens, c);
        });
    }
});

// ---------------------------------------------------------------------------
// French (rule-based IPA)
// ---------------------------------------------------------------------------

describe('G2P golden: French', () => {
    const g2p = new FrenchG2P();
    for (const c of casesFor('fr')) {
        it(c.description ?? c.input, () => {
            const { tokens } = g2p.phonemize(c.input);
            assertTokenCountMin(tokens, c);
            assertExpectedContains(tokens, c);
        });
    }
});

// ---------------------------------------------------------------------------
// Portuguese (rule-based BR IPA)
// ---------------------------------------------------------------------------

describe('G2P golden: Portuguese', () => {
    const g2p = new PortugueseG2P();
    for (const c of casesFor('pt')) {
        it(c.description ?? c.input, () => {
            const { tokens } = g2p.phonemize(c.input);
            assertTokenCountMin(tokens, c);
            assertExpectedContains(tokens, c);
        });
    }
});

// ---------------------------------------------------------------------------
// Swedish (rule-based)
// ---------------------------------------------------------------------------

describe('G2P golden: Swedish', () => {
    const g2p = new SwedishG2P();
    for (const c of casesFor('sv')) {
        it(c.description ?? c.input, () => {
            const { tokens } = g2p.phonemize(c.input);
            assertTokenCountMin(tokens, c);
            assertExpectedContains(tokens, c);
        });
    }
});

// ---------------------------------------------------------------------------
// Korean (rule-based IPA)
// ---------------------------------------------------------------------------

describe('G2P golden: Korean', () => {
    const g2p = new KoreanG2P();
    for (const c of casesFor('ko')) {
        it(c.description ?? c.input, () => {
            const { tokens } = g2p.phonemize(c.input);
            assertTokenCountMin(tokens, c);
            assertExpectedContains(tokens, c);
        });
    }
});

// ---------------------------------------------------------------------------
// Chinese (character-based)
// ---------------------------------------------------------------------------

describe('G2P golden: Chinese', () => {
    const g2p = new ChineseG2P();
    for (const c of casesFor('zh')) {
        it(c.description ?? c.input, () => {
            const { tokens } = g2p.phonemize(c.input);
            assert.ok(
                tokens.length > 0,
                `ZH should produce tokens for ${JSON.stringify(c.input)}`
            );
        });
    }
});

// ---------------------------------------------------------------------------
// Japanese (WASM required -- skipped in Node.js unit tests)
// ---------------------------------------------------------------------------

describe('G2P golden: Japanese', () => {
    it('SKIP: JA requires OpenJTalk WASM (not available in Node.js unit tests)', {
        skip: 'JA G2P requires OpenJTalk WASM -- test via browser E2E or integration test',
    }, () => {});
});

// ---------------------------------------------------------------------------
// Modification 2: encode_test_cases from fixture
//
// Validates that the Encoder correctly converts token sequences into
// phoneme_id arrays with BOS/PAD/EOS insertion and PUA mapping.
// ---------------------------------------------------------------------------

/**
 * Build a minimal phoneme_id_map that can encode all tokens in the fixture's
 * encode_test_cases. Each single-char IPA token gets a unique ID. PUA chars
 * from the PUA_MAP are also registered.
 */
function buildTestPhonemeIdMap(encodeCases) {
    const map = {
        '^': [1],   // BOS
        '$': [2],   // EOS
        '_': [0],   // PAD
    };
    let nextId = 10;

    // Collect all tokens from all encode test cases
    for (const tc of encodeCases) {
        for (const token of tc.tokens) {
            // Map multi-char tokens through PUA
            const mapped = mapToken(token);
            if (!map[mapped]) {
                map[mapped] = [nextId++];
            }
        }
    }
    return map;
}

describe('G2P golden: encode_test_cases', () => {
    const encodeCases = FIXTURE.encode_test_cases;
    if (!encodeCases || encodeCases.length === 0) {
        it('SKIP: no encode_test_cases in fixture', { skip: true }, () => {});
        return;
    }

    const phonemeIdMap = buildTestPhonemeIdMap(encodeCases);
    const encoder = new Encoder(phonemeIdMap);

    // JS Encoder format: BOS + (token_ids + PAD)* + EOS
    // Python/Rust format: BOS + PAD + (token_ids + PAD)* + EOS  (extra PAD after BOS)
    // The fixture expected_min_length is based on the Python/Rust format, which
    // has 1 extra PAD after BOS. We subtract 1 for the JS platform difference.
    const JS_PAD_OFFSET = 1;

    for (const tc of encodeCases) {
        it(tc.description, () => {
            const { phonemeIds } = encoder.encode(tc.tokens);

            // BOS check
            if (tc.expected_has_bos) {
                assert.equal(
                    phonemeIds[0], phonemeIdMap['^'][0],
                    `Expected BOS (^) as first ID`
                );
            }

            // EOS check
            if (tc.expected_has_eos) {
                assert.equal(
                    phonemeIds[phonemeIds.length - 1], phonemeIdMap['$'][0],
                    `Expected EOS ($) as last ID`
                );
            }

            // First token check
            if (tc.expected_first_token) {
                const firstTokenIds = phonemeIdMap[tc.expected_first_token];
                assert.ok(
                    firstTokenIds,
                    `Expected first token "${tc.expected_first_token}" must be in phonemeIdMap`
                );
                assert.equal(
                    phonemeIds[0], firstTokenIds[0],
                    `First phoneme ID should correspond to "${tc.expected_first_token}"`
                );
            }

            // Minimum length check (adjusted for JS encoder padding difference)
            if (tc.expected_min_length !== undefined) {
                const adjustedMin = tc.expected_min_length - JS_PAD_OFFSET;
                assert.ok(
                    phonemeIds.length >= adjustedMin,
                    `phonemeIds length ${phonemeIds.length} < adjusted min ${adjustedMin} ` +
                    `(fixture min ${tc.expected_min_length} - ${JS_PAD_OFFSET} JS offset) ` +
                    `for tokens [${tc.tokens.join(', ')}]`
                );
            }

            // Structural invariant: all IDs must be non-negative integers
            for (const id of phonemeIds) {
                assert.equal(typeof id, 'number', 'phoneme ID must be a number');
                assert.ok(id >= 0, `phoneme ID must be non-negative, got ${id}`);
            }
        });
    }
});
