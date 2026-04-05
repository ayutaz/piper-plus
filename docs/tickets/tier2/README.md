# CPU 推論 Tier 2 Quick Wins — チケット一覧

> **ブランチ**: `feat/cpu-inference-tier2-quick-wins`
> **設計書**: [cpu-inference-tier2-design.md](../../guides/cpu-inference-tier2-design.md)
> **マイルストーン**: [cpu-inference-tier2-milestones.md](../../guides/cpu-inference-tier2-milestones.md)

---

## 進捗サマリ

| チケット | タイトル | ステータス | 依存 |
|----------|---------|-----------|------|
| [M1](M1-python-warmup.md) | Python Warmup 実装 | 完了 | なし |
| [M2](M2-cpp-warmup.md) | C++ Warmup 実装 | 完了 | M1 (参照、並行可) |
| [M3](M3-python-model-cache.md) | Python 最適化モデルキャッシュ | 完了 | M1 |
| [M4](M4-japanese-phonemize-cache.md) | 日本語音素化キャッシュ | 完了 | なし (M1/M3 後が望ましい) |
| [M5](M5-integration.md) | 最終統合・CI・PR | 完了 | M1, M2, M3, M4 |

## 依存関係図

```
M1 (Python Warmup) ──┬──→ M3 (Model Cache) ──┐
                     │                        ├──→ M5 (Integration)
M2 (C++ Warmup) ─────┤                        │
                     │                        │
M4 (JA Cache) ───────┴────────────────────────┘
```

## 実装順序

```
M1 → M2 (並行可) → M3 → M4 → M5
```
