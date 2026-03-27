/**
 * npm package integration tests
 *
 * Validates that the piper-plus package metadata, exports, file listings,
 * and size constraints are consistent and correct before publishing.
 *
 * Run: node --test test/js/test-npm-package.js
 */

import { strict as assert } from 'node:assert';
import { describe, it } from 'node:test';
import { readFileSync, existsSync, statSync, readdirSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

/** Project root: src/wasm/openjtalk-web/ */
const PROJECT_ROOT = resolve(__dirname, '..', '..');

/** Read and parse package.json once for all tests. */
const pkgPath = join(PROJECT_ROOT, 'package.json');
const pkg = JSON.parse(readFileSync(pkgPath, 'utf-8'));

/**
 * Expand simple glob-like entries from the `files` array into concrete
 * filesystem paths.  Only handles the two patterns actually used by this
 * project: "dir/**\/*.ext" (recursive) and bare file/directory paths.
 *
 * This is intentionally minimal -- we are NOT re-implementing npm's full
 * glob logic; we only need to verify the entries that exist on disk.
 *
 * @param {string} pattern - A single entry from package.json `files`
 * @returns {string[]} Resolved absolute paths that match
 */
function expandFilesEntry(pattern) {
  const abs = resolve(PROJECT_ROOT, pattern);

  // Recursive glob: "src/**/*.js"
  if (pattern.includes('**')) {
    const base = resolve(PROJECT_ROOT, pattern.split('**')[0]);
    if (!existsSync(base)) return [];
    const ext = pattern.split('*').pop(); // e.g. ".js"
    return walkDir(base).filter((f) => f.endsWith(ext));
  }

  // Directory entry (e.g. "types/")
  if (pattern.endsWith('/') || (existsSync(abs) && statSync(abs).isDirectory())) {
    if (!existsSync(abs)) return [];
    return walkDir(abs);
  }

  // Literal file
  if (existsSync(abs)) return [abs];
  return [];
}

/**
 * Recursively walk a directory and return all file paths.
 *
 * @param {string} dir
 * @returns {string[]}
 */
function walkDir(dir) {
  const results = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...walkDir(full));
    } else {
      results.push(full);
    }
  }
  return results;
}

// ---------------------------------------------------------------------------
// 1. Exports validation
// ---------------------------------------------------------------------------

describe('exports validation', () => {
  /** Expected named exports from the main entry point. */
  const EXPECTED_EXPORTS = [
    'PiperPlus',
    'AudioResult',
    'ModelManager',
    'DictManager',
    'SimpleUnifiedPhonemizer',
    'WebGPUSessionManager',
    'StreamingTTSPipeline',
    'TextChunker',
    'CacheManager',
  ];

  it('main entry point (src/index.js) can be imported', async () => {
    const entryPath = resolve(PROJECT_ROOT, 'src', 'index.js');
    assert.ok(existsSync(entryPath), `Entry point does not exist: ${entryPath}`);

    const mod = await import(entryPath);
    assert.ok(mod, 'Module should be importable');
  });

  it('all expected names are exported', async () => {
    const entryPath = resolve(PROJECT_ROOT, 'src', 'index.js');
    const mod = await import(entryPath);
    const exportedNames = Object.keys(mod);

    for (const name of EXPECTED_EXPORTS) {
      assert.ok(
        exportedNames.includes(name),
        `Missing export: "${name}". Actual exports: [${exportedNames.join(', ')}]`,
      );
    }
  });

  it('exported names match between index.js and type definitions', async () => {
    const dtsPath = resolve(PROJECT_ROOT, 'types', 'index.d.ts');
    if (!existsSync(dtsPath)) {
      // Type definitions not yet created -- skip gracefully.
      return;
    }

    const dtsContent = readFileSync(dtsPath, 'utf-8');
    const entryPath = resolve(PROJECT_ROOT, 'src', 'index.js');
    const mod = await import(entryPath);
    const exportedNames = Object.keys(mod);

    for (const name of exportedNames) {
      assert.ok(
        dtsContent.includes(name),
        `Export "${name}" is not referenced in types/index.d.ts`,
      );
    }
  });
});

// ---------------------------------------------------------------------------
// 2. package.json validation
// ---------------------------------------------------------------------------

