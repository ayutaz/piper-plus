# G2P 統一マイルストーン: piper-plus 本体を standalone piper-g2p に移行

> **チケット一覧**: [docs/tickets/README.md](tickets/README.md) (全 30 チケット)

## 背景

piper-plus は 3 プラットフォーム (Python/Rust/JS) それぞれに **2 つの phonemizer 実装** を持っている:

| プラットフォーム | 旧 (piper-plus 本体内) | 新 (standalone G2P) |
|---|---|---|
| Python | `piper_train/phonemize/` (24 ファイル) | `piper_g2p` (19 ファイル) |
| Rust | `piper-core/src/phonemize/` (16 ファイル) | `piper-g2p` crate |
| JS/WASM | `SimpleUnifiedPhonemizer` | `@piper-plus/g2p` |

standalone G2P パッケージは既に独立して動作するが、**piper-plus 本体がそれを使っていない**。
本マイルストーンは旧実装を standalone G2P に置き換え、重複コードを削除する計画である。

---

## M0: piper-g2p API ギャップ修正 (前提条件)

> **目的**: 移行前に piper-g2p 側の不足を解消する
> **影響範囲**: `src/python/g2p/`, `src/rust/piper-g2p/`, `src/wasm/g2p/`
> **見積り**: 小

### M0-1: Python — `_get_question_type()` の戻り値修正 → [チケット](tickets/M0-1-fix-question-type-return.md)

- **ファイル**: `src/python/g2p/piper_g2p/japanese.py:77`
- **問題**: 非疑問文で `""` (空文字) を返す。piper_train は `"$"` を返す
- **影響**: MultilingualPhonemizer の EOS トラッキングが壊れる
- **修正**: `return ""` → `return "$"`

### M0-2: Python — JapanesePhonemizer に custom_dict パラメータ追加 → [チケット](tickets/M0-2-japanese-custom-dict-param.md)

- **ファイル**: `src/python/g2p/piper_g2p/japanese.py:207-233`
- **問題**: `phonemize()` / `phonemize_with_prosody()` が `custom_dict` を受け取れない
- **影響**: `preprocess.py:733` が custom_dict 付きで `phonemize_japanese_with_prosody()` を呼ぶ
- **修正**: 約 10 行追加。`CustomDictionary` は既に `piper_g2p/custom_dict.py` に存在する
- **パターン**:
  ```python
  def phonemize_with_prosody(self, text, custom_dict=None):
      if custom_dict is not None:
          if not isinstance(custom_dict, CustomDictionary):
              custom_dict = CustomDictionary(custom_dict)
          text = custom_dict.apply_to_text(text)
      text = self._sanitize_input(text)
      ...
  ```

### M0-3: Python — 互換テスト拡充 → [チケット](tickets/M0-3-expand-compat-tests.md)

- **ファイル**: `src/python/g2p/tests/test_compat.py`
- **現状**: JA トークン互換 + PUA 一致 + JA ID マップ一致 + EN 出力一致 (4 テスト)
- **追加**: ZH/KO/ES/FR/PT/SV の phonemize 出力一致テスト、multilingual ID マップ一致テスト

### M0-4: Rust — piper-g2p encode に動的 EOS トークン対応 → [チケット](tickets/M0-4-rust-dynamic-eos.md)

- **ファイル**: `src/rust/piper-g2p/src/encode.rs`
- **問題**: `PiperEncoder` は固定 EOS (`$`) のみ。日本語は `?`, `?!`, `?.`, `?~` を使う
- **修正**: `encode_with_prosody()` に `eos_token: Option<&str>` パラメータ追加、
  または `PiperEncoder::new()` で EOS を設定可能にする

---

## M1: Python 移行 — piper_train が piper_g2p を使う

> **目的**: `piper_train/phonemize/` の全 import を `piper_g2p` に置換し、旧コードを削除
> **影響範囲**: `src/python/piper_train/` 内 8 ファイル + `src/python/pyproject.toml`
> **見積り**: 中〜大
> **前提**: M0 完了

### M1-1: 依存関係の追加 → [チケット](tickets/M1-1-add-piper-g2p-dependency.md)

