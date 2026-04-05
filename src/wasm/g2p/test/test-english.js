/**
 * EnglishG2P tests
 *
 * Validates English grapheme-to-phoneme conversion including IPA output,
 * stress markers, function-word stress removal, and result structure.
 *
 * Run: node --test src/wasm/g2p/test/test-english.js
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { EnglishG2P } from '../src/en/index.js';

// ---------------------------------------------------------------------------
// Basic phonemization
// ---------------------------------------------------------------------------

describe('EnglishG2P.phonemize - basic', () => {
    const en = new EnglishG2P();

    it('should return { tokens, prosody } structure', () => {
        const result = en.phonemize('hello');
        assert.ok(Array.isArray(result.tokens), 'tokens should be an array');
        assert.ok(Array.isArray(result.prosody), 'prosody should be an array');
        assert.equal(result.tokens.length, result.prosody.length,
            'tokens and prosody must have same length');
    });

    it('should return non-empty tokens for a simple word', () => {
        const { tokens } = en.phonemize('hello');
        assert.ok(tokens.length > 0, 'tokens should not be empty for "hello"');
    });

    it('should return empty arrays for empty string', () => {
        const { tokens, prosody } = en.phonemize('');
        assert.deepEqual(tokens, []);
        assert.deepEqual(prosody, []);
    });

    it('should return empty arrays for null input', () => {
        const { tokens, prosody } = en.phonemize(null);
        assert.deepEqual(tokens, []);
        assert.deepEqual(prosody, []);
    });

    it('should handle a single word', () => {
        const { tokens } = en.phonemize('cat');
        assert.ok(tokens.length > 0);
        // Should contain IPA characters, not ARPAbet
        const hasArpabet = tokens.some(t => /^[A-Z]{2,}$/.test(t));
        assert.ok(!hasArpabet, 'tokens should be IPA, not ARPAbet');
    });

    it('should produce IPA tokens (not uppercase ARPAbet)', () => {
        const { tokens } = en.phonemize('test');
        // IPA tokens should be lowercase or special characters
        for (const t of tokens) {
            if (t === ' ' || t === '\u02C8' || t === '\u02CC') continue;
            assert.ok(
                t === t.toLowerCase() || t.codePointAt(0) > 127,
                `Token "${t}" looks like ARPAbet (should be IPA)`
            );
        }
    });
});

// ---------------------------------------------------------------------------
// Case normalization
// ---------------------------------------------------------------------------

describe('EnglishG2P.phonemize - case normalization', () => {
    const en = new EnglishG2P();

    it('should produce same output for different cases', () => {
        const lower = en.phonemize('hello');
        const upper = en.phonemize('HELLO');
        const mixed = en.phonemize('Hello');
        assert.deepEqual(lower.tokens, upper.tokens);
        assert.deepEqual(lower.tokens, mixed.tokens);
    });
});

// ---------------------------------------------------------------------------
// Multi-word sentences
// ---------------------------------------------------------------------------

describe('EnglishG2P.phonemize - sentences', () => {
    const en = new EnglishG2P();

    it('should insert space tokens between words', () => {
        const { tokens } = en.phonemize('hello world');
        assert.ok(tokens.includes(' '), 'should have space token between words');
    });

    it('should handle punctuation', () => {
        const { tokens } = en.phonemize('hello, world.');
        assert.ok(tokens.length > 0);
    });

    it('should handle multiple words', () => {
        const { tokens } = en.phonemize('the cat sat on the mat');
        assert.ok(tokens.length > 0);
        // Should contain multiple space tokens
        const spaceCount = tokens.filter(t => t === ' ').length;
        assert.ok(spaceCount >= 4, `Expected >= 4 spaces, got ${spaceCount}`);
    });
});

// ---------------------------------------------------------------------------
// Stress markers
// ---------------------------------------------------------------------------

describe('EnglishG2P.phonemize - stress markers', () => {
    const en = new EnglishG2P();

    it('should insert primary stress marker for content words', () => {
        const { tokens } = en.phonemize('hello');
        const hasPrimary = tokens.includes('\u02C8'); // ˈ
        assert.ok(hasPrimary, 'content word "hello" should have primary stress marker');
    });

    it('should not produce stress markers for function words', () => {
        // "the" is a function word -- stress should be removed
        const { tokens } = en.phonemize('the');
        const hasPrimary = tokens.includes('\u02C8');
        const hasSecondary = tokens.includes('\u02CC');
        assert.ok(!hasPrimary && !hasSecondary,
            'function word "the" should have no stress markers');
    });

    it('should remove stress from common function words in context', () => {
        const { tokens } = en.phonemize('I am a cat');
        // "I", "am", "a" are function words; "cat" is content
        // Overall should still have some stress (from "cat")
        const hasPrimary = tokens.includes('\u02C8');
        assert.ok(hasPrimary, '"cat" should still have stress');
    });
});

// ---------------------------------------------------------------------------
// prosody
// ---------------------------------------------------------------------------

describe('EnglishG2P.phonemize - prosody', () => {
    const en = new EnglishG2P();

    it('should return all-null prosody array', () => {
        const { prosody } = en.phonemize('hello');
        assert.ok(prosody.every(p => p === null),
            'English prosody should be all null');
    });

    it('should match tokens length', () => {
        const { tokens, prosody } = en.phonemize('hello world');
        assert.equal(tokens.length, prosody.length);
    });
});

// ---------------------------------------------------------------------------
// phonemizeWithProsody
// ---------------------------------------------------------------------------

describe('EnglishG2P.phonemizeWithProsody', () => {
    const en = new EnglishG2P();

    it('should return same tokens with prosody objects', () => {
        const result1 = en.phonemize('hello');
        const result2 = en.phonemizeWithProsody('hello');
        assert.deepEqual(result1.tokens, result2.tokens);
        // phonemizeWithProsody returns {a1,a2,a3} objects instead of null
        for (const p of result2.prosody) {
            assert.equal(typeof p, 'object');
            assert.ok(p !== null);
            assert.equal(typeof p.a1, 'number');
        }
    });

    it('should return { tokens, prosody } structure', () => {
        const result = en.phonemizeWithProsody('test');
        assert.ok(Array.isArray(result.tokens));
        assert.ok(Array.isArray(result.prosody));
    });
});

// ---------------------------------------------------------------------------
// Complex / irregular pronunciation words
// ---------------------------------------------------------------------------

describe('EnglishG2P.phonemize - irregular words', () => {
    const en = new EnglishG2P();

    it('should handle "through" (silent gh, dictionary entry)', () => {
        const { tokens } = en.phonemize('through');
        assert.ok(tokens.length > 0, '"through" should produce tokens');
        // "through" is in the dictionary: TH R UW1 -> theta, rho, u:
        // Should contain theta (TH -> θ)
        assert.ok(
            tokens.includes('\u03b8'),
            '"through" should contain \u03b8 (theta)'
        );
    });

    it('should handle "thought" (dictionary fallback)', () => {
        const { tokens } = en.phonemize('thought');
        assert.ok(tokens.length > 0, '"thought" should produce tokens');
        // Falls back to digraph/letter rules; "th" -> TH -> theta
        assert.ok(
            tokens.includes('\u03b8'),
            '"thought" should contain \u03b8 (theta) from "th" digraph'
        );
    });

    it('should handle "tough" (irregular ough)', () => {
        const { tokens } = en.phonemize('tough');
        assert.ok(tokens.length > 0, '"tough" should produce tokens');
        // Not in dictionary; uses fallback rules
        // Output should be IPA (no ARPAbet)
        const hasArpabet = tokens.some(t => /^[A-Z]{2,}$/.test(t));
        assert.ok(!hasArpabet, 'tokens should be IPA, not ARPAbet');
    });

    it('should produce different outputs for "through" vs "tough"', () => {
        const through = en.phonemize('through');
        const tough = en.phonemize('tough');
        // These words have very different pronunciations
        const throughStr = through.tokens.join('');
        const toughStr = tough.tokens.join('');
        assert.notEqual(throughStr, toughStr,
            '"through" and "tough" should have different phonemizations');
    });

    it('should handle "read" (dictionary entry)', () => {
        const { tokens } = en.phonemize('read');
        assert.ok(tokens.length > 0);
        // "read" -> R IY1 D in dictionary (present tense)
    });

    it('should handle "woman" (irregular vowel)', () => {
        const { tokens } = en.phonemize('woman');
        assert.ok(tokens.length >= 3,
            '"woman" should produce at least 3 IPA tokens');
    });
});

// ---------------------------------------------------------------------------
// Unknown word fallback
// ---------------------------------------------------------------------------

describe('EnglishG2P.phonemize - unknown word fallback', () => {
    const en = new EnglishG2P();

    it('should fall back to letter rules for unknown words', () => {
        // "flurb" is not in the dictionary
        const { tokens } = en.phonemize('flurb');
        assert.ok(tokens.length > 0,
            'unknown word "flurb" should still produce tokens via fallback');
    });

    it('should apply digraph rules in fallback', () => {
        // "shim" is not in the dictionary
        // "sh" digraph -> SH -> esh
        const { tokens } = en.phonemize('shim');
        assert.ok(tokens.length > 0);
        // Should contain the IPA esh character from "sh" digraph
        assert.ok(
            tokens.includes('\u0283'),
            '"shim" should contain \u0283 (esh) from "sh" digraph fallback'
        );
    });

    it('should handle completely unknown gibberish', () => {
        const { tokens } = en.phonemize('xyzzy');
        assert.ok(tokens.length > 0,
            'gibberish input should produce tokens via letter rules');
        // All tokens should be IPA
        const hasArpabet = tokens.some(t => /^[A-Z]{2,}$/.test(t));
        assert.ok(!hasArpabet, 'tokens should be IPA even for unknown words');
    });

    it('should handle mixed known and unknown words', () => {
        const { tokens } = en.phonemize('the flurb is good');
        assert.ok(tokens.length > 0);
        // Should have space separators
        const spaceCount = tokens.filter(t => t === ' ').length;
        assert.ok(spaceCount >= 3, `Expected >= 3 spaces, got ${spaceCount}`);
    });
});

// ---------------------------------------------------------------------------
// Edge cases
// ---------------------------------------------------------------------------

describe('EnglishG2P - edge cases', () => {
    const en = new EnglishG2P();

    it('should handle single character', () => {
        const { tokens } = en.phonemize('a');
        assert.ok(tokens.length > 0);
    });

    it('should handle numbers in text', () => {
        // Numbers may be passed through or handled by letter rules
        const { tokens } = en.phonemize('test123');
        assert.ok(Array.isArray(tokens));
    });

    it('should handle text with only spaces', () => {
        const { tokens } = en.phonemize('   ');
        assert.ok(Array.isArray(tokens));
    });
});
