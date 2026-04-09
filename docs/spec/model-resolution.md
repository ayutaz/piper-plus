# Model Resolution Specification

> **Version:** 1.0  
> **対象実装:** Python, Rust, C#, Go  
> **テストベクトル:** [`test/model_resolution_vectors.json`](../../test/model_resolution_vectors.json)

---

## 概要

本仕様は、piper-plus の4言語実装 (Python, Rust, C#, Go) における**モデル解決 (model resolution)** アルゴリズムを定義する。ユーザーが `--model` 引数に指定する文字列から、実際の ONNX モデルファイルと config.json のパスを決定するまでの手順を統一する。

---

## 1. Resolution Order

モデル文字列 `model_str` を受け取り、`(onnx_path, config_path)` を返す。

```
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

入力がファイルシステム上に存在するファイルを指す場合、そのパスをそのまま使用する。ディレクトリの場合はエラーとする。

### Step 2: Catalog / alias lookup

Voice catalog から以下の優先順位で検索する:

1. **Exact key match** -- `ja_JP-tsukuyomi-chan-medium` のような完全キー
2. **Name match** -- `tsukuyomi-chan` のような voice name
3. **Alias match** -- `tsukuyomi`, `css10` のようなショートネーム
4. **Partial name match** (Rust/Go) -- `tsukuyomi` が `tsukuyomi-6lang-v2` に部分一致

> **重要:** Partial match は曖昧な場合 (複数候補) はエラーとする。例: `6lang` は `tsukuyomi-6lang-v2` と `css10-6lang` の両方に一致するためエラー。

### Step 3: HuggingFace repo ID

入力に `/` が含まれる場合、HuggingFace repo ID として扱う。`owner/repo` 形式を期待する。

### Step 4: Local cache scan

Cache directory 内で `{model_str}/*.onnx` または `{model_str}.onnx` を探索する。

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
| `quality` | string | `low` / `medium` / `high` |
| `num_speakers` | int | 話者数 |
| `source` | string | `piper-plus` or `piper` |
| `repo_id` | string | HuggingFace リポジトリ ID |
| `files` | array/map | ダウンロード対象ファイル (ONNX + config) |
| `aliases` | array | ショートネームのリスト |
| `description` | string | 説明文 |

### Alias Registry

`test/model_resolution_vectors.json` の `aliases` セクションが正規の alias 定義を保持する。各実装はこの定義と一致しなければならない。

| Alias | Repo ID | ONNX File |
|-------|---------|-----------|
| `tsukuyomi` | `ayousanz/piper-plus-tsukuyomi-chan` | `tsukuyomi-chan-6lang-fp16.onnx` |
| `base` | `ayousanz/piper-plus-base` | `piper-plus-base-6lang-fp16.onnx` |
| `css10` | `ayousanz/piper-plus-css10-ja-6lang` | `css10-ja-6lang-fp16.onnx` |

---

## 3. Config Auto-Detection

ONNX モデルファイルに対応する config.json を以下の順序で検索する。

```
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

`PIPER_MODEL_DIR` 環境変数が設定されている場合、それをキャッシュディレクトリとして使用する。

### Platform Default

| Platform | Default Path |
|----------|-------------|
| Linux | `$XDG_DATA_HOME/piper-plus/models` or `~/.local/share/piper-plus/models` |
| macOS | `~/Library/Application Support/piper-plus/models` |
| Windows | `%APPDATA%/piper-plus/models` |

### Layout

キャッシュディレクトリ内のファイル配置は以下のいずれか:

```
{cache_dir}/
  tsukuyomi-chan-6lang-fp16.onnx      # flat layout (推奨)
  tsukuyomi-chan-6lang-fp16.onnx.json  # or config.json
  config.json
```

または HuggingFace Hub 互換のサブディレクトリ配置:

```
{cache_dir}/
  ayousanz--piper-plus-tsukuyomi-chan/  # repo_id の "/" を "--" に置換
    tsukuyomi-chan-6lang-fp16.onnx
    config.json
```

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

全実装で以下のバリデーションを実施する:

| チェック | 内容 |
|---------|------|
| Path traversal | `..` を含む入力を alias/name 解決で拒否 |
| Repo ID format | `owner/repo` 形式のみ許可 (英数字, `-`, `_`, `.` のみ) |
| Download protocol | HTTPS のみ許可 (`http://localhost` はテスト用に許可) |

---

## 6. 実装マッピング

| 機能 | Python | Rust | C# | Go |
|------|--------|------|-----|-----|
| Entry point | `_model_resolver.resolve_model()` | `model_download::resolve_model_path()` | `ModelManager.ResolveModelPathAsync()` | `ModelManager.FindModel()` |
| Voice catalog | `model_manager._BUILTIN_CATALOG` | `model_download::builtin_registry()` | `VoiceCatalog.LoadMergedCatalog()` | -- (URL-based) |
| Alias lookup | `MODEL_ALIASES` dict | `find_model()` (name/partial/desc) | `FindVoice()` (key/alias dict) | -- |
| Config detection | `_find_config()` | `is_model_cached()` | Download 時に catalog から取得 | `buildModelInfo()` |
| Cache dir | `~/.cache/piper-plus/models` | `default_model_dir()` | `GetDefaultModelDir()` | `DefaultCacheDir()` |
| Download | `huggingface_hub` | `reqwest` (feature-gated) | `HttpClient` | `net/http` |

### ソースファイル

| 実装 | パス |
|------|------|
| Python (高レベル API) | `src/python/piper_plus/_model_resolver.py` |
| Python (学習/推論) | `src/python/piper_train/model_manager.py` |
| Rust | `src/rust/piper-core/src/model_download.rs` |
| C# | `src/csharp/PiperPlus.Core/Config/ModelManager.cs` |
| C++ | `src/cpp/model_manager.hpp`, `src/cpp/model_manager.cpp` |
| Go | `src/go/piperplus/model_manager.go` |

---

## 7. テストベクトル参照

テストベクトルは `test/model_resolution_vectors.json` に定義されている。各実装のテストスイートはこのファイルを読み込み、`test_cases` の各エントリに対して期待動作を検証すること。

### テストケース一覧

| ID | Type | 検証内容 |
|----|------|---------|
| `direct_file_path` | file_path | 既存ファイルパスをそのまま返す |
| `alias_tsukuyomi` | alias | `tsukuyomi` -> repo 解決 |
| `alias_base` | alias | `base` -> repo 解決 |
| `alias_css10` | alias | `css10` -> repo 解決 |
| `catalog_key_exact` | catalog_key | 完全キーマッチ |
| `hf_repo_id` | huggingface | `/` 含む文字列を HF repo として処理 |
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
| Catalog format | Python は dict, Rust は Vec, C# は JSON | JSON catalog を正とし各言語で読み込み |
| Partial match | Rust のみ partial name + description match | 全実装で catalog alias ベースに統一予定 |
| Auto-download | Python は `huggingface_hub`, 他は直接 HTTP | 各実装の依存に応じて許容 |
