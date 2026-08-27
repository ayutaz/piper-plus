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
