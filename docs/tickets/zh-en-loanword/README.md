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
- `zh_en_loanword.json` が **7 箇所** (Python 学習 / Python ランタイム / Rust × 2 crate (`piper-plus-g2p` + `piper-core`) / Go / C# / WASM-data / C++) で byte-for-byte 一致 (CI ガード)
- 性能オーバーヘッドが既存純中国語経路に対して < 5%

---

## 2. 全体ロードマップ

```
Day 1      ┃ Phase 6a: CI sync skeleton 先行 merge          [TICKET-06 一部 / S1+S2]
Day 1-4    ┃ Phase 1:  Rust    (R1-R5, ~600 LOC)            [TICKET-01, 楽観 3→現実 4日]
Day 5-6    ┃ Phase 2:  Go      (G1-G5, ~355 LOC)            [TICKET-02, Rust と並列着手可]
Day 7-9    ┃ Phase 3:  C#      (C1-C4, ~460 LOC)            [TICKET-03, Rust と並列着手可]
Day 10-11  ┃ Phase 4:  JS/WASM (W2-W5, ~250 LOC)            [TICKET-04, TICKET-01 完了依存]
Day 11-14  ┃ Phase 5:  C++     (P1-P6, ~810 LOC)            [TICKET-05, 楽観 3→現実 4日 + Mobile独立日]
Day 14     ┃ Phase 6b: CI 同期 fixture/skill 完成           [TICKET-06 残り / S3-S6]
Day 15     ┃ Phase 7:  Docs/Release (CHANGELOG/README/API)  [TICKET-07]
Day 16     ┃ Phase 8:  統合バッファ (cross-runtime PR review / 最終回帰)
```

**総コード量目安**: **~2,300 行** (テスト含む) / **期間目安**: **16 日 (3 週間以内)**。

**スケジュール根拠 (レビュー指摘 RED-C1 反映)**:
- 当初 14 日 → **16 日に拡張**。Day 16 を統合バッファとして確保し、クリティカルパス (Day 1→4 Rust → Day 10-11 WASM → Day 14 fixture → Day 15 Docs) が 1 日遅延しても全体スケジュールが破綻しないよう設計。
- TICKET-01 (Rust) を **3→4 日**: 2 crate 重複 + `OnceLock` + WASM 用 setter まで含む。Python PR #397 (1,578 LOC) との比較から `~600 LOC + 44 テスト` を 3 日は楽観バイアス。
- TICKET-04 (WASM) を **1→2 日**: TICKET-01 完了直後の 1 日固定は危険。Rust setter shape 確定後にすぐ実装できるよう、Day 4 setter freeze → Day 10-11 で実装。
- TICKET-05 (C++) を **3→4 日**: 5 platform (iOS / Android / Linux / macOS / Windows) CI build + sanitizer + xcframework symbol 検証 (3 層) を 3 日は圧迫。Mobile 検証日 (Day 14) を独立確保。

**並列化注意**: Go / C# / C++ は Rust に依存しないので Day 1-4 期間中に並列着手可能。WASM のみ Rust の `set_loanword_data` setter シグネチャ確定 (Day 4 想定) 待ち。

---

## 3. チケット一覧

| # | チケット | ランタイム | 期間 | LOC | 依存 | ステータス | 担当エージェントチーム |
|---|---------|----------|------|-----|------|----------|----------------------|
| 01 | [TICKET-01-rust.md](TICKET-01-rust.md) | Rust | Day 1-4 | ~600 | なし | 📋 Ready | Lead × 1, Rust Core × 2, QA × 1 |
| 02 | [TICKET-02-go.md](TICKET-02-go.md) | Go | Day 5-6 | ~355 | なし | 📋 Ready | Lead × 1, Go Dev × 1, QA × 1 |
| 03 | [TICKET-03-csharp.md](TICKET-03-csharp.md) | C# | Day 7-9 | ~460 | なし | 📋 Ready | Lead × 1, C# Dev × 2, QA × 1 |
| 04 | [TICKET-04-wasm.md](TICKET-04-wasm.md) | JS/WASM | Day 10-11 | ~250 | TICKET-01 | 📋 Ready | Lead × 1, WASM Dev × 1, JS Dev × 1, QA × 1 |
| 05 | [TICKET-05-cpp.md](TICKET-05-cpp.md) | C++ | Day 11-14 | ~810 | なし | 📋 Ready | Lead × 1, C++ Dev × 2, Mobile × 1, QA × 1 |
| 06a | [TICKET-06-ci-sync.md](TICKET-06-ci-sync.md) (Phase 6a) | CI skeleton | Day 1 | ~80 | なし (先行 merge) | 📋 Ready | DevOps × 1, Python Dev × 1 |
| 06b | [TICKET-06-ci-sync.md](TICKET-06-ci-sync.md) (Phase 6b) | CI fixture/skill | Day 14 | ~120 | TICKET-01〜05 | 📋 Ready | Lead × 1, DevOps × 1, QA × 1 |
| 07 | [TICKET-07-docs.md](TICKET-07-docs.md) | Docs | Day 15 | ~300 | TICKET-01〜06 | 📋 Ready | Lead × 1, Tech Writer × 1, Python Dev × 1, DevOps × 1 |
| 08 | (バッファ) | 統合 | Day 16 | — | TICKET-07 | — | 全 Lead × 1 (cross-runtime PR review) |

**ステータス凡例**: 📝 Draft / 📋 Ready (チケット作成 + エージェントレビュー反映済) / 🚧 In Progress / 👀 Review / ✅ Done / ⏸ Blocked

> **2026-05-07 Phase 7 完了**: 7 commit (PR-A〜PR-E) で全 7 ランタイム展開を完了。
> CI gate `ZH-EN Loanword Sync Gate / json-sync` が green、全 mirror byte-for-byte 一致。
> 残: TICKET-05 P3/P4 (piper.cpp dispatch + C API export) は別 PR で実施予定。

---

## 4. 進捗ダッシュボード

```
[Phase 0] チケット作成 ████████████████████  100%  ✅ Done (7 チケット作成 + レビュー反映済)
[Phase 1] Rust         ████████████████████  100%  ✅ Done (45 tests, 2 crate 対称)
[Phase 2] Go           ████████████████████  100%  ✅ Done (24 tests, embed.FS)
[Phase 3] C#           ████████████████████  100%  ✅ Done (21 tests, PinyinToIpa.cs 独立移植)
[Phase 4] JS/WASM      ████████████████████  100%  ✅ Done (9 tests, setZhEnDispatch FFI)
[Phase 5] C++          ████████████████████  100%  ✅ Done (12 tests, chinese_loanword.{hpp,cpp} 新規)
[Phase 6] CI Sync      ████████████████████  100%  ✅ Done (Phase 6a + 6b、7 copy + 6 fixture mirror)
[Phase 7] Docs         ████████████████████  100%  ✅ Done (CLAUDE.md + INDEX + CHANGELOG + skill)
```

**チケット作成進捗**: 7 / 7 完了 (各チケット Plan エージェントレビュー反映済)。
**実装進捗**: 7 / 7 完了 (~3,700 LOC, 111 ZH-EN tests, regression なし)。

---

## 5. 依存グラフ

```
              ┌───────────────────────────────────────────────┐
              │  Day 1: TICKET-06a (CI skeleton 先行 merge)   │
              └───────────────────────────────────────────────┘
                                    │ (gate 有効化、以降の copy 乖離を即検知)
                                    │
                ┌───────────────────┼───────────────────┐
                ▼                   ▼                   ▼
            TICKET-01          TICKET-02            TICKET-03
            (Rust)             (Go)                 (C#)
            Day 1-4            Day 5-6              Day 7-9
                │
                │ (Day 4 setter shape freeze)
                ▼
            TICKET-04
            (JS/WASM)
            Day 10-11
                                                            ┌─→ TICKET-05 (C++)
                                                            │   Day 11-14
                                                            │
                                                       (parallel)
                                                            │
                                                            ▼
                                              TICKET-06b (fixture/skill)
                                                       Day 14
                                                            │
                                                            ▼
                                              TICKET-07 (Docs/Release)
                                                       Day 15
                                                            │
                                                            ▼
                                              Day 16 統合バッファ
                                              (cross-runtime PR review)
```

**重要**:
- **TICKET-06a を最初に merge** することで、12 日間の gate 不在期間を解消。各 TICKET-01〜05 が JSON copy を追加するたびに hash check が走る。
- **TICKET-04 (JS/WASM)** は TICKET-01 (Rust) の `set_loanword_data` setter shape 確定 (Day 4) が前提。
- **クリティカルパス**: Day 1 → Day 4 (Rust) → Day 11 (WASM) → Day 14 (fixture/CI 完成) → Day 15 (Docs) → Day 16 (バッファ)。
- Go / C# / C++ は Rust に依存しないので並列着手可 (チームヘッドカウントが許す場合)。

---

## 6. 受け入れ基準 (PR マージ条件)

設計書 §6.3 を再掲。すべての項目が満たされた状態で PR マージ。

- [ ] 5 ランタイムすべてで Issue #384 例 3 件が期待 IPA 列を出す
- [ ] 各ランタイムでテストマトリックス全件 PASS (詳細: 設計書 §4.3)
- [ ] `zh_en_loanword.json` が **7 箇所** (Rust 2 crate 含む) で byte-for-byte 一致 (CI ガード)
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
| **7 JSON が時間差で乖離** (Rust 2 crate 含む) | 出力が乱れる | **TICKET-06a を Day 1 で先行 merge** (12 日間 gate 不在を解消)、CI byte-for-byte ガード、`.gitattributes` で `*.json text eol=lf` 強制 (Windows CRLF 衝突回避)、git pre-commit hook 検討 |
| Rust の 2 crate 重複 (§8.5) | 工数増 (~200 LOC) | TICKET-01 で同期テストを必須化、`piper-plus-g2p` を一次実装にして `piper-core` から `pub use` を検討 |
| **Rust 2 crate サイレント drift** (新規追加リスク) | `chinese.rs` 1314 行同士の同期が将来破綻 | TICKET-01 R5 `test_two_crate_consistency` を必須、レビュー指摘 YELLOW-3 で TICKET-06 fixture mirror に `piper-plus-g2p` 側も追加 |
| **pinyin→IPA 移植精度** (新規追加リスク) | 5 ランタイム独立移植で 1 件でも `_INITIAL_TO_IPA` テーブル誤りがあると PUA 列が乱れ、既存学習済モデルとずれる | TICKET-06 cross-runtime fixture matrix で全 5 ランタイム × ~25 ケース byte 一致を CI 強制、Python source を gold standard とする |
| C# DotNetG2P 改修不可 (§8.2, X7) | pinyin→IPA を C# 側に独立実装 (~200 LOC) | TICKET-03 で Python の `pinyin_to_ipa` を移植。fixture で出力比較必須 |
| C++ iOS/Android JSON 同梱 (§8.1) | xcframework / aar に bundle が要 | TICKET-05 で `xxd` 不在環境用に CMake `file(READ HEX)` 採用 |
| **C++ `chinese_phonemize.cpp` 内 `pinyinToIpa` 公開化による既存 ABI 影響** (新規追加リスク) | anonymous namespace 内関数を header 公開すると cross-platform で再コンパイル必須、shared lib 利用者に影響 | TICKET-05 §7 懸念 7 で wrapper 関数を新規追加 (anonymous namespace は変更せず)、ABI snapshot を `tests/abi/symbols.txt` に固定 |
| 巨大 PR (~2,300 LOC) | レビュー困難 | **Stacked PR 戦略**: 単一巨大 PR ではなく以下 5 段階に分割 (レビュー指摘 RED-C3 反映): <br>**PR-A** (Day 1-4): TICKET-01 (Rust ~600) + TICKET-06a (CI skeleton ~80) <br>**PR-B** (Day 5-9): TICKET-02 (Go ~355) + TICKET-03 (C# ~460) <br>**PR-C** (Day 10-11): TICKET-04 (WASM ~250、PR-A merge 後) <br>**PR-D** (Day 11-14): TICKET-05 (C++ ~810) <br>**PR-E** (Day 14-15): TICKET-06b 残り (~120) + TICKET-07 (Docs ~300) |

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

### 9.X 横断的な盲点 (レビュー指摘 D2 反映)

7 チケットの Section 9 を通読して **誰も触れていなかった哲学盲点** を README に集約。個別チケットでは扱えないメタ哲学のため:

| # | 盲点 | 現状の対応 | 将来検討事項 |
|---|------|---------|-----------|
| 1 | **音声品質の哲学**: 「PUA byte 一致」は phoneme 列の合致を保証するが、**生成された音声品質の評価軸 (MOS / PESQ / 主観評価) が一切登場しない**。「正しく動く」と「良く聞こえる」の境界が現状の哲学にない。code-switching の本質は音響なのに、全チケットがテキスト処理層に閉じている | 本 PR では fixture matrix で「Python と byte 一致」を gold standard とする。音響評価は scope 外 | 設計書 v10 候補: ZH-EN code-switching 専用の MOS ベンチマーク (`tools/benchmark/zh-en-mos.md`) を追加、20 サンプル × 5 評価者 で baseline 取得。`docs/benchmark-mos.md` の運用と統合 |
| 2 | **Loanword data の正統性 / governance**: 131 entries (acronyms 65 + loanwords 40 + letter_fallback 26) を「**誰がどの基準で更新するか**」が未定義。Linguist による review process / pull request template / 言語学的根拠の出典は §9 全体で議論ゼロ | TICKET-07 §9.0 #1 の glossary lint は用語のみ、データ自体の linguistic review プロセスは未整備 | 設計書 v10 候補: (a) `CONTRIBUTING_LOANWORDS.md` 作成、(b) `.github/ISSUE_TEMPLATE/loanword-{request,submission}.yml` 追加、(c) 各エントリに `source: <linguist_handle>` フィールドを追加 (schema v2 候補)、(d) Mandarin native speaker 1 名以上の review を required reviewer に設定 |
| 3 | **AI コード生成によるチケット消化フロー**: 5 ランタイム同時展開という構造は「人間が 5 ランタイム書く」前提。Claude Code / Copilot で並列消化する場合の **fixture 一致保証 / linter / review automation** が議論されていない | 本 PR では Stacked PR + 各 phase エージェントレビュー (Plan agent) で対応 | 将来: 専用 `claude-skill` (例: `/check-loanword`) を整備、AI エージェントが PR 提出時に自動で fixture 再生成 + 7 mirror sync を実行する MCP server を提供 |
| 4 | **言語数スケール時の崩壊点**: i18n 拡張パスは 7 チケットで「Phase 3: `LoanwordRegistry::register(src, tgt, data)`」と同一 API を提案。しかし src 言語 N、tgt 言語 M のとき N×M の loanword data が必要 (英語以外も embedded され得る)。**N=10, M=10 で 100 ファイル、5 ランタイム × 100 = 500 ファイル sync**。多次元拡張時の CI scaling が盲点 | 本 PR は ZH-EN 1 軸のみ、TICKET-06 §9.6 は ZH-EN→JA-EN の 1 軸拡張のみ想定 | 設計書 v10 候補: 多次元 loanword の単一 JSON 統合 (`{ "zh": { "en": {...}, "ja": {...} }, "ja": { "en": {...} } }`) で M×N 個別ファイル爆発を回避 |
| 5 | **PUA codepoint 枯渇**: PUA 領域 0xE020-0xE04A は **43 codepoint しか確保されていない**。tone marker 追加 / 新言語の特殊音素で枯渇する想定が §9 全体にない。TICKET-05 §9.9 は struct layout migration を語るが、**PUA 範囲拡張プロトコルは無記載** | 現状 0xE020-0xE04A の 43 codepoint で十分 | 設計書 v10 候補: PUA 第二範囲 (0xE050-0xE07A) の予約と migration プロトコル定義、`pua.json` schema に `range_id` フィールドを追加して将来の co-existence を可能化 |

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
| 2026-05-07 | v2 | 7 チケット全件作成 + Plan エージェントレビュー反映済。各チケットに Section 9「一から作り直すとしたら」を 9.0-9.X で詳細化 (思想 / データ層 / API 層 / Dispatcher / Failure mode / i18n / テスト / Observability)。LOC 見積を実反映 (TICKET-06: 150→200、TICKET-07: 既存通り 300)。 |
| 2026-05-07 | v3 | **横断レビュー (4 エージェント並列) 反映**: <br>**RED 修正**: TICKET-03 §C3 戻り値型を `IReadOnlyList<string>` → `ChineseG2PResult` に統一 / TICKET-05 §P1-P3 戻り値構造を nested → flat に統一 / 「6 箇所」表記揺れを **7 箇所** (Rust 2 crate 含む) に統一 (設計書 §6.3/§8.3/§8.15/§8.21 + TICKET-06 §1 + 本 INDEX) / TICKET-06 を **Day 1 + Day 14 の 2 段階運用** (workflow skeleton 先行 merge で 12 日間 gate 不在を解消) / スケジュール **14 → 16 日** (TICKET-01: 3→4日 / TICKET-04: 1→2日 / TICKET-05: 3→4日 + Day 16 統合バッファ) / リスク表に **3 項目追加** (pinyin→IPA 移植精度 / Rust 2 crate drift / C++ ABI 影響) / **Stacked PR 戦略** (5 段階に分割) を採用。<br>**YELLOW 修正**: TICKET-01 §7 懸念 5 を **Cargo feature opt-in + ランタイム dispatch opt-out** の二層管理に明示化 / TICKET-03 フラグ命名を `EnableZhEnDispatch` に統一 (5 ランタイム整合) / TICKET-06 fixture mirror に `piper-plus-g2p` を追加 / `.gitattributes` に `*.json text eol=lf` 追加 (Windows CRLF 衝突回避) / 全 5 ランタイムテスト表に `test_loader_accepts_unknown_fields_in_schema_v2` 追加 (forward-compat loader)。<br>**思想反映**: TICKET-07 §9.2 compatibility matrix を **API / SemVer / ABI / Schema 4 軸** に拡張 (TICKET-01 §9.4 / TICKET-04 §9.9 / TICKET-05 §9.9 / TICKET-06 §9.5 を集約) / README §9.X に **5 項目の横断的盲点** (音声品質評価 / Loanword governance / AI 並列消化フロー / 多次元 i18n scaling / PUA codepoint 枯渇) を追加。 |