describe('package.json validation', () => {
  it('name is "piper-plus"', () => {
    assert.equal(pkg.name, 'piper-plus');
  });

  it('version follows semver (X.Y.Z)', () => {
    const semverRe = /^\d+\.\d+\.\d+(?:-[\w.]+)?(?:\+[\w.]+)?$/;
    assert.match(
      pkg.version,
      semverRe,
      `Version "${pkg.version}" does not match semver format`,
    );
  });

  it('license is "MIT"', () => {
    assert.equal(pkg.license, 'MIT');
  });

  it('peerDependencies includes "onnxruntime-web"', () => {
    assert.ok(pkg.peerDependencies, 'peerDependencies is missing');
    assert.ok(
      'onnxruntime-web' in pkg.peerDependencies,
      'peerDependencies should include "onnxruntime-web"',
    );
  });

  it('type is "module"', () => {
    assert.equal(pkg.type, 'module');
  });

  it('exports field is defined', () => {
    assert.ok(pkg.exports, 'exports field is missing');
    assert.ok(
      typeof pkg.exports === 'object',
      'exports should be an object',
    );
    assert.ok(pkg.exports['.'], 'exports should contain a "." entry');
  });

  it('files field is defined and is an array', () => {
    assert.ok(Array.isArray(pkg.files), 'files should be an array');
    assert.ok(pkg.files.length > 0, 'files should not be empty');
  });
});

// ---------------------------------------------------------------------------
// 3. files field validation
// ---------------------------------------------------------------------------

describe('files field validation', () => {
  it('files entries resolve to existing paths', () => {
    const missing = [];

    for (const entry of pkg.files) {
      const expanded = expandFilesEntry(entry);
      if (expanded.length === 0) {
        missing.push(entry);
      }
    }

    assert.deepEqual(
      missing,
      [],
      `The following files entries do not resolve to any existing path: ${missing.join(', ')}`,
    );
  });

  it('dist/openjtalk.wasm exists', () => {
    const wasmPath = join(PROJECT_ROOT, 'dist', 'openjtalk.wasm');
    assert.ok(existsSync(wasmPath), 'dist/openjtalk.wasm is missing');
  });

  it('dist/openjtalk.js exists', () => {
    const jsPath = join(PROJECT_ROOT, 'dist', 'openjtalk.js');
    assert.ok(existsSync(jsPath), 'dist/openjtalk.js is missing');
  });

  it('types/index.d.ts exists', () => {
    const dtsPath = join(PROJECT_ROOT, 'types', 'index.d.ts');
    assert.ok(existsSync(dtsPath), 'types/index.d.ts is missing');
  });

  it('dist/espeak-ng/ is NOT included in files', () => {
    const hasEspeakNg = pkg.files.some((entry) => {
      // Check for any pattern that would match dist/espeak-ng/
      return (
        entry === 'dist/espeak-ng/' ||
        entry === 'dist/espeak-ng' ||
        entry === 'dist/espeak-ng/**' ||
        entry === 'dist/**'
      );
    });

    assert.ok(
      !hasEspeakNg,
      'files should NOT include dist/espeak-ng/ (GPL license risk)',
    );
  });
});

// ---------------------------------------------------------------------------
// 4. Package size estimate
// ---------------------------------------------------------------------------

describe('package size estimate', () => {
  const MAX_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB

  it('total size of files entries is under 10 MB', () => {
    let totalBytes = 0;
    const sizeBreakdown = [];

    for (const entry of pkg.files) {
      const expanded = expandFilesEntry(entry);
      let entrySize = 0;
      for (const filePath of expanded) {
        try {
          entrySize += statSync(filePath).size;
        } catch {
          // File may not exist yet -- skip silently (covered by test 3).
        }
      }
      totalBytes += entrySize;
      if (entrySize > 0) {
        sizeBreakdown.push(
          `  ${entry}: ${(entrySize / 1024).toFixed(1)} KB`,
        );
      }
    }

    const totalMB = (totalBytes / (1024 * 1024)).toFixed(2);
    const detail = [
      `Total: ${totalMB} MB (limit: 10 MB)`,
      ...sizeBreakdown,
    ].join('\n');

    assert.ok(
      totalBytes <= MAX_SIZE_BYTES,
      `Package is too large (${totalMB} MB > 10 MB).\n${detail}`,
    );
  });
});