- **ファイル**: `src/python/pyproject.toml`
- **変更**: `piper-g2p` を依存に追加
  ```toml
  dependencies = [
      "numpy<2.3",
      "piper-g2p",
  ]
  [project.optional-dependencies]
  train = [
      "piper-g2p[all]",
      ...
  ]
  ```

### M1-2: 低リスク import 置換 (drop-in) → [チケット](tickets/M1-2-drop-in-import-replacement.md)

以下は API が同一のため直接置換可能:

| ファイル | 旧 import | 新 import |
|---|---|---|
| `infer_onnx.py:31,62` | `from .phonemize.multilingual import UnicodeLanguageDetector` | `from piper_g2p import UnicodeLanguageDetector` |
| `infer_onnx.py:106` | `from .phonemize.registry import get_phonemizer` | `from piper_g2p import get_phonemizer` |
| `vits/lightning.py:177` | `from ..phonemize.registry import get_phonemizer` | `from piper_g2p import get_phonemizer` |
| `update_model_config.py:16` | `from piper_train.phonemize.token_mapper import FIXED_PUA_MAPPING, TOKEN2CHAR` | `from piper_g2p.encode.pua import FIXED_PUA_MAPPING, TOKEN2CHAR` |

### M1-3: ID マップ API 置換 → [チケット](tickets/M1-3-id-map-api-replacement.md)

旧 API は言語別関数、新 API は統一関数:

| 旧 | 新 |
|---|---|
| `get_japanese_id_map()` | `get_phoneme_id_map("ja")` |
| `get_bilingual_id_map()` | `get_phoneme_id_map("ja-en")` |
| `get_multilingual_id_map(["ja","en","zh",...])` | `get_phoneme_id_map("ja-en-zh-...")` |

**影響ファイル**:
- `preprocess.py:76,230,244`
- `tools/prepare_bilingual_dataset.py:25-30`
- `tools/add_prosody_features.py:16`
- `tools/prepare_multilingual_dataset.py:1213`

### M1-4: preprocess.py 音素化パイプライン リファクタ (最大リスク) → [チケット](tickets/M1-4-preprocess-pipeline-refactor.md)

**ファイル**: `src/python/piper_train/preprocess.py` (行 668-952)

2 つのパスが存在し、アーキテクチャが異なる:

**パス A: 日本語モノリンガル (行 668-801)**
```
現在: phonemize_japanese_with_prosody(text, custom_dict=...)
      → トークン列に BOS/EOS が埋め込み済み
      → post_process_ids() は呼ばれない (no-op)

移行後: JapanesePhonemizer(custom_dict=...).phonemize_with_prosody(text)
         → piper_g2p は BOS/EOS を埋め込まない (IPA-first)
         → PiperEncoder で BOS/EOS/padding を追加する必要あり
```

**パス B: マルチリンガル (行 803-952)**
```
現在: MultilingualPhonemizer.phonemize_with_prosody(text)
      → 各言語セグメントの BOS/EOS をストリップ
      → post_process_ids() で BOS/EOS/padding 追加 (動的 EOS トラッキング)

移行後: piper_g2p.MultilingualPhonemizer.phonemize_with_prosody(text)
         → 同様にストリップ
         → PiperEncoder.encode_with_prosody() で一括処理
```

**作業項目**:
1. パス A: `phonemize_japanese_with_prosody()` → `JapanesePhonemizer().phonemize_with_prosody()` + `PiperEncoder` 追加
2. パス B: `MultilingualPhonemizer` + `post_process_ids()` → `piper_g2p.MultilingualPhonemizer` + `PiperEncoder`
3. トークン → ID 変換ループ (行 737-743, 880-886) を `PiperEncoder.encode_with_prosody()` に統一
4. prosody の `dict` → `ProsodyInfo` 型統一 (piper_g2p は `ProsodyInfo` dataclass を返す)

### M1-5: tools/ スクリプト移行 → [チケット](tickets/M1-5-tools-scripts-migration.md)

- `tools/prepare_multilingual_dataset.py`: 行 279-390, 1213 の import 置換
- `tools/prepare_bilingual_dataset.py`: 行 24-30 の import 置換 + `remap_ja_phoneme_ids()` / `_add_inter_phoneme_padding()` を PiperEncoder に統合
- `tools/add_prosody_features.py`: 行 15-16 の import 置換

