# 韓国語 (ko) 対応状況

> **作成日:** 2026-03-31
> **ブランチ:** `feat/korean-support`
> **目的:** 韓国語対応の実装済み/未対応箇所を整理し、追加作業を明確化する

---

## サマリ

| プラットフォーム | G2P実装 | 言語検出 | PUAマッピング | テスト | 総合 |
|:---|:---:|:---:|:---:|:---:|:---|
| **Python** | ✅ | ✅ | ✅ | ✅ 27件 | **完了** |
| **Rust** | ✅ | ✅ | ✅ | ✅ 35件 | **完了** |
| **C++** | ✅ | — | ✅ | — | **完了** |
| **C#** | ❌ | ✅ | ✅ | ❌ | **要実装** |
| **Go** | ❌ | ✅ | — | ❌ | **要実装** |
| **npm/WASM** | ❌ | ❌ | — | ❌ | **要実装** |
| **CI/ドキュメント** | — | — | — | — | **要更新** |

---

## 1. 実装済み (変更不要)

### 1.1 Python

| ファイル | 内容 |
|---------|------|
| `src/python/piper_train/phonemize/korean.py` | `KoreanPhonemizer` — g2pk2 + Hangul分解フォールバック (296行) |
| `src/python/piper_train/phonemize/ko_id_map.py` | `KOREAN_PHONEMES` — 韓国語固有音素リスト |
| `src/python/piper_train/phonemize/registry.py` | `register_language("ko", KoreanPhonemizer())` 登録済み |
| `src/python/piper_train/phonemize/multilingual.py` | Hangul検出 (`_RE_HANGUL`), `_has_ko` フラグ |
| `src/python/piper_train/phonemize/multilingual_id_map.py` | `LANGUAGE_PHONEMES["ko"]` 動的登録 |
| `src/python/piper_train/phonemize/token_mapper.py` | PUA: U+E04B-E052 (8エントリ) |
| `test/test_korean_phonemizer.py` | 27テスト (分解, prosody, g2pキャッシュ, NFD/NFC) |
| `pyproject.toml` | `multilingual` optional-deps に `g2pk2>=0.0.3` |

### 1.2 Rust

| ファイル | 内容 |
|---------|------|
| `src/rust/piper-core/src/phonemize/korean.rs` | `KoreanPhonemizer` — Hangul分解 + IPA変換 (925行) |
| `src/rust/piper-core/src/phonemize/mod.rs` | `pub mod korean;` 登録済み |
| `src/rust/piper-core/src/phonemize/token_map.rs` | PUA: U+E04B-E052 |
| `src/rust/piper-core/src/phonemize/multilingual.rs` | Hangul検出 (AC00-D7AF, 1100-11FF, 3130-318F) |
| `src/rust/piper-core/src/voice.rs` | `"ko" => KoreanPhonemizer::new()` |
| `src/rust/piper-cli/src/main.rs` | `SUPPORTED_LANGUAGES` に `"ko"` 含有 |
| テスト (korean.rs内) | 35テスト (分解, liaison, 경음, 내파음, 이중모음) |

### 1.3 C++

| ファイル | 内容 |
|---------|------|
| `src/cpp/korean_phonemize.hpp` | ヘッダ |
| `src/cpp/korean_phonemize.cpp` | Hangul分解 + IPA変換 |

### 1.4 ドキュメント (記載済み)

| ファイル | 内容 |
|---------|------|
| `docs/api-reference/phoneme-mapping.md` | 韓国語 (KO) 音素体系 — 8エントリ (U+E04B-E052) 完全記載 |

---

## 2. 未対応: C# 実装

### 2.1 既に準備済み (変更不要)

