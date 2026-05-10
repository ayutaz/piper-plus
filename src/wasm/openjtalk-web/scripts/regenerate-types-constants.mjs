#!/usr/bin/env node
// SPDX-License-Identifier: MIT
//
// Regenerate the auto-generated constants block of types/index.d.ts from
// `export const NAME = VALUE` declarations in src/index.js.
//
// Design contract:
//   * src/index.js は public API の Single Source of Truth。
//     `export const` で公開された数値定数は、ここから抽出して
//     types/index.d.ts に projection する (ort_session/contract.json と
//     同様のパターン)。
//   * types/index.d.ts には `// AUTO-GENERATED CONSTANTS START/END` で
//     囲まれたブロックを 1 つだけ置き、その中身が完全に置換される。
//     ブロック外 (interface / class / 型情報) は手動編集領域。
//
// Modes:
//   * (no flag)  -> types/index.d.ts を再生成して書き戻す
//   * --check    -> 現在の types/index.d.ts と再生成結果を比較し、drift があれば
//                   exit 1。CI drift gate 用。
//
// Why this exists:
//   過去 PR #401 で WARMUP_BOS_TOKEN を追加した際 types/index.d.ts への
//   反映漏れで test-openjtalk-web が落ちた。原因は src exports と
//   types/index.d.ts の二重管理。本スクリプトはこの構造的負債を解消する。

import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = resolve(__dirname, '..');
const SRC_INDEX = resolve(PROJECT_ROOT, 'src', 'index.js');
const TYPES_INDEX = resolve(PROJECT_ROOT, 'types', 'index.d.ts');

const BLOCK_START = '// AUTO-GENERATED CONSTANTS START — do not edit by hand';
const BLOCK_END = '// AUTO-GENERATED CONSTANTS END';

// Per-constant TSDoc descriptions. Keyed by export name. Falls back to a
// generic note if a new constant is added without an entry here.
const DESCRIPTIONS = {
  // ORT session contract (cross-runtime parity with Py/Rust/Go/C#/C++)
  WARMUP_PHONEME_LENGTH: 'Phoneme sequence length used by warmup runs (excludes BOS/EOS).',
  WARMUP_BOS_TOKEN: 'BOS token id seeded into warmup phoneme sequences.',
  WARMUP_EOS_TOKEN: 'EOS token id seeded into warmup phoneme sequences.',
  WARMUP_DUMMY_PHONEME: 'Phoneme id used to fill warmup phoneme positions between BOS/EOS.',
  WARMUP_DEFAULT_RUNS: 'Default number of warmup runs after session creation.',
  WARMUP_NOISE_SCALE: 'noise_scale value used in warmup forward passes.',
  WARMUP_LENGTH_SCALE: 'length_scale value used in warmup forward passes.',
  WARMUP_NOISE_W: 'noise_w value used in warmup forward passes.',

  // Short-text contract (cross-runtime parity)
  MIN_PHONEME_IDS: 'Minimum total phoneme-id sequence length before Strategy A padding kicks in.',
  MIN_BODY_FOR_STRATEGY_A: 'Minimum body length required to apply Strategy A padding.',
  TRIM_EOS_MAX_FRAMES: 'Maximum number of trailing frames trimmed when collapsing EOS silence.',

  // Audio / VITS
  DEFAULT_HOP_SIZE: 'STFT hop length used by VITS medium-quality models (alias of DEFAULT_HOP_LENGTH).',
};

const GENERIC_DESCRIPTION = (name) =>
  `Numeric constant exported from src/index.js. See source for canonical value.`;

/**
 * Parse `export const NAME = ...;` declarations from src/index.js.
 * Captures: name, RHS expression (for type inference).
 * Skips lines that are commented out.
 */
function parseExports(source) {
  const re = /^\s*export\s+const\s+([A-Za-z_$][\w$]*)\s*=\s*(.+?);?\s*$/gm;
  const out = [];
  for (const m of source.matchAll(re)) {
    out.push({ name: m[1], rhs: m[2].trim() });
  }
  return out;
}

/**
 * Heuristic type inference from RHS expression. Returns a TypeScript type
 * string. We keep this conservative: integers / floats / aliases all become
 * `number` (which is what the existing types/index.d.ts uses for every
 * numeric constant). String literals -> `string`. Boolean -> `boolean`.
 */
function inferType(rhs) {
  if (/^['"`].*['"`]$/.test(rhs)) return 'string';
  if (/^(true|false)$/.test(rhs)) return 'boolean';
  // Numeric literal, arithmetic, alias of another numeric const.
  return 'number';
}

function renderBlock(exportEntries) {
  const lines = [];
  lines.push(BLOCK_START);
  lines.push('//');
  lines.push('// Generated from src/index.js by scripts/regenerate-types-constants.mjs');
  lines.push('// To update: edit src/index.js, then run `npm run regenerate:types`.');
  lines.push('// CI gates this via `npm run check:types` in test-webassembly.yml.');
  lines.push('');

  for (const { name, rhs } of exportEntries) {
    const desc = DESCRIPTIONS[name] || GENERIC_DESCRIPTION(name);
    const type = inferType(rhs);
    lines.push('/** ' + desc + ' */');
    lines.push(`export const ${name}: ${type};`);
    lines.push('');
  }

  lines.push(BLOCK_END);
  return lines.join('\n');
}

function replaceBlock(typesContent, newBlock) {
  const startIdx = typesContent.indexOf(BLOCK_START);
  const endIdx = typesContent.indexOf(BLOCK_END);
  if (startIdx === -1 || endIdx === -1) {
    throw new Error(
      `types/index.d.ts is missing the ${BLOCK_START} ... ${BLOCK_END} markers.\n` +
        'Add them once (anywhere in the file) and rerun this script.',
    );
  }
  if (endIdx < startIdx) {
    throw new Error('AUTO-GENERATED block markers are out of order in types/index.d.ts.');
  }
  const before = typesContent.slice(0, startIdx);
  const after = typesContent.slice(endIdx + BLOCK_END.length);
  return before + newBlock + after;
}

function main() {
  const checkMode = process.argv.includes('--check');

  const sourceContent = readFileSync(SRC_INDEX, 'utf-8');
  const entries = parseExports(sourceContent);
  if (entries.length === 0) {
    throw new Error('No `export const NAME = ...` declarations found in src/index.js');
  }
  entries.sort((a, b) => a.name.localeCompare(b.name));

  const typesContent = readFileSync(TYPES_INDEX, 'utf-8');
  const newBlock = renderBlock(entries);
  const newTypesContent = replaceBlock(typesContent, newBlock);

  if (checkMode) {
    if (newTypesContent !== typesContent) {
      process.stderr.write(
        'types/index.d.ts is out of sync with src/index.js exports.\n' +
          'Run `npm run regenerate:types` to fix.\n\n' +
          `Found ${entries.length} const exports in src/index.js:\n` +
          entries.map((e) => `  - ${e.name}`).join('\n') +
          '\n',
      );
      process.exit(1);
    }
    process.stdout.write(
      `types/index.d.ts is in sync with ${entries.length} const exports.\n`,
    );
    return;
  }

  if (newTypesContent === typesContent) {
    process.stdout.write(
      `types/index.d.ts already up to date (${entries.length} const exports).\n`,
    );
    return;
  }
  writeFileSync(TYPES_INDEX, newTypesContent, 'utf-8');
  process.stdout.write(
    `Regenerated types/index.d.ts AUTO-GENERATED block (${entries.length} const exports).\n`,
  );
}

main();
