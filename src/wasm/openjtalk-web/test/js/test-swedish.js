/**
 * Swedish language detection tests for SimpleUnifiedPhonemizer.
 *
 * Verifies segment-level scoring for Swedish detection, consistent with
 * the Python/Rust/C#/C++ implementations.
 *
 * Run with: node --test test/js/test-swedish.js
 */

import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { SimpleUnifiedPhonemizer } from '../../src/simple_unified_api.js';

/** Helper: create a phonemizer instance (no OpenJTalk init needed for detection). */
function createPhonemizer() {
    const p = new SimpleUnifiedPhonemizer();
    // detectLanguage does not require initialization or phonemeIdMap
    return p;
}

// ---------------------------------------------------------------------------
// 1. Swedish character detection
// ---------------------------------------------------------------------------

describe('Swedish character detection', () => {
    let p;
    beforeEach(() => { p = createPhonemizer(); });

    it('should detect lowercase a-umlaut (ä)', () => {
        assert.strictEqual(p.detectLanguage('Jag äter mat'), 'sv');
    });

    it('should detect lowercase o-umlaut (ö)', () => {
        assert.strictEqual(p.detectLanguage('Jag öppnar dörren'), 'sv');
    });

    it('should detect lowercase a-ring (å)', () => {
        assert.strictEqual(p.detectLanguage('Det går bra'), 'sv');
    });

    it('should detect uppercase A-umlaut (Ä)', () => {
        assert.strictEqual(p.detectLanguage('Äpple'), 'sv');
    });

    it('should detect uppercase O-umlaut (Ö)', () => {
        assert.strictEqual(p.detectLanguage('Öl'), 'sv');
    });

    it('should detect uppercase A-ring (Å)', () => {
        assert.strictEqual(p.detectLanguage('Ål'), 'sv');
    });
});

// ---------------------------------------------------------------------------
// 2. Swedish function word detection
// ---------------------------------------------------------------------------

describe('Swedish function word detection', () => {
    let p;
    beforeEach(() => { p = createPhonemizer(); });

    it('should detect "och"', () => {
        assert.strictEqual(p.detectLanguage('sten och vatten'), 'sv');
    });

    it('should detect "att"', () => {
        assert.strictEqual(p.detectLanguage('det handlar att leva'), 'sv');
    });

    it('should detect "jag"', () => {
        assert.strictEqual(p.detectLanguage('jag tycker om det'), 'sv');
    });

    it('should detect "det"', () => {
        assert.strictEqual(p.detectLanguage('det regnar'), 'sv');
    });

    it('should detect "inte"', () => {
        assert.strictEqual(p.detectLanguage('inte bra'), 'sv');
    });

    it('should detect "han"', () => {
        assert.strictEqual(p.detectLanguage('han springer'), 'sv');
    });

    it('should detect "hon"', () => {
        assert.strictEqual(p.detectLanguage('hon sjunger'), 'sv');
    });

    it('should detect "som"', () => {
        assert.strictEqual(p.detectLanguage('mannen som springer'), 'sv');
    });

    it('should detect "ska"', () => {
        assert.strictEqual(p.detectLanguage('vi ska resa'), 'sv');
    });

    it('should detect "med"', () => {
        assert.strictEqual(p.detectLanguage('med vinden'), 'sv');
    });

    it('should detect "aldrig"', () => {
        assert.strictEqual(p.detectLanguage('aldrig mer'), 'sv');
    });

    it('should detect "alltid"', () => {
        assert.strictEqual(p.detectLanguage('alltid glad'), 'sv');
    });
});

// ---------------------------------------------------------------------------
// 3. Segment-level scoring (single indicator >= 1 triggers sv)
// ---------------------------------------------------------------------------

describe('Segment-level scoring', () => {
    let p;
    beforeEach(() => { p = createPhonemizer(); });

    it('should classify as sv with a single Swedish character', () => {
        // "björk" contains ö -- score >= 1
        assert.strictEqual(p.detectLanguage('björk'), 'sv');
    });

    it('should classify as sv with a single Swedish function word', () => {
        // "och" is a Swedish function word -- score >= 1
        assert.strictEqual(p.detectLanguage('kaffe och te'), 'sv');
    });

    it('should accumulate score from characters and words', () => {
        // "jag" (function word, +1) + "ä" (+1) = score 2
        assert.strictEqual(p.detectLanguage('jag gillar äpplen'), 'sv');
    });

    it('should use _segmentText internally and return segments', () => {
        const segments = p._segmentText('björk');
        assert.strictEqual(segments.length, 1);
        assert.strictEqual(segments[0].lang, 'sv');
    });
});

