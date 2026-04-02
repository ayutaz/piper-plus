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
 * - ES: no h-silencing, no stress markers
 * - ZH: character-based tokeniser (no pypinyin-style tone markers)
 *
 * This test performs `expected_token_count_min` and `expected_contains`
 * checks only. Exact token match (`expected_tokens`) is skipped for JS.
 * JA is skipped because it requires the OpenJTalk WASM runtime.
 *
 * Run: node --test test/test-g2p-golden.js
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join, dirname } from 'node:path';

import { SpanishG2P } from '../src/es/index.js';
import { FrenchG2P } from '../src/fr/index.js';
import { PortugueseG2P } from '../src/pt/index.js';
import { SwedishG2P } from '../src/sv/index.js';
import { KoreanG2P } from '../src/ko/index.js';
import { ChineseG2P } from '../src/zh/index.js';

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

// ---------------------------------------------------------------------------
// Helper: structural assertion (token count only — JS may differ from Py/Rust)
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
// Spanish (rule-based)
// ---------------------------------------------------------------------------

describe('G2P golden: Spanish', () => {
    const g2p = new SpanishG2P();
    for (const c of casesFor('es')) {
        it(c.description ?? c.input, () => {
            const { tokens } = g2p.phonemize(c.input);
            assertTokenCountMin(tokens, c);
        });
    }
});

// ---------------------------------------------------------------------------
// French (rule-based)
// ---------------------------------------------------------------------------

describe('G2P golden: French', () => {
    const g2p = new FrenchG2P();
    for (const c of casesFor('fr')) {
        it(c.description ?? c.input, () => {
            const { tokens } = g2p.phonemize(c.input);
            assertTokenCountMin(tokens, c);
            if (c.expected_contains) {
                const tokenSet = new Set(tokens);
                for (const expected of c.expected_contains) {
                    assert.ok(
                        tokenSet.has(expected),
                        `FR output missing ${JSON.stringify(expected)} for ${JSON.stringify(c.input)}: [${tokens.join(', ')}]`
                    );
                }
            }
        });
    }
});

// ---------------------------------------------------------------------------
// Portuguese (rule-based)
// ---------------------------------------------------------------------------

describe('G2P golden: Portuguese', () => {
    const g2p = new PortugueseG2P();
    for (const c of casesFor('pt')) {
        it(c.description ?? c.input, () => {
            const { tokens } = g2p.phonemize(c.input);
            assertTokenCountMin(tokens, c);
            if (c.expected_contains) {
                const tokenSet = new Set(tokens);
                for (const expected of c.expected_contains) {
                    assert.ok(
                        tokenSet.has(expected),
                        `PT output missing ${JSON.stringify(expected)} for ${JSON.stringify(c.input)}: [${tokens.join(', ')}]`
                    );
                }
            }
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
            if (c.expected_contains) {
                const tokenSet = new Set(tokens);
                for (const expected of c.expected_contains) {
                    assert.ok(
                        tokenSet.has(expected),
                        `SV output missing ${JSON.stringify(expected)} for ${JSON.stringify(c.input)}: [${tokens.join(', ')}]`
                    );
                }
            }
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
            if (c.expected_contains) {
                const tokenSet = new Set(tokens);
                for (const expected of c.expected_contains) {
                    assert.ok(
                        tokenSet.has(expected),
                        `KO output missing ${JSON.stringify(expected)} for ${JSON.stringify(c.input)}: [${tokens.join(', ')}]`
                    );
                }
            }
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
// Japanese (WASM required — skipped in Node.js unit tests)
// ---------------------------------------------------------------------------

describe('G2P golden: Japanese', () => {
    it('SKIP: JA requires OpenJTalk WASM (not available in Node.js unit tests)', {
        skip: 'JA G2P requires OpenJTalk WASM — test via browser E2E or integration test',
    }, () => {});
});