### M1-6: dead code 削除 → [チケット](tickets/M1-6-dead-code-removal.md)

- `inference_utils.py` の `JapaneseAccentProcessor` import (行 7) — **存在しないモジュール**を参照。削除
- `AccentController` クラス (行 110-189) — 動作不能。削除 or 将来の実装として Issue 化

### M1-7: 旧 phonemize ディレクトリ削除 → [チケット](tickets/M1-7-delete-old-phonemize-dir.md)

- **削除対象**: `src/python/piper_train/phonemize/` (24 ファイル全て)
  - `__init__.py`, `base.py`, `registry.py`, `token_mapper.py`, `custom_dict.py`
  - `japanese.py`, `english.py`, `chinese.py`, `korean.py`, `spanish.py`, `portuguese.py`, `french.py`, `swedish.py`
  - `multilingual.py`, `bilingual.py`
  - `jp_id_map.py`, `zh_id_map.py`, `ko_id_map.py`, `es_id_map.py`, `pt_id_map.py`, `fr_id_map.py`, `sv_id_map.py`
  - `bilingual_id_map.py`, `multilingual_id_map.py`
  - `accent_processor.py`
- **前提**: M1-2〜M1-6 が完了し、全テストが通ること

### M1-8: テスト・CI 対応 → [チケット](tickets/M1-8-test-ci-updates.md)

- `python-tests.yml` の依存インストールに `piper-g2p[all]` 追加
- `test_compat.py` を拡充して全言語の出力一致を検証
- 既存テストが piper_train.phonemize を直接 import している箇所を修正

---

## M2: Rust 移行 — piper-core が piper-g2p crate を使う

> **目的**: `piper-core/src/phonemize/` の言語実装を `piper-g2p` crate に置き換える
> **影響範囲**: `src/rust/piper-core/`
> **見積り**: 中
> **前提**: M0-4 完了

### M2-1: Cargo.toml の features 有効化 → [チケット](tickets/M2-1-enable-g2p-features.md)

- **ファイル**: `src/rust/piper-core/Cargo.toml`
- **変更**:
  ```toml
  # 現在:
  piper-g2p = { path = "../piper-g2p", features = [] }
  
  # 移行後:
  piper-g2p = { path = "../piper-g2p", features = ["all-languages"] }
  ```
- **注意**: `japanese` feature は `jpreprocess` を引き込む。`naist-jdic` は piper-core 側の feature gate で制御

### M2-2: adapter 層の作成 → [チケット](tickets/M2-2-create-adapter-layer.md)

piper-core の `Phonemizer` trait と piper-g2p の `Phonemizer` trait には 2 メソッドの差分がある:

| メソッド | piper-core | piper-g2p |
|---|---|---|
| `get_phoneme_id_map()` | あり (全言語 None 返却) | なし |
| `post_process_ids()` | あり (BOS/EOS/padding) | なし (PiperEncoder が担当) |
| `validate_input()` | なし | あり |

**解決策**: adapter struct を作成

```rust
// src/rust/piper-core/src/phonemize/adapter.rs
pub struct G2pAdapter {
    inner: Box<dyn piper_g2p::Phonemizer>,
}

impl crate::phonemize::Phonemizer for G2pAdapter {
    fn phonemize_with_prosody(&self, text: &str) -> Result<...> {
        self.inner.phonemize_with_prosody(text).map_err(Into::into)
    }
    fn get_phoneme_id_map(&self) -> Option<&PhonemeIdMap> { None }
    fn post_process_ids(&self, ids, prosody, id_map) -> ... {
        default_post_process_ids(ids, prosody, id_map, "$")
    }
    fn language_code(&self) -> &str { self.inner.language_code() }
}
```

**発見事項**: 全言語の `get_phoneme_id_map()` は `None` を返す (config.json を使う)。
日本語の `post_process_ids()` は no-op。これにより adapter は単純になる。

### M2-3: voice.rs のファクトリ書き換え → [チケット](tickets/M2-3-voice-factory-rewrite.md)

