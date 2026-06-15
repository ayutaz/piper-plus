# AI-18: 採否判定レポート作成と統合 PR 提出

## メタ情報

- ID: AI-18
- 親マイルストーン: [M6](../milestones/M6-pr-rebase-integration.md)
- 工数見積: 2 日
- 依存チケット: AI-17 (PR #222 merge 後の FiLM rank-aware 化 + ONNX I/O 同期 + 7 ランタイム ABI 同期)
- 後続チケット: プロジェクト終了 (採否次第で dev へ統合 PR or close)
- ステータス: TODO
- ブランチ: feat/decoder-istftnet2-mswavehax-poc
- 親計画 §: [§6 Action Items AI-18 / §4.6 Benchmarks 目標値 / §5 Milestone 6 Exit Criteria](../../research/implementation-plan-a1-a2-2026-06-16.md)

## タスク目的とゴール

本チケットは A-1 / A-2 PoC の **採否判定とプロジェクト終端処理** を扱う最終アクションである。 計画 §6 AI-18 で要求されるとおり、 M1-M5 で完成した 3 variant (1D baseline / iSTFTNet2-MB / FLY-TTS / MS-Wavehax companion) と AI-16 (PR #537 後の bf16-mixed + TF32-on 再 benchmark)、 AI-17 (PR #222 後の FiLM rank-aware 化 + ONNX I/O 同期) で確定した最終数値を集約し、 計画 §4.6 の 4 指標 (UTMOS proxy MOS / CPU RTF / ONNX op coverage / 7 ランタイム smoke) で **A-1 採用 / FLY-TTS 切替 / 1D 継続** のいずれか 1 案を判断する。

上流からの受け取りは AI-17 完了時点の以下を canonical 入力とする: PR #222 / PR #537 merge 後の rebase 済み 3 variant ONNX (`/data/piper/output-css10-ja-poc-{1d-baseline,istftnet2-mb,fly-convnext6}-rebased/`)、 `audio-parity-contract.toml` の bf16-mixed + TF32-on 環境で確定した tolerance、 `_apply_film` rank-aware 化後の 7 ランタイム smoke 結果 (pairwise SNR ≥ 30 dB)、 AI-12 で生成した UTMOS proxy MOS と AI-13 で確定した 7 ランタイム pairwise SNR。

下流への引き渡しは本プロジェクト終了処理であり、 (a) dev 統合 PR の merge (A-1 採用 / FLY-TTS 切替の 2 ケース) または (b) PR close + ブランチ archive (1D 継続ケース) のいずれかに分岐する。 いずれの分岐でも採否判定レポート (`docs/research/a1-a2-adoption-report-2026-06-16.md`) を canonical 成果物として残し、 PR #222 / #537 rebase の学び (FiLM rank-aware 化テンプレート / TF32 tolerance 拡張パターン) を将来の同種衝突 (別 decoder upgrade × Zero-shot TTS) に再利用可能な形で抽出する。

## 実装内容の詳細

本チケットはコード変更を伴わない **判定 + ドキュメント + PR 提出 工程** が中核である。 編集対象ファイルと新規ファイルを以下に明示する。

### 新規ファイル

- `/Users/s19447/Documents/piper-plus/docs/research/a1-a2-adoption-report-2026-06-16.md` (~400-600 LoC、 markdown)
  - **§1 Executive Summary** — 採用案 (A-1 採用 / FLY-TTS 切替 / 1D 継続) と 1 段落の理由
  - **§2 4 指標判定表** — UTMOS proxy MOS / CPU RTF p50 / ONNX op coverage / 7 ランタイム smoke の 3 variant × 4 指標 = 12 セルマトリクス、 各セルに「達成 / 未達 / 規格外」 と数値、 baseline からの絶対差 / 相対比
  - **§3 採用根拠 (採用案ごとの場合分け)** — 4 指標 AND 判定で全 pass なら A-1 採用、 1 つでも未達なら FLY-TTS 100 epoch 延長判定、 両方未達なら 1D 継続 + A-4/A-5 ライン昇格
  - **§4 PR #222 / #537 rebase の学び** — FiLM rank-aware 化テンプレート (1D split dim=1 / 2D split dim=1 維持 + spatial broadcast) と TF32 tolerance 拡張パターン (1e-3 magnitude drift → `bf16_tolerance_db` キー追加) を将来 epic で再利用可能な形に抽出
  - **§5 後続 epic への引き渡し** — 採用案ごとに HuggingFace push 対象 / contract 確定 section / archive tag を列挙

### 編集対象ファイル

- `/Users/s19447/Documents/piper-plus/docs/research/README.md` — 新規レポートへのリンク追加 (1 行差分のみ、 既存 link 順序維持)
- `/Users/s19447/Documents/piper-plus/CHANGELOG.md` — `## [Unreleased]` セクションに A-1 採用 / FLY-TTS 切替 / 1D 継続のいずれか採用案を 1 行記載 (`/release-prep` で次 release 時に確定)

### 既存 default 値 / 互換維持の制約 (G-1.9 後方互換 gate)

- `decoder_type` default は AI-17 時点で既に確定済み (A-1 採用なら `istftnet2_mb_1d2d`、 FLY-TTS 切替なら `fly_convnext6`、 1D 継続なら `mb_istft_1d` 不変)。 本チケットでは **default 値の変更は行わず**、 採否判定の根拠を文書化するのみ
- `audio-parity-contract.toml` の `[mb_istft_1d]` section は AI-14 で導入済みの編集禁止 gate (G-1.2) を継続遵守。 本チケットでは contract を **読むのみで書かない**
- ONNX I/O は AI-17 で `speaker_embedding[192]` への同期が完了済み。 本チケットでは I/O 変更を行わない (PR #222 二重同期回避の最終 gate)

### PR #222 / PR #537 conflict 回避策

計画 §3 Conflict Map から該当行を引用 (本チケットは benchmark/tests と同水準の NONE 衝突を狙う):

> `tools/benchmark/` + `tests/` | 3 variant 追加、 regression guard | NONE | LOW (pytest 9) | A-1/A-2 先行で OK

- **vs PR #222:** 本チケットは PR #222 merge 後の状態を前提とするため衝突自体が存在しない (AI-17 で全 ABI 同期完了済み)。 採用案で A-1 採用 / FLY-TTS 切替を選ぶ場合、 統合 PR body には PR #222 の `speaker_embedding[192]` を引き継ぐ旨を明示し、 PR #222 merge 前提の rebase 履歴を Test Plan section に列挙する
- **vs PR #537:** AI-16 で bf16-mixed + TF32-on tolerance が `audio-parity-contract.toml` に反映済み。 本チケットの統合 PR は ubuntu-24.04 + py3.13 + torch 2.11 環境を前提とし、 CI matrix に旧 torch 2.2 を残さない (PR #537 で deprecate 済み)

### 採否判定 アルゴリズム (疑似コード)

```python
def decide_adoption(metrics_a1, metrics_fly, baseline_1d):
    # 計画 §4.6 / §5 M6 Exit Criteria
    a1_pass = (
        abs(metrics_a1.utmos_mean - baseline_1d.utmos_mean) <= 0.1
        and metrics_a1.cpu_rtf_p50_ms < 20  # baseline 27 × 0.7
        and metrics_a1.onnx_ops <= ALLOWED_OPS_A1  # Conv2d / Reshape / Transpose only
        and metrics_a1.runtime_pairwise_snr_db >= 30
    )
    if a1_pass:
        return "A-1 採用"
    fly_pass = (
        abs(metrics_fly.utmos_mean - baseline_1d.utmos_mean) <= 0.1
        and metrics_fly.cpu_rtf_p50_ms < 23  # baseline × 0.85
        and metrics_fly.onnx_ops <= ALLOWED_OPS_FLY  # Conv1d + LayerNorm only
        and metrics_fly.runtime_pairwise_snr_db >= 30
    )
    if fly_pass:
        return "FLY-TTS 切替 (100 epoch 延長判定が必要なら追加注記)"
    return "1D 継続 (A-4 Matcha / A-5 StyleTTS2 ライン昇格)"
```

### 統合 PR の構造 (`/create-pr` で提出、 `gh pr create` 直接禁止)

- title: 70 文字以内、 採用案を明示 (例: `feat(decoder): adopt iSTFTNet2-MB 1D-2D backbone (A-1)` または `chore(decoder): keep 1D MB-iSTFT baseline, defer A-1/A-2`)
- body: `pull_request_template.md` の section 構造 (`## Summary` / `## Test Plan` 大文字 P / `## Risk Level` checkbox / `## Affected Components` checkbox / `## Type` checkbox) に準拠
- マイルストーン非付与、 auto-merge 非使用 (CLAUDE.md / user memory `feedback_merge_caution.md` に準拠)
- 1D 継続 (close) ケースでは `gh pr close` ではなく `/create-pr` で「closing PR」 として提出後 user 最終確認を経て close

## エージェントチームの役割と人数

| 役割 | 人数 | 必要スキル | 責任範囲 |
|------|-----|-----------|---------|
| Lead Decision Maker | 1 | UTMOS / RTF 統計 / ONNX op 解析 / project 判断 | 4 指標判定表作成、 採用案最終決定、 §3 採用根拠の場合分け執筆 |
| Documentation Engineer | 1 | markdown / docs スタイル / 計画文書クロスリンク | レポート構造組成、 §4 学び抽出、 README.md / CHANGELOG.md 連動、 cross-link 検証 |
| Release Coordinator | 1 | `/create-pr` skill / `pull_request_template.md` 準拠 / gh workflow | 統合 PR body 構造化、 CI green 待機、 `/watch-pr` 監視、 review thread 対応 |

3 名構成。 PoC ステージ終端の判断・文書・PR 提出工程に絞り、 コード変更を扱わないため Lead Implementer / Test Engineer は配置しない。 ML Researcher は AI-17 までで判断材料を集約済みのため本チケットでは consult のみ (必要に応じ Lead Decision Maker が指名)。

## 提供範囲 (Scope)

### 含むもの

- 採否判定レポート `docs/research/a1-a2-adoption-report-2026-06-16.md` 新規作成 (4 指標判定表 + 採用根拠 + 学び抽出 + 後続 epic 引き渡し)
- 計画 §4.6 の 4 指標 (UTMOS proxy MOS / CPU RTF / ONNX op coverage / 7 ランタイム smoke) を AI-12 / AI-13 / AI-16 / AI-17 の最新成果から集約
- A-1 採用 / FLY-TTS 切替 / 1D 継続 の 3 ケース場合分け文書 (採用案 1 つに収束)
- 統合 PR の `/create-pr` 経由提出 (PR body は `pull_request_template.md` 準拠)
- `docs/research/README.md` への新レポート link 追加 (1 行差分)
- `CHANGELOG.md` `## [Unreleased]` セクションに採用案 1 行記載
- PR #222 / #537 rebase 戦略テンプレートの抽出 (FiLM rank-aware 化 / TF32 tolerance 拡張)

### 含まないもの (Out of Scope)

- **追加学習 (A-1 や FLY-TTS の再学習 / 延長学習)** — AI-18 は判定のみ。 100 epoch 延長判断は本チケット成果物 (採否レポート §3) で 「FLY-TTS 切替時には別 epic で 100 epoch 延長」 と明記するに留め、 学習自体は後続 epic
- **HuggingFace への ONNX push** — 採用案決定後 (PR merge 後) に `/publish-model` skill で別途実施。 本チケットでは push 対象パスを §5 で列挙するのみ
- **`audio-parity-contract.toml` の編集** — AI-14 / AI-16 / AI-17 で確定済み。 本チケットでは contract を読むのみで書かない (G-1.2 baseline 編集禁止 gate)
- **default `decoder_type` 値の変更** — AI-17 で確定済み (採用案を反映した default 切替は M6 完了時点で既に dev 反映可能な状態)
- **新規 ONNX export / 7 ランタイム ABI 変更** — AI-17 で完了済み
- **`_apply_film` の追加修正 / `cond_layers` channel schedule 追加分岐** — AI-17 で完了済み
- **PR #222 / #537 への追加 review / 後追い修正** — 両 PR は merge 完了済みが前提

## テスト項目

### Unit Tests

- `src/python/tests/test_adoption_report_link.py::test_research_readme_has_adoption_report_link`
  - assert: `docs/research/README.md` の本文に `a1-a2-adoption-report-2026-06-16.md` への相対 link が 1 つだけ存在
  - assert: link 先 markdown ファイルが実在 (`Path(...).exists()`)
- `src/python/tests/test_adoption_report_link.py::test_adoption_report_has_required_sections`
  - assert: 新規レポートに `## 1. Executive Summary` / `## 2. 4 指標判定表` / `## 3. 採用根拠` / `## 4. PR #222 / #537 rebase の学び` / `## 5. 後続 epic への引き渡し` の 5 section が全て存在
  - assert: §2 判定表に `UTMOS` / `CPU RTF` / `ONNX op coverage` / `7 ランタイム smoke` の 4 指標列が含まれる
- `src/python/tests/test_changelog_unreleased.py::test_changelog_unreleased_has_adoption_entry`
  - assert: `CHANGELOG.md` `## [Unreleased]` section に「A-1 採用」 「FLY-TTS 切替」 「1D 継続」 のいずれかキーワードが 1 行含まれる
  - 既存テスト `test_changelog_unreleased.py` は touch しない (G-1.9 後方互換 gate、 ファイル存在しない場合は本テストで新規作成)

### E2E Tests

- **docs build smoke:** `uv run --no-sync pytest docs/tests/ --no-cov` で markdown link checker (既存) が新規レポート link を resolve できることを assert
- **PR body 構造 audit:** `/create-pr` で生成した PR body が `pull_request_template.md` の section heading 5 つ (Summary / Test Plan / Risk Level / Affected Components / Type) を全て含むことを `scripts/check_pr_body_structure.py` (M5 AI-15 で導入済み) で機械 check
- **採否判定 reproducibility:** §2 判定表に記載された UTMOS / RTF / ONNX op / SNR 数値が、 AI-12 (`tools/benchmark/metrics.json`) / AI-13 (`tests/runtime_parity/snr_matrix.json`) / AI-16 (`tools/benchmark/results/css10-ja-poc-py313-torch211/`) の artifact から直接引用可能であることを `scripts/check_adoption_report_traceability.py` (本チケットで新規作成、 ~50 LoC) で確認
- **README canonical 環境再現 (1D baseline 値の continuity):** AI-16 完了時点で `audio-parity-contract.toml` の `[mb_istft_1d]` baseline が `expected_p50_ms: 27` のまま不変であることを再確認 (G-1.2 gate の最終 sanity)

### 受入基準 (Acceptance Criteria)

計画 §4.6 / §5 M6 Exit Criteria / §6 AI-18 から該当数値を引用:

- **採用案明示**: A-1 採用 / FLY-TTS 切替 / 1D 継続 のいずれか 1 案が `docs/research/a1-a2-adoption-report-2026-06-16.md` §1 Executive Summary と統合 PR body Summary に明示
- **4 指標判定表完成**: 3 variant × 4 指標 = 12 セルに数値 + baseline 差 + 達成/未達ラベルが入った markdown 表が §2 に存在
- **UTMOS proxy MOS**: 採用案の variant が baseline (`css10-ja-1d-baseline`) ± 0.1 以内 (A-1 採用 / FLY-TTS 切替時の必須条件)
- **CPU RTF p50** (Xeon E5-2650 v4 / 25 phoneme 英文 / warmup 5 + 30 runs): A-1 採用時 < 20ms、 FLY-TTS 切替時 < 23ms
- **ONNX op coverage**: A-1 採用時 Conv2d / Reshape / Transpose のみ、 FLY-TTS 切替時 Conv1d / LayerNorm のみ (mobile EP CPU fallback 回避)
- **7 ランタイム smoke**: 全 7 runtime (Python / Rust / Go / C# / WASM / C++ / C-API) で `[1,1,T]` float32 / pairwise SNR ≥ 30 dB
- **rebase 後 audio-parity test green**: `uv run --no-sync pytest src/python/tests/test_audio_parity.py --no-cov` が全 variant pass
- **PR body 準拠**: `pull_request_template.md` の 5 section 構造を全て含む
- **マイルストーン非付与 / auto-merge 非使用**: user memory `feedback_pr_no_milestones.md` / `feedback_merge_caution.md` に準拠
- **`[mb_istft_1d]` baseline 不変**: `scripts/check_audio_parity_baseline.py` (M5 AI-15) で機械 check pass

## 懸念事項とレビュー項目

### 懸念事項 (リスク)

計画 §7 Risk Register から関連項目 + 本チケット固有の懸念:

- **R3 (MEDIUM/HIGH): Q13 (iSTFTNet2 zero prior art) で A-1 が proxy MOS -0.3 以上劣化した場合の判断**。 本チケットは「採否判断」 を扱うため、 A-1 失敗確定の判定根拠を文書化する責務を負う。 mitigation: 4 指標 AND 判定で「1 つでも未達なら FLY-TTS 切替判定」 のロジックを §3 で明確化し、 採用案が FLY-TTS / 1D 継続に倒れた場合の根拠 (どの指標が未達か) を §2 判定表に数値付きで明示
- **R6 (MEDIUM/HIGH): `audio-parity-contract.toml` baseline regression を本チケットが silently 招くリスク**。 本チケットは contract を読むのみで書かない契約だが、 採用案決定後に dev 統合 PR で contract 編集が走る可能性がある。 mitigation: 統合 PR の Affected Components checkbox から `audio-parity-contract.toml` を除外し、 contract 変更が必要な場合は別 PR (`/bump-deps` 経由) に切り分ける
- **採用案収束失敗リスク (本チケット固有)**: 4 指標 AND 判定が「微妙な未達 (例: UTMOS +0.05 / RTF 21ms / op OK / SNR 32dB)」 を返した場合、 A-1 採用にも FLY-TTS 切替にも倒せない可能性がある。 mitigation: M6 §「一から作り直すとしたら」 で示された weighted score 案 (UTMOS 0.4 / RTF 0.3 / op 0.2 / SNR 0.1) を §3 で補助判定として併載し、 AND 判定の主従関係を明示
- **永久 stale リスク (M6 §「一から作り直すとしたら」 escape hatch)**: PR #222 / #537 のいずれかが本チケット着手時点で merge されていない場合、 本チケットは blocking される。 mitigation: AI-17 完了時点で両 PR merge 完了が保証されているはずだが、 万が一 stale 状態が継続した場合は M6 §「一から作り直すとしたら」 で示された「A-1/A-2 のみで先に statistical merge し PR #222 後追い吸収」 案を採用するかを Lead Decision Maker が user に最終確認
- **PR body section 構造 drift**: user memory `feedback_pr_body_validate_sections.md` で「Test Plan 大文字 P / Risk Level/Affected Components/Type に checkbox」 が必須と明示。 mitigation: `/create-pr` skill が `pull_request_template.md` を自動準拠させるため、 PR body を手動編集しない (`gh pr create` 直接禁止)
- **採用案 = 1D 継続時の close 判定**: 1D 継続選択時はブランチ archive (`archive/a1-a2-poc-2026-06`) が必要だが、 user memory `feedback_merge_caution.md` で merge 前最終確認必須のため close もユーザー判断を待つ。 mitigation: closing PR を `/create-pr` で提出 → user 最終確認 → close の 3 段階を明示

### レビュー項目 (チェックリスト)

- [ ] default decoder_type 不変 (G-1.9 後方互換、 本チケットでは default 値を変更しない)
- [ ] [mb_istft_1d] audio parity 不変 (G-1.2 baseline 編集禁止、 contract を読むのみで書かない)
- [ ] ONNX I/O 不変 (PR #222 二重同期回避、 AI-17 で完了済みの `speaker_embedding[192]` を引き継ぐのみ)
- [ ] PR #537 merge 後の TF32 / bf16-mixed 影響を audio-parity-contract tolerance に反映済み (AI-16 で完了済み、 本チケットでは確認のみ)
- [ ] 採否判定レポートの 5 section (Executive Summary / 4 指標判定表 / 採用根拠 / 学び / 引き渡し) 全て存在
- [ ] §2 判定表に 3 variant × 4 指標 = 12 セルが数値 + baseline 差 + 達成/未達ラベルで埋まっている
- [ ] §3 で採用案 1 つに収束し、 他 2 案を捨てた根拠が明示されている
- [ ] §4 で FiLM rank-aware 化テンプレート / TF32 tolerance 拡張パターンが将来 epic 再利用可能な形に抽出されている
- [ ] §5 で採用案ごとに HuggingFace push 対象 / contract section / archive tag が列挙されている
- [ ] 統合 PR が `/create-pr` 経由で提出されている (`gh pr create` 直接禁止、 user memory `feedback_pr_create_skill_only.md`)
- [ ] PR body が `pull_request_template.md` の 5 section 構造に準拠 (Summary / Test Plan 大文字 P / Risk Level checkbox / Affected Components checkbox / Type checkbox)
- [ ] PR にマイルストーン非付与 (user memory `feedback_pr_no_milestones.md`)
- [ ] PR body に T-XXX / M1 / Phase 名なし (機能名で記述、 user memory `feedback_pr_no_ticket_phase_names.md`)
- [ ] auto-merge 非使用 (user memory `feedback_merge_caution.md`)
- [ ] 1D 継続選択時のブランチ archive tag (`archive/a1-a2-poc-2026-06`) 命名が user 確認済み

## 一から作り直すとしたら (Ticket-level rethinking)

採用案は「**4 指標 AND 判定 + markdown レポート + `/create-pr` で統合 PR 提出**」 の 3 段直列であり、 計画 §4.6 と §5 M6 Exit Criteria に厳密準拠する保守的設計である。 これは PoC ステージ終端の判断を「人間レビューしやすい table 化された数値根拠」 として残す利点があり、 user memory `feedback_conservative_changes.md` (影響が大きい変更は避け、 小さく保守的な選択肢を優先) と整合する。 ただし AND 判定は M6 §「一から作り直すとしたら」 でも指摘されたとおり「全部の指標で baseline 超過」 を要求するため、 微妙な未達 (UTMOS +0.05 / RTF 21ms など) で採用案が収束しない盲点がある。 代替案 1 として **weighted score 主従判定** (UTMOS 0.4 / RTF 0.3 / op 0.2 / SNR 0.1 の総合スコア閾値 vs AND 判定) を採用する設計が考えられる。 これなら「CPU RTF だけ × 0.65 で目標未達だが UTMOS は +0.15」 のような微妙なケースで A-1 採用 / FLY-TTS 切替の判断を機械的に下せるが、 weighted の重み根拠が論文 evidence ベースでなく経験則のため reviewer の納得を得にくい欠点がある。 採用案 (AND 判定主、 weighted score 補助) のままが妥当だが、 補助 score の重み根拠を §3 で明示すれば判断ロジックの再利用性は高まる。

代替案 2 は **integration-test 先行 (本チケットの実装を後回しにする)**: 4 指標判定表を先に書かず、 「dev 統合 PR を仮提出 → CI で 4 指標判定を機械実行 → CI 結果を PR body に自動反映」 とする逆順設計である。 これは「人間が判定数値を写経する手間を省く」 利点があるが、 CI 上で UTMOS proxy MOS を 200 utt × 3 variant 走らせるには Xeon ランナーで 30 分以上かかり (AI-12 受入基準)、 GitHub Actions free tier の job timeout (6h) には収まるが reviewer の wait time が悪化する。 また判定ロジック自体がコード化されると PR review で「アルゴリズムの妥当性議論」 が起き、 採用案決定が遅延する。 採用案 (人間が markdown で判定 → PR 提出) の方が判断主体を人間に保てる点で M6 §「一から作り直すとしたら」 で示された「閾値の AND/weighted は人間判断」 という前提と整合する。

代替案 3 として **採用案を 1 つに収束させず 3 ケース全てを並列 PR で提出** する設計も検討した。 これは「A-1 採用 PR」 「FLY-TTS 切替 PR」 「1D 継続 close PR」 の 3 PR を同時提出し、 user が 1 つを選んで他 2 つを close する分岐構造である。 利点は「user の最終決定権を最大化」 することだが、 reviewer の cognitive load が 3 倍化し、 user memory `feedback_pr_no_milestones.md` (PR に M1 等を入れない) と整合させるためには PR title で 3 案を区別する別軸が必要になる。 また採用案 1 つに絞らないまま 3 PR を維持する状態が続くと M6 マイルストーン自体が unclosed のまま漂流するリスクがある。 採用案 (1 PR に収束) の方が「採否判定の責務を AI-18 で完結させる」 という M6 設計意図と整合し、 final decision の所在を明示できる。

採用案を「現実解」 として位置づける根拠は、 (a) AND 判定で迷ったケースを weighted score 補助で救済できる柔軟性、 (b) markdown レポートで人間判断の根拠を将来 epic に再利用可能、 (c) `/create-pr` skill 経由で PR body 構造が機械的に保証される、 の 3 点である。 代替案 1 (weighted 主) は判断機械化の魅力はあるが reviewer の納得性で劣り、 代替案 2 (integration-test 先行) は CI 上での MOS 計算コストが問題、 代替案 3 (3 案並列 PR) は cognitive load 過大で M6 closing 遅延リスクが大きい。 これら別案の利点 (機械化 / CI 統合 / user 決定権最大化) は本チケット範囲外の epic (例えば次世代採否判定 framework 構築 epic) で再考すべきと整理し、 本チケットでは保守的選択を採る。

## 後続タスクへの連絡事項

本チケット完了でプロジェクトは終了する。 採用案 3 ケース (A-1 採用 / FLY-TTS 切替 / 1D 継続) ごとに後続作業に引き渡すべき具体的成果物を以下に明示する (M6 マイルストーン §「後続マイルストーンへの連絡事項」 を補完する細粒度の引き渡し)。

### 共通の成果物 (採用案によらず引き渡す)

- **採否判定レポート (canonical):** `/Users/s19447/Documents/piper-plus/docs/research/a1-a2-adoption-report-2026-06-16.md`
- **更新後 `docs/research/README.md`:** 新規レポートへの link が追加された状態
- **`CHANGELOG.md` `## [Unreleased]`:** 採用案 1 行記載 (`/release-prep` で次 release 時に確定)
- **学び抽出 (将来 epic 再利用テンプレート):**
  - FiLM rank-aware 化パターン: 1D split dim=1 / 2D split dim=1 維持 + spatial broadcast (`_apply_film` 拡張ロジック、 AI-17 成果)
  - TF32 tolerance 拡張パターン: `bf16_tolerance_db` / `tf32_drift_threshold` キー追加 (`audio-parity-contract.toml`、 AI-16 成果)

### A-1 採用ケースの引き渡し

- **新 baseline ckpt 仮置きパス:** `/data/piper/output-css10-ja-poc-istftnet2-mb-rebased/last.ckpt` (PR #222 + PR #537 環境で再学習推奨、 学習コマンドは統合 PR body Test Plan に記載)
- **ONNX 配布対象:** `tsukuyomi.istftnet2.onnx` (A-1 backbone) + `tsukuyomi.wavehax.onnx` (A-2 companion) の 2 枚を HuggingFace `ayousanz/piper-plus-tsukuyomi-chan` に追加 push (本チケット範囲外、 `/publish-model` で別途実施)
- **contract 確定 section:** `docs/spec/audio-parity-contract.toml` の `[istftnet2_mb_1d2d]` / `[mswavehax]` section が ubuntu-24.04 + py3.13 + torch 2.11 + bf16-mixed の tolerance で AI-16 / AI-17 で確定済み
- **default `decoder_type` 切替:** AI-17 完了時点で `istftnet2_mb_1d2d` を default に切替済み (1D 継続 fallback としては引き続き `mb_istft_1d` 利用可)
- **7 ランタイム ABI:** PR #222 既存 diff に乗った状態で `sid → speaker_embedding[192]` 同期済み、 後続言語追加 (例: ko/sv の強化) は本 ABI を前提とする
- **次の方向:** M5 AI-15 の `regression-guard` workflow を継続稼働、 CSS10 JA 以外の学習データセット (6lang base / 多話者 FT) への iSTFTNet2-MB / MS-Wavehax 拡張は別 epic として切り出し

### FLY-TTS 切替ケースの引き渡し

- **新 baseline ckpt 仮置きパス:** `/data/piper/output-css10-ja-poc-fly-convnext6-rebased/last.ckpt` (rebase 後 100 epoch 延長判断が必要なら別 epic で追学習)
- **ONNX 配布対象:** `tsukuyomi.fly.onnx` を HuggingFace に追加 push、 既存 `tsukuyomi.onnx` (1D MB-iSTFT) と併売
- **contract 確定 section:** `[fly_convnext6]` のみが採用 variant、 `[istftnet2_mb_1d2d]` / `[mswavehax]` は abandoned variant として section header に `# abandoned 2026-06-16` コメント追記 (本チケット成果として contract 編集権限を一時解放、 ただし `[mb_istft_1d]` は依然 G-1.2 編集禁止)
- **default `decoder_type` 切替:** AI-17 完了時点で `fly_convnext6` を default に切替済み
- **次の方向:** A-2 MS-Wavehax は streaming-only として独立 epic 化、 A-1 iSTFTNet2-MB は backlog として残置

### 1D 継続ケースの引き渡し (統合 PR close)

- **学習成果:** CSS10 JA 50 epoch baseline ckpt のみ HuggingFace に push (補助 baseline として利用可能、 `/data/piper/output-css10-ja-poc-1d-baseline-rebased/`)
- **ブランチ archive:** `feat/decoder-istftnet2-mswavehax-poc` を archive tag (`archive/a1-a2-poc-2026-06`) として保存し close
- **default `decoder_type`:** `mb_istft_1d` 不変 (AI-17 でも切替せず温存済み)
- **次の方向:** 親計画 §1 の通り A-4 (Matcha-TTS) / A-5 (StyleTTS2) ラインに昇格、 改善調査 [improvement-survey-2026-06-15.md](../../research/improvement-survey-2026-06-15.md) の §A-4 / §A-5 を起点に新 epic 立ち上げ

### 仮置きパスと暫定値の確定

- 採否判定レポートファイル名の `2026-06-16` は本チケット着手日 (2026-06-16) で確定 (M6 マイルストーン文書では `2026-09-XX` と暫定表記されていたが、 本チケット着手日に合わせて確定)
- contract `[istftnet2_mb_1d2d]` の `bf16_tolerance_db` 値は AI-16 完了時に確定済み (本チケットでは引用のみ)
- 統合 PR の title / body draft は本チケット完了時点で `/create-pr` skill が `pull_request_template.md` を自動準拠で生成

## 関連ドキュメント

- 親マイルストーン: [../milestones/M6-pr-rebase-integration.md](../milestones/M6-pr-rebase-integration.md)
- 親計画 §6 AI-18 / §4.6 / §5 M6 Exit Criteria: [../../research/implementation-plan-a1-a2-2026-06-16.md](../../research/implementation-plan-a1-a2-2026-06-16.md)
- 改善調査: [../../research/improvement-survey-2026-06-15.md](../../research/improvement-survey-2026-06-15.md)
- Decoder Upgrade deep-dive: [../../research/decoder-upgrades-istftnet2-and-mswavehax.md](../../research/decoder-upgrades-istftnet2-and-mswavehax.md)
- 前チケット: [AI-17-pr222-rebase-integration.md](AI-17-pr222-rebase-integration.md)
- 関連 spec:
  - [`docs/spec/audio-parity-contract.toml`](../../spec/audio-parity-contract.toml) — `[mb_istft_1d]` 編集禁止 (G-1.2) / `[istftnet2_mb_1d2d]` / `[mswavehax]` / `[fly_convnext6]` は AI-14 / AI-16 / AI-17 で確定済み
  - [`docs/spec/ort-session-contract.toml`](../../spec/ort-session-contract.toml) — bf16-mixed 環境での ORT session 設定継続性
- 関連 PR:
  - [#222 Zero-shot TTS (CAM++ + DINO)](https://github.com/ayutaz/piper-plus/pull/222) — AI-17 完了時点で merge 済み前提
  - [#537 Python 3.13 + CUDA 12.8 + Ubuntu 24.04 統一](https://github.com/ayutaz/piper-plus/pull/537) — AI-16 完了時点で merge 済み前提
- 論文・PR テンプレート:
  - [arXiv 2308.07117](https://arxiv.org/pdf/2308.07117) iSTFTNet2 (Kaneko et al., Interspeech 2023)
  - [arXiv 2506.03554](https://arxiv.org/html/2506.03554) MS-Wavehax (Yoneyama et al., Interspeech 2025)
  - [FLY-TTS PDF (Guo Interspeech 2024)](https://www.isca-archive.org/interspeech_2024/guo24c_interspeech.pdf) ConvNeXt × 6 + iSTFT
  - [`.github/pull_request_template.md`](../../../.github/pull_request_template.md) — 統合 PR body 構造の準拠先
- 関連 skill:
  - `/create-pr` — 統合 PR 提出の唯一の入口 (`gh pr create` 直接禁止、 user memory `feedback_pr_create_skill_only.md`)
  - `/watch-pr` — 統合 PR の CI green / review thread 監視
  - `/release-prep` — `CHANGELOG.md` `## [Unreleased]` の次 release 確定
