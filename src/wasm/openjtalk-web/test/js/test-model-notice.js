/**
 * Model usage notice (docs/reference/model-resolution.md §9)
 *
 * テスト対象:
 *   - src/model-manager.js: getModelNotice / isModelNoticeDisabled /
 *     emitModelNotice / ModelManager.resolveUrls().notice / loadModel()
 *   - src/index.js: PiperPlus.initialize() の console.warn 表示
 *   - bin/piper-cli.js: --model のファイル名で stderr に表示
 *
 * 案内文の正本は test/model_resolution_vectors.json の voice_catalog.<key>.notice。
 * ネットワークには出ない (fetch / indexedDB はモック)。
 */

import assert from "node:assert/strict";
import { describe, it, beforeEach, afterEach } from "node:test";
import { spawnSync } from "node:child_process";
import { readFileSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  ModelManager,
  MODEL_NOTICE_FOOTER,
  emitModelNotice,
  getModelNotice,
  isModelNoticeDisabled,
  _resetModelNoticeState,
} from "../../src/model-manager.js";
import * as packageRoot from "../../src/index.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "../../../../..");
const BIN = resolve(__dirname, "../../bin/piper-cli.js");
const VECTORS = JSON.parse(
  readFileSync(join(REPO_ROOT, "test/model_resolution_vectors.json"), "utf8")
);
const TSUKUYOMI = VECTORS.voice_catalog["ja_JP-tsukuyomi-chan-medium"];
const REPO_ID = TSUKUYOMI.repo_id;
const ENV_NAME = "PIPER_PLUS_DISABLE_MODEL_NOTICE";

/** Run fn with console.warn captured; returns the captured messages. */
async function captureWarnings(fn) {
  const warnings = [];
  const origWarn = console.warn;
  console.warn = (...args) => warnings.push(args.join(" "));
  try {
    await fn();
  } finally {
    console.warn = origWarn;
  }
  return warnings;
}

/** Save and clear the opt-out env var around each test. */
function useCleanEnv() {
  let saved;
  beforeEach(() => {
    saved = process.env[ENV_NAME];
    delete process.env[ENV_NAME];
    _resetModelNoticeState();
  });
  afterEach(() => {
    if (saved === undefined) {
      delete process.env[ENV_NAME];
    } else {
      process.env[ENV_NAME] = saved;
    }
    _resetModelNoticeState();
  });
}

function mockFetch(routes) {
  return async (url) => {
    for (const [pattern, body] of routes) {
      if (pattern.test(url)) {
        return {
          ok: true,
          status: 200,
          statusText: "OK",
          headers: new Map(),
          json: () => Promise.resolve(body),
          arrayBuffer: () => Promise.resolve(new ArrayBuffer(64)),
          body: null,
        };
      }
    }
    return { ok: false, status: 404, statusText: "Not Found" };
  };
}

function installIndexedDB() {
  const store = new Map();
  const wrap = (result) => {
    const req = { result, error: null, onsuccess: null, onerror: null };
    globalThis.queueMicrotask(() => req.onsuccess?.());
    return req;
  };
  const db = {
    transaction() {
      return {
        objectStore() {
          return {
            get: (key) => wrap(store.get(key)),
            put: (value, key) => {
              store.set(key, value);
              return wrap(undefined);
            },
          };
        },
      };
    },
  };
  globalThis.indexedDB = {
    open() {
      const req = { result: db, error: null, onsuccess: null, onerror: null };
      globalThis.queueMicrotask(() => req.onsuccess?.());
      return req;
    },
  };
}

// ---------------------------------------------------------------------------
// 1. 正本との一致
// ---------------------------------------------------------------------------

