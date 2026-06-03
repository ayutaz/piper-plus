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
// Swedish word-level LID post-pass (Issue #539)
//
// Swedish is detected by a CONSERVATIVE word-level post-pass, NOT by the
// per-character path. At char level, å/ä/ö fall through to the default Latin
// language (like every other runtime); after segmentation, a post-pass
// re-classifies a whole default-Latin segment to "sv" iff it contains a strong
// indicator: an å/Å char, or an exact function-word match (och/jag/för/är/...).
// Weak chars ä/ö are deliberately NOT strong (shared with German/Finnish).
// ---------------------------------------------------------------------------

describe('UnicodeLanguageDetector Swedish detection (word-level)', () => {
    const detector = new UnicodeLanguageDetector();

    // --- char level must NOT return sv (no fragmentation source) -----------

    it('should NOT classify å/ä/ö as sv at the character level', () => {
        // The strong char å and the weak chars ä/ö all fall through to the
        // default Latin language at char level; Swedish is decided per-word.
        assert.equal(detector.detectChar('å'), 'en');
        assert.equal(detector.detectChar('ä'), 'en');
        assert.equal(detector.detectChar('ö'), 'en');
    });

    it('should NOT classify uppercase Å/Ä/Ö as sv at the character level', () => {
        assert.equal(detector.detectChar('Å'), 'en');
        assert.equal(detector.detectChar('Ä'), 'en');
        assert.equal(detector.detectChar('Ö'), 'en');
    });

    it('should fall back to default Latin for å when sv is not in languages', () => {
        const detectorNoSv = new UnicodeLanguageDetector(['ja', 'en', 'zh']);
        assert.equal(detectorNoSv.detectChar('å'), 'en');
    });

    // --- strong char words (å) -> single sv segment, no fragmentation ------

    it('should keep "så" as a single sv segment (å strong, not fragmented)', () => {
        const segments = detector.segmentText('så');
        assert.equal(segments.length, 1);
        assert.equal(segments[0].language, 'sv');
        assert.equal(segments[0].text, 'så');
    });

    it('should keep "från" as a single sv segment (å strong, not fragmented)', () => {
        const segments = detector.segmentText('från');
        assert.equal(segments.length, 1);
        assert.equal(segments[0].language, 'sv');
        assert.equal(segments[0].text, 'från');
    });

    // --- function words with NO special char (impossible under char-level) --

    it('should detect "och" as sv (function word, no special char)', () => {
        const segments = detector.segmentText('och');
        assert.equal(segments.length, 1);
        assert.equal(segments[0].language, 'sv');
        assert.equal(segments[0].text, 'och');
    });

    it('should detect "jag" as sv (function word, no special char)', () => {
        const segments = detector.segmentText('jag');
        assert.equal(segments.length, 1);
        assert.equal(segments[0].language, 'sv');
    });

    it('should detect "inte" as sv (function word, no special char)', () => {
        const segments = detector.segmentText('inte');
        assert.equal(segments.length, 1);
        assert.equal(segments[0].language, 'sv');
    });

    // --- function words that DO carry a weak/strong char --------------------

    it('should detect "för" as a single sv segment (function word)', () => {
        const segments = detector.segmentText('för');
        assert.equal(segments.length, 1);
        assert.equal(segments[0].language, 'sv');
        assert.equal(segments[0].text, 'för');
    });

    it('should detect "när" as a single sv segment (function word)', () => {
        const segments = detector.segmentText('när');
        assert.equal(segments.length, 1);
        assert.equal(segments[0].language, 'sv');
        assert.equal(segments[0].text, 'när');
    });

    it('should detect "är" as a single sv segment (function word)', () => {
        const segments = detector.segmentText('är');
        assert.equal(segments.length, 1);
        assert.equal(segments[0].language, 'sv');
        assert.equal(segments[0].text, 'är');
    });

    // --- weak-char invariant: ä/ö alone must NOT trigger sv ----------------

    it('should NOT classify "Mädchen" (German, ä) as sv', () => {
        const segments = detector.segmentText('Mädchen');
        assert.equal(segments.length, 1);
        assert.notEqual(segments[0].language, 'sv');
    });

    it('should NOT classify "schön" (German, ö) as sv', () => {
        const segments = detector.segmentText('schön');
        assert.equal(segments.length, 1);
        assert.notEqual(segments[0].language, 'sv');
    });

    it('should NOT classify "wörter" (ö only, not a function word) as sv', () => {
        const segments = detector.segmentText('wörter');
        assert.equal(segments.length, 1);
        assert.notEqual(segments[0].language, 'sv');
    });

    it('should NOT classify "xöx" (ö only, weak-char invariant) as sv', () => {
        const segments = detector.segmentText('xöx');
        assert.equal(segments.length, 1);
        assert.notEqual(segments[0].language, 'sv');
    });

    // --- conservative gate: needs sv + >=2 Latin langs ---------------------

    it('should NOT classify "från" as sv when sv is not among the languages', () => {
        const detectorNoSv = new UnicodeLanguageDetector(['en', 'es']);
        const segments = detectorNoSv.segmentText('från');
        assert.equal(segments.length, 1);
        assert.notEqual(segments[0].language, 'sv');
    });

    // --- sentence-level: one strong word reclassifies the whole segment ----

    it('should classify "jag heter Anna" as sv (function word triggers segment)', () => {
        const segments = detector.segmentText('jag heter Anna');
        assert.equal(segments.length, 1);
        assert.equal(segments[0].language, 'sv');
        assert.equal(segments[0].text, 'jag heter Anna');
    });

    // --- detectLanguage stays consistent with the post-pass ----------------

    it('should detect "och jag" as sv via detectLanguage', () => {
        assert.equal(detector.detectLanguage('och jag'), 'sv');
    });

    it('should detect "Mädchen" as en via detectLanguage (ä weak)', () => {
        assert.equal(detector.detectLanguage('Mädchen'), 'en');
    });

    // --- mixed Swedish + Japanese: no fragmentation of the Swedish word ----

    it('should segment "från こんにちは" as [sv, ja] without fragmenting "från"', () => {
        // 'från' is a default-Latin segment reclassified to sv by the post-pass;
        // 'こんにちは' is ja. The Swedish word must stay whole (no f|å|n split).
        const segments = detector.segmentText('från こんにちは');
        assert.equal(segments.length, 2);
        assert.equal(segments[0].language, 'sv');
        assert.equal(segments[0].text.trim(), 'från');
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
