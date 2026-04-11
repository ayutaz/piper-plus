# Issue #346 チケット一覧

> **マイルストーン:** [milestones-346-cpp-cjk-closing-bracket.md](../milestones-346-cpp-cjk-closing-bracket.md)
> **調査レポート:** [investigation-346-cpp-cjk-closing-bracket.md](../investigation-346-cpp-cjk-closing-bracket.md)
> **Issue:** [#346](https://github.com/ayutaz/piper-plus/issues/346)
> **ブランチ:** `fix/cpp-cjk-closing-bracket-346`

## チケット依存関係

```
M1 ─→ M2 ─→ M3 ─→ M4
```

## チケット一覧

| チケット | タイトル | 対象ファイル | 状態 |
|---------|---------|------------|------|
| [M1](M1-add-isClosingPunctuation-helper.md) | `isClosingPunctuation()` ヘルパー追加 | `piper.cpp` | pending |
| [M2](M2-add-closing-bracket-consumption-loop.md) | 閉じ括弧消費ループ追加 | `piper.cpp` | pending |
| [M3](M3-update-test-mirror-and-add-tests.md) | テストミラー更新 + テスト10個追加 | `test_split_sentences.cpp` | pending |
| [M4](M4-ci-verification-and-pr.md) | CI 検証 + PR 作成 | - | pending |

## 変更ファイルサマリ

- `src/cpp/piper.cpp` — M1 + M2
- `src/cpp/tests/test_split_sentences.cpp` — M3
- ヘッダー変更なし、CMake 変更なし、依存追加なし