describe("model notice: canonical text", () => {
  it("tsukuyomi の案内文が test/model_resolution_vectors.json と一致する", () => {
    assert.deepEqual([...getModelNotice(REPO_ID)], TSUKUYOMI.notice);
  });

  it("notice_files のどれもが判定に当たる", () => {
    for (const name of TSUKUYOMI.notice_files) {
      assert.deepEqual([...getModelNotice(name)], TSUKUYOMI.notice, name);
    }
  });

  it("消し方の行が全ランタイム共通の文言である", () => {
    assert.equal(
      MODEL_NOTICE_FOOTER,
      "(この表示は PIPER_PLUS_DISABLE_MODEL_NOTICE=1 で消せます / Set PIPER_PLUS_DISABLE_MODEL_NOTICE=1 to hide this notice.)"
    );
  });

  it("package root から getModelNotice と MODEL_NOTICE_FOOTER を使える", () => {
    assert.equal(packageRoot.getModelNotice, getModelNotice);
    assert.equal(packageRoot.MODEL_NOTICE_FOOTER, MODEL_NOTICE_FOOTER);
  });
});

// ---------------------------------------------------------------------------
// 2. 判定表
// ---------------------------------------------------------------------------

describe("model notice: getModelNotice() detection", () => {
  const HITS = [
    ["alias tsukuyomi", "tsukuyomi"],
    ["alias tsukuyomi-chan", "tsukuyomi-chan"],
    ["alias ja-tsukuyomi", "ja-tsukuyomi"],
    ["catalog key", "ja_JP-tsukuyomi-chan-medium"],
    ["repo id", REPO_ID],
    [
      "HF resolve URL",
      `https://huggingface.co/${REPO_ID}/resolve/main/tsukuyomi-chan-6lang-fp16.onnx`,
    ],
    [
      "HF pinned URL",
      `https://huggingface.co/${REPO_ID}/resolve/93c1fb6d67c29accc9ddf52326bb4582b1b52a3d/releases/zs-v1/tsukuyomi.onnx`,
    ],
    ["URL with query", "https://cdn.example.com/models/tsukuyomi.onnx?download=true"],
    ["POSIX path", "/models/tsukuyomi-chan-6lang-fp16.onnx"],
    ["relative path", "models/tsukuyomi.onnx"],
    ["Windows path", "C:\\models\\tsukuyomi.onnx"],
    ["bare file name", "tsukuyomi-chan-6lang-fp16.onnx"],
  ];
  for (const [label, input] of HITS) {
    it(`当たる: ${label} (${input})`, () => {
      assert.deepEqual([...(getModelNotice(input) ?? [])], TSUKUYOMI.notice);
    });
  }

  const MISSES = [
    ["css10 alias", "css10"],
    ["css10-ja alias", "css10-ja"],
    ["css10 repo id", "ayousanz/piper-plus-css10-ja-6lang"],
    [
      "css10 URL",
      "https://huggingface.co/ayousanz/piper-plus-css10-ja-6lang/resolve/main/model.onnx",
    ],
    ["public base alias", "base"],
    ["public base repo", "ayousanz/piper-plus-base"],
    ["other onnx", "/models/model.onnx"],
    ["file name that only contains tsukuyomi", "/models/my-tsukuyomi.onnx"],
    ["repo id as a prefix only", `${REPO_ID}-fork`],
    ["case differs", "Tsukuyomi"],
    ["empty", ""],
  ];
  for (const [label, input] of MISSES) {
    it(`当たらない: ${label} (${JSON.stringify(input)})`, () => {
      assert.equal(getModelNotice(input), null);
    });
  }

  it("文字列以外は null", () => {
    assert.equal(getModelNotice(undefined), null);
    assert.equal(getModelNotice(null), null);
    assert.equal(getModelNotice(42), null);
  });
});

// ---------------------------------------------------------------------------
// 3. 環境変数
// ---------------------------------------------------------------------------

describe("model notice: isModelNoticeDisabled()", () => {
  for (const value of ["1", "true", "TRUE", "Yes", " yes ", "\ttrue\n"]) {
    it(`${JSON.stringify(value)} で無効`, () => {
      assert.equal(isModelNoticeDisabled({ [ENV_NAME]: value }), true);
    });
  }
  for (const value of ["", "0", "false", "no", "on", "2"]) {
    it(`${JSON.stringify(value)} では無効にならない`, () => {
      assert.equal(isModelNoticeDisabled({ [ENV_NAME]: value }), false);
    });
  }
  it("env が無い (ブラウザ相当) ときは無効にならない", () => {
    assert.equal(isModelNoticeDisabled(undefined), false);
    assert.equal(isModelNoticeDisabled({}), false);
  });
});

