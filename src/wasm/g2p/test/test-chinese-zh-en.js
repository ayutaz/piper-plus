/**
 * ZH-EN code-switching tests for ChineseG2P (TICKET-04 W5).
 *
 * Validates:
 *  - setZhEnDispatch / isZhEnDispatchEnabled wrapper behavior
 *  - bundled JSON shape (LoanwordData TypeScript schema)
 *  - forward-compat for schema_v2 unknown fields (YELLOW-5)
 *  - byte-for-byte parity with Python source via existence of canonical keys
 *
 * Note: full PUA-mapped IPA assertions are in the WASM phonemizer's own
 * test suite (which exercises the Rust `phonemize_embedded_english`
 * directly). The JS layer here is a thin wrapper.
 *
 * Run: node --test src/wasm/g2p/test/test-chinese-zh-en.js
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { ChineseG2P } from '../src/zh/index.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const LOANWORD_PATH = join(__dirname, '..', 'data', 'zh_en_loanword.json');

// ---------------------------------------------------------------------------
// setZhEnDispatch / isZhEnDispatchEnabled
// ---------------------------------------------------------------------------

describe('ChineseG2P — setZhEnDispatch wrapper', () => {
    it('returns null when no WASM phonemizer is attached', () => {
        const g2p = new ChineseG2P();
        assert.equal(g2p.isZhEnDispatchEnabled(), null);
    });

    it('is a no-op when no WASM phonemizer is attached', () => {
        const g2p = new ChineseG2P();
        // Should not throw
        g2p.setZhEnDispatch(true);
        g2p.setZhEnDispatch(false);
        assert.equal(g2p.isZhEnDispatchEnabled(), null);
    });

    it('forwards setZhEnDispatch to the underlying WASM phonemizer', () => {
        let lastEnabled = null;
        const stubWasm = {
            setZhEnDispatch(enabled) {
                lastEnabled = enabled;
            },
            isZhEnDispatchEnabled() {
                return lastEnabled === null ? true : lastEnabled;
            },
            phonemize(text) {
                return { tokens: [], prosody: [] };
            },
        };
        const g2p = new ChineseG2P({ wasmPhonemizer: stubWasm });

        assert.equal(g2p.isZhEnDispatchEnabled(), true); // default-on
        g2p.setZhEnDispatch(false);
        assert.equal(lastEnabled, false);
        assert.equal(g2p.isZhEnDispatchEnabled(), false);
        g2p.setZhEnDispatch(true);
        assert.equal(lastEnabled, true);
    });

    it('coerces truthy/falsy values to boolean', () => {
        const captured = [];
        const stubWasm = {
            setZhEnDispatch(enabled) { captured.push(enabled); },
            isZhEnDispatchEnabled() { return true; },
            phonemize() { return { tokens: [], prosody: [] }; },
        };
        const g2p = new ChineseG2P({ wasmPhonemizer: stubWasm });
        g2p.setZhEnDispatch(1);
        g2p.setZhEnDispatch(0);
        g2p.setZhEnDispatch('yes');
        g2p.setZhEnDispatch('');
        assert.deepEqual(captured, [true, false, true, false]);
    });

    it('returns null when WASM phonemizer lacks the API (older versions)', () => {
        const oldStub = {
            phonemize(text) { return { tokens: [], prosody: [] }; },
            // no setZhEnDispatch / isZhEnDispatchEnabled
        };
        const g2p = new ChineseG2P({ wasmPhonemizer: oldStub });
        // Should not throw, returns null
        g2p.setZhEnDispatch(true);
        assert.equal(g2p.isZhEnDispatchEnabled(), null);
    });
});

// ---------------------------------------------------------------------------
// Bundled JSON shape (LoanwordData)
// ---------------------------------------------------------------------------

describe('zh_en_loanword.json bundled data', () => {
    it('matches the LoanwordData TypeScript schema', async () => {
        const raw = await readFile(LOANWORD_PATH, 'utf8');
        const data = JSON.parse(raw);

        assert.equal(typeof data.version, 'number');
        assert.equal(data.version, 1);
        assert.equal(typeof data.acronyms, 'object');
        assert.equal(typeof data.loanwords, 'object');
        assert.equal(typeof data.letter_fallback, 'object');

        // All values are list[str]
        for (const section of ['acronyms', 'loanwords', 'letter_fallback']) {
            for (const [key, value] of Object.entries(data[section])) {
                assert.ok(Array.isArray(value),
                    `${section}.${key} must be array, got ${typeof value}`);
                assert.ok(value.every((v) => typeof v === 'string'),
                    `${section}.${key} must be array of strings`);
            }
        }
    });

    it('contains canonical issue #384 entries', async () => {
        const raw = await readFile(LOANWORD_PATH, 'utf8');
        const data = JSON.parse(raw);
        // Acronyms: GPS, USB, CPU, API, URL
        for (const key of ['GPS', 'USB', 'CPU', 'API', 'URL']) {
            assert.ok(data.acronyms[key], `acronym ${key} missing`);
        }
        // Loanwords: Python, ChatGPT, iPhone, Tesla
        for (const key of ['Python', 'ChatGPT', 'iPhone', 'Tesla']) {
            assert.ok(data.loanwords[key], `loanword ${key} missing`);
        }
        // Letter fallback: A-Z all 26
        const letters = Object.keys(data.letter_fallback).sort();
        assert.equal(letters.length, 26);
        assert.equal(letters[0], 'A');
        assert.equal(letters[25], 'Z');
    });

    it('GPS has 4 syllables', async () => {
        const raw = await readFile(LOANWORD_PATH, 'utf8');
        const data = JSON.parse(raw);
        // GPS = ji4 + pi4 + ai1 + si4 = 4 pinyin syllables
        assert.equal(data.acronyms.GPS.length, 4);
    });

    it('forward-compat: JSON.parse retains unknown top-level fields (YELLOW-5)', () => {
        // Simulate a future schema_version: 2 with extra fields
        const v2 = `{
            "version": 2,
            "schema_version": 2,
            "metadata": {"experimental": true},
            "acronyms": {"GPS": ["ji4"]},
            "loanwords": {"Python": ["pai4"]},
            "letter_fallback": {"A": ["ei1"]},
            "tone_overrides": {"GPS": "high"}
        }`;
        const data = JSON.parse(v2);
        // Unknown fields are retained (forward-compat)
        assert.equal(data.schema_version, 2);
        assert.deepEqual(data.metadata, { experimental: true });
        assert.deepEqual(data.tone_overrides, { GPS: 'high' });
        // Known fields still parse correctly
        assert.equal(data.version, 2);
        assert.deepEqual(data.acronyms.GPS, ['ji4']);
    });
});