- **ファイル**: `src/rust/piper-core/src/voice.rs` (行 48-358)
- **変更**: `create_language_phonemizer()` 内の phonemizer 生成を piper-g2p のコンストラクタに置換
- **コンストラクタ対応表**:

| 言語 | piper-core (現在) | piper-g2p |
|---|---|---|
| ja | `JapanesePhonemizer::new_bundled()` | `piper_g2p::japanese::JapanesePhonemizer::new_bundled()` |
| en | `EnglishPhonemizer::new_with_dict(&path)` | `piper_g2p::english::EnglishPhonemizer::new_with_dict(&path)` |
| zh | `ChinesePhonemizer::new(&single, &phrases)` | `piper_g2p::chinese::ChinesePhonemizer::new(&single, &phrases)` |
| es/fr/pt/ko/sv | `XxxPhonemizer::new()` | `piper_g2p::xxx::XxxPhonemizer::new()` |

各生成後に `G2pAdapter` でラップする。

### M2-4: phoneme_converter.rs の統合 → [チケット](tickets/M2-4-phoneme-converter-consolidation.md)

- **現在**: `piper-core/src/phonemize/phoneme_converter.rs` の `tokens_to_ids()` / `prosody_to_features()`
- **piper-g2p**: `piper_g2p::encode` に同一関数あり
- **変更**: piper-core 側を削除し、piper-g2p の encode を re-export

### M2-5: MultilingualPhonemizer の統合 → [チケット](tickets/M2-5-multilingual-phonemizer-consolidation.md)

- **現在**: `piper-core/src/phonemize/multilingual.rs` (~1000 行)
  - `UnicodeLanguageDetector` + `segment_text()` + `default_post_process_ids()` + `MultilingualPhonemizer` + `PassthroughPhonemizer`
- **piper-g2p**: 同等の実装あり
- **変更**: piper-g2p の MultilingualPhonemizer を adapter でラップして使用
- **注意**: `PassthroughPhonemizer` (辞書未検出時のフォールバック) は piper-core 固有。残すか piper-g2p に移植

### M2-6: custom_dict.rs の統合 → [チケット](tickets/M2-6-custom-dict-consolidation.md)

- API はほぼ同一 (piper-g2p 側に 10MB 制限あり)
- piper-core 側を削除し、piper-g2p の custom_dict を使用
- error 型変換は既存の `From<G2pError> for PiperError` で対応

### M2-7: 旧 phonemize ディレクトリ削除 → [チケット](tickets/M2-7-delete-old-phonemize-files.md)

- **削除対象**: `src/rust/piper-core/src/phonemize/` 内の言語実装ファイル
  - `english.rs`, `chinese.rs`, `japanese.rs`, `korean.rs`, `spanish.rs`, `french.rs`, `portuguese.rs`, `swedish.rs`
  - `custom_dict.rs`, `token_map.rs` (re-export のみ残す or 削除)
  - `phoneme_converter.rs`
- **残す**: `mod.rs` (adapter + trait 定義), `multilingual.rs` (adapter 経由に書き換え)

### M2-8: テスト・CI 対応 → [チケット](tickets/M2-8-test-ci-updates.md)

- `test_token_map_parity.rs` (96 PUA マッピングの一致検証) が引き続きパスすることを確認
- `rust-tests.yml`: feature 変更による影響確認 (jpreprocess ビルド時間)
- piper-core 統合テスト (24 ファイル) の動作確認

---

## M3: JS/WASM 移行 — openjtalk-web が @piper-plus/g2p を使う

> **目的**: `SimpleUnifiedPhonemizer` を `G2P` クラスに置換し、deprecated コードを削除
> **影響範囲**: `src/wasm/openjtalk-web/`
> **見積り**: 小〜中
> **前提**: M0 完了

### M3-1: PiperPlus 初期化の切り替え → [チケット](tickets/M3-1-piperplus-init-switch.md)

- **ファイル**: `src/wasm/openjtalk-web/src/index.js` (行 257-268)
- **変更**:
  ```javascript
  // Before:
  this._phonemizer = new SimpleUnifiedPhonemizer();
  await this._phonemizer.initialize({ openjtalk: { dictData, voiceData } });
  this._phonemizer.setPhonemeIdMap(this._config.phoneme_id_map);
  
  // After:
  const { G2P } = await import('@piper-plus/g2p');
  this._g2p = await G2P.create({
    languages: Object.keys(this._config.language_id_map || { ja: 0 }),
    jaDict: { dictData, voiceData },
  });
  this._encoder = new Encoder(this._config.phoneme_id_map);
  ```