// ---------------------------------------------------------------------------
// 4. 表示 (console.warn, 1 回だけ)
// ---------------------------------------------------------------------------

describe("model notice: emitModelNotice()", () => {
  useCleanEnv();

  it("案内文の各行と消し方の行を console.warn で 1 回だけ出す", async () => {
    const notice = getModelNotice("tsukuyomi");
    const warnings = await captureWarnings(() => {
      assert.equal(emitModelNotice(notice), true);
      assert.equal(emitModelNotice(notice), false);
      assert.equal(emitModelNotice(getModelNotice(REPO_ID)), false);
    });
    assert.equal(warnings.length, 1);
    assert.deepEqual(warnings[0].split("\n"), [...TSUKUYOMI.notice, MODEL_NOTICE_FOOTER]);
  });

  it("showModelNotice: false では出さず、後の表示も妨げない", async () => {
    const notice = getModelNotice("tsukuyomi");
    const warnings = await captureWarnings(() => {
      assert.equal(emitModelNotice(notice, { showModelNotice: false }), false);
    });
    assert.equal(warnings.length, 0);
    const later = await captureWarnings(() => emitModelNotice(notice));
    assert.equal(later.length, 1);
  });

  it("PIPER_PLUS_DISABLE_MODEL_NOTICE=1 では出さない", async () => {
    process.env[ENV_NAME] = "1";
    const warnings = await captureWarnings(() => {
      assert.equal(emitModelNotice(getModelNotice("tsukuyomi")), false);
    });
    assert.equal(warnings.length, 0);
  });

  it("notice が null / 空なら何も出さない", async () => {
    const warnings = await captureWarnings(() => {
      assert.equal(emitModelNotice(null), false);
      assert.equal(emitModelNotice(getModelNotice("css10")), false);
      assert.equal(emitModelNotice([]), false);
    });
    assert.equal(warnings.length, 0);
  });

  it("logger を渡すとそちらに出す", () => {
    const lines = [];
    emitModelNotice(getModelNotice("tsukuyomi"), { logger: (m) => lines.push(m) });
    assert.equal(lines.length, 1);
    assert.ok(lines[0].endsWith(MODEL_NOTICE_FOOTER));
  });
});

// ---------------------------------------------------------------------------
// 5. ModelManager
// ---------------------------------------------------------------------------

