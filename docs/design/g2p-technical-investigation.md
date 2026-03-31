# G2P 独立パッケージ化 -- 技術調査レポート

> 調査日: 2026-03-31
> 前提ドキュメント: `docs/design/g2p-package-requirements.md`

---

## 1. PUA マッピングテーブル差分調査

### 結果: 現在の HEAD では全プラットフォーム 87 エントリで一致

| プラットフォーム | ファイル | エントリ数 |
|----------------|--------|----------|
| Python | `token_mapper.py` | 87 |
| Rust | `token_map.rs` | 87 |
| C# | `OpenJTalkToPiperMapping.cs` | 87 |

**言語別内訳**: JA (29) + 共有 (2) + ZH (43) + KO (8) + ES/PT (2) + FR (3) = 87

**注**: 開発ブランチ (Swedish PR #296) で一時的に Python が 96 エントリ (+9 SV) に増えた履歴があるが、HEAD では全プラットフォーム同期済み。要求定義の「88 vs 87」は中間状態のスナップショットだった可能性が高い。

**対応**: 要求定義の PUA 差分タスクは不要。ただし言語追加時に全プラットフォーム同期を CI で検証する仕組みは必要。

---

## 2. Python パッケージ抽出分析

### 2.1 移動対象: 22 ファイル

`src/python/piper_train/phonemize/` 配下の全ファイル:
- コア: `__init__.py`, `base.py`, `registry.py`, `token_mapper.py`, `custom_dict.py`
- 言語 (7): `japanese.py`, `english.py`, `chinese.py`, `korean.py`, `spanish.py`, `portuguese.py`, `french.py`
- 多言語: `multilingual.py`, `bilingual.py`
- ID マップ (8): `jp_id_map.py`, `zh_id_map.py`, `ko_id_map.py`, `es_id_map.py`, `pt_id_map.py`, `fr_id_map.py`, `bilingual_id_map.py`, `multilingual_id_map.py`

### 2.2 依存関係

**piper_train 他モジュールへの依存: ゼロ**。phonemize は完全に自己完結。

**サードパーティ依存** (全て条件付き import):
- `pyopenjtalk` / `pyopenjtalk_plus` (JA)
- `g2p_en` (EN)
- `pypinyin` (ZH)
- `g2pk2` (KO)

### 2.3 piper_train 側で互換シムが必要な箇所 (6 ファイル)

| ファイル | import 内容 |
|---------|-----------|
| `preprocess.py` | `phonemize_japanese_with_prosody`, `CustomDictionary`, `get_japanese_id_map` |
| `update_model_config.py` | `FIXED_PUA_MAPPING`, `TOKEN2CHAR` |
| `vits/lightning.py` | `get_phonemizer` (相対 import) |
| `tools/prepare_bilingual_dataset.py` | `BilingualPhonemizer`, `get_bilingual_id_map` |
| `tools/prepare_multilingual_dataset.py` | `MultilingualPhonemizer`, `get_phonemizer`, `phonemize_from_pinyin_syllables`, `get_multilingual_id_map` |
| `tools/add_prosody_features.py` | `phonemize_japanese_with_prosody`, `get_japanese_id_map` |

### 2.4 pyproject.toml 設計案

```toml
[build-system]
requires = ["setuptools>=45", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "piper-g2p"
version = "0.1.0"
description = "Multi-language G2P (Grapheme-to-Phoneme) library for TTS — eSpeak-ng free"
license = {text = "MIT"}
requires-python = ">=3.11"
dependencies = []  # コア依存なし

[project.optional-dependencies]
ja = ["pyopenjtalk-plus>=0.4"]
en = ["g2p-en>=2.1.0"]
zh = ["pypinyin>=0.50"]
ko = ["g2pk2>=0.0.3"]
es = []
fr = []
pt = []
all = ["piper-g2p[ja,en,zh,ko]"]
dev = ["pytest>=7.0", "ruff>=0.12", "mypy>=1.0"]
```

### 2.5 互換シム設計

```python
# piper_train/phonemize/__init__.py (移行後)
import warnings
warnings.warn(
    "piper_train.phonemize is deprecated. Use piper_g2p instead.",
    DeprecationWarning, stacklevel=2,
)
from piper_g2p import *  # re-export
```

---

## 3. Rust crate 分離分析

### 3.1 移動対象: 12 ファイル

`src/rust/piper-core/src/phonemize/` 配下:
`mod.rs`, `japanese.rs`, `english.rs`, `chinese.rs`, `korean.rs`, `spanish.rs`, `portuguese.rs`, `french.rs`, `multilingual.rs`, `custom_dict.rs`, `token_map.rs`, `phoneme_converter.rs`

### 3.2 piper-core への依存 (断ち切りが必要)

| 依存 | 使用箇所 | 解決方針 |
|------|---------|---------|
| `crate::config::PhonemeIdMap` | 全 phonemizer | `piper-g2p` 内で `pub type PhonemeIdMap = HashMap<String, Vec<i64>>` を再定義 |
| `crate::error::PiperError` | 全 phonemizer | `piper-g2p` 内で `G2pError` を新規定義。`From<G2pError> for PiperError` で変換 |
| `crate::engine::SynthesisRequest` | `phoneme_converter.rs` のみ | `phoneme_converter` を2分割: `tokens_to_ids()` は piper-g2p、`build_synthesis_request()` は piper-core に残す |

### 3.3 piper-core から phonemize への依存

| ファイル | 依存内容 |
|---------|---------|
| `lib.rs` | `pub mod phonemize`, `pub use phonemize::{ProsodyFeature, ProsodyInfo}` |
| `voice.rs` | `Box<dyn Phonemizer>`, `phoneme_converter`, 各言語 Phonemizer コンストラクタ |

### 3.4 Cargo.toml 設計案

```toml
[package]
name = "piper-g2p"
version = "0.1.0"
edition = "2024"
license = "MIT"
description = "Multi-language G2P library for TTS"

[features]
default = ["naist-jdic", "multilingual"]
japanese = ["dep:jpreprocess"]
naist-jdic = ["japanese", "jpreprocess/naist-jdic"]
english = []
chinese = []
spanish = []
french = []
portuguese = []
korean = []
multilingual = ["english", "chinese", "spanish", "french", "portuguese", "korean"]

[dependencies]
thiserror = "2"
regex = "1"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
jpreprocess = { version = "0.9", optional = true }
```

### 3.5 piper-core 側変更

```toml
# piper-core/Cargo.toml
[dependencies]
piper-g2p = { path = "../piper-g2p", features = ["multilingual"] }

[features]
japanese = ["piper-g2p/japanese"]
naist-jdic = ["piper-g2p/naist-jdic"]
```

```rust
// piper-core/src/lib.rs
pub use piper_g2p::{Phonemizer, ProsodyInfo, ProsodyFeature, PhonemeIdMap};
```

---

## 4. C# プロジェクト分離分析

### 4.1 移動対象: 21 ファイル (Phonemize/) + 1 ファイル (Mapping/)

**Phonemize 内部の PiperPlus.Core への依存: 2 ファイルのみ**
- `PiperPhonemeConverter.cs` → `PiperPlus.Core.Mapping.OpenJTalkToPiperMapping`
- `RawPhonemeParser.cs` → 同上

**解決**: `OpenJTalkToPiperMapping.cs` も `PiperPlus.Phonemize` に含める。

**ONNX Runtime への直接依存: なし** (完全分離可能)

### 4.2 プロジェクト構成案

```
PiperPlus.Phonemize/           ← インターフェース + 6言語 Phonemizer + ユーティリティ
PiperPlus.Phonemize.DotNetG2P/ ← DotNetG2P エンジンアダプタ (Cli から移動)
PiperPlus.Core/                ← Inference + Config (Phonemize 参照、TypeForward)
```

### 4.3 PiperPlus.Phonemize.csproj

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <PackageId>PiperPlus.Phonemize</PackageId>
    <Version>0.1.0</Version>
    <PackageLicenseExpression>MIT</PackageLicenseExpression>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.Extensions.Logging.Abstractions" Version="8.0.3" />
  </ItemGroup>
</Project>
```

### 4.4 TypeForward による互換性維持

`PiperPlus.Core/TypeForwards.cs`:
```csharp
using System.Runtime.CompilerServices;

[assembly: TypeForwardedTo(typeof(PiperPlus.Phonemize.IPhonemizer))]
[assembly: TypeForwardedTo(typeof(PiperPlus.Phonemize.ProsodyInfo))]
[assembly: TypeForwardedTo(typeof(PiperPlus.Phonemize.MultilingualPhonemizer))]
[assembly: TypeForwardedTo(typeof(PiperPlus.Phonemize.JapanesePhonemizer))]
[assembly: TypeForwardedTo(typeof(PiperPlus.Phonemize.EnglishPhonemizer))]
// ... 全 public 型
```

### 4.5 テスト分離: Phonemize 関連 14 ファイルを新プロジェクトへ

---

## 5. JS/WASM G2P 分離分析

### 5.1 移動対象

- `simple_unified_api.js` (統一フォネマイザー)
- `simple_english_phonemizer.js` (英語 G2P、完全独立)
- `japanese_phoneme_extract.js` (JA ラベルパーサー、完全独立)
- `custom_dictionary.js` (カスタム辞書、完全独立)

### 5.2 onnxruntime-web への依存: なし

G2P レイヤーは onnxruntime-web に依存していない。依存は `index.js` の `PiperPlus` クラス (推論パイプライン) に集中。

### 5.3 OpenJTalk WASM の DI 化

現状: `initializeOpenJTalk()` が jsPath/wasmPath を自動解決してハードコード。

変更: コンストラクタで `openjtalkModule` を注入可能にする:
```javascript
class SimpleUnifiedPhonemizer {
    constructor(options = {}) {
        this.openjtalkModule = options.openjtalkModule || null;
    }
}
```

### 5.4 package.json 設計案

```json
{
  "name": "@piper-plus/g2p",
  "version": "1.0.0",
  "type": "module",
  "exports": {
    ".": "./src/index.js",
    "./ja": "./src/japanese_phoneme_extract.js",
    "./en": "./src/simple_english_phonemizer.js",
    "./dict": "./src/custom_dictionary.js"
  },
  "files": ["src/", "dist/", "types/"],
  "engines": { "node": ">=18.0.0" }
}
```

---

## 6. クロスプラットフォーム互換テスト設計

### 6.1 テストフィクスチャ JSON スキーマ

```json
{
  "version": "1.0",
  "test_cases": [
    {
      "id": "ja_001",
      "language": "ja",
      "input_text": "こんにちは",
      "expected_phonemes": ["^", "k", "o", "N_n", "n", "i", "ch", "i", "h", "a", "$"],
      "expected_prosody": [null, {"a1":0,"a2":1,"a3":5}, ...],
      "note": "N→N_n before n"
    }
  ]
}
```

### 6.2 テストケース一覧 (6 言語 x 3 文)

| 言語 | テスト | 入力 | 検証ポイント |
|------|-------|------|------------|
| JA | ja_001 | こんにちは | N→N_n (歯茎音前) |
| JA | ja_002 | 何ですか？ | 疑問詞マーカー `?` |
| JA | ja_003 | さんぽ | N→N_m (両唇音前) |
| EN | en_001 | Hello world | ストレス + 語境界 |
| EN | en_002 | the cat | 機能語ストレス除去 |
| EN | en_003 | cat | 基本単語 |
| ZH | zh_001 | 你好 | 声調サンドヒ (T3+T3→T2+T3) |
| ZH | zh_002 | 中国 | 複数音節 |
| ZH | zh_003 | 元 | ü final (üan→yɛn) |
| ES | es_001 | Hola mundo | 語境界 |
| FR | fr_001 | Bonjour | 鼻母音 |
| PT | pt_001 | Olá mundo | 強勢母音 |

### 6.3 混在テキストテスト

| テスト | 入力 | セグメント | 検証ポイント |
|-------|------|----------|------------|
| multi_001 | こんにちはHello | ja + en | BOS/EOS 除去・連結 |
| multi_002 | 漢字を | ja (仮名あり→JA) | CJK 曖昧性解消 |
| multi_003 | こんにちはHello你好 | ja + en + zh | 3 言語混在 |

### 6.4 JS/WASM 制約

- EN/ZH/ES/FR/PT はキャラクタベースのため phoneme_ids が異なる
- JA の phoneme_ids は完全一致を要求
- テストに `"wasm_skip": true` フラグで分離

---

## 7. CI/CD ワークフロー設計

### 7.1 ワークフロー一覧

| ワークフロー | paths filter | タグトリガー | レジストリ |
|-----------|------------|-----------|----------|
| `g2p-python-ci.yml` | `src/python/g2p/**` | `python-g2p-v*` | PyPI |
| `g2p-rust-ci.yml` | `src/rust/piper-g2p/**` | `rust-g2p-v*` | crates.io |
| `g2p-csharp-ci.yml` | `src/csharp/PiperPlus.Phonemize/**` | `csharp-g2p-v*` | NuGet |
| `g2p-wasm-ci.yml` | `src/wasm/g2p/**` | `wasm-g2p-v*` | npm |

### 7.2 Python CI (`g2p-python-ci.yml`)

```yaml
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v6
      - run: uv run ruff check src/python/g2p/
      - run: uv run ruff format --check src/python/g2p/
      - run: uv run mypy src/python/g2p/ --strict --ignore-missing-imports

  test:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python-version: ['3.11', '3.12', '3.13']
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v6
        with:
          python-version: ${{ matrix.python-version }}
      - run: uv sync --all-extras
        working-directory: src/python/g2p
      - run: uv run pytest tests/ -v --cov=piper_g2p
        working-directory: src/python/g2p

  publish:
    if: startsWith(github.ref, 'refs/tags/python-g2p-v')
    needs: [lint, test]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v6
      - run: uv build
        working-directory: src/python/g2p
      - run: uv publish
        working-directory: src/python/g2p
```

### 7.3 Rust CI (`g2p-rust-ci.yml`)

- `cargo fmt -- --check`
- `cargo clippy --all-features -- -D warnings`
- `cargo test --all-features` (3 OS x stable/beta)
- クロスコンパイル: linux-x64, linux-arm64, darwin-arm64, win-x64
- `cargo publish -p piper-g2p` (タグトリガー)

### 7.4 C# CI (`g2p-csharp-ci.yml`)

- `dotnet build` + `dotnet format --verify-no-changes`
- `dotnet test` (3 OS x .NET 8.0/9.0)
- `dotnet pack` + `dotnet nuget push` (タグトリガー)

### 7.5 JS/WASM CI (`g2p-wasm-ci.yml`)

- `node --test` (3 OS x Node 18/20/22)
- パッケージサイズ検証 (< 10MB)
- `npm publish --provenance --access public` (タグトリガー)

### 7.6 共通テストフィクスチャ

`test/fixtures/g2p-compatibility.json` を全 CI で参照:
```
tests/fixtures/g2p/
├── phoneme_test_cases.json
├── prosody_expected_outputs.json
└── multilingual_test_sets.json
```

### 7.7 既存 CI との共存

- paths filter で分離: 新 G2P CI は `src/*/g2p/**` のみ、既存 CI は `src/**` 全体
- タグパターン分離: `python-g2p-v*` / `rust-g2p-v*` / `csharp-g2p-v*` / `wasm-g2p-v*`
- 既存の `ci.yml`, `python-tests.yml`, `rust-tests.yml`, `csharp-ci.yml` は変更不要

---

## 8. 全プラットフォーム共通の設計判断

### 8.1 EspeakPostProcessIds → DefaultPostProcessIds リネーム

C# の `PiperPhonemeConverter.EspeakPostProcessIds` は eSpeak-ng 非依存パッケージにふさわしくないため `DefaultPostProcessIds` にリネーム。影響範囲:
- `PiperPhonemeConverter.cs` (定義)
- `EnglishPhonemizer.cs`, `ChinesePhonemizer.cs`, `SpanishPhonemizer.cs`, `FrenchPhonemizer.cs`, `PortuguesePhonemizer.cs` (呼び出し)

### 8.2 phoneme_converter の分割 (Rust)

`phoneme_converter.rs` を 2 つに分割:
- `piper-g2p/src/phoneme_converter.rs`: `tokens_to_ids()`, `prosody_to_features()` (G2P のみ)
- `piper-core/src/phoneme_converter.rs`: `build_synthesis_request()` (推論パイプライン)

### 8.3 CustomDictionary のデフォルトパス

Python の `CustomDictionary` はデフォルト辞書パスをハードコード (`Path(__file__).parent.../"data"/"dictionaries"`)。独立パッケージでは:
- `piper_g2p` パッケージ内に `data/dictionaries/` をバンドル
- `CustomDictionary(load_defaults=False)` でスキップ可能 (既存動作維持)
