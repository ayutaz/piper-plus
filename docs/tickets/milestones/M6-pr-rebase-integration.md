# M6: PR #222 / #537 rebase 取込と統合判定

## メタ情報

- ID: M6
- 期間見積: 2 週
- 依存マイルストーン: [M5](M5-runtime-abi-audio-parity.md) + PR #537 merge + PR #222 merge
- 含まれるチケット: [AI-16](../tickets/AI-16-pr537-rebase-benchmark.md), [AI-17](../tickets/AI-17-pr222-rebase-integration.md), [AI-18](../tickets/AI-18-adoption-report.md)
- ステータス: TODO
- ブランチ: feat/decoder-istftnet2-mswavehax-poc
- 親計画: [../../research/implementation-plan-a1-a2-2026-06-16.md §5](../../research/implementation-plan-a1-a2-2026-06-16.md)

## フェーズの目的とゴール

本マイルストーンは A-1 / A-2 PoC の **採否判定と dev への統合** を扱う最終フェーズである。 M1-M5 で完成した CSS10 JA PoC 成果物 (1D baseline / iSTFTNet2-MB 1D-2D / FLY-TTS / MS-Wavehax companion / 7 ランタイム smoke / `audio-parity-contract.toml` の新 variant section) を、 並走していた 2 つの in-flight PR (#537 プラットフォーム統一 / #222 Zero-shot TTS) の merge 完了後に取り込み、 4 指標 (UTMOS / CPU RTF / ONNX op coverage / 7 ランタイム smoke) で dev 統合の採否を最終判断する。

A-1/A-2 PoC を PR #222/#537 より先行 merge した戦略の最大の負債が本フェーズに集中する。 PR #537 は TF32-on + bf16-mixed default + pytest 9 を持ち込むためコード衝突こそ無いが 1e-3 magnitude の数値ドリフトを発生させ、 `audio-parity-contract.toml` の tolerance 拡張なしには pairwise SNR≥30dB gate が落ちる。 PR #222 は `_apply_film` が channel-axis split (dim=1) 前提のため A-1 の 4D ([B,C,F,T]) backbone と forward 構造で HIGH conflict を起こし、 rank-aware 化と ONNX I/O の `sid → speaker_embedding[192]` 同期を A-1/A-2 export 経路 (companion ONNX 含む) で同時反映する必要がある。

ゴールは 3 段階に分かれる。 第一に PR #537 merge 後の bf16-mixed + TF32-on 環境で全 variant の 5 epoch sanity + ONNX export + benchmark を再測定し audio-parity の tolerance を新環境に合わせて拡張する (AI-16)。 第二に PR #222 merge 後の `_apply_film` rank-aware 化と ONNX I/O 同期を A-1/A-2 経路に反映し 7 ランタイム ABI 同期を PR #222 既存 diff に乗せて 1 回で完了させる (AI-17)。 第三に 4 指標で A-1 採用 / FLY-TTS 切替 / 1D 継続のいずれかを判断し採否判定レポートを PR body に記載して `/create-pr` で統合 PR を提出する (AI-18)。

## 達成判定 (Exit Criteria)

- **rebase 後 audio-parity test green**
  - 検証: `uv run --no-sync pytest src/python/tests/test_audio_parity.py --no-cov` が全 variant で pass (新 tolerance section 反映後)
  - CI gate: `audio-parity` workflow が PR #222 / #537 merge 後の dev で green (ubuntu-24.04 + py3.13 + torch 2.11)
  - 補強: `[mb_istft_1d]` baseline section が編集されていないことを `scripts/check_audio_parity_baseline.py` で機械 check (M5 の AI-15 で導入済み gate を継続利用)
- **bf16-mixed + TF32-on 再 benchmark 完了**
  - 検証: AI-16 で全 variant (1D baseline / istftnet2-mb / fly-convnext6 / mswavehax companion) の 5 epoch sanity が ubuntu-24.04 + py3.13 + torch 2.11 で完走、 ONNX export が成功
  - benchmark: `tools/benchmark/` で再測定した Xeon E5-2650 v4 p50 (25 phoneme 英文) を新 baseline として `audio-parity-contract.toml` に反映
- **PR #222 rebase 完了 + FiLM rank-aware 化検証**
  - 検証: `_apply_film` が `decoder_type` に応じて 1D (split dim=1) と 2D ([B,C,F,T]) 両方で動作することを `test_istftnet2_generator.py` + 既存 PR #222 test で確認
  - ONNX I/O 同期: A-1 backbone と A-2 companion ONNX の両方で `sid → speaker_embedding[192]` 入力変更が反映され 7 ランタイム smoke green
- **7 ランタイム ABI 同期完了 (1 回完了原則)**
  - 検証: Rust / Go / C# / WASM / C++ / C-API で PR #222 の `speaker_embedding[192]` 入力を受領しつつ A-1/A-2 経路でも `[1,1,T]` float32 / pairwise SNR ≥ 30 dB を維持
  - CI gate: M5 で導入した `regression-guard` workflow が全 7 ランタイムで pass
- **採否判定レポート完成と統合 PR 提出**
  - 検証: 4 指標 (UTMOS / CPU RTF / ONNX op coverage / 7 ランタイム smoke) の判定表が AI-18 の成果物として markdown に記録される
  - 判断: A-1 採用 / FLY-TTS 切替 / 1D 継続の **いずれか 1 案** が PR body に明示され、 `/create-pr` 経由で統合 PR が dev に向けて提出されている
  - 構造: PR body が `pull_request_template.md` の section 構造 (Summary / Test Plan / Risk Level / Affected Components / Type) に準拠

## Deliverable

- **AI-16 成果物 (PR #537 merge 後の再 benchmark)**
  - 全 variant の 5 epoch sanity ログ: `tools/benchmark/results/css10-ja-poc-py313-torch211/` 配下に variant 別 JSON
  - 更新後 contract: `docs/spec/audio-parity-contract.toml` に bf16-mixed + TF32-on 環境の tolerance 拡張 (新キー: `bf16_tolerance_db` / `tf32_drift_threshold`)
  - 再測定 benchmark: `README.md` の Benchmark 表に新 baseline (ubuntu-24.04 + py3.13 + torch 2.11、 Xeon p50) を追記
- **AI-17 成果物 (PR #222 rebase + FiLM rank-aware 化)**
  - 編集: `src/python/piper_train/vits/mb_istft.py` の `_apply_film` を rank-aware 化 (1D: split dim=1 / 2D: split dim=1 維持 + spatial broadcast)
  - 編集: `src/python/piper_train/vits/models.py` の `cond_layers` channel schedule を `decoder_type` 別に保持
  - 編集: `src/python/piper_train/export_onnx.py` の A-1 backbone export と A-2 companion ONNX export 経路で `sid → speaker_embedding[192]` 入力同期
  - 編集: 7 ランタイム inference (Rust / Go / C# / WASM / C++ / C-API) の入力 spec 同期 (PR #222 既存 diff に追従)
- **AI-18 成果物 (採否判定と統合 PR)**
  - 採否レポート: `docs/research/a1-a2-adoption-report-2026-09-XX.md` (4 指標判定表 + 推奨案 + 根拠)
  - 統合 PR: `feat/decoder-istftnet2-mswavehax-poc` → `dev` (or close 判断時の closing comment)
  - PR body: `pull_request_template.md` 準拠、 採否判断 (A-1 採用 / FLY-TTS 切替 / 1D 継続) を Summary に明示

## チケット一覧と進捗

| ID | 概要 | 工数 | 依存 | ステータス |
|----|------|------|------|-----------|
| [AI-16](../tickets/AI-16-pr537-rebase-benchmark.md) | PR #537 merge 後の bf16-mixed + TF32-on 全 variant 5 epoch sanity + ONNX export + benchmark 再測定、 audio-parity tolerance 拡張 | 2d | M5 AI-15, **PR #537 merge** | TODO |
| [AI-17](../tickets/AI-17-pr222-rebase-integration.md) | PR #222 merge 後の `_apply_film` rank-aware 化 + `cond_layers` channel schedule 分岐 + ONNX I/O sid→speaker_embedding[192] 同期 (A-1 backbone + A-2 companion ONNX) + 7 ランタイム ABI 同期 | 3d | AI-16, **PR #222 merge** | TODO |
| [AI-18](../tickets/AI-18-adoption-report.md) | 4 指標 (UTMOS / CPU RTF / ONNX op coverage / 7 ランタイム smoke) で採否判定、 レポート作成、 `/create-pr` 経由で dev 統合 PR 提出 | 2d | AI-17 | TODO |

## このフェーズで考慮すべき主要リスク

- **R1 (HIGH/HIGH): PR #222 Multi-scale FiLM と A-1 1D-2D backbone の forward 構造 HIGH conflict** — 本フェーズの中核リスク。 `_apply_film` が channel-axis split (dim=1) 前提のため 4D ([B,C,F,T]) で破綻する。 mitigation: AI-17 で `_apply_film` を rank-aware (1D=split dim=1 / 2D=split dim=1 維持 + spatial broadcast) に拡張する差分のみで吸収。 M2-M4 で `_forward_1d` / `_forward_1d2d` を分離済みのため、 forward 本体への侵襲はゼロに保つ。 PR #222 既存 test と `test_istftnet2_generator.py` を並走させて rank-aware 拡張の正しさを double check。
- **R4 (MEDIUM/MEDIUM): A-2 companion ONNX と PR #222 の ONNX I/O 変更の二重同期** — AI-17 で 7 ランタイム ABI 同期を PR #222 既存 diff に乗せて **1 回で完了** させる戦略が本フェーズで実行される。 mitigation: companion ONNX も同 contract (`sid → speaker_embedding[192]`) に固定し、 Rust new_with_wavehax / Go option pattern / C-API 新 entry の ABI 互換性を維持しつつ I/O 変更だけを差分として乗せる。 AI-17 の 7 ランタイム smoke で SNR≥30dB の continuity を検証。
- **R5 (MEDIUM/MEDIUM): PR #537 の TF32-on + bf16-mixed default + NumPy 2.x + pytest 9** — 本フェーズの第一段階 (AI-16) で正面突破する。 mitigation: torch-2.11 sandbox で全 variant 5 epoch sanity を先に通し、 1e-3 magnitude drift を `audio-parity-contract.toml` の tolerance 拡張に反映。 pytest 9 deprecation で既存 mb_istft fixture が落ちる場合は AI-16 内で fixture 修正を完結させ AI-17 を blocking しない。
- **R6 (MEDIUM/HIGH): `audio-parity-contract.toml` の baseline regression を AI-16 が誤って書き換え 1D MB-iSTFT への regression を silently 招く** — M5 AI-14 で `[mb_istft_1d]` section 編集禁止 gate (`scripts/check_audio_parity_baseline.py` + `contract-gates.yml`) を導入済み。 AI-16 では `[istftnet2_mb_1d2d]` / `[mswavehax]` / `[fly_convnext6]` の tolerance 拡張のみに編集を局所化し、 `[mb_istft_1d]` への touch を gate で機械 block。 PR body checklist でも二重 check。

## 一から作り直すとしたら (Phase-level rethinking)

本フェーズの設計を一から考えるなら、 最初に再考すべきは **「PR #222 / #537 を blocking 依存にすること自体の是非」** である。 採用したアプローチは「A-1/A-2 PoC を先行 → in-flight PR 待ち → rebase 取込」だが、 この戦略は 2 つの PR が永久に DRAFT のまま漂流するリスク (PR #222 は実際に 25 日 stale + mergeable=UNKNOWN) を本フェーズで全て吸収させる構造になっている。 代替案として「**PR #222 の機能を A-1/A-2 ブランチ内で local fork して評価し、 統合 PR を 3 つ並列に提出する**」案が考えられる。 これなら PR #222 が永久 stale でも本フェーズが unblock できるが、 reviewer の review burden が 3 倍化し emb_g→spk_proj 重み移行の責務が PoC 側に移転するためトータルでは loss が大きい。 採用案 (本マイルストーン) のままが妥当だが、 PR #222 が更に 2 週間 stale を続ける場合の **escape hatch** (A-1/A-2 のみで先に statistical merge し PR #222 後追い吸収) を AI-18 の判断軸に追加すべきだった。

第二に **AI-17 の差分粒度** を再設計するなら、 「`_apply_film` rank-aware 化」「`cond_layers` 分岐」「ONNX I/O 同期」「7 ランタイム ABI 同期」 の 4 タスクを 1 チケット (3d) に詰め込まずに、 各タスクを独立 PR として分割し reviewer の cognitive load を下げる選択肢がある。 特に 7 ランタイム ABI 同期は他フェーズ (M5 AI-13) で既に類似作業の経験があるため、 ABI 同期だけを独立 PR にして merge を先行できれば、 FiLM rank-aware 化の review が ONNX レイヤーの議論に汚染されない。 ただしこれは PR #222 既存 diff に乗せる戦略 (R4 mitigation の核心) と矛盾するため、 「PR #222 が ONNX I/O 同期を含んだまま merge される」 という前提が崩れた場合のみ採用すべき。

第三に **採否判定の構造** を再考するなら、 現在の 4 指標 (UTMOS / CPU RTF / ONNX op coverage / 7 ランタイム smoke) は閾値 (baseline ± 0.1 / × 0.7 / op 限定 / SNR≥30dB) の AND 判定になっているが、 これは「全部の指標で baseline 超過」を要求するため A-1 採用のハードルが高過ぎる。 代替として **weighted score (UTMOS 0.4 / CPU RTF 0.3 / ONNX op coverage 0.2 / 7 ランタイム smoke 0.1) で総合判定** する設計のほうが「CPU RTF だけ × 0.65 で目標未達だが UTMOS は +0.15」のような微妙なケースに対応できる。 早期失敗指標として「**Day 1 で AI-16 の sanity が 1 variant でも fail したら AI-17/AI-18 を中止して PR #222 後追いを諦め、 PR #537 のみ取込で close 判断**」 という kill switch を AI-16 の Exit Criteria に追加することも、 永久 stale を避ける現実的な工夫として考えられる。

第四に **本フェーズ全体を直列ではなく integration-first** で再設計するなら、 AI-16 (PR #537 再 benchmark) を待たずに PR #222 merge を先に受け、 「TF32 drift と FiLM rank-aware 化を同時に audio-parity に吸収」 することで 2 段階を 1 段階に圧縮できる。 ただし bf16-mixed と Multi-scale FiLM の interaction が未知のため debug 困難になるリスクがあり、 採用案 (PR #537 → PR #222 直列) のほうが root cause isolation の点で優れる。 一から作り直すなら「**AI-16 と AI-17 の境界を contract 編集権限で分離** (AI-16 は tolerance のみ編集可、 AI-17 は variant section のみ編集可)」 という権限分離を明示化し、 contract 編集の責務を機械的に強制する設計を採るのが理想的である。

## 後続マイルストーンへの連絡事項

本マイルストーン完了でプロジェクトは終了する。 統合 PR が dev へ merge される場合と close される場合の 2 分岐を想定し、 後続作業に引き渡すべき成果物を以下に明示する。

**A-1 採用で dev 統合 PR merge した場合:**
- 新 baseline ckpt: `/data/piper/output-css10-ja-poc-istftnet2-mb-rebased/` 配下の rebase 後 50 epoch ckpt (PR #222 + PR #537 環境で再学習推奨、 学習コマンドは AI-18 PR body に記載)
- ONNX 配布: `tsukuyomi.istftnet2.onnx` + `tsukuyomi.wavehax.onnx` (companion) の 2 枚を HuggingFace `ayousanz/piper-plus-tsukuyomi-chan` に追加 push
- contract 追加: `docs/spec/audio-parity-contract.toml` の `[istftnet2_mb_1d2d]` / `[mswavehax]` section が ubuntu-24.04 + py3.13 + torch 2.11 + bf16-mixed の tolerance で確定済み
- 7 ランタイム ABI: PR #222 既存 diff に A-1/A-2 経路の `sid → speaker_embedding[192]` 同期が乗った状態で merge 済み、 後続言語追加 (例: ko/sv の更なる強化) は本 ABI を前提とする
- 次の方向: M5 AI-15 の regression guard CI gate (`regression-guard` workflow) を継続稼働させ、 CSS10 JA 以外の学習データセット (6lang base / 多話者 FT) への iSTFTNet2-MB / MS-Wavehax 拡張は別 epic として切り出す

**FLY-TTS 切替で dev 統合 PR merge した場合:**
- 新 baseline ckpt: `/data/piper/output-css10-ja-poc-fly-convnext6-rebased/` 配下の rebase 後 100 epoch ckpt (50 epoch では不足のため AI-18 で延長判断したケース)
- ONNX 配布: `tsukuyomi.fly.onnx` を HuggingFace に追加 push、 既存 `tsukuyomi.onnx` (1D MB-iSTFT) と併売
- contract: `[fly_convnext6]` section のみが採用 variant、 `[istftnet2_mb_1d2d]` / `[mswavehax]` は abandoned variant として section header に `# abandoned 2026-09-XX` コメント追記
- 次の方向: A-2 MS-Wavehax は streaming-only として独立 epic 化、 A-1 iSTFTNet2-MB は backlog として残置

**1D 継続で dev 統合 PR を close した場合:**
- 学習成果: CSS10 JA 50 epoch baseline ckpt のみ HuggingFace に push (補助 baseline として利用可能)
- ブランチ: `feat/decoder-istftnet2-mswavehax-poc` を archive tag (`archive/a1-a2-poc-2026-09`) として保存し close
- 次の方向: 親計画 §1 の通り A-4 (Matcha-TTS) / A-5 (StyleTTS2) ラインに昇格、 改善調査 [improvement-survey-2026-06-15.md](../../research/improvement-survey-2026-06-15.md) の §A-4 / §A-5 を起点に新 epic 立ち上げ

**いずれの場合も共通の引き渡し物:**
- 採否判定レポート `docs/research/a1-a2-adoption-report-2026-09-XX.md` (4 指標判定表 + 根拠)
- PR #222 / #537 rebase の学び: rebase 戦略 (FiLM rank-aware 化 / TF32 tolerance 拡張) を将来の同種衝突 (例: 別 decoder upgrade × Zero-shot TTS) に再利用するためのテンプレートとして抽出
- 仮置きパス: AI-18 までの作業中は `docs/research/a1-a2-adoption-report-2026-09-XX.md` の `XX` を AI-18 着手日に確定、 contract `[istftnet2_mb_1d2d]` の `bf16_tolerance_db` 値は AI-16 完了時に確定

## 関連ドキュメント

- 親計画: [../../research/implementation-plan-a1-a2-2026-06-16.md](../../research/implementation-plan-a1-a2-2026-06-16.md)
- 改善調査: [../../research/improvement-survey-2026-06-15.md](../../research/improvement-survey-2026-06-15.md)
- Deep-dive: [../../research/decoder-upgrades-istftnet2-and-mswavehax.md](../../research/decoder-upgrades-istftnet2-and-mswavehax.md)
- 前マイルストーン: [M5-runtime-abi-audio-parity.md](M5-runtime-abi-audio-parity.md)
- 関連 PR:
  - [#222 Zero-shot TTS (CAM++ + DINO)](https://github.com/ayutaz/piper-plus/pull/222)
  - [#537 Python 3.13 + CUDA 12.8 + Ubuntu 24.04 統一](https://github.com/ayutaz/piper-plus/pull/537)
- 関連 spec:
  - [`docs/spec/audio-parity-contract.toml`](../../spec/audio-parity-contract.toml) — `[istftnet2_mb_1d2d]` / `[mswavehax]` / `[fly_convnext6]` tolerance 拡張対象
  - [`docs/spec/ort-session-contract.toml`](../../spec/ort-session-contract.toml) — bf16-mixed 環境での ORT session 設定継続性
- 論文・PR テンプレート:
  - [arXiv 2308.07117](https://arxiv.org/pdf/2308.07117) iSTFTNet2 (Kaneko et al., Interspeech 2023)
  - [`.github/pull_request_template.md`](../../../.github/pull_request_template.md) — 統合 PR body 構造の準拠先
