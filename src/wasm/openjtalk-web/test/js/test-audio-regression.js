/**
 * M4-2: 音声品質の回帰テスト (JS)
 *
 * `data/test-fixtures/audio-regression-baseline.json` を読み込み、
 * 現在の @piper-plus/g2p で同一テキストの phoneme_ids を生成し、
 * ベースラインとビット完全一致を検証する。
 *
 * phoneme_ids が一致すれば deterministic ONNX 推論で同一音声が得られる。
 *
 * Run with: node --test test/js/test-audio-regression.js
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
    Encoder,
} from '@piper-plus/g2p';

// ---------------------------------------------------------------------------
// Paths
// ---------------------------------------------------------------------------

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const REPO_ROOT = join(__dirname, '..', '..', '..', '..', '..');
const BASELINE_PATH = join(REPO_ROOT, 'tests', 'fixtures', 'g2p', 'audio-regression-baseline.json');
const CONFIG_PATH = join(REPO_ROOT, 'test', 'models', 'multilingual-test-medium.onnx.json');

// ---------------------------------------------------------------------------
// Fixture loading
// ---------------------------------------------------------------------------

const BASELINE = JSON.parse(readFileSync(BASELINE_PATH, 'utf-8'));
const CONFIG = JSON.parse(readFileSync(CONFIG_PATH, 'utf-8'));
const PHONEME_ID_MAP = CONFIG.phoneme_id_map;

// ---------------------------------------------------------------------------
// G2P factory by language
// ---------------------------------------------------------------------------

const G2P_FACTORIES = {
    es: () => new SpanishG2P(),
    fr: () => new FrenchG2P(),
    pt: () => new PortugueseG2P(),
    sv: () => new SwedishG2P(),
    ko: () => new KoreanG2P(),
};

function encodeText(language, text) {
    const factory = G2P_FACTORIES[language];
    if (!factory) {
        throw new Error(`No G2P factory for language: ${language}`);
    }
    const g2p = factory();
    const { tokens, prosody } = g2p.phonemize(text);
    const enc = new Encoder(PHONEME_ID_MAP, {
        unknownTokenMode: 'skip',
        sentenceBoundary: '$',
        padding: '_',
    });
    const result = enc.encodeWithProsody(tokens, prosody);
    return { phonemeIds: Array.from(result.phonemeIds), tokenCount: tokens.length };
}

// ---------------------------------------------------------------------------
// Regression tests
// ---------------------------------------------------------------------------

describe('Audio regression: phoneme_ids bit-exact match', () => {
    for (const baseline of BASELINE.tests) {
        it(`${baseline.language}: "${baseline.text}"`, () => {
            const { phonemeIds, tokenCount } = encodeText(baseline.language, baseline.text);

            // token count check
            assert.strictEqual(
                tokenCount,
                baseline.token_count,
                `${baseline.language} token count mismatch: got ${tokenCount}, expected ${baseline.token_count}`
            );

            // bit-exact phoneme_ids comparison
            assert.deepStrictEqual(
                phonemeIds,
                baseline.phoneme_ids,
                [
                    `${baseline.language} phoneme_ids mismatch for "${baseline.text}"`,
                    `Expected: [${baseline.phoneme_ids.join(', ')}]`,
                    `Got:      [${phonemeIds.join(', ')}]`,
                    `First diff at index: ${phonemeIds.findIndex((v, i) => v !== baseline.phoneme_ids[i])}`,
                ].join('\n')
            );
        });
    }
});