| ファイル | 内容 |
|---------|------|
| `UnicodeLanguageDetector.cs` | `IsHangul()` + `_hasKo` — Hangul検出完全実装 |
| `OpenJTalkToPiperMapping.cs` | PUA: U+E04B-E052 (8エントリ) 登録済み |
| `MultilingualPhonemizer.cs` | 汎用的 — phonemizerが登録されれば自動対応 |
| `UnicodeLanguageDetectorTests.cs` | `Hangul_DetectsKorean()`, `HangulJamo_Detected()` テスト済み |

### 2.2 新規作成が必要

| ファイル | 内容 | 参考 |
|---------|------|------|
| `PiperPlus.Core/Phonemize/IKoreanG2PEngine.cs` | G2Pエンジンインターフェース | `ISpanishG2PEngine.cs` |
| `PiperPlus.Core/Phonemize/KoreanG2PEngine.cs` | Hangul分解 + IPA変換エンジン | `SpanishG2PEngine.cs` |
| `PiperPlus.Core/Phonemize/KoreanPhonemizer.cs` | `IPhonemizer` 実装 | `SpanishPhonemizer.cs` |
| `PiperPlus.Core.Tests/KoreanPhonemizerTests.cs` | xUnitテスト (40+件想定) | `SpanishPhonemizerTests.cs` |

### 2.3 既存ファイルの修正が必要

| ファイル | 修正内容 |
|---------|---------|
| `PiperPlus.Cli/Program.cs` | `ResolveTextModePhonemizer()` に `case "ko":` 追加 |
| `PiperPlus.Cli/Program.cs` | `--language` ヘルプテキストに `ko` 追加 |

---

## 3. 未対応: Go 実装

### 3.1 既に準備済み (変更不要)

| ファイル | 内容 |
|---------|------|
| `phonemize/unicode_detect.go` | `hasKO` + Hangul検出 (AC00-D7AF, 1100-11FF, 3130-318F) |
| `phonemize/unicode_detect_test.go` | Hangul検出テスト (境界値, 未登録時) 9件 |
| `phonemize/phonemizer.go` | `Phonemizer` インターフェース (言語中立) |

### 3.2 新規作成が必要

| ファイル | 内容 | 参考 |
|---------|------|------|
| `phonemize/korean.go` | `KoreanPhonemizer` — Hangul分解 + IPA変換 (推定250-400行) | `spanish.go` |
| `phonemize/korean_test.go` | ユニットテスト (30+件想定) | `spanish_test.go` |

### 3.3 既存ファイルの修正が必要

| ファイル | 修正内容 |
|---------|---------|
| `piperplus/synthesize.go` | `phonemizerForLanguage()` に `case "ko":` 追加 |
| `cmd/piper-plus/main.go` | `--language` ヘルプテキストに `ko` 追加 |
| `phonemize/phonemizer.go` | `ProsodyInfo` コメントに ko の A1/A2/A3 仕様追加 |

---

## 4. 未対応: npm/WASM 実装

### 4.1 既に準備済み

なし — 韓国語関連コードは一切含まれていない。

### 4.2 既存ファイルの修正が必要

| ファイル | 修正内容 |
|---------|---------|
| `types/index.d.ts` | `Language` 型に `'ko'` 追加 |
| `src/simple_unified_api.js` | `_classifyChar()` に Hangul範囲追加 |
| `src/simple_unified_api.js` | `textToPhonemes()` に `ko` ケース追加 |
| `src/simple_unified_api.js` | `phonemizeKorean()` メソッド新規追加 |
| `src/index.js` | `_textToPhonemeIds()` の言語リストに `ko` 追加 |
| `src/index.js` | JSDoc の言語リスト更新 |
| `package.json` | description + keywords に Korean 追加 |

### 4.3 新規作成が必要

| ファイル | 内容 | 参考 |
|---------|------|------|
| `test/js/test-korean.js` | 言語検出 + 音素化テスト (30+件想定) | `test-swedish.js` |

---

## 5. 未対応: CI/ドキュメント更新

### 5.1 ドキュメント

