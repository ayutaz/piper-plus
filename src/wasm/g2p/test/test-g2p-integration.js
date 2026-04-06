/**
 * G2P integration tests -- all-language unified instance & phonemize-encode pipeline
 *
 * Covers two critical gaps in the G2P test suite:
 *   A) G2P.create() with ALL 7 supported non-JA languages at once
 *   B) Full phonemize -> encode pipeline integration (per-language)
 *   C) Language detection accuracy across all loaded languages
 *
 * Note: Japanese (ja) is excluded from all tests because it requires the
 * OpenJTalk WASM runtime + dictionary, which is not available in Node.js.
 *
 * Run: cd src/wasm/g2p && node --test test/test-g2p-integration.js
 */

import { describe, it, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { G2P, Encoder, UnicodeLanguageDetector } from '../src/index.js';
import { mapToken } from '../src/pua-map.js';

// ---------------------------------------------------------------------------
// All 7 non-JA languages
// ---------------------------------------------------------------------------

const ALL_NON_JA = ['en', 'zh', 'ko', 'es', 'fr', 'pt', 'sv'];

// Sample texts for each language
const SAMPLE_TEXTS = {
    en: 'Hello world',
    zh: '\u4F60\u597D\u4E16\u754C',       // 你好世界
    ko: '\uC548\uB155\uD558\uC138\uC694',  // 안녕하세요
    es: '\u00BFHola c\u00F3mo est\u00E1s?', // ¿Hola cómo estás?
    fr: 'Bonjour comment allez-vous',
    pt: 'Ol\u00E1 como voc\u00EA est\u00E1', // Olá como você está
    sv: 'Hej hur m\u00E5r du',              // Hej hur mår du
};

// ---------------------------------------------------------------------------
// A) G2P.create() with all 7 non-JA languages
// ---------------------------------------------------------------------------

describe('A) G2P.create with all 7 non-JA languages', () => {
    let g2p;

    before(async () => {
        g2p = await G2P.create({ languages: ALL_NON_JA });
    });

    after(() => {
        if (g2p) g2p.dispose();
    });

    it('should initialise all 7 languages', () => {
        assert.equal(g2p._phonemizers.size, 7,
            `expected 7 phonemizers, got ${g2p._phonemizers.size}`);
        for (const lang of ALL_NON_JA) {
            assert.ok(g2p._phonemizers.has(lang),
                `phonemizer missing for "${lang}"`);
        }
    });

    it('should phonemize text for every loaded language', () => {
        for (const lang of ALL_NON_JA) {
            const result = g2p.phonemize(SAMPLE_TEXTS[lang], { language: lang });
            assert.ok(result.tokens.length > 0,
                `${lang}: expected non-empty tokens for ${JSON.stringify(SAMPLE_TEXTS[lang])}`);
            assert.equal(result.language, lang);
        }
    });

    it('should detect Chinese from CJK characters', () => {
        assert.equal(g2p.detectLanguage('\u4F60\u597D'), 'zh'); // 你好
    });

    it('should detect Korean from Hangul characters', () => {
        assert.equal(g2p.detectLanguage('\uD55C\uAD6D\uC5B4'), 'ko'); // 한국어
    });

    it('should fall back to en for plain Latin text (ja not loaded)', () => {
        // Without ja loaded, Japanese kana would not resolve to ja.
        // Plain Latin text defaults to en.
        assert.equal(g2p.detectLanguage('Hello world'), 'en');
    });

    it('should dispose cleanly', () => {
        // Covered by after(), but verify double-dispose is safe
        const g2p2 = g2p; // alias -- after() will also dispose
        g2p2.dispose();
        g2p2.dispose(); // should not throw
    });
});

// ---------------------------------------------------------------------------
// B) Full phonemize -> encode pipeline
// ---------------------------------------------------------------------------

/**
 * Build a phoneme_id_map that covers all tokens produced by a G2P for
 * a given text. Assigns sequential IDs starting at 10.
 * Always includes BOS (^), EOS ($), and PAD (_).
 */
function buildPhonemeIdMap(tokens) {
    const map = {
        '^': [1],  // BOS
        '$': [2],  // EOS
        '_': [0],  // PAD
    };
    let nextId = 10;
    for (const token of tokens) {
        const mapped = mapToken(token);
        if (!map[mapped]) {
            map[mapped] = [nextId++];
        }
    }
    return map;
}

describe('B) Full phonemize -> encode pipeline', () => {
    for (const lang of ALL_NON_JA) {
        describe(`${lang}: phonemize then encode`, () => {
            let g2p;

            before(async () => {
                g2p = await G2P.create({ languages: [lang] });
            });

            after(() => {
                if (g2p) g2p.dispose();
            });

            it('should produce phonemeIds starting with BOS and ending with EOS', () => {
                const { tokens } = g2p.phonemize(SAMPLE_TEXTS[lang], { language: lang });
                assert.ok(tokens.length > 0,
                    `${lang}: phonemize produced no tokens`);

                const phonemeIdMap = buildPhonemeIdMap(tokens);
                const encoder = new Encoder(phonemeIdMap);
                const { phonemeIds } = encoder.encode(tokens);

                // BOS + at least one token + PAD + EOS = minimum 4 elements
                assert.ok(phonemeIds.length > 2,
                    `${lang}: phonemeIds length ${phonemeIds.length} should be > 2`);
                assert.equal(phonemeIds[0], 1,
                    `${lang}: first ID should be BOS (1)`);
                assert.equal(phonemeIds[phonemeIds.length - 1], 2,
                    `${lang}: last ID should be EOS (2)`);
            });

            it('should produce only non-negative integer IDs', () => {
                const { tokens } = g2p.phonemize(SAMPLE_TEXTS[lang], { language: lang });
                const phonemeIdMap = buildPhonemeIdMap(tokens);
                const encoder = new Encoder(phonemeIdMap);
                const { phonemeIds } = encoder.encode(tokens);

                for (const id of phonemeIds) {
                    assert.equal(typeof id, 'number',
                        `${lang}: expected number, got ${typeof id}`);
                    assert.ok(id >= 0,
                        `${lang}: expected non-negative, got ${id}`);
                }
            });

            it('should work via G2P.encode() convenience method', () => {
                const { tokens } = g2p.phonemize(SAMPLE_TEXTS[lang], { language: lang });
                const phonemeIdMap = buildPhonemeIdMap(tokens);

                const { phonemeIds, prosodyFlat } = g2p.encode(
                    SAMPLE_TEXTS[lang], phonemeIdMap, { language: lang }
                );

                assert.ok(phonemeIds.length > 2,
                    `${lang}: G2P.encode phonemeIds too short`);
                assert.equal(phonemeIds[0], 1, `${lang}: BOS`);
                assert.equal(phonemeIds[phonemeIds.length - 1], 2, `${lang}: EOS`);
                // prosodyFlat is either null or a flat array of integers
                // (some non-JA languages return syllable-level prosody)
                if (prosodyFlat !== null) {
                    assert.ok(Array.isArray(prosodyFlat),
                        `${lang}: prosodyFlat should be null or array`);
                    assert.equal(prosodyFlat.length, phonemeIds.length * 3,
                        `${lang}: prosodyFlat length should be phonemeIds.length * 3`);
                }
            });
        });
    }
});

// ---------------------------------------------------------------------------
// C) Language detection accuracy with all 7 languages loaded
// ---------------------------------------------------------------------------

describe('C) Language detection with all 7 non-JA languages', () => {
    let g2p;

    before(async () => {
        g2p = await G2P.create({ languages: ALL_NON_JA });
    });

    after(() => {
        if (g2p) g2p.dispose();
    });

    it('should detect zh for Chinese characters', () => {
        assert.equal(g2p.detectLanguage('\u4F60\u597D\u4E16\u754C'), 'zh'); // 你好世界
    });

    it('should detect ko for Korean Hangul', () => {
        assert.equal(g2p.detectLanguage('\uD55C\uAD6D\uC5B4'), 'ko'); // 한국어
    });

    it('should detect sv for text with Swedish-specific characters', () => {
        // Strings dominated by å, ä, ö should be detected as Swedish
        assert.equal(g2p.detectLanguage('\u00E5\u00E4\u00F6'), 'sv'); // åäö
    });

    it('should detect sv for short Swedish words with diacritics', () => {
        assert.equal(g2p.detectLanguage('\u00F6l'), 'sv'); // öl
    });

    it('should default to en for plain Latin text', () => {
        assert.equal(g2p.detectLanguage('Hello world'), 'en');
    });

    it('should default to en for Latin text without distinguishing marks', () => {
        // "Bonjour" is French but has no unique Unicode markers
        assert.equal(g2p.detectLanguage('Bonjour'), 'en');
    });

    it('should detect zh for mixed CJK + Latin text', () => {
        // CJK characters dominate
        assert.equal(g2p.detectLanguage('\u4ECA\u5929\u5929\u6C14\u5F88\u597D hello'), 'zh');
    });

    it('should detect ko for mixed Hangul + Latin text', () => {
        assert.equal(
            g2p.detectLanguage('\uC548\uB155\uD558\uC138\uC694 hello'),
            'ko'
        ); // 안녕하세요 hello
    });
});
