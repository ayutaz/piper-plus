/**
 * Package metadata verification tests.
 *
 * `files` is a promise about what reaches the registry, and npm keeps that
 * promise silently: an entry pointing at something that does not exist is
 * dropped without a warning. Two such promises were broken here at once —
 * `dist/openjtalk.wasm` and `dist/openjtalk.js` were listed long after the
 * Emscripten OpenJTalk build was retired in #301, so the published tarball
 * contained no `dist/` at all; and `license: "MIT"` was declared while the
 * tarball shipped no permission notice, which MIT requires in every copy.
 *
 * Run: node --test src/wasm/g2p/test/test-package-metadata.js
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));

/** Package root: src/wasm/g2p/ */
const PKG_ROOT = resolve(__dirname, '..');

const pkg = JSON.parse(readFileSync(join(PKG_ROOT, 'package.json'), 'utf-8'));

/**
 * Resolve the concrete prefix of a `files` entry — the part before any glob.
 * A path that does not exist cannot be packed no matter how the glob expands.
 *
 * @param {string} entry
 * @returns {string}
 */
function concretePrefix(entry) {
    const star = entry.indexOf('*');
    const head = star === -1 ? entry : entry.slice(0, star);
    const cut = head.lastIndexOf('/');
    return star === -1 ? entry : head.slice(0, cut === -1 ? head.length : cut);
}

describe('package.json files フィールド', () => {
    it('全 files エントリが実在するパスに解決される', () => {
        const missing = pkg.files.filter((entry) => {
            const prefix = concretePrefix(entry);
            return prefix !== '' && !existsSync(join(PKG_ROOT, prefix));
        });

        assert.deepEqual(
            missing,
            [],
            'A files entry that does not exist is dropped by npm without any ' +
                'warning, leaving the package smaller than declared.'
        );
    });
});

describe('ライセンス同梱', () => {
    it('license フィールドが宣言されている', () => {
        assert.equal(typeof pkg.license, 'string');
        assert.ok(pkg.license.length > 0, 'license should not be empty');
    });

    it('許諾文のファイルが実在し files に含まれている', () => {
        // MIT requires the copyright notice and permission notice to appear in
        // all copies, so declaring the identifier alone is not compliance.
        const candidates = ['LICENSE', 'LICENSE.md', 'LICENSE.txt'];
        const present = candidates.filter((name) => existsSync(join(PKG_ROOT, name)));

        assert.notDeepEqual(
            present,
            [],
            `Declared "license": "${pkg.license}" but no license text file exists ` +
                `in ${PKG_ROOT} (looked for ${candidates.join(', ')}).`
        );

        const shipped = present.filter((name) => pkg.files.includes(name));
        assert.notDeepEqual(
            shipped,
            [],
            `License text exists (${present.join(', ')}) but no entry in files ` +
                'ships it, so the published tarball carries no permission notice.'
        );
    });

    it('許諾文に著作権表示と permission notice が含まれる', () => {
        const name = ['LICENSE', 'LICENSE.md', 'LICENSE.txt'].find((n) =>
            existsSync(join(PKG_ROOT, n))
        );
        assert.ok(name, 'a license text file must exist');

        const text = readFileSync(join(PKG_ROOT, name), 'utf-8');
        assert.match(text, /Copyright/i, 'license text must carry a copyright notice');
        assert.match(
            text,
            /Permission is hereby granted/i,
            'MIT license text must carry the permission notice'
        );
    });
});

/**
 * The files `npm pack` would publish, with their sizes, read from
 * `npm pack --dry-run --json` (the same listing check-cdn-delivery.mjs uses).
 *
 * @returns {{ path: string, size: number }[]}
 */
function packedFiles() {
    const out = execFileSync('npm', ['pack', '--dry-run', '--json', '--ignore-scripts'], {
        cwd: PKG_ROOT,
        encoding: 'utf-8',
        shell: process.platform === 'win32',
        stdio: ['ignore', 'pipe', 'ignore'],
    });
    return JSON.parse(out)[0].files.map((f) => ({ path: f.path.replace(/\\/g, '/'), size: f.size }));
}

describe('CMU 辞書の同梱 (Issue #828)', () => {
    const DICT = 'data/cmudict_data.json';

    it('files に data/cmudict_data.json が含まれる', () => {
        assert.ok(
            pkg.files.includes(DICT),
            `${DICT} must be listed in files, or the English G2P has no dictionary once published`
        );
    });

    it('npm pack の内容に辞書と CMU の許諾文が入る', () => {
        const packed = packedFiles();
        const dict = packed.find((f) => f.path === DICT);
        assert.ok(dict, `${DICT} is not in the npm pack listing`);
        assert.equal(dict.size, readFileSync(join(PKG_ROOT, DICT)).length);

        // The CMU license requires its notice in every redistribution.
        assert.ok(
            packed.some((f) => f.path === 'THIRD_PARTY_LICENSES.md'),
            'THIRD_PARTY_LICENSES.md (CMU notice) is not in the npm pack listing'
        );
        const notices = readFileSync(join(PKG_ROOT, 'THIRD_PARTY_LICENSES.md'), 'utf-8');
        assert.match(notices, /Carnegie Mellon University/);
        assert.match(notices, /This product includes data from the Carnegie\s+>?\s*Mellon Pronouncing Dictionary/);
    });
});
