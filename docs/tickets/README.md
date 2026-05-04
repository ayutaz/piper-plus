# Tickets

piper-plus の実装チケット管理。チケットは [`docs/spec/`](../spec/) のマイルストーン仕様から派生する個別実装単位を定義し、PR との紐付けを明示する。

> **本書は進捗の Single Source of Truth (SoT)**。各チケット先頭の `状態` および仕様書 §8 の状態行はここを参照する形に統一されている。マイルストーン完了時は本表のみ更新すれば全ドキュメントに伝搬する。

## チケット ⇄ マイルストーン 相互紐付け

| チケット | マイルストーン (仕様) | 親 Issue | 状態 | 想定 PR / 実装時間 (Claude Code) | PR |
|---------|---------------------|---------|------|------------------------------|-----|
| [377-M1-ort-fetch-fix](377-M1-ort-fetch-fix.md) | [M1: 取得経路の修復](../spec/ios-shared-lib.md#m1-取得経路の修復-release-ジョブの解凍) | [#377](https://github.com/ayutaz/piper-plus/issues/377) | pending | ~60-80 行 / 1-2h + CI ~20m | — |
| [377-M2-xcframework](377-M2-xcframework.md) | [M2: xcframework 化](../spec/ios-shared-lib.md#m2-xcframework-化-配布形式の実用化) | [#377](https://github.com/ayutaz/piper-plus/issues/377) | pending | ~180-230 行 / 2-4h + CI ~30m | — |
| [377-M3-docs-migration](377-M3-docs-migration.md) | [M3: ドキュメント・移行ガイド整備](../spec/ios-shared-lib.md#m3-ドキュメント移行ガイド整備) | [#377](https://github.com/ayutaz/piper-plus/issues/377) | pending | ~440 行 / 1-2h + lint ~10m | — |
| [377-M4-spm-package](377-M4-spm-package.md) | [M4: SPM パッケージ併設](../spec/ios-shared-lib.md#m4-将来-swift-package-manager-パッケージ併設) | [#377](https://github.com/ayutaz/piper-plus/issues/377) | pending | ~50-80 行 / 1-2h + resolve ~15m | — |

**道 A 確定** (2026-05-04): 全 4 マイルストーンを本ブランチで実装。M4 は §11 推奨に従い案 X (本体 repo `Package.swift` 単一管理) を主仕様とする。総実装時間 5-10 時間 + CI サイクル時間。Apple Silicon Mac は本セッションで使用不可、CI 完結フロー。

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

- **本書 README の表が Single Source of Truth (SoT)**。各 PR でこの表のみ更新すれば、他文書 (チケット先頭 `状態:` / 仕様書 §8) は自動的に同期される (両者は本書を参照する形に統一済)
- 状態列の値は以下のいずれかに統一:
  - `pending` (未着手)
  - `in progress (PR #XXX)` (実装中)
  - `done (PR #XXX, YYYY-MM-DD)` (完了)
  - `blocked (理由: ...)` (停止)
- マイルストーン完了 PR では本表の該当行のみ更新。仕様書 §8 のチェックボックス (`[ ]` → `[x]`) は spec 冒頭 Status の更新タイミング (M3 完了時に `Implemented (v1.13.0)` へ) のみで併せて更新

## 利用者観測タイムライン (道 A 確定後の運用)

M3 完了から **6 ヶ月以内** に iOS 利用者の実数を把握し、追加対応の要否を判断する。観測手段:

- GitHub Releases API の `download_count` 週次収集 (`gh api repos/ayutaz/piper-plus/releases --jq '...'`)
- Issue / Discussions での「iOS で動かした」報告の集計
- Discord 言及 (任意)

判断ゲート:
- ≥ 10 DL/月 または ≥ 2 件/月 の活動 → visionOS / Mac Catalyst / .dSYM 別配布など M5 候補を起票
- ≤ 1 DL/月 かつ Issue 0 件 → iOS 拡張投資を停止、現状維持で運用
- 6 ヶ月起点は **M3 完了 PR マージ日** (リマインダー登録は M3 §12.4 マージ後アクションを参照)

## 関連仕様

- [iOS Shared Library Distribution Specification](../spec/ios-shared-lib.md) — Plan A 採用方針とマイルストーン定義
- [ONNX Runtime Version Matrix](../spec/ort-versions.md) — ランタイム別 ORT バージョン管理
