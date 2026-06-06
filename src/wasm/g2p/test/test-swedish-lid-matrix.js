/**
 * Cross-runtime Swedish per-word LID parity fixture matrix (Issue #539).
 *
 * Loads `test/fixtures/swedish_lid_matrix.json` (mirrored byte-for-byte from
 * the canonical `tests/fixtures/g2p/swedish_lid_matrix.json` by
 * scripts/check_swedish_lid_consistency.py) and verifies that the WASM/JS
 * `UnicodeLanguageDetector.segmentText` per-word Swedish post-pass agrees with
 * each case's `expect_contains_sv` flag.
 *
 * Each case builds a detector with `languages = fixture.languages` and
 * `{ defaultLatinLanguage: fixture.default_latin }`, runs segmentation, and
 * asserts `("sv" in segment languages) === expect_contains_sv`. The sister
 * tests in Python / Rust×2 / Go / C++ / C# consume the SAME fixture, so
 * cross-runtime agreement on these cases is the parity proof.
 *
 * Mirror of the cross-runtime fixture consumer in test-chinese-zh-en.js.
 *
 * Run: node --test src/wasm/g2p/test/test-swedish-lid-matrix.js
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { UnicodeLanguageDetector } from '../src/detect.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const MATRIX_PATH = join(__dirname, 'fixtures', 'swedish_lid_matrix.json');

async function loadMatrix() {
    const raw = await readFile(MATRIX_PATH, 'utf8');
    return JSON.parse(raw);
}

/** Does any segment of `text` get classified as Swedish? */
function containsSv(languages, defaultLatin, text) {
    const detector = new UnicodeLanguageDetector(languages, {
        defaultLatinLanguage: defaultLatin,
    });
    return detector.segmentText(text).some((seg) => seg.language === 'sv');
}

describe('swedish_lid_matrix.json fixture (cross-runtime)', () => {
    it('loads as valid JSON with schema_version 1 and a non-empty `cases` array', async () => {
        const data = await loadMatrix();
        assert.equal(data.schema_version, 1, 'unexpected schema_version');
        assert.deepEqual(data.languages, ['en', 'sv']);
        assert.equal(data.default_latin, 'en');
        assert.ok(Array.isArray(data.cases), 'matrix must have `cases` array');
        assert.ok(data.cases.length >= 10, 'matrix `cases` must have >=10 entries');
    });

    it('agrees with every case `expect_contains_sv` via segmentText', async () => {
        const data = await loadMatrix();
        for (const c of data.cases) {
            const got = containsSv(data.languages, data.default_latin, c.text);
            assert.equal(
                got,
                c.expect_contains_sv,
                `[sv-lid] "${c.text}": expected contains_sv=${c.expect_contains_sv}, ` +
                    `got ${got}. If intentional, update ` +
                    'tests/fixtures/g2p/swedish_lid_matrix.json and re-sync via ' +
                    '`python scripts/check_swedish_lid_consistency.py --fix`.',
            );
        }
    });

    it('matches the matrix mirrored under tests/fixtures/g2p (byte-identical)', async () => {
        // The CI sync gate (scripts/check_swedish_lid_consistency.py) keeps the
        // mirrors byte-identical to tests/fixtures/g2p/. This adds a JS-side
        // check: even if the gate is bypassed, drift between the WASM mirror and
        // the source fixture surfaces here at npm-test time.
        const repoRoot = join(__dirname, '..', '..', '..', '..');
        const sourceFixture = join(
            repoRoot, 'tests', 'fixtures', 'g2p', 'swedish_lid_matrix.json',
        );
        let sourceRaw;
        try {
            sourceRaw = await readFile(sourceFixture, 'utf8');
        } catch {
            // Source fixture not present in this checkout (npm-published packages
            // don't ship tests/fixtures/). Skip silently.
            return;
        }
        const mirrorRaw = await readFile(MATRIX_PATH, 'utf8');
        const norm = (s) => s.replace(/\r\n/g, '\n');
        assert.equal(
            norm(mirrorRaw),
            norm(sourceRaw),
            'WASM matrix mirror has drifted from tests/fixtures/g2p — run ' +
                '`python scripts/check_swedish_lid_consistency.py --fix`',
        );
    });
});
