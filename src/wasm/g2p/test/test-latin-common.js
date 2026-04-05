/**
 * latin-common shared module tests
 *
 * Validates the shared utilities used by ES, FR, and PT G2P modules:
 * collapseNfdAccents, isPunctuation, tokenize, normalizeWhitespace.
 *
 * Run: node --test src/wasm/g2p/test/test-latin-common.js
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
    collapseNfdAccents,
    isPunctuation,
    PUNCTUATION,
    tokenize,
    normalizeWhitespace,
} from '../src/latin-common/index.js';

// ===========================================================================
// collapseNfdAccents
// ===========================================================================

describe('collapseNfdAccents -- acute accent (U+0301)', () => {
    it('a + combining acute -> \u00E1', () => {
        const result = collapseNfdAccents(['a', '\u0301']);
        assert.deepEqual(result, ['\u00E1']);
    });

    it('e + combining acute -> \u00E9', () => {
        const result = collapseNfdAccents(['e', '\u0301']);
        assert.deepEqual(result, ['\u00E9']);
    });

    it('uppercase O + combining acute -> \u00D3', () => {
        const result = collapseNfdAccents(['O', '\u0301']);
        assert.deepEqual(result, ['\u00D3']);
    });
});

describe('collapseNfdAccents -- grave accent (U+0300)', () => {
    it('a + combining grave -> \u00E0', () => {
        const result = collapseNfdAccents(['a', '\u0300']);
        assert.deepEqual(result, ['\u00E0']);
    });

    it('E + combining grave -> \u00C8', () => {
        const result = collapseNfdAccents(['E', '\u0300']);
        assert.deepEqual(result, ['\u00C8']);
    });
});

describe('collapseNfdAccents -- circumflex (U+0302)', () => {
    it('e + combining circumflex -> \u00EA', () => {
        const result = collapseNfdAccents(['e', '\u0302']);
        assert.deepEqual(result, ['\u00EA']);
    });

    it('a + combining circumflex -> \u00E2', () => {
        const result = collapseNfdAccents(['a', '\u0302']);
        assert.deepEqual(result, ['\u00E2']);
    });
});

describe('collapseNfdAccents -- tilde (U+0303)', () => {
    it('n + combining tilde -> \u00F1', () => {
        const result = collapseNfdAccents(['n', '\u0303']);
        assert.deepEqual(result, ['\u00F1']);
    });

    it('a + combining tilde -> \u00E3', () => {
        const result = collapseNfdAccents(['a', '\u0303']);
        assert.deepEqual(result, ['\u00E3']);
    });
});

describe('collapseNfdAccents -- diaeresis (U+0308)', () => {
    it('u + combining diaeresis -> \u00FC', () => {
        const result = collapseNfdAccents(['u', '\u0308']);
        assert.deepEqual(result, ['\u00FC']);
    });

    it('e + combining diaeresis -> \u00EB', () => {
        const result = collapseNfdAccents(['e', '\u0308']);
        assert.deepEqual(result, ['\u00EB']);
    });
});

describe('collapseNfdAccents -- cedilla (U+0327)', () => {
    it('c + combining cedilla -> \u00E7', () => {
        const result = collapseNfdAccents(['c', '\u0327']);
        assert.deepEqual(result, ['\u00E7']);
    });

    it('C + combining cedilla -> \u00C7', () => {
        const result = collapseNfdAccents(['C', '\u0327']);
        assert.deepEqual(result, ['\u00C7']);
    });
});

describe('collapseNfdAccents -- edge cases', () => {
    it('empty array -> empty array', () => {
        const result = collapseNfdAccents([]);
        assert.deepEqual(result, []);
    });

    it('single character -> returned as-is', () => {
        const result = collapseNfdAccents(['a']);
        assert.deepEqual(result, ['a']);
    });

    it('no combining marks -> unchanged', () => {
        const result = collapseNfdAccents(['h', 'o', 'l', 'a']);
        assert.deepEqual(result, ['h', 'o', 'l', 'a']);
    });

    it('mixed: plain chars + NFD sequences', () => {
        // "cafe" with NFD e-acute: c a f e + combining acute
        const result = collapseNfdAccents(['c', 'a', 'f', 'e', '\u0301']);
        assert.deepEqual(result, ['c', 'a', 'f', '\u00E9']);
    });

    it('unknown combining mark is left as-is', () => {
        // U+030C combining caron -- not in the NFC_TABLE
        const result = collapseNfdAccents(['a', '\u030C']);
        assert.deepEqual(result, ['a', '\u030C']);
    });

    it('consecutive NFD sequences', () => {
        // a+acute, e+grave -> \u00E1, \u00E8
        const result = collapseNfdAccents(['a', '\u0301', 'e', '\u0300']);
        assert.deepEqual(result, ['\u00E1', '\u00E8']);
    });
});

// ===========================================================================
// isPunctuation / PUNCTUATION
// ===========================================================================

describe('isPunctuation -- common punctuation', () => {
    it('comma is punctuation', () => {
        assert.equal(isPunctuation(','), true);
    });

    it('period is punctuation', () => {
        assert.equal(isPunctuation('.'), true);
    });

    it('exclamation mark is punctuation', () => {
        assert.equal(isPunctuation('!'), true);
    });

    it('question mark is punctuation', () => {
        assert.equal(isPunctuation('?'), true);
    });

    it('inverted exclamation (\u00A1) is punctuation', () => {
        assert.equal(isPunctuation('\u00A1'), true);
    });

    it('inverted question (\u00BF) is punctuation', () => {
        assert.equal(isPunctuation('\u00BF'), true);
    });

    it('em dash (\u2014) is punctuation', () => {
        assert.equal(isPunctuation('\u2014'), true);
    });

    it('left guillemet (\u00AB) is punctuation', () => {
        assert.equal(isPunctuation('\u00AB'), true);
    });

    it('right guillemet (\u00BB) is punctuation', () => {
        assert.equal(isPunctuation('\u00BB'), true);
    });

    it('ellipsis (\u2026) is punctuation', () => {
        assert.equal(isPunctuation('\u2026'), true);
    });
});

describe('isPunctuation -- non-punctuation', () => {
    it('letter "a" is not punctuation', () => {
        assert.equal(isPunctuation('a'), false);
    });

    it('digit "1" is not punctuation', () => {
        assert.equal(isPunctuation('1'), false);
    });

    it('space is not punctuation', () => {
        assert.equal(isPunctuation(' '), false);
    });

    it('hyphen-minus is not punctuation', () => {
        assert.equal(isPunctuation('-'), false);
    });

    it('apostrophe is not punctuation', () => {
        assert.equal(isPunctuation("'"), false);
    });
});

describe('PUNCTUATION set', () => {
    it('has 13 entries', () => {
        assert.equal(PUNCTUATION.size, 13);
    });
});

// ===========================================================================
// tokenize
// ===========================================================================

describe('tokenize -- basic word splitting', () => {
    const isAlpha = (ch) => /^[a-z]$/.test(ch);

    it('single word -> one word token', () => {
        const tokens = tokenize(['h', 'o', 'l', 'a'], isAlpha);
        assert.equal(tokens.length, 1);
        assert.deepEqual(tokens[0].chars, ['h', 'o', 'l', 'a']);
        assert.equal(tokens[0].isPunct, false);
    });

    it('two words separated by space -> two word tokens', () => {
        const tokens = tokenize(['h', 'i', ' ', 'y', 'o'], isAlpha);
        assert.equal(tokens.length, 2);
        assert.deepEqual(tokens[0].chars, ['h', 'i']);
        assert.deepEqual(tokens[1].chars, ['y', 'o']);
    });

    it('empty input -> empty tokens', () => {
        const tokens = tokenize([], isAlpha);
        assert.deepEqual(tokens, []);
    });

    it('only whitespace -> empty tokens', () => {
        const tokens = tokenize([' ', ' ', ' '], isAlpha);
        assert.deepEqual(tokens, []);
    });
});

describe('tokenize -- punctuation handling', () => {
    const isAlpha = (ch) => /^[a-z]$/.test(ch);

    it('word followed by punctuation -> word + punct tokens', () => {
        const tokens = tokenize(['h', 'i', '!'], isAlpha);
        assert.equal(tokens.length, 2);
        assert.deepEqual(tokens[0].chars, ['h', 'i']);
        assert.equal(tokens[0].isPunct, false);
        assert.deepEqual(tokens[1].chars, ['!']);
        assert.equal(tokens[1].isPunct, true);
    });

    it('punctuation before word', () => {
        const tokens = tokenize(['\u00BF', 'q', 'u', 'e', '?'], isAlpha);
        assert.equal(tokens.length, 3);
        assert.equal(tokens[0].isPunct, true);
        assert.deepEqual(tokens[0].chars, ['\u00BF']);
        assert.equal(tokens[1].isPunct, false);
        assert.equal(tokens[2].isPunct, true);
    });

    it('digits are skipped', () => {
        const tokens = tokenize(['a', '1', '2', 'b'], isAlpha);
        assert.equal(tokens.length, 2);
        assert.deepEqual(tokens[0].chars, ['a']);
        assert.deepEqual(tokens[1].chars, ['b']);
    });
});

describe('tokenize -- custom isWordCharFn predicate', () => {
    it('predicate that includes accented chars', () => {
        const isWordChar = (ch) => /^[a-z\u00E0-\u00FF]$/.test(ch);
        const tokens = tokenize(['c', 'a', 'f', '\u00E9'], isWordChar);
        assert.equal(tokens.length, 1);
        assert.deepEqual(tokens[0].chars, ['c', 'a', 'f', '\u00E9']);
    });

    it('predicate that rejects all chars -> only punct tokens', () => {
        const rejectAll = () => false;
        const tokens = tokenize(['a', '.', 'b'], rejectAll);
        assert.equal(tokens.length, 1);
        assert.equal(tokens[0].isPunct, true);
        assert.deepEqual(tokens[0].chars, ['.']);
    });
});

// ===========================================================================
// normalizeWhitespace
// ===========================================================================

describe('normalizeWhitespace -- collapsing', () => {
    it('multiple spaces -> single space', () => {
        const result = normalizeWhitespace(['a', ' ', ' ', ' ', 'b']);
        assert.deepEqual(result, ['a', ' ', 'b']);
    });

    it('tabs collapsed to single space', () => {
        const result = normalizeWhitespace(['a', '\t', '\t', 'b']);
        assert.deepEqual(result, ['a', ' ', 'b']);
    });

    it('mixed whitespace collapsed', () => {
        const result = normalizeWhitespace(['a', ' ', '\t', '\n', 'b']);
        assert.deepEqual(result, ['a', ' ', 'b']);
    });
});

describe('normalizeWhitespace -- trimming', () => {
    it('leading whitespace trimmed', () => {
        const result = normalizeWhitespace([' ', ' ', 'a', 'b']);
        assert.deepEqual(result, ['a', 'b']);
    });

    it('trailing whitespace trimmed', () => {
        const result = normalizeWhitespace(['a', 'b', ' ', ' ']);
        assert.deepEqual(result, ['a', 'b']);
    });

    it('both leading and trailing trimmed', () => {
        const result = normalizeWhitespace([' ', 'a', ' ', 'b', ' ']);
        assert.deepEqual(result, ['a', ' ', 'b']);
    });
});

describe('normalizeWhitespace -- edge cases', () => {
    it('empty array -> empty array', () => {
        const result = normalizeWhitespace([]);
        assert.deepEqual(result, []);
    });

    it('only whitespace -> empty array', () => {
        const result = normalizeWhitespace([' ', '\t', '\n', ' ']);
        assert.deepEqual(result, []);
    });

    it('no whitespace -> unchanged', () => {
        const result = normalizeWhitespace(['a', 'b', 'c']);
        assert.deepEqual(result, ['a', 'b', 'c']);
    });

    it('single non-whitespace char -> unchanged', () => {
        const result = normalizeWhitespace(['x']);
        assert.deepEqual(result, ['x']);
    });
});