### M3-2: _textToPhonemeIds() の統一 → [チケット](tickets/M3-2-unify-text-to-phoneme-ids.md)

- **ファイル**: `src/wasm/openjtalk-web/src/index.js` (行 282-329)
- **現在**: JA/EN はトークン返却 → `_phonemesToIds()`、ZH/KO/ES/FR/PT/SV は ID 直接返却 (分岐あり)
- **移行後**: 全言語で `G2P.encode(text, phonemeIdMap, { language })` → `{ phonemeIds, prosodyFlat }` に統一
- **メリット**: BOS/EOS/PAD 挿入が自動化、言語分岐が不要に

### M3-3: prosody 抽出の統合 → [チケット](tickets/M3-3-prosody-extraction-consolidation.md)

- **現在**: `_extractProsodyFromLabels()` (行 336-368) で OpenJTalk ラベルから A1/A2/A3 を独自抽出
- **移行後**: `G2P.encode()` が prosodyFlat を返すため不要
- **削除**: `_extractProsodyFromLabels()` メソッド

### M3-4: テスト更新 (11 ファイル) → [チケット](tickets/M3-4-test-updates.md)

- mock を `G2P` API に合わせて更新 (`test/helpers/create-mock-phonemizer.js`)
- `test-piper-plus-boundary.js` (13+ テスト): `_phonemesToIds()` テスト → `Encoder` テスト
- `test-korean.js`, `test-swedish.js`: `SimpleUnifiedPhonemizer` → `G2P` インスタンス
- `test-piper-plus.js`: export チェック更新

### M3-5: deprecated コード削除 → [チケット](tickets/M3-5-deprecated-code-removal.md)

- **削除対象**:
  - `src/wasm/openjtalk-web/src/simple_unified_api.js` (692 行) — 既に `@deprecated` 記載
  - `src/wasm/openjtalk-web/src/simple_english_phonemizer.js` (157 行)
  - `src/wasm/openjtalk-web/src/japanese_phoneme_extract.js` (155 行)
  - `src/wasm/openjtalk-web/src/phonemizer.js` (63 行) — レガシー
  - `src/wasm/openjtalk-web/src/unified_api.js` (100+ 行) — レガシー
  - `src/wasm/openjtalk-web/src/unified_api_with_espeak.js` (36 行) — レガシー
- **注意**: `SimpleUnifiedPhonemizer` は public export されている。breaking change となるため CHANGELOG に記載

### M3-6: CI 対応 → [チケット](tickets/M3-6-ci-updates.md)

- `npm-publish.yml` のテストコマンド更新
- `g2p-wasm-ci.yml` は変更不要 (standalone G2P の CI)
- package.json の `@piper-plus/g2p` 依存は既に `file:../g2p` で宣言済み

---

## M4: 検証・クリーンアップ

> **目的**: 全プラットフォームの移行が正しいことを検証し、ドキュメントを更新
> **前提**: M1〜M3 完了

### M4-1: クロスプラットフォーム互換テスト → [チケット](tickets/M4-1-cross-platform-compat-tests.md)

- Python/Rust/JS で同一テキストを phonemize し、出力トークン列が一致することを検証
- 共有テストフィクスチャ (`data/test-fixtures/`) の活用

### M4-2: 音声品質の回帰テスト → [チケット](tickets/M4-2-audio-quality-regression.md)

- つくよみちゃんモデルで移行前後の推論結果を比較
- phoneme_ids が完全一致すれば音声は同一

### M4-3: CLAUDE.md 更新 → [チケット](tickets/M4-3-update-claude-md.md)

- 「ファイルパス」セクションから旧 phonemize パスを削除
- piper_g2p への依存関係を記載
- 「実装済み機能 > 多言語 Phonemizer」セクション更新

### M4-4: 削除ファイル数の確認 → [チケット](tickets/M4-4-final-verification.md)

