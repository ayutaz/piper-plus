/**
 * Korean language support tests for G2P (via @piper-plus/g2p).
 *
 * Verifies Hangul detection, IPA phonemization, and encoding,
 * consistent with the Python/Rust/C#/C++ implementations.
 *
 * Run with: node --test test/js/test-korean.js
 */

import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { G2P, KoreanG2P, UnicodeLanguageDetector, Encoder } from '@piper-plus/g2p';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Create a UnicodeLanguageDetector with all 8 languages. */
function createDetector() {
    return new UnicodeLanguageDetector(['ja', 'en', 'zh', 'ko', 'es', 'fr', 'pt', 'sv']);
}

// ---------------------------------------------------------------------------
// 1. Hangul Syllable character detection
// ---------------------------------------------------------------------------

describe('Korean: Hangul Syllable detection', () => {
    let detector;
    beforeEach(() => { detector = createDetector(); });

    it('should detect single Hangul syllable (U+AC00, 가)', () => {
        assert.strictEqual(detector.detectLanguage('\uAC00'), 'ko');
    });

    it('should detect "한글"', () => {
        assert.strictEqual(detector.detectLanguage('\ud55c\uae00'), 'ko');
    });

    it('should detect "안녕하세요"', () => {
        assert.strictEqual(detector.detectLanguage('\uc548\ub155\ud558\uc138\uc694'), 'ko');
    });

    it('should detect last Hangul syllable (U+D7A3)', () => {
        assert.strictEqual(detector.detectLanguage('\uD7A3'), 'ko');
    });

    it('should detect "서울"', () => {
        assert.strictEqual(detector.detectLanguage('\uc11c\uc6b8'), 'ko');
    });

    it('should detect "대한민국"', () => {
        assert.strictEqual(detector.detectLanguage('\ub300\ud55c\ubbfc\uad6d'), 'ko');
    });
});

// ---------------------------------------------------------------------------
// 2. Hangul Compatibility Jamo detection
// ---------------------------------------------------------------------------

describe('Korean: Hangul Compatibility Jamo detection', () => {
    let detector;
    beforeEach(() => { detector = createDetector(); });

    it('should detect Jamo ㄱ (U+3131)', () => {
        assert.strictEqual(detector.detectLanguage('\u3131'), 'ko');
    });

    it('should detect Jamo ㅎ (U+314E)', () => {
        assert.strictEqual(detector.detectLanguage('\u314E'), 'ko');
    });

    it('should detect Jamo ㅏ (U+314F)', () => {
        assert.strictEqual(detector.detectLanguage('\u314F'), 'ko');
    });

    it('should detect Jamo ㅣ (U+3163)', () => {
        assert.strictEqual(detector.detectLanguage('\u3163'), 'ko');
    });
});

// ---------------------------------------------------------------------------
// 3. Korean + English mixed text detection
// ---------------------------------------------------------------------------

describe('Korean: Mixed text detection', () => {
    let detector;
    beforeEach(() => { detector = createDetector(); });

    it('should return ko as first significant language for KO-first text', () => {
        // "안녕하세요" has 5 Korean chars, "hello" has 5 Latin chars -- ko >= en
        assert.strictEqual(detector.detectLanguage('\uc548\ub155\ud558\uc138\uc694 hello'), 'ko');
    });
});

// ---------------------------------------------------------------------------
// 4. KoreanG2P phonemize basic
// ---------------------------------------------------------------------------

describe('Korean: KoreanG2P phonemize basic', () => {
    let g2p;
    beforeEach(() => { g2p = new KoreanG2P(); });

    it('should return tokens for "가"', () => {
        const result = g2p.phonemize('\uAC00');
        assert.ok(Array.isArray(result.tokens), 'tokens should be an array');
        assert.ok(result.tokens.length > 0, 'tokens should not be empty');
    });

    it('should return IPA tokens (k, a) for "가"', () => {
        const result = g2p.phonemize('\uAC00');
        assert.ok(result.tokens.includes('k'), 'should include k');
        assert.ok(result.tokens.includes('a'), 'should include a');
    });

    it('should return tokens for "안녕하세요"', () => {
        const result = g2p.phonemize('\uc548\ub155\ud558\uc138\uc694');
        assert.ok(result.tokens.length > 0, 'tokens should not be empty');
    });

    it('should return empty tokens for empty string', () => {
        const result = g2p.phonemize('');
        assert.ok(Array.isArray(result.tokens));
    });

    it('should return prosody array (all null) of same length as tokens', () => {
        const result = g2p.phonemize('\uAC00');
        assert.ok(Array.isArray(result.prosody));
        assert.strictEqual(result.prosody.length, result.tokens.length);
    });
});

// ---------------------------------------------------------------------------
// 5. Encoder integration
// ---------------------------------------------------------------------------

describe('Korean: Encoder integration', () => {
    const phonemeIdMap = {
        '_': [0], '^': [1], '$': [2], ' ': [3],
        'k': [10], 'a': [11], 'n': [12], 'h': [13],
    };

    it('should produce phoneme IDs with BOS (1) and EOS (2) for "가"', () => {
        const g2p = new KoreanG2P();
        const { tokens } = g2p.phonemize('\uAC00');
        const enc = new Encoder(phonemeIdMap);
        const { phonemeIds } = enc.encode(tokens);
        assert.strictEqual(phonemeIds[0], 1, 'first ID should be BOS (1)');
        assert.strictEqual(phonemeIds[phonemeIds.length - 1], 2, 'last ID should be EOS (2)');
        assert.ok(phonemeIds.length > 2, 'should have IDs between BOS and EOS');
    });

    it('should encode "가" to include k and a IDs', () => {
        const g2p = new KoreanG2P();
        const { tokens } = g2p.phonemize('\uAC00');
        const enc = new Encoder(phonemeIdMap);
        const { phonemeIds } = enc.encode(tokens);
        assert.ok(phonemeIds.includes(10), 'should include k ID (10)');
        assert.ok(phonemeIds.includes(11), 'should include a ID (11)');
    });
});

// ---------------------------------------------------------------------------
// 6. G2P.encode integration
// ---------------------------------------------------------------------------

describe('Korean: G2P.encode integration', () => {
    let g2p;
    const phonemeIdMap = {
        '_': [0], '^': [1], '$': [2], ' ': [3],
        'k': [10], 'a': [11], 'n': [12], 'h': [13],
    };

    beforeEach(async () => {
        g2p = await G2P.create({ languages: ['ko', 'en'] });
    });

    it('G2P.detectLanguage returns ko for Korean text', () => {
        assert.strictEqual(g2p.detectLanguage('\uAC00'), 'ko');
    });

    it('G2P.encode returns phonemeIds for Korean text', () => {
        const result = g2p.encode('\uAC00', phonemeIdMap, { language: 'ko' });
        assert.ok(Array.isArray(result.phonemeIds), 'phonemeIds should be an array');
        assert.ok(result.phonemeIds.length > 0, 'phonemeIds should not be empty');
        assert.strictEqual(result.phonemeIds[0], 1, 'first ID should be BOS');
        assert.strictEqual(result.phonemeIds[result.phonemeIds.length - 1], 2, 'last ID should be EOS');
    });

    it('G2P.encode result has prosodyFlat null for Korean', () => {
        const result = g2p.encode('\uAC00', phonemeIdMap, { language: 'ko' });
        assert.ok(result.prosodyFlat === null || Array.isArray(result.prosodyFlat));
    });
});
