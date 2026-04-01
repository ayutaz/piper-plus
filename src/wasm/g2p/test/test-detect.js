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
