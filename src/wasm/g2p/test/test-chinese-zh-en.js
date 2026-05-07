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

// ---------------------------------------------------------------------------
// CI-C1: cross-runtime fixture matrix consumer (WASM/JS side).
//
// `test/fixtures/zh_en_loanword_matrix.json` is mirrored from
// `tests/fixtures/g2p/zh_en_loanword_matrix.json` by the JSON sync gate.
// Until this consumer landed the JS side had no test depending on it. We
// assert the fixture loads and is well-formed + every case has the required
// `name` field. We do NOT exercise the embedded-english path here because
// the JS layer is a thin wrapper around Rust WASM (covered by Rust tests);
// the goal of this consumer is to catch fixture rot at JS-test time and to
// pin the schema for downstream npm consumers.
// ---------------------------------------------------------------------------

const MATRIX_PATH = join(__dirname, 'fixtures', 'zh_en_loanword_matrix.json');

describe('zh_en_loanword_matrix.json fixture (cross-runtime)', () => {
    it('loads as valid JSON with a non-empty `cases` array', async () => {
        const raw = await readFile(MATRIX_PATH, 'utf8');
        const data = JSON.parse(raw);
        assert.equal(typeof data, 'object');
        assert.ok(Array.isArray(data.cases), 'matrix must have `cases` array');
        assert.ok(data.cases.length > 0, 'matrix `cases` must be non-empty');
    });

    it('every case has a `name` field', async () => {
        const raw = await readFile(MATRIX_PATH, 'utf8');
        const data = JSON.parse(raw);
        for (const c of data.cases) {
            assert.equal(typeof c.name, 'string', `case missing name: ${JSON.stringify(c)}`);
            assert.ok(c.name.length > 0, `case name empty: ${JSON.stringify(c)}`);
        }
    });

    it('cases with `expected_token_count` have number values', async () => {
        const raw = await readFile(MATRIX_PATH, 'utf8');
        const data = JSON.parse(raw);
        let countCases = 0;
        for (const c of data.cases) {
            if ('expected_token_count' in c) {
                assert.equal(typeof c.expected_token_count, 'number',
                    `${c.name}: expected_token_count must be a number`);
                countCases++;
            }
        }
        assert.ok(countCases > 0, 'no cases have expected_token_count — fixture is stale');
    });

    it('schema_v2 forward-compat case round-trips through JSON.parse', async () => {
        const raw = await readFile(MATRIX_PATH, 'utf8');
        const data = JSON.parse(raw);
        const schemaV2Case = data.cases.find(
            (c) => c.name === 'schema_v2_forward_compat_loader',
        );
        if (!schemaV2Case) {
            return; // Skipped: fixture without this case is allowed for older snapshots
        }
        assert.ok(schemaV2Case.input_json, 'schema_v2 case must have input_json');
        // Round-trip via JSON to verify the inline payload is itself valid.
        const reparsed = JSON.parse(JSON.stringify(schemaV2Case.input_json));
        assert.deepEqual(reparsed.acronyms, schemaV2Case.input_json.acronyms);
    });

    it('matches the matrix mirrored under tests/fixtures/g2p (byte-identical)', async () => {
        // The CI sync gate (scripts/check_loanword_consistency.py) keeps the 6
        // fixture mirrors byte-identical to tests/fixtures/g2p/. This test
        // adds a JS-side check: even if the gate is bypassed, drift between
        // the WASM mirror and the source fixture surfaces here at npm-test time.
        const repoRoot = join(__dirname, '..', '..', '..', '..');
        const sourceFixture = join(
            repoRoot, 'tests', 'fixtures', 'g2p', 'zh_en_loanword_matrix.json',
        );
        let sourceRaw;
        try {
            sourceRaw = await readFile(sourceFixture, 'utf8');
        } catch {
            // Source fixture not present in this checkout — npm-published
            // packages don't ship tests/fixtures/. Skip silently.
            return;
        }
        const mirrorRaw = await readFile(MATRIX_PATH, 'utf8');
        // Normalize line endings so a stray CRLF on Windows checkouts doesn't
        // false-flag the gate. The byte-for-byte gate is enforced separately
        // by scripts/check_loanword_consistency.py at CI time.
        const norm = (s) => s.replace(/\r\n/g, '\n');
        assert.equal(norm(mirrorRaw), norm(sourceRaw),
            'WASM matrix mirror has drifted from tests/fixtures/g2p — run ' +
            '`python scripts/check_loanword_consistency.py --fix`');
    });
});