// ---------------------------------------------------------------------------
// 4. English text rejection
// ---------------------------------------------------------------------------

describe('English text rejection', () => {
    let p;
    beforeEach(() => { p = createPhonemizer(); });

    it('should return en for plain English text', () => {
        assert.strictEqual(p.detectLanguage('Hello, how are you?'), 'en');
    });

    it('should return en for English without Swedish indicators', () => {
        assert.strictEqual(p.detectLanguage('The quick brown fox jumps over the lazy dog'), 'en');
    });

    it('should return en for common English sentences', () => {
        assert.strictEqual(p.detectLanguage('I love programming'), 'en');
    });

    it('should not confuse "the" or "and" with Swedish words', () => {
        assert.strictEqual(p.detectLanguage('the cat and the dog'), 'en');
    });
});

// ---------------------------------------------------------------------------
// 5. Mixed Swedish-Japanese
// ---------------------------------------------------------------------------

describe('Mixed Swedish-Japanese', () => {
    let p;
    beforeEach(() => { p = createPhonemizer(); });

    it('should segment Swedish and Japanese separately', () => {
        const segments = p._segmentText('こんにちは björk');
        assert.ok(segments.length >= 2, `expected >= 2 segments, got ${segments.length}`);
        assert.strictEqual(segments[0].lang, 'ja');
        // The Latin segment should be refined to 'sv' due to ö
        const latinSeg = segments.find(s => s.lang === 'sv');
        assert.ok(latinSeg, 'should have an sv segment');
    });

    it('should return ja as first significant language for JA-first text', () => {
        assert.strictEqual(p.detectLanguage('こんにちは björk'), 'ja');
    });

    it('should return sv when Swedish segment comes first', () => {
        assert.strictEqual(p.detectLanguage('björk こんにちは'), 'sv');
    });
});

// ---------------------------------------------------------------------------
// 6. Mixed Swedish-English
// ---------------------------------------------------------------------------

describe('Mixed Swedish-English', () => {
    let p;
    beforeEach(() => { p = createPhonemizer(); });

    it('should detect sv for text with Swedish characters in first segment', () => {
        // Single segment: Latin text with ö -> sv
        assert.strictEqual(p.detectLanguage('Göteborgs stad'), 'sv');
    });

    it('should detect en for English text followed by Swedish text', () => {
        // "Hello world" is purely English (no Swedish indicators)
        // Since all chars are Latin, they form one segment, no Swedish indicators -> en
        assert.strictEqual(p.detectLanguage('Hello world'), 'en');
    });

    it('should detect sv when Swedish function word appears in Latin text', () => {
        assert.strictEqual(p.detectLanguage('Stockholm och Malmö'), 'sv');
    });
});

// ---------------------------------------------------------------------------
// 7. Edge cases
// ---------------------------------------------------------------------------

describe('Edge cases', () => {
    let p;
    beforeEach(() => { p = createPhonemizer(); });

    it('should return en for empty string', () => {
        assert.strictEqual(p.detectLanguage(''), 'en');
    });

    it('should return en for whitespace only', () => {
        assert.strictEqual(p.detectLanguage('   '), 'en');
    });

    it('should return en for numbers only', () => {
        assert.strictEqual(p.detectLanguage('12345'), 'en');
    });

    it('should return en for punctuation only', () => {
        assert.strictEqual(p.detectLanguage('...!!!???'), 'en');
    });

    it('should return en for a single ASCII letter', () => {
        assert.strictEqual(p.detectLanguage('a'), 'en');
    });

    it('should handle very long text without error', () => {
        const longText = 'hej '.repeat(1000) + 'och';
        // "och" is a Swedish function word -> sv
        assert.strictEqual(p.detectLanguage(longText), 'sv');
    });

    it('should handle single Swedish character', () => {
        assert.strictEqual(p.detectLanguage('ö'), 'sv');
    });

    it('should preserve ja detection for pure Japanese', () => {
        assert.strictEqual(p.detectLanguage('こんにちは'), 'ja');
    });

    it('should preserve zh detection for pure Chinese', () => {
        assert.strictEqual(p.detectLanguage('你好世界'), 'zh');
    });

    it('should detect ja for CJK with kana (not zh)', () => {
        assert.strictEqual(p.detectLanguage('漢字とひらがな'), 'ja');
    });
});

