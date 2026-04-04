# WASM G2P チケット一覧

> **マイルストーン:** [wasm-g2p-implementation-milestones.md](../wasm-g2p-implementation-milestones.md)
> **ギャップ分析:** [wasm-g2p-zh-fr-pt-gap-analysis.md](../wasm-g2p-zh-fr-pt-gap-analysis.md)

## 進捗サマリ

| チケット | Phase | 言語 | ステータス | 依存 |
|---------|-------|------|----------|------|
| [WASM-G2P-ES](./WASM-G2P-ES.md) | 1 | スペイン語 | 未着手 | なし |
| [WASM-G2P-FR](./WASM-G2P-FR.md) | 2 | フランス語 | 未着手 | なし |
| [WASM-G2P-PT](./WASM-G2P-PT.md) | 3 | ポルトガル語 | 未着手 | なし |
| [WASM-G2P-ZH](./WASM-G2P-ZH.md) | 4 | 中国語 | 未着手 | なし |
| [WASM-G2P-TEST](./WASM-G2P-TEST.md) | 5 | 横断 | 未着手 | Phase 1-4 |

## 並列化マップ

```
Phase 1 (ES) ──┐
Phase 2 (FR) ──┼── Phase 5 (テスト統合)
Phase 3 (PT) ──┘         │
Phase 4 (ZH) ────────────┘
```

Phase 1-3 は **3エージェント同時並行**可能。Phase 4 は独立開始可能。
