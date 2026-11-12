# Model Resolution Specification

> **Version:** 1.0  
> **対象実装:** Python, Rust, C#, Go  
> **テストベクトル:** [`test/model_resolution_vectors.json`](../../test/model_resolution_vectors.json)

---

## 概要

本仕様は、piper-plus の4言語実装 (Python, Rust, C#, Go) における**モデル解決 (model resolution)** アルゴリズムを定義する。ユーザーが `--model` 引数に指定する文字列から、実際の ONNX モデルファイルと config.json のパスを決定するまでの手順を統一する。

解決順序は統一を目指す仕様であり、全ランタイムで全経路が実装済みという意味ではない。
現在の入口と差異は§6・§8を参照。

---

## 1. Resolution Order

モデル文字列 `model_str` を受け取り、`(onnx_path, config_path)` を返す。

```text
function resolve_model(model_str, config=None, cache_dir=None):
    cache_dir = cache_dir or default_cache_dir()

    # Step 1: Direct file path
    if is_file(model_str):
        return (model_str, find_config(model_str, config))

    # Step 2: Catalog key / alias lookup
    voice = find_voice(model_str)  # exact key → name → alias → partial match
    if voice is not None:
        return resolve_from_catalog(voice, cache_dir, config)

    # Step 3: HuggingFace repo ID
    if "/" in model_str:
        return download_from_hf(model_str, cache_dir, config)

    # Step 4: Local cache scan
    cached = scan_cache(model_str, cache_dir)
    if cached is not None:
        return cached

    # Step 5: Error
    raise ModelNotFoundError(model_str)
```

### Step 1: Direct file path

入力がファイルシステム上に存在するファイルを指す場合、そのパスをそのまま使用する。
catalog/native runtime の共有目標ではディレクトリを明示的な directory error とする。
Python high-level API は現状ディレクトリを cache candidate として扱い、ONNX が見つから
なければ通常の `ModelNotFoundError` にフォールバックする。

### Step 2: Catalog / alias lookup

Voice catalog から以下の優先順位で検索する:

1. **Exact key match** -- `ja_JP-tsukuyomi-chan-medium` のような完全キー
2. **Name match** -- `tsukuyomi-chan` のような voice name
3. **Alias match** -- `tsukuyomi`, `css10` のようなショートネーム
4. **Partial name match** (Rust) -- `tsukuyomi` が `tsukuyomi-6lang-v2` に部分一致

> **重要:** Partial match は曖昧な場合 (複数候補) はエラーとする。例: `6lang` は `tsukuyomi-6lang-v2` と `css10-6lang` の両方に一致するためエラー。

### Step 3: HuggingFace repo ID

入力に `/` が含まれる場合、HuggingFace repo ID として扱う。`owner/repo` 形式を期待する。

### Step 4: Local cache scan

これは共有目標であり、runtime ごとの cache layout を確認する。Python high-level API
は `cache_dir/{model_str}/*.onnx` の subdirectory layout を読むが、
`cache_dir/{model_str}.onnx` の flat layout は読まない。Python CLI と native runtime
には flat layout を使う入口があるため、flat-cache の例を全 runtime の API 契約として
解釈してはならない。

### Step 5: Error

いずれにも該当しない場合は `ModelNotFoundError` (または各言語の同等例外) を送出する。

---

## 2. Voice Catalog Format

各実装は以下のフィールドを持つ voice catalog エントリを保持する。

| Field | Type | 説明 |
|-------|------|------|
| `key` | string | 一意識別子 (例: `ja_JP-tsukuyomi-chan-medium`) |
| `name` | string | Voice 名 (例: `tsukuyomi-chan`) |
| `language_code` | string | Locale コード (例: `ja_JP`) |
| `language_family` | string | 言語ファミリー (例: `ja`) |
| `quality` | string | `low` / `medium` / `high` / `experimental` |
| `num_speakers` | int | 話者数 |
| `source` | string | `piper-plus` or `piper` |
| `repo_id` | string | HuggingFace リポジトリ ID |
| `revision` | string (optional) | 固定HF revision。省略時は従来の`main` |
| `files` | array/map | ダウンロード対象ファイル (ONNX + config) |
| `aliases` | array | ショートネームのリスト |
| `description` | string | 説明文 |
| `notice` | array of string (optional) | モデルを使う前に表示する利用案内。1 要素が 1 行 ([§9](#9-利用案内-model-notice)) |
| `notice_files` | array of string (optional) | パスで指定されたときに、このエントリの利用案内を出す ONNX のファイル名 ([§9](#9-利用案内-model-notice)) |

### Alias Registry and catalog key

`test/model_resolution_vectors.json` の `voice_catalog` が、モデル名の正本である。
各エントリの `key` (完全なカタログ識別子) と `aliases` のすべてを、catalog を持つ
すべてのランタイムが受け付け、正本の `repo_id` / `onnx_file` / `config_file` /
`revision` に解決する。HuggingFace の repo ID も `aliases` に入れてあるので、
`ayousanz/piper-plus-tsukuyomi-chan` のような指定も Step 3 の自動検出ではなく
カタログのファイルに解決される。`scripts/check_voice_catalog_parity.py` が、
各ランタイムの写しに `key` と全 `aliases` が文字列リテラルとして出てくることを
検査する。正本の先頭にある旧 `aliases` セクションは参照用で、どのランタイムも読まない。

| Key | Aliases | Repo ID | ONNX File |
|-----|---------|---------|-----------|
| `ja_JP-tsukuyomi-chan-medium` | `tsukuyomi`, `tsukuyomi-chan`, `ja-tsukuyomi`, `ayousanz/piper-plus-tsukuyomi-chan` | `ayousanz/piper-plus-tsukuyomi-chan` | `tsukuyomi-chan-6lang-fp16.onnx` |
| `ja_JP-css10-6lang-medium` | `css10`, `css10-6lang`, `css10-ja`, `ja-css10`, `ayousanz/piper-plus-css10-ja-6lang` | `ayousanz/piper-plus-css10-ja-6lang` | `css10-ja-6lang-fp16.onnx` |
| `multilingual-zero-shot-base-zs-v1` | `base`, `zero-shot-base-zs-v1`, `ayousanz/piper-plus-base` | `ayousanz/piper-plus-base` at revision `3620ed788667cb76f08bd6cf2db8152c1f4c8bd1` | `releases/zs-v1/base.onnx` |

> `base` と `zero-shot-base-zs-v1` は、v2.0.2 で公開した pinned aliases です。
> いずれも root の legacy `model.ckpt` を指さず、上記 revision の
> `releases/zs-v1/base.onnx` と対応する `releases/zs-v1/base.onnx.json` を解決します。v2.0.0/v2.0.1
> には含まれず、alias 表にも遡及して追加しません。`base.onnx` は 192 次元 CAM++
> `speaker_embedding` を使う実験用 Zero-Shot base で、通常の参照なし音声用 alias ではありません。

#### Runtime-specific alias status

| ランタイム | 名前を受け付ける入口 |
|-----------|--------------------|
| Python | CLI と HTTP サーバー (`download.find_voice()`)、高レベル API (`_model_resolver.resolve_model()`)。どちらも `download.PIPER_PLUS_VOICES` を引く。`MODEL_ALIASES` はこのカタログから作る読み取り専用の一覧 (`PiperPlus.list_models()` が返す) |
| Rust | `find_model()` が `MODEL_ALIASES` 表で完全一致を引き、旧 registry 名・部分一致・説明文一致も互換のため残す |
| C# / C++ | `FindVoice()` / `findVoice()` (key と alias) |
| WASM / npm | `ModelManager.resolveUrls()` / `loadModel()`。カタログの名前は HF API を呼ばずに URL を組み立てる |
| Go | `piperplus.FindVoice()`。CLI (`--model`、`serve --model`、`--download-model`) は `ModelManager.ResolveVoice()` / `DownloadVoice()` でカタログから解決し、未取得なら自動 DL する |

---

## 3. Config Auto-Detection

ONNX モデルファイルに対応する config.json を以下の順序で検索する。

```text
function find_config(onnx_path, explicit_config=None):
    # 1. Explicit parameter
    if explicit_config is not None:
        if is_file(explicit_config):
            return explicit_config
        raise Error("Config file not found: " + explicit_config)

    # 2. {model_path}.json  (e.g., model.onnx.json)
    candidate = onnx_path + ".json"
    if is_file(candidate):
        return candidate

    # 3. {model_dir}/config.json
    candidate = dirname(onnx_path) / "config.json"
    if is_file(candidate):
        return candidate

    # 4. Error
    raise Error("Config file not found for " + onnx_path)
```

### 実装間の差異

| 実装 | `.onnx.json` パターン | `config.json` パターン |
|------|----------------------|----------------------|
| Python (`_model_resolver`) | `onnx_path.with_suffix(suffix + ".json")` | `onnx_path.parent / "config.json"` |
| Rust | `{name}.onnx.json` | `config.json` |
| C# | ダウンロード時に catalog から取得 | `config.json` |
| Go | -- | `config.json` (隣接ファイル) |

---

## 4. Cache Directory Structure

### 環境変数オーバーライド

`PIPER_PLUS_MODEL_DIR` 環境変数が設定されている場合、それをキャッシュディレクトリとして使用する。

### Platform Default

| Platform | Default Path |
|----------|-------------|
| Linux | `$XDG_DATA_HOME/piper-plus/models` or `~/.local/share/piper-plus/models` |
| macOS | `~/Library/Application Support/piper-plus/models` |
| Windows | `%APPDATA%/piper-plus/models` |

### Layout

キャッシュディレクトリ内のファイル配置は以下のいずれか:

```text
{cache_dir}/
  tsukuyomi-chan-6lang-fp16.onnx      # flat layout (推奨)
  tsukuyomi-chan-6lang-fp16.onnx.json  # or config.json
  config.json
```

または HuggingFace Hub 互換のサブディレクトリ配置:

```text
{cache_dir}/
  ayousanz--piper-plus-tsukuyomi-chan/  # repo_id の "/" を "--" に置換
    tsukuyomi-chan-6lang-fp16.onnx
    config.json
```

Go はカタログのモデルを `{cache_dir}/{catalog key}/` に置く (例: `ja_JP-tsukuyomi-chan-medium/tsukuyomi-chan-6lang-fp16.onnx` と `config.json`)。tsukuyomi と css10 はどちらも `config.json` を持つので、モデルごとにディレクトリを分けて上書きを防ぐ。revision を固定したモデル (base) はカタログのサイズと一致するファイルだけをキャッシュとみなし、`main` を指すモデルは Hub 側で更新されうるのでサイズを問わない。

> **Note:** Python `_model_resolver.py` は `~/.cache/piper-plus/models/{repo_id_with_dashes}/` を使用する (huggingface_hub 方式)。他の実装はプラットフォームデータディレクトリを使用する。将来的に統一予定。

---

## 5. Error Handling

### ModelNotFoundError

以下の状況で `ModelNotFoundError` (または同等の例外/エラー型) を送出する:

| 条件 | エラーメッセージに含めるべき情報 |
|------|-------------------------------|
| 入力が空文字列 | "Model '' not found" |
| ファイルが存在しない & alias にもない | 利用可能な alias のリスト |
| ディレクトリが指定された | "is a directory" の旨 |
| Ambiguous partial match | 曖昧である旨 |
| ダウンロード失敗 | 元の HTTP エラー情報 |

### Security Validation

以下は共有契約として目指す検証項目である。現行実装の挙動はランタイムごとに異なり、
この表だけでは全実装が同じ検証を行うことを意味しない。

| チェック | 共有目標 | 現行実装の差異 |
|---------|------|------|
| Path traversal | `..` を含む入力を alias/name 解決で拒否 | Python API は入力を明示検証しない。C#/C++/Go の catalog/download 経路には検証があるが、入口が異なる |
| Repo ID format | `owner/repo` 形式のみ許可 (英数字, `-`, `_`, `.` のみ) | Python API は `/` を含む文字列を Hub repo として渡す。C# catalog は形式検証する。Go のカタログ DL は key・repo ID・revision・ファイルパスを検証する |
| Download protocol | HTTPS のみ許可 (`http://localhost` はテスト用に許可) | Go は `https://`、`file://`、localhost HTTP を許可する。ブラウザの direct URL は `http://` と `https://` の両方を受け付ける |

---

## 6. 実装マッピング

| 機能 | Python | Rust | C# | Go |
|------|--------|------|-----|-----|
| Entry point | `_model_resolver.resolve_model()` | `model_download::resolve_model_path()` | `ModelManager.ResolveModelPathAsync()` | CLI `resolveModelArg()` (`ModelManager.ResolveVoice()` → `FindModel()`) |
| Voice catalog | `download.PIPER_PLUS_VOICES` (CLI と API で共通) | `model_download::builtin_registry()` | `VoiceCatalog.LoadMergedCatalog()` | `voice_catalog.go` (CLI と共通) |
| Alias lookup | `download.resolve_piper_plus_voice()` | `find_model()` (`MODEL_ALIASES` 表、name/partial/desc) | `FindVoice()` (key/alias dict) | `FindVoice()` (key/alias) |
| Config detection | API: `_find_config()`; CLI: `download.find_voice()` | `resolve_model_path()` | Download 時に catalog から取得 | `buildModelInfo()` |
| Cache dir | API: `~/.cache/piper-plus/models`; CLI: 指定download dir | `default_model_dir()` | `GetDefaultModelDir()` | `DefaultCacheDir()` |
| Download | API: `huggingface_hub`; CLI: `urlopen` | `reqwest` (feature-gated) | `HttpClient` | `net/http` |

### ソースファイル

| 実装 | パス |
|------|------|
| Python (高レベル API) | `src/python_run/piper_plus/api/_model_resolver.py` |
| Python (推論CLIのcatalog/取得) | `src/python_run/piper_plus/download.py` |
| Python (旧学習側の通常音声catalog) | `src/python/piper_train/model_manager.py`。公開baseの取得元ではない |
| Rust | `src/rust/piper-core/src/model_download.rs` |
| C# | `src/csharp/PiperPlus.Core/Config/ModelManager.cs` |
| C++ | `src/cpp/model_manager.hpp`, `src/cpp/model_manager.cpp` |
| Go | `src/go/piperplus/model_manager.go` |

---

## 7. テストベクトル参照

テストベクトルは `test/model_resolution_vectors.json` に定義されている。これは共有目標
と検証項目の canonical matrix であり、各 runtime のテストは実装済み入口に対応する
case を読み込んで検証する。runtime-specific な未実装経路（たとえば flat cache、directory-specific error）は、実装済みと
報告せず差異として扱う。モデル名については、各ランタイムのテストが `voice_catalog` の
`key` と全 `aliases` を読み、それぞれが正本のファイルに解決されることを確かめる。

### テストケース一覧

| ID | Type | 検証内容 |
|----|------|---------|
| `direct_file_path` | file_path | 既存ファイルパスをそのまま返す |
| `alias_tsukuyomi` | alias | `tsukuyomi` -> repo 解決 |
| `alias_base` | alias | `base` -> repo 解決 |
| `alias_css10` | alias | `css10` -> repo 解決 |
| `catalog_key_exact` | catalog_key | 完全キーマッチ。公開 base では `multilingual-zero-shot-base-zs-v1` |
| `catalog_repo_id` | alias | カタログにあるモデルの repo ID はエイリアスとしてカタログのファイルに解決する |
| `hf_repo_id` | huggingface | カタログにない `/` 含む文字列を HF repo として処理 |
| `nonexistent_alias` | error | 不明な名前でエラー |
| `empty_input` | error | 空文字列でエラー |
| `config_auto_detect_onnx_json` | config_detection | `.onnx.json` -> `config.json` の順で検索 |
| `config_explicit` | config_detection | 明示的 config パラメータの優先 |
| `cached_model_subdir` | cache_hit | キャッシュ済みモデルの解決 |
| `cached_model_flat` | cache_hit | Flat layout キャッシュの解決 |
| `directory_input` | error | ディレクトリ指定でエラー |
| `path_traversal_rejected` | error | Path traversal 拒否 |
| `ambiguous_partial_match` | error | 曖昧一致でエラー |

---

## 8. 既知の実装差異 (convergence TODO)

| 差異 | 現状 | 統一方針 |
|------|------|---------|
| Cache directory path | Python は `~/.cache/`, 他は platform data dir | Platform data dir に統一予定 |
| Catalog format | Python CLIはdict、Rust/C#/Goはsource内定義、C++はJSONと埋め込み定義 | JSON catalog を正とし各言語で読み込み |
| Partial match | Rust のみ partial name + description match | 全実装で catalog alias ベースに統一予定 |
| Auto-download | Python は `huggingface_hub`, 他は直接 HTTP | 各実装の依存に応じて許容 |

---

## 9. 利用案内 (model notice)

利用条件のあるモデル (現在はつくよみちゃんモデルのみ) を使うとき、CLI とサーバーは
`notice` を stderr に表示する。つくよみちゃんモデルは、生成音声を使うときに
「Piper Plus:つくよみちゃん」のクレジット表記が必須で、つくよみちゃん側から見ると
非公式の作品である (規約: <https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan>)。

### 正本

`test/model_resolution_vectors.json` の `voice_catalog.<key>.notice` が案内文の正本で、
`notice_files` がファイル名による判定の正本である。各ランタイムの catalog はこれを写し、
`scripts/check_voice_catalog_parity.py` が写しの各行の有無を検査する。案内文の行には
`"` と `\` を入れない (各言語の文字列リテラルにそのまま書けるようにするため)。

### 判定

入力 (モデル名・パス・URL) が次のどれかに当たるとき、そのエントリの `notice` を返す。

1. catalog の `key`、`aliases` のどれか、または `repo_id` と完全に一致する
2. URL で、`/<repo_id>/` を含む
3. パスで、ファイル名 (最後の要素) が `notice_files` のどれかと一致する

### 表示

| 項目 | 規則 |
|------|------|
| 表示する側 | CLI とサーバー (HTTP / Wyoming / OpenAI 互換 / WebUI) などの実行ファイル。ライブラリは判定結果を返すだけで、自分では表示しない |
| 出力先 | stderr (ブラウザは `console.warn`)。stdout は音声やパスの出力に使われるため使わない |
| 回数 | 1 プロセスで 1 回 |
| 形式 | `notice` の各行をそのまま 1 行ずつ出し、最後に下の消し方の行を出す |
| 消し方 | 環境変数 `PIPER_PLUS_DISABLE_MODEL_NOTICE` が `1` / `true` / `yes` (大文字小文字を区別せず、前後の空白を除く) のとき表示しない。`--quiet` では消えない。ブラウザ (npm) は `showModelNotice: false` オプション |

消し方の行 (各ランタイム共通):

```text
(この表示は PIPER_PLUS_DISABLE_MODEL_NOTICE=1 で消せます / Set PIPER_PLUS_DISABLE_MODEL_NOTICE=1 to hide this notice.)
```

### 実装

| ランタイム | 判定 (ライブラリ) | 表示 (実行ファイル) |
|-----------|------------------|--------------------|
| Python | `piper_plus.download.get_model_notice()`、`PiperPlus.model_notice` (表示は `print_model_notice()` / `show_model_notice()`) | CLI、HTTP サーバー、Wyoming |
| Python (学習側・Docker) | `piper_train.model_manager.get_model_notice()` | `infer_onnx`、`model_manager.download_model()`、OpenAI 互換サーバー、WebUI |
| Rust | `piper_plus::model_download::model_notice()` (旧名 `tsukuyomi-6lang-v2` とそのキャッシュファイル名も判定する) | `piper-plus` CLI |
| Go | `piperplus.ModelNotice()` | `piper-plus` CLI (合成と `serve`) |
| C# | `ModelManager.GetModelNotice()`、`VoiceInfo.Notice` | `piper-plus` CLI |
| C++ | `piper::getModelNotice()` (`model_manager.hpp`) | `piper` CLI |
| WASM / npm | `getModelNotice()`、`ModelManager.resolveUrls()` / `loadModel()` の `notice` | ブラウザにはプロセスの stderr がないため、`PiperPlus.initialize()` と `ModelManager.loadModel()` が `console.warn` で出す (`showModelNotice: false` で止める)。`piper-cli.js` は stderr |
| C API / Swift / Kotlin | なし (モデルのパスだけを受け取るため) | アプリ側で表示する |


## Public baseline cache and integrity scope

For `zs-v1`, Python API and browser caches isolate the pinned revision/path.
Python CLI and native catalogs pin download URLs but retain flat local filenames;
those local filenames alone do not establish a file's revision or SHA-256.
Use a separate model directory for the public baseline and verify files against
its bundled manifest when importing/reusing manually downloaded artifacts.
Browser resolution likewise does not enforce the release manifest's hashes;
its existing hash check uses `config.sha256` when a config supplies that field.
Inference uses `base.onnx` + `base.onnx.json`; fine-tuning uses `base.ckpt` +
the same release's `config.json`. Never substitute the repository's legacy root config.