| プラットフォーム | 削除ファイル数 | 削除行数 (概算) |
|---|---|---|
| Python | 24 ファイル (`piper_train/phonemize/`) | ~4,000 行 |
| Rust | 12 ファイル (`piper-core/src/phonemize/`) | ~3,500 行 |
| JS/WASM | 6 ファイル (deprecated phonemizers) | ~1,200 行 |
| **合計** | **42 ファイル** | **~8,700 行** |

---

## 依存関係グラフ

```
M0 (API ギャップ修正)
├── M0-1: _get_question_type 修正
├── M0-2: custom_dict パラメータ追加
├── M0-3: 互換テスト拡充
└── M0-4: Rust 動的 EOS 対応
    │
    ├──→ M1 (Python 移行)
    │    ├── M1-1: 依存追加
    │    ├── M1-2: drop-in 置換
    │    ├── M1-3: ID マップ API 置換
    │    ├── M1-4: preprocess.py リファクタ ← 最大リスク
    │    ├── M1-5: tools/ 移行
    │    ├── M1-6: dead code 削除
    │    ├── M1-7: 旧ディレクトリ削除
    │    └── M1-8: テスト・CI
    │
    ├──→ M2 (Rust 移行)      ※ M1 と並行可能
    │    ├── M2-1: features 有効化
    │    ├── M2-2: adapter 層作成
    │    ├── M2-3: voice.rs 書き換え
    │    ├── M2-4: phoneme_converter 統合
    │    ├── M2-5: MultilingualPhonemizer 統合
    │    ├── M2-6: custom_dict 統合
    │    ├── M2-7: 旧ディレクトリ削除
    │    └── M2-8: テスト・CI
    │
    └──→ M3 (JS/WASM 移行)   ※ M1 と並行可能
         ├── M3-1: PiperPlus 初期化切り替え
         ├── M3-2: _textToPhonemeIds 統一
         ├── M3-3: prosody 統合
         ├── M3-4: テスト更新
         ├── M3-5: deprecated 削除
         └── M3-6: CI 対応

M1 + M2 + M3 ──→ M4 (検証・クリーンアップ)
```

---

## リスク・注意事項

### 高リスク項目

1. **preprocess.py の日本語モノリンガルパス (M1-4)**
   - piper_train の日本語 phonemizer は BOS/EOS をトークン列に埋め込む
   - piper_g2p は IPA-first で BOS/EOS を埋め込まない
   - 移行時に PiperEncoder を追加しないと BOS/EOS が欠落し **学習データが壊れる**

2. **日本語の動的 EOS トークン (M0-1, M0-4)**
   - `?`, `?!`, `?.`, `?~` の 4 種類 + `$` (非疑問文)
   - マルチリンガル時は最後のセグメントの EOS を全体の EOS として使う
   - PUA マッピング経由で 1 文字に変換される

3. **piper_train の post_process_ids が日本語 no-op (M1-4)**
   - 日本語の `post_process_ids()` は意図的に no-op (BOS/EOS は phonemizer が追加済み)
   - 他言語は `post_process_ids()` で BOS/EOS/padding を追加
   - 移行後は PiperEncoder が全言語で統一的に処理するため、日本語パスの特殊ケースが消える

### 中リスク項目

4. **BilingualPhonemizer の後方互換 (M1-3)**
   - `get_bilingual_id_map()` は piper_g2p の `get_phoneme_id_map("ja-en")` に対応
   - 旧データセットの `config.json` との互換性を確認

5. **Rust PassthroughPhonemizer (M2-5)**
   - 辞書ファイル未検出時のフォールバック (piper-core 固有)
   - piper-g2p に移植するか piper-core に残すか判断が必要

6. **JS/WASM の public API 変更 (M3-5)**
   - `SimpleUnifiedPhonemizer` は public export
   - 削除は breaking change → semver major bump or deprecation period

### 低リスク項目

7. **PUA マッピング一致**: test_compat.py + test_token_map_parity.rs で検証済み (96 エントリ完全一致)
8. **registry API**: module-level 関数は同一シグネチャ
9. **CustomDictionary**: 両実装で API 同一 (piper_g2p 側に 10MB 制限あり)
