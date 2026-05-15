# Python (Canonical) — ZH-EN Loanword 実装

> Index: [`README.md`](README.md)

Python は ZH-EN code-switching の **canonical source of truth**。学習側 (`src/python/g2p/piper_plus_g2p/`) とランタイム側 (`src/python_run/piper/phonemize/`) 両方で実装済 (PR #397)。他 5 ランタイムは Python から byte-for-byte 同期。

## 1. 実装ファイル

| 用途 | パス |
|------|------|
| Phonemizer 本体 (学習側) | `src/python/g2p/piper_plus_g2p/chinese.py` |
| Phonemizer 本体 (ランタイム側) | `src/python_run/piper/phonemize/chinese.py` |
| 辞書データ (canonical) | `src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json` |
| 辞書データ (mirror) | `src/python_run/piper/phonemize/data/zh_en_loanword.json` |
| テスト | `src/python/g2p/tests/test_zh_en_loanword.py` (~698 行) |

## 2. JSON 同期 CI 戦略

**問題**: **7 箇所** (Python 学習側 / Python ランタイム側 / Rust 2 crate (`piper-plus-g2p` + `piper-core`) / Go / C# / WASM / C++) に同じ JSON が分散する。

> 注: 実際の mirror は 10 箇所まで拡大済 (Kotlin/Android + Swift G2P 追加)。最新は `docs/spec/loanword-mirrors.toml` を参照。

**既存パターン**: `pua.json` の同期は `check_pua_consistency.py` + `/check-pua` skill + pre-commit hook で実現済み (commit `3a38a61f`, `96138922`, `90ff6390`)。これを踏襲する。

**4 案比較**:

| 案 | 工数 | CI 速度 | 開発体験 | Windows 対応 |
|---|-----|---------|---------|------------|
| **A** | 各ランタイム側 unit test で byte 比較 | ★★ | 手動同期必要 | ◯ |
| **B** | 専用 CI job で sha256 比較 | ★ | CI 報告のみ | ◯ |
| **C** | 自動 sync スクリプト + pre-commit hook | ★★★ | ベスト | △ (CRLF 注意) |
| **D** | symlink で single source 化 | ★ | ベスト | ✗ (Windows 非対応) |

**推奨**: **案 A + B のハイブリッド** — 既存 PUA 同期戦略を踏襲しつつ、CI で hash 比較を最終ガード

**段階構成**:

```text
段階 1: Python 既存テスト保持 (TestRuntimeBundleSync) - 0.5h
段階 2: 各ランタイムに schema 検証 + byte 比較テスト追加 - 3h
段階 3: 専用 CI job で sha256 hash 比較 - 1h
段階 4: ドキュメント / QA - 1h

合計: ~5.5h
```

**新規 CI job (案)**:

```yaml
# .github/workflows/loanword-consistency.yml
name: Loanword Dictionary Sync
on:
  pull_request:
    paths:
      - '**/zh_en_loanword.json'
      - '.github/workflows/loanword-consistency.yml'
jobs:
  hash-consistency:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - name: Verify byte-for-byte sync
        run: |
          SOURCE=src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json
          HASH=$(sha256sum "$SOURCE" | cut -d' ' -f1)
          COPIES=(
            src/python_run/piper/phonemize/data/zh_en_loanword.json
            src/rust/piper-plus-g2p/data/zh_en_loanword.json
            src/rust/piper-core/data/zh_en_loanword.json
            src/go/phonemize/data/zh_en_loanword.json
            src/csharp/PiperPlus.Core/Phonemize/Data/zh_en_loanword.json
            src/wasm/g2p/data/zh_en_loanword.json
            src/cpp/data/zh_en_loanword.json
          )
          for copy in "${COPIES[@]}"; do
            [ -f "$copy" ] || { echo "MISSING: $copy"; exit 1; }
            COPY_HASH=$(sha256sum "$copy" | cut -d' ' -f1)
            [ "$HASH" = "$COPY_HASH" ] || {
              echo "MISMATCH: $copy"
              echo "Expected: $HASH"
              echo "Got:      $COPY_HASH"
              exit 1
            }
          done
          echo "All 7 copies match $SOURCE"
```

**新規 helper script (PUA パターン踏襲)**:

```python
# scripts/check_loanword_consistency.py (PUA 同等)
# 使い方: python scripts/check_loanword_consistency.py [--fix]
# --fix オプションで Python source から自動コピー
```

これで `/check-loanword` skill 化して開発者体験を向上できる (将来課題)。

## 3. 後方互換性戦略

**Breaking change 評価**: **なし** (詳細分析済)

| 既存ユースケース | 影響 | 対策 |
|----------------|------|------|
| ZH のみ使用 | なし | 設定不要、既存挙動維持 |
| EN のみ使用 | なし | 設定不要、既存挙動維持 |
| ZH-EN mixed (新機能歓迎) | 改善 | デフォルト有効 |
| ZH-EN mixed (英語発音維持希望) | 影響あり | **opt-out flag が必要** |

**Python (PR #397) で確認済み**:

- `test_multilingual_pure_zh_unaffected`: 純 ZH は同一出力
- `test_multilingual_pure_english_uses_english_path`: 純 EN は EnglishPhonemizer 経路
- 既存 g2p テスト 791 件全 PASS、リグレッションなし

**opt-out flag 設計**:

各ランタイムに `enable_zh_en_dispatch` (default `True`) を追加し、既存ユーザーが旧挙動 (英語発音) を維持できる経路を提供する:

```python
# Python
MultilingualPhonemizer(
    languages=["zh", "en"],
    default_latin_language="en",
    enable_zh_en_dispatch=True,        # NEW: opt-out 用 flag (default ON)
    zh_en_loanword_dict_paths=None,    # NEW: カスタム辞書
)
```

```rust
// Rust
MultilingualPhonemizer::builder()
    .languages(vec!["zh", "en"])
    .enable_zh_en_dispatch(true)       // NEW: builder pattern 推奨
    .build()
```

```go
// Go
func NewMultilingualPhonemizer(opts ...Option) *MultilingualPhonemizer
WithZhEnDispatch(enabled bool) Option   // NEW: functional options
```

```csharp
// C#
new MultilingualPhonemizer(
    languages: new[] { "zh", "en" },
    enableZhEnDispatch: true            // NEW
);
```

```typescript
// TypeScript
new G2P({ languages: ["zh", "en"], enableZhEnDispatch: true })
```

**Phase 戦略**:

| Phase | 内容 | 期間 |
|-------|------|------|
| **Phase 1 (本 PR)** | 全ランタイムに default-on で機能展開、opt-out flag は Python のみ追加 (リファレンス) | 本 PR |
| **Phase 2** | 各ランタイムに opt-out flag 追加 (互換性 100% 保証) | フォローアップ |
| **Phase 3** | Beta 期間 (1 minor version) でフィードバック収集 | 1-2 ヶ月 |

**API ドキュメント更新ガイドライン**:

```markdown
##### ZH-EN Code-Switching (v0.5.0+)

MultilingualPhonemizer で中国語に隣接する英単語を自動検出し、
英語発音ではなく Mandarin pinyin で発音します。

例:
  p.phonemize("请打开 GPS")
    → GPS = "ji4 pi4 ai1 si4" (pinyin via tone markers)

カスタマイズ:
  - 無効化: enable_zh_en_dispatch=False
  - カスタム辞書: zh_en_loanword_dict_paths=[Path("my_dict.json")]
```

**将来機能との API 整合性**:

| Phase | 機能 | API 追加 | 既存影響 |
|-------|------|---------|--------|
| A1 (本 PR) | ZH-EN code-switching | `enable_zh_en_dispatch` | なし |
| A2 | プロソディ平滑化 | `prosody_smooth=True` | 独立 |
| A3 | 言語切替トークン | `insert_language_tags=True` | 独立 |
| B | Fine-tuning コーパス | (新規パイプライン) | 独立 |

設計原則: **新規機能は opt-in flag で統一、既存 API 非修飾**。

## 4. データセット拡張運用フロー

**目的**: 将来 `acronyms` / `loanwords` の追加要望が来た時の管理プロセスを定める。

**PR テンプレート追記** (`.github/PULL_REQUEST_TEMPLATE.md`):

```markdown
##### Dictionary Update (if zh_en_loanword.json modified)

- [ ] 新規エントリは **標準 Mandarin pinyin** + tone marker (1-5) で記述
- [ ] 参考辞書を PR description に明記 (MDBG / Pleco / 新华字典 等)
- [ ] **7 箇所すべて** (Rust 2 crate 含む) で同期 (CI `zh-en-loanword-sync` で自動検証)
- [ ] テスト追加 (`test_zh_en_loanword.py` の TestSchemaValidation pattern)
- [ ] 既存エントリとの重複検証 (CI で自動)
- [ ] エントリ数 sanity check 通過 (acronyms ≥ 50, loanwords ≥ 30)
```

**新規 GitHub Issue テンプレート** (`.github/ISSUE_TEMPLATE/dict-request.yml`):

```yaml
name: Dictionary Entry Request (ZH-EN)
description: 新規 acronym/loanword エントリのリクエスト
labels: ["dict", "enhancement", "zh-en"]
body:
  - type: input
    id: token
    attributes:
      label: English Token
      placeholder: "e.g., ChatGPT, GitHub"
    validations: { required: true }
  - type: textarea
    id: pinyin
    attributes:
      label: Proposed Pinyin (tone付き)
      placeholder: "e.g., chai4 ti2 ji4 pi4 ti4"
    validations: { required: true }
  - type: dropdown
    id: category
    attributes:
      label: Category
      options:
        - acronym (e.g., GPS, USB)
        - loanword (e.g., Python, iPhone)
        - new letter mapping
    validations: { required: true }
  - type: input
    id: reference
    attributes:
      label: Reference Source
      placeholder: "MDBG, Pleco, 新华字典 等"
    validations: { required: true }
```

**レビュー基準**:

| 評価軸 | OK | NG |
|-------|----|----|
| pinyin の正確性 | 標準 Mandarin pinyin + tone | 非標準音 / tone なし |
| 重複検証 | 既存エントリと衝突なし | 重複あり |
| 文化的適切性 | 中立、商標侵害なし | ヘイト用語、政治的バイアス |
| 出典 | 信頼できる辞書 | 出典なし |

**Schema バージョン bump ルール**:

| 変更 | version bump | 理由 |
|------|------------|------|
| エントリ追加のみ | **不要** (v1 維持) | backward compatible |
| 既存エントリの修正 | **不要** (v1 維持) | 出力が変わるが構造同じ |
| 新フィールド追加 | **必要** (v2) | スキーマ拡張 |
| フィールド削除 | **必要** (v2) | breaking |

**自動 CI 検証** (`zh-en-loanword-sync.yml` 拡張):

```yaml
- name: Pinyin syntax + duplicate detection
  run: python scripts/validate_loanword_dict.py src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json
```

```python
# scripts/validate_loanword_dict.py
def validate(path):
    data = json.load(open(path))
    seen = {}
    for section in ("acronyms", "loanwords", "letter_fallback"):
        for key, syllables in data[section].items():
            # 1. 重複検出
            if key in seen:
                raise ValueError(f"Duplicate: {key} in {seen[key]} and {section}")
            seen[key] = section
            # 2. tone marker 検証
            for syl in syllables:
                if not syl[-1].isdigit() or not 1 <= int(syl[-1]) <= 5:
                    raise ValueError(f"{section}.{key}: invalid tone in {syl!r}")
            # 3. IPA 変換可能性 (phonemize_from_pinyin_syllables で)
            try:
                phonemize_from_pinyin_syllables(syllables)
            except Exception as e:
                raise ValueError(f"{section}.{key}: IPA conversion failed: {e}")
```

**実装工数**: PR テンプレート 5 分、Issue テンプレート 10 分、CI スクリプト 20 分 = **~35 分**
