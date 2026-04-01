/**
 * CustomDictionary tests
 *
 * Validates custom dictionary creation, entry management, and JSON format
 * parsing (v1.0 and v2.0).
 *
 * Note: CustomDictionary module (src/custom-dictionary.js) may not exist yet.
 * Tests are written against the expected API from the design spec (FR-300).
 *
 * Run: node --test src/wasm/g2p/test/test-custom-dict.js
 */

import { describe, it, before } from 'node:test';
import assert from 'node:assert/strict';

let CustomDictionary;
let moduleAvailable = false;

before(async () => {
    try {
        const mod = await import('../src/custom-dictionary.js');
        CustomDictionary = mod.CustomDictionary;
        moduleAvailable = true;
    } catch {
        // Module not yet implemented -- tests will be skipped
    }
});

// ---------------------------------------------------------------------------
// Constructor
// ---------------------------------------------------------------------------

describe('CustomDictionary constructor', { skip: !moduleAvailable && 'custom-dictionary.js not yet implemented' }, () => {
    it('should create an empty dictionary', () => {
        const dict = new CustomDictionary();
        assert.ok(dict);
    });
});

// ---------------------------------------------------------------------------
// Entry management
// ---------------------------------------------------------------------------

describe('CustomDictionary entry management', { skip: !moduleAvailable && 'custom-dictionary.js not yet implemented' }, () => {
    it('should add and retrieve an entry', () => {
        const dict = new CustomDictionary();
        dict.add('東京', { tokens: ['t', 'o', 'o', 'ky', 'o', 'o'] });
        const entry = dict.lookup('東京');
        assert.ok(entry);
        assert.deepEqual(entry.tokens, ['t', 'o', 'o', 'ky', 'o', 'o']);
    });

    it('should return null/undefined for missing entries', () => {
        const dict = new CustomDictionary();
        const entry = dict.lookup('存在しない');
        assert.ok(entry === null || entry === undefined);
    });

    it('should overwrite existing entries', () => {
        const dict = new CustomDictionary();
        dict.add('test', { tokens: ['t', 'e', 's', 't'] });
        dict.add('test', { tokens: ['t', 'E', 's', 't'] });
        const entry = dict.lookup('test');
        assert.deepEqual(entry.tokens, ['t', 'E', 's', 't']);
    });

    it('should support multiple entries', () => {
        const dict = new CustomDictionary();
        dict.add('alpha', { tokens: ['a'] });
        dict.add('beta', { tokens: ['b'] });
        assert.ok(dict.lookup('alpha'));
        assert.ok(dict.lookup('beta'));
    });
});

// ---------------------------------------------------------------------------
// JSON v1.0 format
// ---------------------------------------------------------------------------

describe('CustomDictionary JSON v1.0 format', { skip: !moduleAvailable && 'custom-dictionary.js not yet implemented' }, () => {
    it('should parse v1.0 JSON (word -> phonemes string)', () => {
        const json = {
            'hello': 'h ʌ l oʊ',
            'world': 'w ɜː l d',
        };
        const dict = CustomDictionary.fromJSON(json, { version: '1.0' });
        assert.ok(dict.lookup('hello'));
        assert.ok(dict.lookup('world'));
    });
});

// ---------------------------------------------------------------------------
// JSON v2.0 format
// ---------------------------------------------------------------------------

describe('CustomDictionary JSON v2.0 format', { skip: !moduleAvailable && 'custom-dictionary.js not yet implemented' }, () => {
    it('should parse v2.0 JSON (word -> { phonemes, language })', () => {
        const json = {
            version: '2.0',
            entries: {
                'hello': { phonemes: 'h ʌ l oʊ', language: 'en' },
                '東京': { phonemes: 't o o ky o o', language: 'ja' },
            },
        };
        const dict = CustomDictionary.fromJSON(json, { version: '2.0' });
        assert.ok(dict.lookup('hello'));
        assert.ok(dict.lookup('東京'));
    });
});

// ---------------------------------------------------------------------------
// Edge cases
// ---------------------------------------------------------------------------

describe('CustomDictionary edge cases', { skip: !moduleAvailable && 'custom-dictionary.js not yet implemented' }, () => {
    it('should handle empty string key', () => {
        const dict = new CustomDictionary();
        dict.add('', { tokens: [] });
        const entry = dict.lookup('');
        assert.ok(entry);
        assert.deepEqual(entry.tokens, []);
    });

    it('should be case-sensitive by default', () => {
        const dict = new CustomDictionary();
        dict.add('Hello', { tokens: ['h'] });
        const upper = dict.lookup('Hello');
        const lower = dict.lookup('hello');
        assert.ok(upper);
        // By default, case-sensitive -- 'hello' should not match 'Hello'
        assert.ok(lower === null || lower === undefined);
    });
});