| ファイル | 修正内容 |
|---------|---------|
| `README.md` | 「7言語」→「8言語」、言語リストに韓国語追加 |
| `README_EN.md` | 同上 (英語版) |
| `README_ZH.md` | 同上 (中国語版) |
| `README_FR.md` | 同上 (フランス語版) |
| `src/wasm/openjtalk-web/README.npm.md` | 言語数・Language型・テーブルに韓国語追加 |
| `docs/guides/testing/multilingual-testing.md` | テスト対象言語に韓国語追加 |
| `CLAUDE.md` | フォネマイザーテーブル + ファイルパスに韓国語追加 |

### 5.2 CI ワークフロー

| ファイル | 修正内容 |
|---------|---------|
| `.github/workflows/test-multilingual-tts.yml` | テスト対象言語リストに `ko` 追加 (モデル対応後) |

> **注意:** Python/Rust/C#/Go の CI ワークフローは言語をコード内で定義しているため、ワークフロー自体の修正は不要。テストファイルが追加されれば自動実行される。

---

## 6. モデル/データセット (コード対応外)

| 項目 | 状態 | 備考 |
|------|------|------|
| 韓国語学習データ | ❌ 未準備 | KSS、AI-Hub等のコーパス選定が必要 |
| テストモデル (ko含有) | ❌ なし | 現在の `multilingual-test-medium.onnx` は6言語 (ko未含有) |
| 言語ID | 未割当 | `ko=7` が有力候補 (sv=6の次) |

---

## 実装順序 (推奨)

```
Phase 1: C# 実装 (Python参照実装をミラー)
  1.1 IKoreanG2PEngine + KoreanG2PEngine
  1.2 KoreanPhonemizer
  1.3 Program.cs 統合
  1.4 KoreanPhonemizerTests

Phase 2: Go 実装
  2.1 korean.go (Phonemizer)
  2.2 synthesize.go 統合
  2.3 korean_test.go

Phase 3: npm/WASM 実装
  3.1 言語検出 + 型定義
  3.2 phonemizeKorean()
  3.3 test-korean.js

Phase 4: ドキュメント + CI
  4.1 README系更新 (全言語版)
  4.2 CLAUDE.md 更新
  4.3 テストガイド更新
```

---

## 韓国語 G2P の仕様 (全プラットフォーム共通)

### 音素インベントリ (PUA: U+E04B-E052)

| PUA | IPA | 説明 |
|-----|-----|------|
| U+E04B | p͈ | 경음 (tensed bilabial, ㅃ) |
| U+E04C | t͈ | 경음 (tensed alveolar, ㄸ) |
| U+E04D | k͈ | 경음 (tensed velar, ㄲ) |
| U+E04E | s͈ | 경음 (tensed sibilant, ㅆ) |
| U+E04F | t͈ɕ | 경음 (tensed alveolo-palatal, ㅉ) |
| U+E050 | k̚ | 내파음 (unreleased velar) |
| U+E051 | t̚ | 내파음 (unreleased alveolar) |
| U+E052 | p̚ | 내파음 (unreleased bilabial) |

### Prosody 値

| フィールド | 値 | 説明 |
|-----------|-----|------|
| A1 | 0 | 韓国語にピッチアクセントなし |
| A2 | 0 | 韓国語にレキシカルストレスなし |
| A3 | Hangul音節数 | 単語内のハングル字数 |

### Hangul 分解

初声 (19) × 中声 (21) × 終声 (28, 含む空終声) = 11,172 音節 (U+AC00-D7A3)

```
syllable_index = code - 0xAC00
initial  = syllable_index / (21 * 28)  → 초성 IPA
medial   = (syllable_index / 28) % 21  → 중성 IPA
final    = syllable_index % 28         → 종성 IPA (0 = なし)
```

### 연음화 (Liaison)

終声 + 다음音節の初声がㅇの場合、終声が次の初声に移動する。
例: `한국어` → `han.gu.gʌ` (ㄱ が ㅇ に連音)
