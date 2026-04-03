# M5-13: ステータスコード enum 化

> **Phase:** 5 -- 品質改善
> **利用者視点の優先度:** 低 -- デバッガ表示の改善 + 型安全性
> **見積り:** 小
> **依存:** Phase 1 完了 (M1-5)
> **ブロック:** なし
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

現在のステータスコードは `#define` マクロで定義されている。これを `typedef enum` に変更し、デバッガでのシンボル名表示と型安全性を改善する。

**現状:**

```c
#define PIPER_PLUS_OK          0
#define PIPER_PLUS_DONE        1
#define PIPER_PLUS_ERR        (-1)
#define PIPER_PLUS_ERR_MODEL  (-2)
#define PIPER_PLUS_ERR_CONFIG (-3)
#define PIPER_PLUS_ERR_TEXT   (-4)
#define PIPER_PLUS_ERR_BUSY   (-5)
```

`#define` ではデバッガに `-1` としか表示されず、どのエラーか識別困難。

**ゴール:** `typedef enum PiperPlusStatus` に変更し、関数の戻り値型を `PiperPlusStatus` にする。ABI 互換: `enum` の基底型は `int` (C99) で `int32_t` と同サイズ。

---

## 2. 実装する内容の詳細

### 2.1 piper_plus.h の変更

```c
/* ===== Status codes ===== */

typedef enum PiperPlusStatus {
    PIPER_PLUS_OK          =  0,
    PIPER_PLUS_DONE        =  1,
    PIPER_PLUS_ERR         = -1,
    PIPER_PLUS_ERR_MODEL   = -2,
    PIPER_PLUS_ERR_CONFIG  = -3,
    PIPER_PLUS_ERR_TEXT    = -4,
    PIPER_PLUS_ERR_BUSY    = -5
} PiperPlusStatus;
```

関数宣言の戻り値を `int32_t` から `PiperPlusStatus` に変更:

```c
PIPER_PLUS_API PiperPlusStatus piper_plus_synthesize(
    PiperPlusEngine              *engine,
    const char                   *text,
    const PiperPlusSynthOptions  *opts,
    float                       **out_samples,
    int32_t                      *out_num_samples,
    int32_t                      *out_sample_rate);

// ... 他の全関数も同様
```

### 2.2 piper_plus_c_api.cpp の変更

関数の戻り値型を `int32_t` から `PiperPlusStatus` に変更:

```cpp
PIPER_PLUS_API PiperPlusStatus piper_plus_synthesize(...) {
    // ...
    return PIPER_PLUS_OK;
}
```

### 2.3 ABI 互換性の保証

- C99: `enum` のサイズは `int` (通常 4 bytes = `int32_t`) -- ABI 互換
- C++: `enum` のサイズは実装定義だが、負値を含むため `signed int` と同等
- 既存の FFI バインディングが `int32_t` で受け取っている場合、値は変わらないため互換

### 2.4 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `src/cpp/piper_plus.h` | `#define` を `typedef enum PiperPlusStatus` に変更、全関数の戻り値型を変更 |
| `src/cpp/piper_plus_c_api.cpp` | 全関数の戻り値型を `PiperPlusStatus` に変更 |

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | マクロ -> enum 変換 + テスト |

合計 1 名。

---

## 4. 提供範囲とテスト項目

### ユニットテスト

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestStatusEnumSize` | `sizeof(PiperPlusStatus) == sizeof(int32_t)` | true |
| `TestStatusValues` | 各 enum 値が期待値と一致 | `OK=0`, `DONE=1`, `ERR=-1` 等 |
| `TestStatusEnumC99` | C99 モードでヘッダーがコンパイル可能 | コンパイル成功 |

### 回帰テスト

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| 既存全テスト | 戻り値の比較が引き続き動作 | 全パス (`int32_t` との暗黙変換) |

---

## 5. 懸念事項とレビュー項目

| リスク | 影響度 | 対策 |
|--------|--------|------|
| C++ で `enum` サイズが `int` と異なるコンパイラ | 極低 | GCC/Clang/MSVC の全メジャーコンパイラで `int` サイズ。念のため `static_assert(sizeof(PiperPlusStatus) == sizeof(int32_t))` を追加 |
| Dart FFI が `int32_t` ではなく `enum` 型を期待する可能性 | 低 | Dart `ffigen` は C enum を `int` にマッピングする。値は変わらないため互換 |
| `#define` を参照している既存コードが壊れる | 低 | `enum` メンバー名は `#define` と同一のため、`if (rc == PIPER_PLUS_ERR)` のようなコードはそのまま動作 |

### レビュー時の確認項目

1. 全関数の戻り値型が `PiperPlusStatus` に変更されていること
2. `#define` が完全に削除されていること (重複定義を防ぐ)
3. `static_assert` で enum サイズが `int32_t` と一致することを保証
4. テスト内の `int32_t rc = ...` が `PiperPlusStatus rc = ...` に更新されていること

---

## 6. 一から作り直すとしたら

C11 の `_Static_assert` や C++ の `enum class : int32_t` を使う方がより厳密。ただし C99 互換を維持するため、plain `enum` + `static_assert` (C++側) の組み合わせが最も広い互換性を持つ。

---

## 7. 後続タスクへの連絡事項

- M5-12 (`_reserved` 追加) と同じリリースで実施するのが効率的 (ヘッダーの ABI 関連変更をまとめる)。
- 将来のステータスコード追加時は `enum` にメンバーを追加するだけで済む (`#define` の名前衝突リスクがない)。