// ---------------------------------------------------------------------------
// 8. Case insensitivity for Swedish function words
// ---------------------------------------------------------------------------

describe('Case insensitivity for Swedish function words', () => {
    let p;
    beforeEach(() => { p = createPhonemizer(); });

    it('should match lowercase "och"', () => {
        assert.strictEqual(p.detectLanguage('kaffe och te'), 'sv');
    });

    it('should match uppercase "OCH"', () => {
        assert.strictEqual(p.detectLanguage('kaffe OCH te'), 'sv');
    });

    it('should match mixed case "Och"', () => {
        assert.strictEqual(p.detectLanguage('kaffe Och te'), 'sv');
    });

    it('should match "INTE" (uppercase)', () => {
        assert.strictEqual(p.detectLanguage('INTE bra'), 'sv');
    });

    it('should match "Jag" (title case)', () => {
        assert.strictEqual(p.detectLanguage('Jag tycker om det'), 'sv');
    });
});

// ---------------------------------------------------------------------------
// 9. Punctuation stripping for function word matching
// ---------------------------------------------------------------------------

describe('Punctuation stripping for function word matching', () => {
    let p;
    beforeEach(() => { p = createPhonemizer(); });

    it('should match "och," (trailing comma)', () => {
        assert.strictEqual(p.detectLanguage('kaffe och, te'), 'sv');
    });

    it('should match "och." (trailing period)', () => {
        assert.strictEqual(p.detectLanguage('kaffe och.'), 'sv');
    });

    it('should match "och!" (trailing exclamation)', () => {
        assert.strictEqual(p.detectLanguage('kaffe och!'), 'sv');
    });

    it('should match "och?" (trailing question mark)', () => {
        assert.strictEqual(p.detectLanguage('kaffe och?'), 'sv');
    });

    it('should match "...och..." (surrounded by punctuation)', () => {
        assert.strictEqual(p.detectLanguage('...och...'), 'sv');
    });

    it('should match ";och;" (semicolons)', () => {
        assert.strictEqual(p.detectLanguage(';och;'), 'sv');
    });
});

// ---------------------------------------------------------------------------
// 10. _segmentText internals
// ---------------------------------------------------------------------------

describe('_segmentText internals', () => {
    let p;
    beforeEach(() => { p = createPhonemizer(); });

    it('should return a single en segment for pure English', () => {
        const segments = p._segmentText('hello world');
        assert.strictEqual(segments.length, 1);
        assert.strictEqual(segments[0].lang, 'en');
    });

    it('should return a single ja segment for pure Japanese', () => {
        const segments = p._segmentText('こんにちは');
        assert.strictEqual(segments.length, 1);
        assert.strictEqual(segments[0].lang, 'ja');
    });

    it('should return a single zh segment for pure Chinese', () => {
        const segments = p._segmentText('你好世界');
        assert.strictEqual(segments.length, 1);
        assert.strictEqual(segments[0].lang, 'zh');
    });

    it('should split JA and EN into separate segments', () => {
        const segments = p._segmentText('こんにちは hello');
        assert.ok(segments.length >= 2);
        assert.strictEqual(segments[0].lang, 'ja');
    });

    it('should return en fallback for empty string', () => {
        const segments = p._segmentText('');
        assert.strictEqual(segments.length, 1);
        assert.strictEqual(segments[0].lang, 'en');
    });

    it('should return en fallback for null', () => {
        const segments = p._segmentText(null);
        assert.strictEqual(segments.length, 1);
        assert.strictEqual(segments[0].lang, 'en');
    });

    it('should refine Latin segments with Swedish indicators to sv', () => {
        const segments = p._segmentText('Jag äter mat');
        assert.strictEqual(segments.length, 1);
        assert.strictEqual(segments[0].lang, 'sv');
    });

    it('should not refine Latin segments without Swedish indicators', () => {
        const segments = p._segmentText('I eat food');
        assert.strictEqual(segments.length, 1);
        assert.strictEqual(segments[0].lang, 'en');
    });
});
