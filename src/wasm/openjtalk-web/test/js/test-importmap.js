/**
 * Import map validation tests
 *
 * Ensures every HTML demo page that loads ES modules with bare specifiers
 * (e.g. "@piper-plus/g2p") has a matching <script type="importmap"> entry,
 * and that each such specifier is mapped in BARE_SPECIFIER_SOURCE_MAP to a
 * corresponding source-tree file that exists on disk.
 *
 * Run: node --test test/js/test-importmap.js
 */

import { strict as assert } from 'node:assert';
import { describe, it } from 'node:test';
import { readFileSync, existsSync, readdirSync } from 'node:fs';
import { join, resolve, dirname, basename } from 'node:path';
import { fileURLToPath } from 'node:url';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

/** Project root: src/wasm/openjtalk-web/ */
const PROJECT_ROOT = resolve(__dirname, '..', '..');

/** Directory containing source JS modules that will be loaded in-browser. */
const SRC_DIR = join(PROJECT_ROOT, 'src');

/** Demo HTML directory */
const DEMO_DIR = join(PROJECT_ROOT, 'test', 'multilingual-demo');

/**
 * Known bare-specifier → source-tree package root mapping.
 * Import map paths are written for the *deployed* directory layout, so they
 * don't resolve correctly relative to the source tree.  This map lets us
 * verify the underlying package file actually exists.
 */
const BARE_SPECIFIER_SOURCE_MAP = {
  '@piper-plus/g2p': resolve(PROJECT_ROOT, '..', 'g2p', 'src', 'index.js'),
};

/**
 * Extract bare module specifiers (npm-style, starting with @ or a letter,
 * not relative ./ or ../) from ES module import statements in a JS file.
 *
 * @param {string} filePath
 * @returns {string[]} Unique bare specifiers
 */
function extractBareSpecifiers(filePath) {
  const content = readFileSync(filePath, 'utf-8');
  const specifiers = new Set();

  // Match: import ... from 'specifier'  or  import ... from "specifier"
  // Also match: export ... from 'specifier'
  const importRegex = /(?:import|export)\s+.*?\s+from\s+['"]([^'"]+)['"]/g;
  // Match: import 'specifier' (side-effect imports)
  const sideEffectRegex = /import\s+['"]([^'"]+)['"]/g;

  for (const regex of [importRegex, sideEffectRegex]) {
    let match;
    while ((match = regex.exec(content)) !== null) {
      const specifier = match[1];
      // Bare specifiers don't start with . or /
      if (!specifier.startsWith('.') && !specifier.startsWith('/')) {
        specifiers.add(specifier);
      }
    }
  }

  return [...specifiers];
}

/**
 * Parse import map entries from an HTML file.
 *
 * @param {string} htmlPath
 * @returns {{ imports: Record<string, string> } | null}
 */
function parseImportMap(htmlPath) {
  const content = readFileSync(htmlPath, 'utf-8');
  const match = content.match(/<script\s+type=["']importmap["']\s*>([\s\S]*?)<\/script>/);
  if (!match) return null;
  try {
    return JSON.parse(match[1]);
  } catch {
    return null;
  }
}

/**
 * Collect all HTML files in a directory (non-recursive).
 *
 * @param {string} dir
 * @returns {string[]}
 */
function htmlFiles(dir) {
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter((f) => f.endsWith('.html'))
    .map((f) => join(dir, f));
}

/**
 * Collect all JS files in a directory (non-recursive).
 *
 * @param {string} dir
 * @returns {string[]}
 */
function jsFiles(dir) {
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter((f) => f.endsWith('.js'))
    .map((f) => join(dir, f));
}

// ---------------------------------------------------------------------------
// Collect bare specifiers required by all src/*.js modules
// ---------------------------------------------------------------------------

const allBareSpecifiers = new Set();
for (const jsFile of jsFiles(SRC_DIR)) {
  for (const spec of extractBareSpecifiers(jsFile)) {
    allBareSpecifiers.add(spec);
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Import map coverage', () => {
  it('src/*.js files use at least one bare specifier (sanity check)', () => {
    assert.ok(
      allBareSpecifiers.size > 0,
      'Expected at least one bare module specifier in src/*.js — ' +
        'if none exist, this test suite can be removed'
    );
  });

  const htmlPaths = htmlFiles(DEMO_DIR);

  it('demo directory contains HTML files', () => {
    assert.ok(htmlPaths.length > 0, `No HTML files found in ${DEMO_DIR}`);
  });

  for (const htmlPath of htmlPaths) {
    const fileName = basename(htmlPath);

    // Only test HTML files that actually import from src/ (i.e. use ES modules)
    const htmlContent = existsSync(htmlPath) ? readFileSync(htmlPath, 'utf-8') : '';
    const usesModules = htmlContent.includes('type="module"') || htmlContent.includes("type='module'");
    if (!usesModules) continue;

    // Check if this HTML imports from src/ (directly or indirectly)
    const importsSrc =
      htmlContent.includes('/src/index.js') ||
      htmlContent.includes('/src/phonemizer-compat.js');
    if (!importsSrc) continue;

    describe(`${fileName}`, () => {
      it('has a <script type="importmap"> block', () => {
        const importMap = parseImportMap(htmlPath);
        assert.ok(importMap, `${fileName} is missing <script type="importmap">`);
        assert.ok(importMap.imports, `${fileName} import map has no "imports" key`);
      });

      it('covers all bare module specifiers used by src/*.js', () => {
        const importMap = parseImportMap(htmlPath);
        assert.ok(importMap, `${fileName} is missing import map`);

        const missing = [];
        for (const specifier of allBareSpecifiers) {
          if (!(specifier in importMap.imports)) {
            missing.push(specifier);
          }
        }

        assert.strictEqual(
          missing.length,
          0,
          `${fileName} import map is missing entries for: ${missing.join(', ')}`
        );
      });

      it('import map targets point to packages that exist in source tree', () => {
        const importMap = parseImportMap(htmlPath);
        assert.ok(importMap, `${fileName} is missing import map`);

        const broken = [];
        for (const specifier of Object.keys(importMap.imports)) {
          // Import map paths are for the deployed layout, so we verify
          // against the known source-tree location instead.
          const sourcePath = BARE_SPECIFIER_SOURCE_MAP[specifier];
          if (!sourcePath) {
            broken.push(
              `${specifier} — no entry in BARE_SPECIFIER_SOURCE_MAP (add one)`
            );
          } else if (!existsSync(sourcePath)) {
            broken.push(`${specifier} -> ${sourcePath} (file not found)`);
          }
        }

        assert.strictEqual(
          broken.length,
          0,
          `${fileName} has import map entries pointing to missing packages:\n  ${broken.join('\n  ')}`
        );
      });
    });
  }
});
