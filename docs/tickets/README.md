# Tickets

piper-plus の実装チケット管理。チケットは [`docs/spec/`](../spec/) のマイルストーン仕様から派生する個別実装単位を定義し、PR との紐付けを明示する。

## チケット ⇄ マイルストーン 相互紐付け

| チケット | マイルストーン (仕様) | 親 Issue | 状態 | PR |
|---------|---------------------|---------|------|-----|
| [377-M1-ort-fetch-fix](377-M1-ort-fetch-fix.md) | [M1: 取得経路の修復](../spec/ios-shared-lib.md#m1-取得経路の修復-release-ジョブの解凍) | [#377](https://github.com/ayutaz/piper-plus/issues/377) | pending | — |
| [377-M2-xcframework](377-M2-xcframework.md) | [M2: xcframework 化](../spec/ios-shared-lib.md#m2-xcframework-化-配布形式の実用化) | [#377](https://github.com/ayutaz/piper-plus/issues/377) | pending | — |
| [377-M3-docs-migration](377-M3-docs-migration.md) | [M3: ドキュメント・移行ガイド整備](../spec/ios-shared-lib.md#m3-ドキュメント移行ガイド整備) | [#377](https://github.com/ayutaz/piper-plus/issues/377) | pending | — |
| [377-M4-spm-package](377-M4-spm-package.md) | [M4: SPM パッケージ併設](../spec/ios-shared-lib.md#m4-将来-swift-package-manager-パッケージ併設) | [#377](https://github.com/ayutaz/piper-plus/issues/377) | pending (別 issue 化想定) | — |

## ファイル命名規約

```
docs/tickets/
├── README.md                              ← 本書 (一覧 + 紐付け)
├── <issue>-<milestone>-<slug>.md          ← 個別チケット
│   例: 377-M1-ort-fetch-fix.md
└── _template.md                           ← (任意) 新規チケット作成用テンプレ
```

- `<issue>`: 親 GitHub Issue 番号
- `<milestone>`: 仕様文書中のマイルストーン ID (`M1`, `M2`, ...)
- `<slug>`: 短い英小文字スラッグ (kebab-case)

## チケット標準セクション

各チケットは以下のセクションを順番に持つ:

1. **メタ情報** — マイルストーン/Issue/ブランチ/PR/状態の相互リンク
2. **タスク目的とゴール** — Why と Done の宣言
3. **実装する内容の詳細** — ファイル単位の変更スコープ
4. **エージェントチームの役割と人数** — 作業分担
5. **提供範囲** — Included / Excluded
6. **テスト項目** — 検証する観点リスト
7. **Unit テストの内容** — 単体テストの追加・変更
8. **E2E テストの内容** — 結合・受け入れテストの追加・変更
9. **懸念事項** — リスクと未解決事項
10. **レビュー項目** — レビュアーが確認するチェックリスト
11. **一から作り直すとしたら** — フェーズの設計・実装・思想を白紙から再設計するなら何を選ぶか (批判的視点)
12. **後続タスクへの連絡事項** — 次フェーズへの引き継ぎ

「一から作り直すとしたら」は本プロジェクト固有のセクション。マイルストーン依存の積み上げに引きずられず、白紙からの最適解と現実解の差分を可視化することを目的とする。エージェントチームによる独立レビューで補強する。

## 進捗トラッキング規約

- チケット先頭の `状態:` を以下のいずれかに更新:
  - `pending` (未着手)
  - `in progress (PR #XXX)` (実装中)
  - `done (PR #XXX, YYYY-MM-DD)` (完了)
  - `blocked (理由: ...)` (停止)
- 状態更新時は本書 README の表も同期
- マイルストーン仕様 ([docs/spec/ios-shared-lib.md §8](../spec/ios-shared-lib.md#8-マイルストーン)) の状態行も併せて更新

## 関連仕様

- [iOS Shared Library Distribution Specification](../spec/ios-shared-lib.md) — Plan A 採用方針とマイルストーン定義
- [ONNX Runtime Version Matrix](../spec/ort-versions.md) — ランタイム別 ORT バージョン管理