describe("model notice: ModelManager", () => {
  useCleanEnv();
  let origFetch;
  let origIndexedDB;

  beforeEach(() => {
    origFetch = globalThis.fetch;
    origIndexedDB = globalThis.indexedDB;
    installIndexedDB();
  });
  afterEach(() => {
    globalThis.fetch = origFetch;
    globalThis.indexedDB = origIndexedDB;
  });

  const config = { audio: { sample_rate: 22050 } };

  it("resolveUrls() の notice: 直接 URL", async () => {
    const mgr = new ModelManager();
    const tsukuyomi = await mgr.resolveUrls(
      `https://huggingface.co/${REPO_ID}/resolve/main/tsukuyomi-chan-6lang-fp16.onnx`
    );
    assert.deepEqual([...tsukuyomi.notice], TSUKUYOMI.notice);
    const other = await mgr.resolveUrls("https://example.com/model.onnx");
    assert.equal(other.notice, null);
  });

  it("resolveUrls() の notice: alias は HF API 経由で解決しても付く", async () => {
    globalThis.fetch = mockFetch([
      [
        /huggingface\.co\/api\/models\/ayousanz\/piper-plus-tsukuyomi-chan$/,
        {
          siblings: [{ rfilename: "tsukuyomi-chan-6lang-fp16.onnx" }, { rfilename: "config.json" }],
        },
      ],
      [
        /huggingface\.co\/api\/models\/ayousanz\/piper-plus-css10-ja-6lang$/,
        { siblings: [{ rfilename: "model.onnx" }, { rfilename: "config.json" }] },
      ],
    ]);
    const mgr = new ModelManager();
    const warnings = await captureWarnings(async () => {
      const tsukuyomi = await mgr.resolveUrls("tsukuyomi");
      assert.deepEqual([...tsukuyomi.notice], TSUKUYOMI.notice);
      const css10 = await mgr.resolveUrls("css10");
      assert.equal(css10.notice, null);
    });
    // resolveUrls() は結果を返すだけで表示しない。
    assert.equal(warnings.length, 0);
  });

  it("resolveUrls() の notice: public base は null", async () => {
    const mgr = new ModelManager();
    assert.equal((await mgr.resolveUrls("base")).notice, null);
  });

  it("loadModel() は notice を返し、console.warn で 1 回だけ出す (cache hit でも返す)", async () => {
    const url = `https://huggingface.co/${REPO_ID}/resolve/main/tsukuyomi-chan-6lang-fp16.onnx`;
    globalThis.fetch = mockFetch([
      [/\.onnx\.json$/, config],
      [/\.onnx$/, null],
    ]);
    const mgr = new ModelManager();
    let first;
    let second;
    const warnings = await captureWarnings(async () => {
      first = await mgr.loadModel(url);
      second = await mgr.loadModel(url); // cache hit
    });
    assert.deepEqual([...first.notice], TSUKUYOMI.notice);
    assert.deepEqual([...second.notice], TSUKUYOMI.notice);
    assert.equal(warnings.length, 1);
    assert.deepEqual(warnings[0].split("\n"), [...TSUKUYOMI.notice, MODEL_NOTICE_FOOTER]);
  });

  it("loadModel(): showModelNotice: false では出さないが notice は返す", async () => {
    globalThis.fetch = mockFetch([
      [/\.onnx\.json$/, config],
      [/\.onnx$/, null],
    ]);
    const mgr = new ModelManager({ showModelNotice: false });
    let result;
    const warnings = await captureWarnings(async () => {
      result = await mgr.loadModel("https://example.com/tsukuyomi.onnx");
    });
    assert.equal(warnings.length, 0);
    assert.deepEqual([...result.notice], TSUKUYOMI.notice);
  });

  it("loadModel(): PIPER_PLUS_DISABLE_MODEL_NOTICE=true では出さない", async () => {
    process.env[ENV_NAME] = " TRUE ";
    globalThis.fetch = mockFetch([
      [/\.onnx\.json$/, config],
      [/\.onnx$/, null],
    ]);
    const mgr = new ModelManager();
    const warnings = await captureWarnings(() =>
      mgr.loadModel("https://example.com/tsukuyomi.onnx")
    );
    assert.equal(warnings.length, 0);
  });

  it("loadModel(): 案内のないモデルでは notice が null で何も出さない", async () => {
    globalThis.fetch = mockFetch([
      [/\.onnx\.json$/, config],
      [/\.onnx$/, null],
    ]);
    const mgr = new ModelManager();
    let result;
    const warnings = await captureWarnings(async () => {
      result = await mgr.loadModel("https://example.com/model.onnx");
    });
    assert.equal(result.notice, null);
    assert.equal(warnings.length, 0);
  });
});

// ---------------------------------------------------------------------------
// 6. PiperPlus.initialize()
// ---------------------------------------------------------------------------

