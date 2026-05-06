# ZH-EN Code-Switching 全ランタイム展開 — マイルストーン INDEX

> **親 Issue**: [#384](https://github.com/ayutaz/piper-plus/issues/384)
> **親 PR (Python 完了済み)**: [#397](https://github.com/ayutaz/piper-plus/pull/397)
> **設計書**: [docs/spec/zh-en-loanword-runtime-rollout.md](../../spec/zh-en-loanword-runtime-rollout.md) (1956 行 / v9 / 24 深堀り項目)
> **作業ブランチ**: `feat/zh-en-loanword-runtimes`

このドキュメントは設計書から派生したチケット群の進捗ハブです。各チケットはマイルストーン (Day 番号) と相互に紐付き、依存関係および進捗を一望できます。

---

## 1. ゴール

5 ランタイム (Rust / Go / C# / JS-WASM / C++) で `[zh, en, *]` パターンの英語トークンを Mandarin pinyin に変換する機能を、Python 実装 ([#397](https://github.com/ayutaz/piper-plus/pull/397)) と byte-for-byte 一致する出力にする。

**主要 KPI**:
- Issue [#384](https://github.com/ayutaz/piper-plus/issues/384) 例 3 件 (`请打开 GPS` / `我喜欢用 Python 写代码` / `让我用 ChatGPT 写代码`) が全 5 ランタイムで Python と同じ IPA 列を返す
- `zh_en_loanword.json` が 6 箇所 (Python 学習 / Python ランタイム / Rust / Go / C# / WASM-data / C++) で byte-for-byte 一致 (CI ガード)
- 性能オーバーヘッドが既存純中国語経路に対して < 5%

---

## 2. 全体ロードマップ

```
Day 1-3   ┃ Phase 1: Rust    (R1-R5, ~600 LOC)            [TICKET-01]
Day 4-5   ┃ Phase 2: Go      (G1-G5, ~355 LOC)            [TICKET-02]
Day 6-8   ┃ Phase 3: C#      (C1-C4, ~460 LOC)            [TICKET-03]
Day 9     ┃ Phase 4: JS/WASM (W2-W5, ~250 LOC)            [TICKET-04]
Day 10-12 ┃ Phase 5: C++     (P1-P6, ~810 LOC)            [TICKET-05]
Day 13    ┃ Phase 6: CI 同期 (X5)                          [TICKET-06]
Day 14    ┃ Phase 7: Docs/Release (CHANGELOG/README/API)   [TICKET-07]
```

総コード量目安: **~2,300 行** (テスト含む) / 期間目安: **2 週間**。

---

## 3. チケット一覧

| # | チケット | ランタイム | LOC | 依存 | ステータス | 担当エージェントチーム |
|---|---------|----------|-----|------|----------|----------------------|
| 01 | [TICKET-01-rust.md](TICKET-01-rust.md) | Rust | ~600 | なし | 📝 Draft | Lead × 1, Rust Core × 2, QA × 1 |
| 02 | [TICKET-02-go.md](TICKET-02-go.md) | Go | ~355 | なし | 📝 Draft | Lead × 1, Go Dev × 1, QA × 1 |
| 03 | [TICKET-03-csharp.md](TICKET-03-csharp.md) | C# | ~460 | なし | 📝 Draft | Lead × 1, C# Dev × 2, QA × 1 |
| 04 | [TICKET-04-wasm.md](TICKET-04-wasm.md) | JS/WASM | ~250 | TICKET-01 | 📝 Draft | Lead × 1, WASM Dev × 1, JS Dev × 1, QA × 1 |
| 05 | [TICKET-05-cpp.md](TICKET-05-cpp.md) | C++ | ~810 | なし | 📝 Draft | Lead × 1, C++ Dev × 2, Mobile × 1, QA × 1 |
| 06 | [TICKET-06-ci-sync.md](TICKET-06-ci-sync.md) | CI | ~150 | TICKET-01〜05 | 📝 Draft | Lead × 1, DevOps × 1 |
| 07 | [TICKET-07-docs.md](TICKET-07-docs.md) | Docs | ~300 | TICKET-01〜06 | 📝 Draft | Lead × 1, Tech Writer × 1 |

**ステータス凡例**: 📝 Draft / 🚧 In Progress / 👀 Review / ✅ Done / ⏸ Blocked

---

## 4. 進捗ダッシュボード

```
[Phase 1] Rust      ░░░░░░░░░░░░░░░░░░░░  0%   📝 Draft
[Phase 2] Go        ░░░░░░░░░░░░░░░░░░░░  0%   📝 Draft
[Phase 3] C#        ░░░░░░░░░░░░░░░░░░░░  0%   📝 Draft
[Phase 4] JS/WASM   ░░░░░░░░░░░░░░░░░░░░  0%   📝 Draft
[Phase 5] C++       ░░░░░░░░░░░░░░░░░░░░  0%   📝 Draft
[Phase 6] CI Sync   ░░░░░░░░░░░░░░░░░░░░  0%   📝 Draft
[Phase 7] Docs      ░░░░░░░░░░░░░░░░░░░░  0%   📝 Draft
```

**全体進捗**: 0 / 7 チケット完了。

---

## 5. 依存グラフ

```
                  (none)
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
   TICKET-01    TICKET-02   TICKET-03
   (Rust)       (Go)        (C#)
        │
        ▼
   TICKET-04
   (JS/WASM)
                                ┌─→ TICKET-05 (C++) ──┐
                                                       │
                                       (parallel)      │
                                                       ▼
                                              TICKET-06 (CI Sync)
                                                       │
                                                       ▼
                                              TICKET-07 (Docs)
```

**重要**: TICKET-04 (JS/WASM) は TICKET-01 (Rust) 完了が前提。他のチケットは独立して並列実装可能。

---

## 6. 受け入れ基準 (PR マージ条件)

設計書 §6.3 を再掲。すべての項目が満たされた状態で PR マージ。

- [ ] 5 ランタイムすべてで Issue #384 例 3 件が期待 IPA 列を出す
- [ ] 各ランタイムでテストマトリックス全件 PASS (詳細: 設計書 §4.3)
- [ ] `zh_en_loanword.json` が 6 箇所で byte-for-byte 一致 (CI ガード)
- [ ] 既存の純中国語 / 純英語 / `[ja, en]` パターンにリグレッションなし
- [ ] CI 全 job green (lint, ruff format, build matrix, runtime tests)
- [ ] 各ランタイムの README / CHANGELOG 更新
- [ ] iOS xcframework / Android aar ビルドで JSON 同梱確認

---

## 7. エージェントチーム編成 (全 phase 共通)

| 役割 | 主な責任 | 主な参照ドキュメント |
|------|---------|---------------------|
| **Phase Lead** | チケット内容統括、レビュー後修正の判断 | 設計書 §6, 本 INDEX |
| **Runtime Dev** | 実装本体 (各言語) | 設計書 §2.X, §4.1, §8.X |
| **QA / Test** | テストマトリックス実装、CI 確認 | 設計書 §4.3, §8.7 |
| **DevOps** (Phase 6) | CI 同期ジョブ追加、ベンチ測定 | 設計書 §8.3, §8.15 |
| **Tech Writer** (Phase 7) | API doc / README / CHANGELOG 更新 | 設計書 §8.11, §8.19 |
| **Mobile Engineer** (Phase 5 のみ) | iOS xcframework / Android aar の JSON 同梱 | 設計書 §8.1, §8.23 |

---

## 8. リスクと注意事項

| リスク | 影響 | 緩和策 |
|-------|------|-------|
| 6 JSON が時間差で乖離 | 出力が乱れる | TICKET-06 で CI byte-for-byte ガード、git pre-commit hook 検討 |
| Rust の 2 crate 重複 (§8.5) | 工数増 (~200 LOC) | TICKET-01 で同期テストを必須化、`piper-plus-g2p` を一次実装にして `piper-core` から `pub use` を検討 |
| C# DotNetG2P 改修不可 (§8.2, X7) | pinyin→IPA を C# 側に独立実装 (~200 LOC) | TICKET-03 で Python の `pinyin_to_ipa` を移植。fixture で出力比較必須 |
| C++ iOS/Android JSON 同梱 (§8.1) | xcframework / aar に bundle が要 | TICKET-05 で `xxd` 不在環境用に CMake `file(READ HEX)` 採用 |
| 巨大 PR (~2,300 LOC) | レビュー困難 | コミットを **ランタイム単位**で分割 + PR description に章立て |

---

## 9. 「一から作り直すなら」検討プロセス

各チケットに **Section 9: 一から作り直すとしたら** を必須記載。

> エージェントチームはチケット作成後、この Section 9 を起点に「現実装案 vs 理想の設計」を議論し、軽微な改善は **そのチケット内**で取り込む。大きな変更は次フェーズの設計書改訂として記録する。

各 Section 9 の典型骨子:
1. **データ層**: JSON か code-gen か / fixture 形式
2. **API 層**: 関数シグネチャ、エラー型、opt-out 制御
3. **Dispatcher 設計**: パターンマッチの抽象化
4. **テスト戦略**: 単一 fixture を全ランタイムで読む / 個別維持
5. **思想**: コア哲学 (例: source of truth は単一、ランタイムは consumer)

---

## 10. 関連ドキュメント

- [設計書 (本ロードマップの大本)](../../spec/zh-en-loanword-runtime-rollout.md)
- [PUA 仕様](../../spec/pua-contract.toml)
- [Phoneme Timing 仕様](../../spec/phoneme-timing-contract.toml)
- [iOS shared lib 仕様](../../spec/ios-shared-lib.md)
- [v1.11 → v1.12 マイグレーション](../../migration/v1.11-to-v1.12.md)

---

## 11. 改訂履歴

| 日付 | 版 | 変更内容 |
|------|----|---------|
| 2026-05-07 | v1 | INDEX 初版作成 (7 チケットの骨子確定) |
