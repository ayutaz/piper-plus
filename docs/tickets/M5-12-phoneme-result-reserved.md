# M5-12: PiperPlusPhonemeResult._reserved 追加

> **Phase:** 5 -- 品質改善
> **利用者視点の優先度:** 低 -- ABI 安定性のための予防措置
> **見積り:** 小
> **依存:** M4-3 (G2P API)
> **ブロック:** なし
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Done

---

## 1. タスク目的とゴール

`PiperPlusPhonemeResult` に `_reserved[4]` フィールドを追加し、将来のフィールド追加時に ABI 互換を維持できるようにする。

**現状:** `PiperPlusPhonemeResult` は `phonemes`, `language`, `num_phonemes` の 3 フィールドのみで、`_reserved` パディングがない。将来フィールドを追加する場合、構造体サイズが変わり ABI 互換が破壊される。

```c
// 現在
typedef struct PiperPlusPhonemeResult {
    const char *phonemes;
    const char *language;
    int32_t     num_phonemes;
} PiperPlusPhonemeResult;
```

**対比:** `PiperPlusConfig` は `_reserved[7]`, `PiperPlusSynthOptions` は `_reserved[8]` を持ち、ABI パディングが確保されている。

**ゴール:** `PiperPlusPhonemeResult` に `_reserved[4]` を追加し、他の構造体と同等の ABI 安定性を確保する。

---

## 2. 実装する内容の詳細

### 2.1 piper_plus.h の変更

```c
typedef struct PiperPlusPhonemeResult {
    const char *phonemes;      /**< Space-separated IPA phoneme string (BORROWED) */
    const char *language;      /**< Detected language code (BORROWED) */
    int32_t     num_phonemes;  /**< Number of phoneme tokens */
    int32_t     _reserved[4];  /**< Must be zero -- reserved for future fields */
} PiperPlusPhonemeResult;
```

### 2.2 piper_plus_c_api.cpp の変更

`piper_plus_phonemize()` 内で `out_result` を返す前に `_reserved` をゼロ初期化:

```cpp
std::memset(out_result->_reserved, 0, sizeof(out_result->_reserved));
```

### 2.3 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `src/cpp/piper_plus.h` | `PiperPlusPhonemeResult` に `_reserved[4]` 追加 |
| `src/cpp/piper_plus_c_api.cpp` | `piper_plus_phonemize` で `_reserved` ゼロ初期化 |

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | フィールド追加 + テスト |

合計 1 名。

---

## 4. 提供範囲とテスト項目

### ユニットテスト

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestPhonemeResultSize` | `sizeof(PiperPlusPhonemeResult)` の確認 | ポインタ x2 + int32_t x5 = 期待サイズ |
| `TestPhonemeResultReservedZero` | `piper_plus_phonemize` 後の `_reserved` | 全要素が 0 |

### 回帰テスト

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| 既存 M4-3 テスト | `piper_plus_phonemize` の既存テスト | 全パス |

---

## 5. 懸念事項とレビュー項目

| リスク | 影響度 | 対策 |
|--------|--------|------|
| 構造体サイズ変更による既存 FFI バインディングの破壊 | 高 | **M4-3 がまだ未リリースの場合は問題なし**。リリース済みの場合は API バージョンインクリメントが必要 |
| `PiperPlusPhonemeInfo`, `PiperPlusTimingResult` にも `_reserved` がない | 低 | 同時に追加を検討。ただし BORROWED ポインタ構造体は読み取り専用のため優先度低 |

### レビュー時の確認項目

1. `_reserved` のサイズ (4) が将来の拡張に十分か (候補: `phoneme_ids`, `confidence`, `duration_ms`, `lang_id`)
2. 既存の FFI バインディング (Dart `ffigen` 等) が再生成されること
3. `memset` で `_reserved` がゼロ初期化されること

---

## 6. 一から作り直すとしたら

全構造体に対して一貫した `_reserved` サイズポリシーを定義すべき。`PiperPlusConfig` (7), `PiperPlusSynthOptions` (8), `PiperPlusPhonemeResult` (4) とサイズが不統一。統一ルール (例: 全構造体 `_reserved[8]`) があれば判断が容易。

---

## 7. 後続タスクへの連絡事項

- `PiperPlusPhonemeInfo` と `PiperPlusTimingResult` (M4-2) にも `_reserved` を追加するかは別途検討。これらは BORROWED ポインタ構造体で利用者が初期化するものではないため、優先度は低い。
- M5-13 (ステータスコード enum 化) と同じリリースで実施するのが効率的 (ヘッダーの ABI 変更をまとめる)。
