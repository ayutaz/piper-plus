# 韓国語 (ko) 対応状況

> **作成日:** 2026-03-31
> **更新日:** 2026-04-01
> **ブランチ:** `feat/korean-support`
> **ステータス:** 全プラットフォーム実装済み

---

## サマリ

| プラットフォーム | G2P実装 | 言語検出 | PUAマッピング | テスト | 総合 |
|:---|:---:|:---:|:---:|:---:|:---|
| **Python** | ✅ | ✅ | ✅ | ✅ 27件 | **完了** |
| **Rust** | ✅ | ✅ | ✅ | ✅ 35件 | **完了** |
| **C++** | ✅ | — | ✅ | — | **完了** |
| **C#** | ✅ | ✅ | ✅ | ✅ | **完了** |
| **Go** | ✅ | ✅ | ✅ | ✅ | **完了** |
| **npm/WASM** | ✅ | ✅ | ✅ | ✅ | **完了** |
| **CI/ドキュメント** | — | — | — | — | **更新済み** |

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

## 2. 実装済み: C#

| ファイル | 内容 |
|---------|------|
| `PiperPlus.Core/Phonemize/KoreanPhonemizer.cs` | `IPhonemizer` 実装 |
| `PiperPlus.Core/Phonemize/KoreanG2PEngine.cs` | Hangul分解 + IPA変換エンジン |
| `PiperPlus.Core/Phonemize/IKoreanG2PEngine.cs` | G2Pエンジンインターフェース |
| `PiperPlus.Core.Tests/KoreanPhonemizerTests.cs` | xUnitテスト |
| `PiperPlus.Cli/Program.cs` | `case "ko":` 統合済み |

---

## 3. 実装済み: Go

| ファイル | 内容 |
|---------|------|
| `phonemize/korean.go` | `KoreanPhonemizer` -- Hangul分解 + IPA変換 + liaison |
| `phonemize/korean_test.go` | ユニットテスト |
| `piperplus/synthesize.go` | `case "ko":` 統合済み |

---

## 4. 実装済み: npm/WASM

| ファイル | 内容 |
|---------|------|
| `src/simple_unified_api.js` | `phonemizeKorean()` -- Hangul Jamo 分解 |
| `src/index.js` | direct-ID 言語リストに `ko` 追加済み |
| `types/index.d.ts` | `Language` 型に `'ko'` 追加済み |
| `test/js/test-korean.js` | 言語検出 + 音素化テスト |

---

## 5. ドキュメント/CI (更新済み)

README系 (全言語版)、CLAUDE.md、npm README、テストガイド -- 全て韓国語対応に更新済み。

---

## 6. モデル/データセット (コード対応外)

| 項目 | 状態 | 備考 |
|------|------|------|
| 韓国語学習データ | ❌ 未準備 | KSS、AI-Hub等のコーパス選定が必要 |
| テストモデル (ko含有) | ❌ なし | 現在の `multilingual-test-medium.onnx` は6言語 (ko未含有) |
| 言語ID | 未割当 | `ko=7` が有力候補 (sv=6の次) |

---

## 実装完了

全フェーズ (C#, Go, npm/WASM, ドキュメント/CI) が実装済み。残作業はモデル/データセットのみ。

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
