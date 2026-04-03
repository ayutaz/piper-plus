# M5-9: SynthOptions ゼロ初期化対策

> **Phase:** 5 -- 品質改善
> **利用者視点の優先度:** 中 -- FFI 利用者が `memset(&opts, 0, sizeof(opts))` するのは一般的
> **見積り:** 小
> **依存:** Phase 1 完了 (M1-6)
> **ブロック:** なし
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

FFI 利用者 (Dart, Godot, Swift) が `PiperPlusSynthOptions` をゼロ初期化 (`memset` / `calloc`) した場合、`noise_scale=0.0`, `length_scale=0.0`, `noise_w=0.0` となり、VITS モデルが無音または異常音声を生成する。ゼロ値をデフォルト値に置換する安全策を追加する。

**現状:** `applySynthOptions()` はゼロ値をそのまま `synthConfig` に設定する。`noise_scale=0` は完全な決定論的推論 (品質低下)、`length_scale=0` はゼロ長音声 (無音) を生成する。

**ゴール:** `applySynthOptions()` で `noise_scale`, `length_scale`, `noise_w` が `0.0` の場合にデフォルト値 (`0.667`, `1.0`, `0.8`) に置換する。

---

## 2. 実装する内容の詳細

### 2.1 piper_plus_c_api.cpp (`applySynthOptions`) の変更

```cpp
static void applySynthOptions(piper::SynthesisConfig &synthConfig,
                              const PiperPlusSynthOptions *opts) {
    PiperPlusSynthOptions effectiveOpts;
    if (opts) {
        effectiveOpts = *opts;
    } else {
        effectiveOpts = piper_plus_default_options();
    }

    // Zero-init safety: replace 0.0 with sensible defaults
    if (effectiveOpts.noise_scale == 0.0f)
        effectiveOpts.noise_scale = 0.667f;
    if (effectiveOpts.length_scale == 0.0f)
        effectiveOpts.length_scale = 1.0f;
    if (effectiveOpts.noise_w == 0.0f)
        effectiveOpts.noise_w = 0.8f;

    // ... (rest unchanged)
}
```

### 2.2 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `src/cpp/piper_plus_c_api.cpp` | `applySynthOptions` にゼロ値チェックを追加 |

**変更不要:** `piper_plus.h` (構造体定義は変更なし)

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | ゼロ値チェック追加 + テスト |

合計 1 名。

---

## 4. 提供範囲とテスト項目

### ユニットテスト (モデル不要)

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestZeroInitOptions` | `memset(&opts, 0, sizeof(opts))` で合成呼び出し | クラッシュなし (モデル不要テストでは引数チェックのみ) |
| `TestDefaultOptionsNotZero` | `piper_plus_default_options()` の各フィールド | `noise_scale=0.667`, `length_scale=1.0`, `noise_w=0.8` |

### E2E テスト (モデル必要)

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestZeroInitSynthesizes` | ゼロ初期化 opts で合成 | 音声データが生成される (num_samples > 0) |
| `TestZeroInitMatchesDefault` | ゼロ初期化 vs `default_options()` | 同一の音声出力 |

---

## 5. 懸念事項とレビュー項目

| リスク | 影響度 | 対策 |
|--------|--------|------|
| 意図的に `noise_scale=0` (決定論的推論) を使いたいユーザー | 低 | 極めて稀なユースケース。必要なら `noise_scale=0.001` 等の微小値を使用可能。ドキュメントに注記 |
| `sentence_silence_sec=0` は意図的な設定の可能性 | 低 | `sentence_silence_sec` はゼロ値でも安全 (無音なし) のため置換しない |

### レビュー時の確認項目

1. `noise_scale`, `length_scale`, `noise_w` の 3 フィールドのみ置換すること
2. `speaker_id=0`, `language_id=0`, `sentence_silence_sec=0` は置換しないこと
3. ヘッダーの構造体コメントにゼロ初期化安全の注記を追加すること

---

## 6. 一から作り直すとしたら

構造体にバージョンフィールド (`uint32_t struct_size`) を追加し、利用者が `opts.struct_size = sizeof(PiperPlusSynthOptions)` を設定する設計。サイズが一致しないフィールドはデフォルト値で埋める。Win32 API の `cbSize` パターン。ただし Phase 5 の範囲では `_reserved` フィールドの存在で ABI 拡張は可能なため、ゼロ値チェックの方がシンプル。

---

## 7. 後続タスクへの連絡事項

- ヘッダー (`piper_plus.h`) の `PiperPlusSynthOptions` コメントに「ゼロ初期化安全: `noise_scale`, `length_scale`, `noise_w` が 0 の場合はデフォルト値に置換されます」を追加すること。