describe("model notice: PiperPlus.initialize()", () => {
  useCleanEnv();
  let origFetch;

  beforeEach(() => {
    origFetch = globalThis.fetch;
    // config の取得で止める: 表示は resolve 直後なので、その先は不要。
    globalThis.fetch = async () => ({ ok: false, status: 500, statusText: "stop" });
  });
  afterEach(() => {
    globalThis.fetch = origFetch;
  });

  async function initAndCapture(options) {
    return captureWarnings(async () => {
      await assert.rejects(
        packageRoot.PiperPlus.initialize({ ort: {}, ...options }),
        /Failed to fetch config/
      );
    });
  }

  it("tsukuyomi の URL で console.warn を 1 回出す", async () => {
    const warnings = await initAndCapture({
      model: `https://huggingface.co/${REPO_ID}/resolve/main/tsukuyomi-chan-6lang-fp16.onnx`,
    });
    assert.equal(warnings.length, 1);
    assert.deepEqual(warnings[0].split("\n"), [...TSUKUYOMI.notice, MODEL_NOTICE_FOOTER]);
    // 同じページで 2 回目の initialize では出さない。
    const again = await initAndCapture({ model: "https://example.com/tsukuyomi.onnx" });
    assert.equal(again.length, 0);
  });

  it("showModelNotice: false で出さない", async () => {
    const warnings = await initAndCapture({
      model: "https://example.com/tsukuyomi.onnx",
      showModelNotice: false,
    });
    assert.equal(warnings.length, 0);
  });

  it("PIPER_PLUS_DISABLE_MODEL_NOTICE=yes で出さない", async () => {
    process.env[ENV_NAME] = "yes";
    const warnings = await initAndCapture({ model: "https://example.com/tsukuyomi.onnx" });
    assert.equal(warnings.length, 0);
  });

  it("resolveUrls() を差し替えて notice が無くても、入力名から判定する", async () => {
    const orig = ModelManager.prototype.resolveUrls;
    ModelManager.prototype.resolveUrls = async (name) => ({
      modelUrl: `https://mock.example/${name}/model.onnx`,
      configUrl: `https://mock.example/${name}/model.onnx.json`,
    });
    try {
      const warnings = await initAndCapture({ model: "tsukuyomi" });
      assert.equal(warnings.length, 1);
    } finally {
      ModelManager.prototype.resolveUrls = orig;
    }
  });

  it("案内のないモデルでは出さない", async () => {
    const warnings = await initAndCapture({ model: "https://example.com/model.onnx" });
    assert.equal(warnings.length, 0);
  });
});

// ---------------------------------------------------------------------------
// 7. piper-cli.js (stderr)
// ---------------------------------------------------------------------------

describe("model notice: bin/piper-cli.js", () => {
  function runBin(modelName, env = {}) {
    const tmp = mkdtempSync(join(tmpdir(), "piper-notice-"));
    const model = join(tmp, modelName);
    writeFileSync(model, Buffer.alloc(0));
    const childEnv = { ...process.env, ...env };
    if (!(ENV_NAME in env)) {
      delete childEnv[ENV_NAME];
    }
    // config が無いので ORT を読む前に止まる。案内はその前に出る。
    return spawnSync(
      process.execPath,
      [BIN, "--model", model, "--config", join(tmp, "missing.json"), "--json-input"],
      { input: "", env: childEnv, timeout: 30_000 }
    );
  }

  it("tsukuyomi.onnx で stderr に案内文と消し方の行を出し、stdout には出さない", () => {
    const out = runBin("tsukuyomi.onnx");
    const err = out.stderr.toString("utf8");
    for (const line of [...TSUKUYOMI.notice, MODEL_NOTICE_FOOTER]) {
      assert.ok(err.includes(line), `stderr lacks: ${line}\n---\n${err}`);
    }
    assert.equal(out.stdout.toString("utf8").includes(TSUKUYOMI.notice[0]), false);
  });

  it("PIPER_PLUS_DISABLE_MODEL_NOTICE=1 で出さない", () => {
    const out = runBin("tsukuyomi-chan-6lang-fp16.onnx", { [ENV_NAME]: "1" });
    assert.equal(out.stderr.toString("utf8").includes(TSUKUYOMI.notice[0]), false);
  });

  it("案内のないモデルでは出さない", () => {
    const out = runBin("model.onnx");
    assert.equal(out.stderr.toString("utf8").includes(MODEL_NOTICE_FOOTER), false);
  });
});
