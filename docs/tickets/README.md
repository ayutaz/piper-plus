# HTS Voice 依存除去 — チケット管理

> **ブランチ:** `feature/remove-hts-voice-dependency`
> **参照:** [調査結果](../remove-hts-voice-dependency.md) | [マイルストーン](../remove-hts-voice-milestones.md)

## 進捗サマリー

| マイルストーン | チケット | 状態 | 削除行数 | 新規テスト |
|--------------|---------|------|---------|-----------|
| [M1: C++ ランタイム](M1-cpp-runtime.md) | M1-001 | :white_check_mark: 完了 | ~230 | 0 (既存安全網) |
| [M2: WASM G2P + openjtalk-web](M2-wasm-g2p.md) | M2-001 | :white_check_mark: 完了 | ~200 | 0 (既存安全網) |
| [M3: CI / CMake](M3-ci-cmake.md) | M3-001 | :white_large_square: 未着手 | ~120 (+93行ファイル削除) | 0 |
| [M4: テスト + クリーンアップ](M4-tests-cleanup.md) | M4-001 | :white_large_square: 未着手 | ~50 | 9 |
| **合計** | **4 チケット** | | **~600 (+93行ファイル削除)** | **9** |

## 依存関係グラフ

```
M1 (C++ ランタイム) ── M3 (CI/CMake) ──┐
                                        ├── M4 (テスト + クリーンアップ) ── dev マージ
M2 (WASM G2P + openjtalk-web) ─────────┘
```

## 状態凡例

| アイコン | 状態 |
|---------|------|
| :white_large_square: | 未着手 |
| :construction: | 作業中 |
| :mag: | レビュー中 |
| :white_check_mark: | 完了 |

## チケット一覧

1. **[M1-001](M1-cpp-runtime.md)** — C++ ランタイムから HTS voice フォールバックを除去
2. **[M2-001](M2-wasm-g2p.md)** — WASM G2P + openjtalk-web から voice 依存を除去
3. **[M3-001](M3-ci-cmake.md)** — CI ワークフロー・CMake から HTS 依存を除去
4. **[M4-001](M4-tests-cleanup.md)** — テスト追加 + クリーンアップ + バージョンバンプ

## マージ順序ガイドライン

M1 と M2 は並行開発可能だが、dev へのマージは以下の順序を推奨:

1. **M1** (C++ ランタイム) — M3 の前提条件
2. **M3** (CI/CMake) — M1 完了が前提
3. **M2** (WASM G2P) — M1/M3 とは独立だが、M4 の前に完了させる
4. **M4** (テスト + クリーンアップ) — M1/M2/M3 全完了が前提
