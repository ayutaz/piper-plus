/**
 * npm package integration tests
 *
 * Validates that the piper-plus package metadata, exports, file listings,
 * and size constraints are consistent and correct before publishing.
 *
 * Run: node --test test/js/test-npm-package.js
 */

import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
import { readFileSync, existsSync, statSync, readdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

/** Project root: src/wasm/openjtalk-web/ */
const PROJECT_ROOT = resolve(__dirname, "..", "..");

/** Read and parse package.json once for all tests. */
const pkgPath = join(PROJECT_ROOT, "package.json");
const pkg = JSON.parse(readFileSync(pkgPath, "utf-8"));

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
  if (pattern.includes("**")) {
    const base = resolve(PROJECT_ROOT, pattern.split("**")[0]);
    if (!existsSync(base)) {
      return [];
    }
    const ext = pattern.split("*").pop(); // e.g. ".js"
    return walkDir(base).filter((f) => f.endsWith(ext));
  }

  // Directory entry (e.g. "types/")
  if (pattern.endsWith("/") || (existsSync(abs) && statSync(abs).isDirectory())) {
    if (!existsSync(abs)) {
      return [];
    }
    return walkDir(abs);
  }

  // Literal file
  if (existsSync(abs)) {
    return [abs];
  }
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
// 1. exports バリデーション
// ---------------------------------------------------------------------------

describe("exports バリデーション", () => {
  /** Expected named exports from the main entry point. */
  const EXPECTED_EXPORTS = [
    "PiperPlus",
    "AudioResult",
    "ModelManager",
    "WebGPUSessionManager",
    "StreamingTTSPipeline",
    "TextChunker",
    "CacheManager",
  ];

  it("メインエントリポイント (src/index.js) がインポートできる", async () => {
    const entryPath = resolve(PROJECT_ROOT, "src", "index.js");
    assert.ok(existsSync(entryPath), `Entry point does not exist: ${entryPath}`);

    // Convert to file:// URL for Windows compatibility with dynamic import().
    const mod = await import(pathToFileURL(entryPath).href);
    assert.ok(mod, "Module should be importable");
  });

  it("すべての期待されるシンボルがエクスポートされている", async () => {
    const entryPath = resolve(PROJECT_ROOT, "src", "index.js");
    const mod = await import(pathToFileURL(entryPath).href);
    const exportedNames = Object.keys(mod);

    for (const name of EXPECTED_EXPORTS) {
      assert.ok(
        exportedNames.includes(name),
        `Missing export: "${name}". Actual exports: [${exportedNames.join(", ")}]`
      );
    }
  });

  it("エクスポート名が index.js と型定義で一致する", async () => {
    const dtsPath = resolve(PROJECT_ROOT, "types", "index.d.ts");
    if (!existsSync(dtsPath)) {
      // Type definitions not yet created -- skip gracefully.
      return;
    }

    const dtsContent = readFileSync(dtsPath, "utf-8");
    const entryPath = resolve(PROJECT_ROOT, "src", "index.js");
    const mod = await import(pathToFileURL(entryPath).href);
    const exportedNames = Object.keys(mod);

    for (const name of exportedNames) {
      assert.ok(
        dtsContent.includes(name),
        `Export "${name}" is not referenced in types/index.d.ts.\n` +
          `\n` +
          `Numeric \`export const\` declarations from src/index.js are projected\n` +
          `into the AUTO-GENERATED block at the bottom of types/index.d.ts.\n` +
          `\n` +
          `Fix:\n` +
          `  npm run regenerate:types   # regenerate the auto-gen block\n` +
          `  npm run check:types        # verify drift in CI\n` +
          `\n` +
          `For non-numeric / function / class exports, add the declaration to\n` +
          `the manual section of types/index.d.ts (above the AUTO-GENERATED block)`
      );
    }
  });
});

// ---------------------------------------------------------------------------
// 2. package.json バリデーション
// ---------------------------------------------------------------------------

describe("package.json バリデーション", () => {
  it('パッケージ名が "piper-plus" である', () => {
    assert.equal(pkg.name, "piper-plus");
  });

  it("バージョンが semver 形式 (X.Y.Z) に従っている", () => {
    const semverRe = /^\d+\.\d+\.\d+(?:-[\w.]+)?(?:\+[\w.]+)?$/;
    assert.match(pkg.version, semverRe, `Version "${pkg.version}" does not match semver format`);
  });

  it('ライセンスが "MIT" である', () => {
    assert.equal(pkg.license, "MIT");
  });

  it('peerDependencies に "onnxruntime-web" が含まれている', () => {
    assert.ok(pkg.peerDependencies, "peerDependencies is missing");
    assert.ok(
      "onnxruntime-web" in pkg.peerDependencies,
      'peerDependencies should include "onnxruntime-web"'
    );
  });

  it('type が "module" である', () => {
    assert.equal(pkg.type, "module");
  });

  it("exports フィールドが存在する", () => {
    assert.ok(pkg.exports, "exports field is missing");
  });

  it("exports がオブジェクトである", () => {
    assert.ok(typeof pkg.exports === "object", "exports should be an object");
  });

  it('exports に "." エントリが存在する', () => {
    assert.ok(pkg.exports["."], 'exports should contain a "." entry');
  });

  it("files フィールドが定義されており配列である", () => {
    assert.ok(Array.isArray(pkg.files), "files should be an array");
    assert.ok(pkg.files.length > 0, "files should not be empty");
  });
});

// ---------------------------------------------------------------------------
// 2.1 subpath exports バリデーション
// ---------------------------------------------------------------------------

describe("subpath exports バリデーション", () => {
  it("./phonemizer サブパスエクスポートが定義されている", () => {
    assert.ok(pkg.exports["./phonemizer"], 'exports should contain a "./phonemizer" entry');
  });

  it("./phonemizer の参照先ファイルが存在する", () => {
    const importPath = pkg.exports["./phonemizer"].import;
    assert.ok(importPath, './phonemizer export should have an "import" field');
    const absPath = resolve(PROJECT_ROOT, importPath);
    assert.ok(existsSync(absPath), `./phonemizer import target does not exist: ${importPath}`);
  });

  it("./streaming サブパスエクスポートが定義されている", () => {
    assert.ok(pkg.exports["./streaming"], 'exports should contain a "./streaming" entry');
  });

  it("./streaming の参照先ファイルが存在する", () => {
    const importPath = pkg.exports["./streaming"].import;
    assert.ok(importPath, './streaming export should have an "import" field');
    const absPath = resolve(PROJECT_ROOT, importPath);
    assert.ok(existsSync(absPath), `./streaming import target does not exist: ${importPath}`);
  });
});

// ---------------------------------------------------------------------------
// 2.2 keywords バリデーション
// ---------------------------------------------------------------------------

describe("keywords バリデーション", () => {
  const ESSENTIAL_KEYWORDS = ["tts", "wasm", "japanese", "multilingual"];

  it("keywords フィールドが定義されており配列である", () => {
    assert.ok(Array.isArray(pkg.keywords), "keywords should be an array");
    assert.ok(pkg.keywords.length > 0, "keywords should not be empty");
  });

  for (const keyword of ESSENTIAL_KEYWORDS) {
    it(`必須キーワード "${keyword}" が含まれている`, () => {
      assert.ok(
        pkg.keywords.includes(keyword),
        `keywords should include "${keyword}". Actual: [${pkg.keywords.join(", ")}]`
      );
    });
  }
});

// ---------------------------------------------------------------------------
// 3. files フィールドバリデーション
// ---------------------------------------------------------------------------

describe("files フィールドバリデーション", () => {
  it("files エントリが既存のパスに解決される (build artifacts excluded)", () => {
    // dist/ entries are WASM build artifacts that only exist after
    // wasm-pack build.  Skip them so this test passes in CI without
    // a prior WASM build step.
    const BUILD_ARTIFACT_PREFIX = "dist/";
    const missing = [];

    for (const entry of pkg.files) {
      if (entry.startsWith(BUILD_ARTIFACT_PREFIX)) {
        continue;
      }
      const expanded = expandFilesEntry(entry);
      if (expanded.length === 0) {
        missing.push(entry);
      }
    }

    assert.deepEqual(
      missing,
      [],
      `The following files entries do not resolve to any existing path: ${missing.join(", ")}`
    );
  });

  it("types/index.d.ts が存在する", () => {
    const dtsPath = join(PROJECT_ROOT, "types", "index.d.ts");
    assert.ok(existsSync(dtsPath), "types/index.d.ts is missing");
  });

  it("dist/espeak-ng/ が files に含まれていない", () => {
    const hasEspeakNg = pkg.files.some((entry) => {
      // Check for any pattern that would match dist/espeak-ng/
      return (
        entry === "dist/espeak-ng/" ||
        entry === "dist/espeak-ng" ||
        entry === "dist/espeak-ng/**" ||
        entry === "dist/**"
      );
    });

    assert.ok(!hasEspeakNg, "files should NOT include dist/espeak-ng/ (GPL license risk)");
  });
});

// ---------------------------------------------------------------------------
// 4. パッケージサイズ見積もり
// ---------------------------------------------------------------------------

describe("パッケージサイズ見積もり", () => {
  const MAX_SIZE_BYTES = 100 * 1024 * 1024; // 100 MB (WASM binary with bundled NAIST-JDIC dict is ~57 MB)

  it("files エントリの合計サイズが 100 MB 以下である", () => {
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
        sizeBreakdown.push(`  ${entry}: ${(entrySize / 1024).toFixed(1)} KB`);
      }
    }

    const totalMB = (totalBytes / (1024 * 1024)).toFixed(2);
    const detail = [`Total: ${totalMB} MB (limit: 100 MB)`, ...sizeBreakdown].join("\n");

    assert.ok(
      totalBytes <= MAX_SIZE_BYTES,
      `Package is too large (${totalMB} MB > 100 MB).\n${detail}`
    );
  });
});

