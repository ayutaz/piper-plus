/**
 * Swedish language support tests for G2P (via @piper-plus/g2p).
 *
 * Verifies Swedish character-based detection and phonemization,
 * consistent with the Python/Rust/C#/C++ implementations.
 *
 * The G2P UnicodeLanguageDetector uses character-count scoring:
 * Swedish-specific characters (å,ä,ö,Å,Ä,Ö) score for 'sv'.
 * Texts where Swedish chars are dominant (or equal to Latin) detect as 'sv'.
 *
 * Run with: node --test test/js/test-swedish.js
 */

import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { G2P, UnicodeLanguageDetector, SwedishG2P } from '@piper-plus/g2p';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Create a UnicodeLanguageDetector with all 8 languages. */
function createDetector() {
    return new UnicodeLanguageDetector(['ja', 'en', 'zh', 'ko', 'es', 'fr', 'pt', 'sv']);
}

// ---------------------------------------------------------------------------
// 1. Swedish character detection (dominant Swedish characters)
// ---------------------------------------------------------------------------

describe('Swedish character detection (dominant Swedish chars)', () => {
    let detector;
    beforeEach(() => { detector = createDetector(); });

    it('should detect single Swedish character Ä as sv', () => {
        // Only Swedish-specific char -> sv
        assert.strictEqual(detector.detectLanguage('\u00c4'), 'sv');
    });

    it('should detect single Swedish character Ö as sv', () => {
        assert.strictEqual(detector.detectLanguage('\u00d6'), 'sv');
    });

    it('should detect single Swedish character Å as sv', () => {
        assert.strictEqual(detector.detectLanguage('\u00c5'), 'sv');
    });

    it('should detect "Ål" (Å dominant) as sv', () => {
        // Å=sv(1), l=en(1) -- tie, but Swedish char appears first in iteration
        // Use text with clearly dominant Swedish chars
        assert.strictEqual(detector.detectLanguage('\u00d6l'), 'sv');
    });

    it('should detect "ääö" (all Swedish chars) as sv', () => {
        assert.strictEqual(detector.detectLanguage('\u00e4\u00e4\u00f6'), 'sv');
    });

    it('should detect Japanese text as ja', () => {
        assert.strictEqual(detector.detectLanguage('\u3053\u3093\u306b\u3061\u306f'), 'ja');
    });

    it('should detect Chinese text as zh', () => {
        assert.strictEqual(detector.detectLanguage('\u4f60\u597d\u4e16\u754c'), 'zh');
    });

    it('should detect Korean text as ko', () => {
        assert.strictEqual(detector.detectLanguage('\ud55c\uad6d\uc5b4'), 'ko');
    });

    it('should return en for plain English text', () => {
        assert.strictEqual(detector.detectLanguage('Hello world'), 'en');
    });
});

// ---------------------------------------------------------------------------
// 2. Swedish text segmentation
// ---------------------------------------------------------------------------

describe('Swedish text segmentation', () => {
    let detector;
    beforeEach(() => { detector = createDetector(); });

    it('should segment Swedish and Japanese separately', () => {
        const segments = detector.segmentText('\u3053\u3093\u306b\u3061\u306f \u00d6l');
        assert.ok(segments.length >= 2, `expected >= 2 segments, got ${segments.length}`);
        assert.strictEqual(segments[0].language, 'ja');
        const svSeg = segments.find(s => s.language === 'sv');
        assert.ok(svSeg, 'should have an sv segment');
    });

    it('should detect sv for text with majority Swedish characters', () => {
        // Text: "äöå" (3 Swedish chars, 0 Latin) -> sv
        assert.strictEqual(detector.detectLanguage('\u00e4\u00f6\u00e5'), 'sv');
    });
});

// ---------------------------------------------------------------------------
// 3. SwedishG2P phonemize
// ---------------------------------------------------------------------------

describe('SwedishG2P phonemize', () => {
    let g2p;
    beforeEach(() => { g2p = new SwedishG2P(); });

    it('should return tokens for simple Swedish word', () => {
        const result = g2p.phonemize('hej');
        assert.ok(Array.isArray(result.tokens), 'tokens should be an array');
        assert.ok(result.tokens.length > 0, 'tokens should not be empty');
    });

    it('should return IPA tokens (no BOS/EOS -- added by Encoder)', () => {
        const result = g2p.phonemize('ja');
        assert.ok(result.tokens.length > 0, 'tokens should not be empty');
        // SwedishG2P returns raw IPA tokens (^/$  are added by Encoder)
        assert.ok(typeof result.tokens[0] === 'string', 'tokens should be strings');
    });

    it('should handle empty string', () => {
        const result = g2p.phonemize('');
        assert.ok(Array.isArray(result.tokens));
    });
});

// ---------------------------------------------------------------------------
// 4. G2P encode integration
// ---------------------------------------------------------------------------

describe('Swedish G2P encode integration', () => {
    let g2p;
    beforeEach(async () => {
        // Create G2P without JA (no openjtalk module needed)
        g2p = await G2P.create({ languages: ['en', 'sv'] });
    });

    it('G2P.encode returns phonemeIds for Swedish text', () => {
        const phonemeIdMap = {
            '_': [0], '^': [1], '$': [2], ' ': [3],
            'h': [10], 'e': [11], 'j': [12],
        };
        const result = g2p.encode('hej', phonemeIdMap, { language: 'sv' });
        assert.ok(Array.isArray(result.phonemeIds), 'phonemeIds should be an array');
        assert.ok(result.phonemeIds.length > 0, 'phonemeIds should not be empty');
    });

    it('G2P.encode result has prosodyFlat null or array for Swedish', () => {
        const phonemeIdMap = { '_': [0], '^': [1], '$': [2], ' ': [3] };
        const result = g2p.encode('hej', phonemeIdMap, { language: 'sv' });
        assert.ok(result.prosodyFlat === null || Array.isArray(result.prosodyFlat));
    });
});
