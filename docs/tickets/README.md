# HTS Voice 依存除去 — チケット管理

> **ブランチ:** `feature/remove-hts-voice-dependency`
> **参照:** [調査結果](../remove-hts-voice-dependency.md) | [マイルストーン](../remove-hts-voice-milestones.md)

## 進捗サマリー

| マイルストーン | チケット | 状態 | 削除行数 | 新規テスト |
|--------------|---------|------|---------|-----------|
| [M1: C++ ランタイム](M1-cpp-runtime.md) | M1-001 | :white_large_square: 未着手 | ~230 | 0 (既存安全網) |
| [M2: WASM G2P + openjtalk-web](M2-wasm-g2p.md) | M2-001 | :white_large_square: 未着手 | ~200 | 0 (既存安全網) |
| [M3: CI / CMake](M3-ci-cmake.md) | M3-001 | :white_large_square: 未着手 | ~100 | 0 |
| [M4: テスト + クリーンアップ](M4-tests-cleanup.md) | M4-001 | :white_large_square: 未着手 | ~50 | 6 |
| **合計** | **4 チケット** | | **~580** | **6** |

## 依存関係グラフ

```
M1 (C++ ランタイム)          ──┐
                               ├── M3 (CI/CMake) ──┐
M2 (WASM G2P + openjtalk-web) ─┘                   ├── M4 (テスト + クリーンアップ)
                                                    │
                                                    └── dev へマージ
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