// ---------------------------------------------------------------------------
// 7. exports↔files 整合バリデーション
// ---------------------------------------------------------------------------

/**
 * Normalise a `files` entry or an exports target to a comparable path.
 * Strips a leading "./" and any trailing slashes.
 *
 * @param {string} p
 * @returns {string}
 */
function normPath(p) {
  return p.replace(/^\.\//, "").replace(/\/+$/, "");
}

/**
 * Decide whether a single `files` entry covers a concrete path.
 *
 * npm treats a bare directory entry as "include the whole directory" and `**`
 * as a recursive wildcard.  The property that matters here is that matching
 * happens on *path segment* boundaries: `dist/rust-wasm/**` must not cover
 * `dist/rust-wasm-ja/...`.  That distinction is exactly how `./wasm/ja` came
 * to be declared in `exports` while never being published (#301).
 *
 * @param {string} entry - one element of package.json `files`
 * @param {string} target - a concrete path relative to the package root
 * @returns {boolean}
 */
function filesEntryCovers(entry, target) {
  const e = normPath(entry);
  const t = normPath(target);

  const star = e.indexOf("**");
  if (star === -1) {
    return t === e || t.startsWith(e + "/");
  }

  const base = normPath(e.slice(0, star));
  const tail = e.slice(star + 2).replace(/^\//, "");

  if (base !== "" && !(t === base || t.startsWith(base + "/"))) {
    return false;
  }
  if (tail === "" || tail === "*") {
    return true;
  }
  if (tail.startsWith("*.")) {
    return t.endsWith(tail.slice(1));
  }
  return t === tail || t.endsWith("/" + tail);
}

/**
 * Flatten package.json `exports` into `{subpath, condition, target}` records.
 *
 * @param {object} exportsField
 * @returns {Array<{subpath: string, condition: string, target: string}>}
 */
function collectExportTargets(exportsField) {
  const out = [];
  for (const [subpath, value] of Object.entries(exportsField ?? {})) {
    if (typeof value === "string") {
      out.push({ subpath, condition: "default", target: value });
      continue;
    }
    for (const [condition, target] of Object.entries(value ?? {})) {
      if (typeof target === "string") {
        out.push({ subpath, condition, target });
      }
    }
  }
  return out;
}

describe("exports↔files 整合バリデーション", () => {
  it("files glob matcher が path segment 境界を守る", () => {
    const cases = [
      ["dist/rust-wasm/**", "dist/rust-wasm/piper_plus_wasm.js", true],
      ["dist/rust-wasm/**", "dist/rust-wasm", true],
      // 兄弟ディレクトリを飲み込まないこと。素朴な startsWith で書くとここが true になり、
      // 下の整合テストが緑のまま ./wasm/ja 相当の欠陥を見逃す。
      ["dist/rust-wasm/**", "dist/rust-wasm-ja/piper_plus_wasm.js", false],
      ["dist/rust-wasm/**", "dist/rust-wasm-ja-lite/piper_plus_wasm.js", false],
      ["src/**/*.js", "src/index.js", true],
      ["src/**/*.js", "src/phonemizer/rust-wasm-adapter.js", true],
      ["src/**/*.js", "src/index.mjs", false],
      ["types/", "types/index.d.ts", true],
      ["types/", "typesX/index.d.ts", false],
      ["LICENSE.md", "LICENSE.md", true],
    ];

    for (const [entry, target, expected] of cases) {
      assert.equal(
        filesEntryCovers(entry, target),
        expected,
        `filesEntryCovers(${JSON.stringify(entry)}, ${JSON.stringify(target)}) should be ${expected}`
      );
    }
  });

  it("全 exports target が files のいずれかにカバーされる", () => {
    const targets = collectExportTargets(pkg.exports);
    assert.ok(targets.length > 0, "exports should declare at least one target");

    const uncovered = targets
      .filter(({ target }) => !pkg.files.some((entry) => filesEntryCovers(entry, target)))
      .map(({ subpath, condition, target }) => `exports["${subpath}"].${condition} -> ${target}`);

    assert.deepEqual(
      uncovered,
      [],
      "Every exports target must be covered by a files entry; otherwise the subpath " +
        "is declared but never published (#301: ./wasm/ja shipped 0 files)."
    );
  });
});

// ---------------------------------------------------------------------------
// 8. scripts フィールドバリデーション
// ---------------------------------------------------------------------------

/**
 * Extract repo-local shell scripts invoked by an npm script.
 *
 * Matches `./foo.sh` and `foo/bar.sh`, resolved relative to an optional
 * leading `cd <dir> &&`.
 *
 * @param {string} command
 * @returns {string[]} paths relative to the package root
 */
function localShellScripts(command) {
  const cdMatch = command.match(/^cd\s+([^\s&|;]+)\s*&&\s*/);
  const base = cdMatch ? cdMatch[1] : "";
  const body = cdMatch ? command.slice(cdMatch[0].length) : command;

  const found = [];
  for (const m of body.matchAll(/(?:^|[\s&|;])(\.\/)?([\w./-]+\.sh)\b/g)) {
    found.push(base ? `${base}/${m[2]}` : m[2]);
  }
  return found;
}

describe("scripts フィールドバリデーション", () => {
  it("npm script が参照するローカルシェルスクリプトが実在する", () => {
    const broken = [];
    for (const [name, command] of Object.entries(pkg.scripts ?? {})) {
      for (const rel of localShellScripts(command)) {
        if (!existsSync(join(PROJECT_ROOT, rel))) {
          broken.push(`${name}: ${rel}`);
        }
      }
    }

    assert.deepEqual(
      broken,
      [],
      "An npm script pointing at a missing shell script fails only when someone " +
        "runs it, so it can rot indefinitely."
    );
  });

  it("clean スクリプトが git 追跡下のパスを削除しない", () => {
    const clean = pkg.scripts?.clean;
    assert.ok(typeof clean === "string", "a clean script should exist");

    // Expand each `rm -rf` target as a shell glob and check the results
    // against the index. `rm -rf dist build/build-*` used to match three
    // tracked build scripts, so `npm run clean` deleted source files.
    const tracked = new Set(
      execFileSync("git", ["ls-files"], { cwd: PROJECT_ROOT, encoding: "utf-8" })
        .split("\n")
        .filter(Boolean)
    );

    const targets = clean
      .replace(/^rm\s+(-\w+\s+)*/, "")
      .split(/\s+/)
      .filter(Boolean);

    const destroyed = [];
    for (const target of targets) {
      const dir = target.includes("/") ? target.slice(0, target.lastIndexOf("/")) : ".";
      const pattern = target.includes("/") ? target.slice(target.lastIndexOf("/") + 1) : target;
      const absDir = join(PROJECT_ROOT, dir);
      if (!existsSync(absDir)) continue;

      const rx = new RegExp("^" + pattern.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*") + "$");
      for (const name of readdirSync(absDir)) {
        if (!rx.test(name)) continue;
        const rel = dir === "." ? name : `${dir}/${name}`;
        if (tracked.has(rel)) destroyed.push(rel);
      }
    }

    assert.deepEqual(
      destroyed,
      [],
      `\`npm run clean\` would delete git-tracked files: ${destroyed.join(", ")}`
    );
  });
});
