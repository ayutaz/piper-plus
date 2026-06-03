# Swedish per-word LID: 全ランタイム同期設計

**ステータス**: Implemented (Issue #539)
**親 Issue**: [#539](https://github.com/ayutaz/piper-plus/issues/539) (Swedish per-word LID parity)

スウェーデン語 (sv) の **単語単位 言語判定 (per-word language detection)** を全 7 ランタイムで統一する。ZH-EN loanword (Issue #384) と同じ「Python canonical + byte-for-byte mirror + CI sync gate」構造に従う。

---

## 1. 背景 (回帰の経緯)

`å`/`ä`/`ö` を含む sv 語 (例: `så` / `och` / `för` / `är`) が、canonical Python と Rust の G2P で **英語と誤判定**されていた。

- **#297**: 全ランタイムに per-word Swedish LID を追加。
- **#300**: g2p パッケージ抽出時に Python / Rust から silent に脱落 (回帰)。
- 残存していた C++ / C# / Go コピーはその後 drift、WASM は char-level の別アプローチを使用。

本対応で全ランタイムを **保守的ポリシーで再実装・統一**する。

---

## 2. 保守的ポリシー

単語が Swedish と判定されるのは、以下のいずれかを満たす場合のみ:

| 条件 | 強度 | 内容 |
|------|------|------|
| `strong_chars` 一致 | strong | `å` / `Å` を含む |
| `function_words` 完全一致 | strong | 46 語の function-word リストに一致 (大小無視) |

> **`ä` / `ö` 単独は weak**: 独語 / フィンランド語 / 借用語と共有されるため、これらだけでは Swedish 判定に**不十分** (= `strong_chars` に含めない)。誤検出を抑える設計。

---

## 3. Canonical + ミラー

- **Source of truth**: `src/python/g2p/piper_plus_g2p/data/sv_function_words.json`
- **Schema**: `{ schema_version, strong_chars: list[str], function_words: list[str] }`。Forward-compat: 全ランタイムの loader が未知の top-level フィールドと `schema_version` の不在/将来値 (例: `2`) を silently 受理 (ZH-EN loanword loader と同じ stance)。

### 7 データミラー (byte-for-byte)

| ランタイム | パス |
|-----------|------|
| Python canonical | `src/python/g2p/piper_plus_g2p/data/sv_function_words.json` |
| Python runtime | `src/python_run/piper/phonemize/data/sv_function_words.json` |
| Rust (`piper-plus-g2p`) | `src/rust/piper-plus-g2p/data/sv_function_words.json` |
| Rust (`piper-core`) | `src/rust/piper-core/data/sv_function_words.json` |
| Go | `src/go/phonemize/data/sv_function_words.json` |
| C# | `src/csharp/PiperPlus.Core/Phonemize/Data/sv_function_words.json` |
| WASM (`@piper-plus/g2p`) | `src/wasm/g2p/data/sv_function_words.json` |
| C++ | `src/cpp/data/sv_function_words.json` |

### 6 fixture ミラー (cross-runtime parity matrix)

`tests/fixtures/g2p/swedish_lid_matrix.json` を canonical とし、各ランタイムが同一 fixture をロードして「`languages=[en,sv]` / `default_latin=en` で segmentation した結果に `sv` が含まれるか」を assert する。Python は canonical を直接読む (mirror なし)。Go / C# / C++ / WASM / Rust×2 が mirror。

---

## 4. CI sync gate

- **gate**: `Swedish LID Sync Gate / json-sync` (`.github/workflows/swedish-lid-sync.yml`)
- **script**: `scripts/check_swedish_lid_consistency.py` (mirror 宣言は `docs/spec/swedish-lid-mirrors.toml`)
- 7 データミラー + 6 fixture ミラーの byte-for-byte 一致と JSON schema を強制。`--fix` で canonical → ミラーへ伝播 (idempotent)。

---

## 5. 影響範囲

学習済み 6lang モデルは **sv を含まない**ため、デフォルト推論は不変。本機能は **独立 G2P 用途** (`piper-plus-g2p` / `@piper-plus/g2p` 等) と **将来の sv モデル**に影響する。
