/**
 * M4-1: クロスプラットフォーム G2P ゴールデンテスト (JS)
 *
 * `tests/fixtures/g2p/phoneme_test_cases.json` を読み込み、
 * @piper-plus/g2p の各言語 G2P に対してアサーションを実行する。
 * Python/Rust と同じフィクスチャを共有することで 3 プラットフォームの
 * 出力一致を保証する。
 *
 * ## JS プラットフォームの特性
 *
 * JS G2P はブラウザ向けに最適化された軽量実装のため、いくつかの
 * 動作差異がある:
 * - ES: h 無音化なし、ストレスマーカーなし (Python/Rust と異なる)
 * - ZH: 文字ベーストークナイザ (pypinyin ベースの Python/Rust と異なる)
 *
 * このテストは `expected_token_count_min` による最小トークン数チェックと、
 * JS 実装に適合する `expected_contains` チェックのみを実行する。
 * exact token match (`expected_tokens`) は JS ではスキップする。
 *
 * JA は WASM が必要なためスキップ。
 *
 * Run with: node --test test/js/test-g2p-golden.js
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join, dirname } from 'node:path';

import {
    SpanishG2P,
    FrenchG2P,
    PortugueseG2P,
    SwedishG2P,
    KoreanG2P,
    ChineseG2P,
} from '@piper-plus/g2p';

// ---------------------------------------------------------------------------
// Fixture loading
// ---------------------------------------------------------------------------

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const FIXTURE_PATH = join(
    __dirname,
    '..', '..', '..', '..', '..',
    'tests', 'fixtures', 'g2p', 'phoneme_test_cases.json'
);

const FIXTURE = JSON.parse(readFileSync(FIXTURE_PATH, 'utf-8'));

// Build a reverse PUA map: multi-char token name -> PUA single character.
// The JS G2P emits PUA codepoints (e.g. U+E01E for "y_vowel"), while the
// fixture's expected_contains uses human-readable token names.  This map
// lets us translate fixture expectations to the actual PUA characters so
// that Set.has() comparisons succeed.
const TOKEN_NAME_TO_PUA = {};
if (FIXTURE.pua_map) {
    for (const [name, hex] of Object.entries(FIXTURE.pua_map)) {
        TOKEN_NAME_TO_PUA[name] = String.fromCodePoint(parseInt(hex, 16));
    }
}

/**
 * Check whether the token set contains the expected token.
 * Tries both the literal token string AND its PUA-mapped equivalent
 * (if one exists), because some JS G2P implementations emit PUA
 * codepoints while others emit the raw multi-character string.
 */
function tokenSetHasExpected(tokenSet, expected) {
    if (tokenSet.has(expected)) return true;
    const pua = TOKEN_NAME_TO_PUA[expected];
    if (pua && tokenSet.has(pua)) return true;
    return false;
}

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
// Note: JS SpanishG2P does not silence 'h' or add stress markers — structural
//       checks only; exact token match is reserved for Python/Rust tests.
// ---------------------------------------------------------------------------

describe('G2P golden: Spanish', () => {
    const g2p = new SpanishG2P();
    for (const c of casesFor('es')) {
        it(c.description ?? c.input, () => {
            const { tokens } = g2p.phonemize(c.input);
            assertTokenCountMin(tokens, c);
            // Exact token match skipped: JS phonemizer uses character-level
            // mapping without IPA stress markers or silent-h rules.
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
                        tokenSetHasExpected(tokenSet, expected),
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
                        tokenSetHasExpected(tokenSet, expected),
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
                        tokenSetHasExpected(tokenSet, expected),
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
                        tokenSetHasExpected(tokenSet, expected),
                        `KO output missing ${JSON.stringify(expected)} for ${JSON.stringify(c.input)}: [${tokens.join(', ')}]`
                    );
                }
            }
        });
    }
});

// ---------------------------------------------------------------------------
// Chinese (character-based)
// Note: JS ChineseG2P uses character-level tokenization. Tone markers
//       (tone1-tone5) are not available in the JS implementation.
//       Only structural checks (token count) are performed.
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
            // expected_token_count_min and expected_contains_any_tone are
            // skipped: JS ChineseG2P uses character-level tokenization
            // which does not emit tone1-tone5 markers.
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
