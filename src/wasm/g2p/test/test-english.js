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

    it('should return same result as phonemize', () => {
        const result1 = en.phonemize('hello');
        const result2 = en.phonemizeWithProsody('hello');
        assert.deepEqual(result1.tokens, result2.tokens);
        assert.deepEqual(result1.prosody, result2.prosody);
    });

    it('should return { tokens, prosody } structure', () => {
        const result = en.phonemizeWithProsody('test');
        assert.ok(Array.isArray(result.tokens));
        assert.ok(Array.isArray(result.prosody));
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
