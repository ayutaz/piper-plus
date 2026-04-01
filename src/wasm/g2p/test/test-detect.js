/**
 * UnicodeLanguageDetector tests
 *
 * Validates language detection from Unicode character ranges and
 * text segmentation into per-language chunks.
 *
 * Run: node --test src/wasm/g2p/test/test-detect.js
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { UnicodeLanguageDetector } from '../src/detect.js';

// ---------------------------------------------------------------------------
// detectLanguage()
// ---------------------------------------------------------------------------

describe('UnicodeLanguageDetector.detectLanguage', () => {
    const detector = new UnicodeLanguageDetector();

    it('should detect hiragana text as Japanese', () => {
        assert.equal(detector.detectLanguage('こんにちは'), 'ja');
    });

    it('should detect katakana text as Japanese', () => {
        assert.equal(detector.detectLanguage('カタカナ'), 'ja');
    });

    it('should detect mixed kana + kanji text as Japanese', () => {
        assert.equal(detector.detectLanguage('東京は晴れです'), 'ja');
    });

    it('should detect CJK-only text (no kana) as Chinese', () => {
        assert.equal(detector.detectLanguage('你好世界'), 'zh');
    });

    it('should detect CJK + kana mix as Japanese (kana wins)', () => {
        // Text with both kanji and hiragana should be JA
        assert.equal(detector.detectLanguage('漢字とひらがな'), 'ja');
    });

    it('should detect English text as en', () => {
        assert.equal(detector.detectLanguage('Hello world'), 'en');
    });

    it('should detect Latin extended characters as en by default', () => {
        assert.equal(detector.detectLanguage('cafe'), 'en');
    });

    it('should fall back to en for empty string', () => {
        assert.equal(detector.detectLanguage(''), 'en');
    });

    it('should fall back to en for digits/punctuation only', () => {
        assert.equal(detector.detectLanguage('12345!@#'), 'en');
    });

    it('should respect defaultLatinLanguage option', () => {
        const detector2 = new UnicodeLanguageDetector(
            ['ja', 'en', 'zh', 'es', 'fr', 'pt'],
            { defaultLatinLanguage: 'es' }
        );
        assert.equal(detector2.detectLanguage('Hola mundo'), 'es');
    });

    it('should detect majority language in mixed text', () => {
        // More Japanese characters than English
        assert.equal(detector.detectLanguage('こんにちはworld'), 'ja');
    });
});

// ---------------------------------------------------------------------------
// detectChar()
// ---------------------------------------------------------------------------

describe('UnicodeLanguageDetector.detectChar', () => {
    const detector = new UnicodeLanguageDetector();

    it('should detect kana as ja', () => {
        assert.equal(detector.detectChar('あ'), 'ja');
        assert.equal(detector.detectChar('ア'), 'ja');
    });

    it('should detect CJK as zh when no kana context', () => {
        assert.equal(detector.detectChar('漢', false), 'zh');
    });

    it('should detect CJK as ja when kana context is true', () => {
        assert.equal(detector.detectChar('漢', true), 'ja');
    });

    it('should detect Latin letters as en', () => {
        assert.equal(detector.detectChar('A'), 'en');
        assert.equal(detector.detectChar('z'), 'en');
    });

    it('should return null for whitespace (neutral)', () => {
        assert.equal(detector.detectChar(' '), null);
    });

    it('should return null for digits (neutral)', () => {
        assert.equal(detector.detectChar('5'), null);
    });

    it('should return null for ASCII punctuation (neutral)', () => {
        assert.equal(detector.detectChar('.'), null);
    });

    it('should detect fullwidth Latin as default Latin language', () => {
        // Fullwidth A = U+FF21
        assert.equal(detector.detectChar('\uFF21'), 'en');
    });

    it('should detect CJK punctuation as ja', () => {
        // Ideographic comma U+3001
        assert.equal(detector.detectChar('\u3001'), 'ja');
    });
});

// ---------------------------------------------------------------------------
// hasKana()
// ---------------------------------------------------------------------------

describe('UnicodeLanguageDetector.hasKana', () => {
    const detector = new UnicodeLanguageDetector();

    it('should return true for text with hiragana', () => {
        assert.equal(detector.hasKana('あいう'), true);
    });

    it('should return true for text with katakana', () => {
        assert.equal(detector.hasKana('アイウ'), true);
    });

    it('should return false for CJK-only text', () => {
        assert.equal(detector.hasKana('你好'), false);
    });

    it('should return false for Latin text', () => {
        assert.equal(detector.hasKana('Hello'), false);
    });

    it('should return false for empty string', () => {
        assert.equal(detector.hasKana(''), false);
    });
});

// ---------------------------------------------------------------------------
// segmentText()
// ---------------------------------------------------------------------------

describe('UnicodeLanguageDetector.segmentText', () => {
    const detector = new UnicodeLanguageDetector();

    it('should return empty array for empty string', () => {
        assert.deepEqual(detector.segmentText(''), []);
    });

    it('should return empty array for whitespace-only string', () => {
        assert.deepEqual(detector.segmentText('   '), []);
    });

    it('should return single segment for pure Japanese', () => {
        const segments = detector.segmentText('こんにちは');
        assert.equal(segments.length, 1);
        assert.equal(segments[0].language, 'ja');
        assert.equal(segments[0].text, 'こんにちは');
    });

    it('should return single segment for pure English', () => {
        const segments = detector.segmentText('Hello');
        assert.equal(segments.length, 1);
        assert.equal(segments[0].language, 'en');
        assert.equal(segments[0].text, 'Hello');
    });

    it('should segment JA + EN mixed text', () => {
        const segments = detector.segmentText('こんにちはHello');
        assert.equal(segments.length, 2);
        assert.equal(segments[0].language, 'ja');
        assert.equal(segments[1].language, 'en');
    });

    it('should absorb neutral chars into preceding segment', () => {
        const segments = detector.segmentText('Hello 123');
        assert.equal(segments.length, 1);
        assert.equal(segments[0].language, 'en');
        assert.equal(segments[0].text, 'Hello 123');
    });

    it('should fall back to default language for digits-only text', () => {
        const segments = detector.segmentText('12345');
        assert.equal(segments.length, 1);
        assert.equal(segments[0].language, 'en');
    });

    it('should handle Chinese text as zh', () => {
        const segments = detector.segmentText('你好世界');
        assert.equal(segments.length, 1);
        assert.equal(segments[0].language, 'zh');
    });
});

// ---------------------------------------------------------------------------
// Korean (Hangul) detection
// ---------------------------------------------------------------------------

describe('UnicodeLanguageDetector Korean detection', () => {
    // Default languages do NOT include 'ko', so we need to add it explicitly.
    const detector = new UnicodeLanguageDetector(
        ['ja', 'en', 'zh', 'ko', 'es', 'fr', 'pt', 'sv']
    );

    it('should detect Hangul syllables as Korean', () => {
        assert.equal(detector.detectLanguage('한국어'), 'ko');
    });

    it('should detect Hangul Jamo as Korean', () => {
        // Hangul Compatibility Jamo: U+3130-318F
        assert.equal(detector.detectLanguage('ㅎㅏㄴ'), 'ko');
    });

    it('should detect mixed Korean/English text by majority', () => {
        // 3 Hangul syllables vs 2 Latin chars -- Korean wins
        assert.equal(detector.detectLanguage('한국어hi'), 'ko');
    });

    it('should detect Korean char via detectChar', () => {
        assert.equal(detector.detectChar('한'), 'ko');
    });

    it('should detect Hangul Jamo char via detectChar', () => {
        assert.equal(detector.detectChar('ㅎ'), 'ko');
    });

    it('should return null for Hangul when ko is not in languages', () => {
        const detectorNoKo = new UnicodeLanguageDetector(['ja', 'en', 'zh']);
        assert.equal(detectorNoKo.detectChar('한'), null);
    });

    it('should segment Korean + English mixed text', () => {
        const segments = detector.segmentText('한국어Hello');
        assert.equal(segments.length, 2);
        assert.equal(segments[0].language, 'ko');
        assert.equal(segments[0].text, '한국어');
        assert.equal(segments[1].language, 'en');
        assert.equal(segments[1].text, 'Hello');
    });
});

// ---------------------------------------------------------------------------
// Swedish (å/ä/ö) detection
// ---------------------------------------------------------------------------

describe('UnicodeLanguageDetector Swedish detection', () => {
    const detector = new UnicodeLanguageDetector();

    it('should detect Swedish-specific characters as sv', () => {
        assert.equal(detector.detectChar('å'), 'sv');
        assert.equal(detector.detectChar('ä'), 'sv');
        assert.equal(detector.detectChar('ö'), 'sv');
    });

    it('should detect uppercase Swedish characters as sv', () => {
        assert.equal(detector.detectChar('Å'), 'sv');
        assert.equal(detector.detectChar('Ä'), 'sv');
        assert.equal(detector.detectChar('Ö'), 'sv');
    });

    it('should detect text with å/ä/ö as Swedish by majority', () => {
        // 'åäö' -- all 3 chars are Swedish-specific, so sv wins
        assert.equal(detector.detectLanguage('åäö'), 'sv');
    });

    it('should detect plain Latin as en even when text has few Swedish chars', () => {
        // 'räksmörgås': ä, ö, å = 3 sv chars vs r, k, s, m, r, g, s = 7 en chars
        // English wins by majority -- this is the expected behaviour
        assert.equal(detector.detectLanguage('räksmörgås'), 'en');
    });

    it('should detect mixed Swedish/English text by majority', () => {
        // 4 Swedish-specific chars vs 2 plain Latin -> sv wins
        assert.equal(detector.detectLanguage('åäöö go'), 'sv');
    });

    it('should fall back to default Latin when sv is not in languages', () => {
        const detectorNoSv = new UnicodeLanguageDetector(['ja', 'en', 'zh']);
        assert.equal(detectorNoSv.detectChar('å'), 'en');
    });

    it('should segment Swedish chars + Japanese text', () => {
        // 'ö' is sv, then 'こんにちは' is ja
        const segments = detector.segmentText('öこんにちは');
        assert.equal(segments.length, 2);
        assert.equal(segments[0].language, 'sv');
        assert.equal(segments[0].text, 'ö');
        assert.equal(segments[1].language, 'ja');
        assert.equal(segments[1].text, 'こんにちは');
    });
});

// ---------------------------------------------------------------------------
// Constructor with limited languages
// ---------------------------------------------------------------------------

describe('UnicodeLanguageDetector with limited languages', () => {
    it('should return null for kana when ja is not in languages', () => {
        const detector = new UnicodeLanguageDetector(['en', 'zh']);
        assert.equal(detector.detectChar('あ'), null);
    });

    it('should return null for CJK when neither ja nor zh is available', () => {
        const detector = new UnicodeLanguageDetector(['en']);
        assert.equal(detector.detectChar('漢'), null);
    });

    it('should return zh for CJK when only zh is available', () => {
        const detector = new UnicodeLanguageDetector(['en', 'zh']);
        assert.equal(detector.detectChar('漢', false), 'zh');
    });

    it('should detect with only en', () => {
        const detector = new UnicodeLanguageDetector(['en']);
        assert.equal(detector.detectLanguage('Hello'), 'en');
    });
});
