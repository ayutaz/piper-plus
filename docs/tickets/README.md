# Tickets

A-1 (iSTFTNet2-MB) / A-2 (MS-Wavehax) PoC 実装計画 ([../research/implementation-plan-a1-a2-2026-06-16.md](../research/implementation-plan-a1-a2-2026-06-16.md)) を実行するためのマイルストーン + チケット集約 index。

ブランチ: feat/decoder-istftnet2-mswavehax-poc

## 概要

本チケットシステムは、 改善調査統合 §A-1 (iSTFTNet2-MB 1D-2D backbone 化、 Interspeech 2023 NTT) と §A-2 (MS-Wavehax dual vocoder 併設、 Interspeech 2025) の PoC を「現行 dev (torch 2.2 / py3.11 / CUDA 12.6)」で並走させ、 1 GPU × 約 9 週間で採否判定まで完走させるための工程管理レイヤである。 計画の核心はコードではなく **in-flight PR との衝突回避戦略** にあり、 PR #222 (Zero-shot TTS、 Multi-scale FiLM + ONNX I/O 破壊) と PR #537 (Python 3.13 + bf16-mixed + TF32-on) を PoC 完走後に rebase 吸収することで、 二重同期と warm-start 喪失の双方を回避する。

全体は **6 マイルストーン × 18 チケット** に分解される。 M1 (データ整備) は前提、 M2/M3/M4 が PoC 本体 (iSTFTNet2-MB / FLY-TTS 保険 / MS-Wavehax 並走)、 M5 が 7 ランタイム ABI 検証と audio-parity 再 baseline、 M6 が PR rebase 後の統合判定を担う。 各チケットは依存 (blocked by) を明示しており、 M2-M4 は GPU 占有さえ調整できれば並走可能。 単一の `MBiSTFTGenerator.forward` を `_forward_1d` (既存温存) と `_forward_1d2d` (新規) に分離して `decoder_type` config 分岐に落とすことで、 baseline 退化と PR #222 衝突を同時に断つのが設計上の最重要決定である。

PoC 失敗時の保険として **FLY-TTS** (ConvNeXt × 6 + iSTFT、 MOS 4.12 実証済) を同 CSS10 JA dataset で並走させ、 Q13 (iSTFTNet2 specific MOS の zero prior art) リスクに対する fallback を Day 0 から確保している。 採否判定は 4 指標 (UTMOS proxy / CPU RTF / ONNX op coverage / 7 ランタイム smoke) で M6 の AI-18 にて実施し、 「A-1 採用」「FLY-TTS 切替」「1D 継続 + A-4/A-5 ライン昇格」のいずれかを統合 PR body に記載する。

## マイルストーン一覧

| ID | 概要 | 期間 | チケット | ステータス |
|----|------|------|---------|-----------|
| [M1](milestones/M1-css10-ja-dataset.md) | CSS10 JA PoC データセット整備 | 0.2 週 | AI-01, AI-02 | TODO |
| [M2](milestones/M2-istftnet2-mb-backbone.md) | iSTFTNet2-MB 1D-2D backbone PoC 動作確認 | 2 週 | AI-03, AI-04, AI-05 | TODO |
| [M3](milestones/M3-fly-tts-parallel-harness.md) | FLY-TTS 並走 harness 構築 | 2 週 | AI-06, AI-07 | TODO |
| [M4](milestones/M4-mswavehax-dual-vocoder.md) | MS-Wavehax dual vocoder PoC 動作確認 | 1.5 週 | AI-08, AI-09, AI-10, AI-11 | TODO |
| [M5](milestones/M5-runtime-abi-parity.md) | 7 ランタイム ABI 検証 + audio-parity 再 baseline | 1.5 週 | AI-12, AI-13, AI-14, AI-15 | TODO |
| [M6](milestones/M6-pr-rebase-integration.md) | PR #222 / #537 rebase 取込と統合判定 | 2 週 | AI-16, AI-17, AI-18 | TODO |

## チケット一覧

| ID | マイルストーン | 概要 | 工数 | ステータス |
|----|---------------|------|------|-----------|
| [AI-01](tickets/AI-01-css10-dataset-prep.md) | [M1](milestones/M1-css10-ja-dataset.md) | CSS10 JA データセット取得 + 前処理 | 0.5d | TODO |
| [AI-02](tickets/AI-02-baseline-training.md) | [M1](milestones/M1-css10-ja-dataset.md) | 既存 1D MB-iSTFT baseline 学習 50 epoch | 1.5d | TODO |
| [AI-03](tickets/AI-03-istftnet2-backbone-impl.md) | [M2](milestones/M2-istftnet2-mb-backbone.md) | iSTFTNet2-MB 1D-2D backbone 実装 (decoder_type 分岐 + _forward_1d2d) | 3d | TODO |
| [AI-04](tickets/AI-04-istftnet2-unit-tests.md) | [M2](milestones/M2-istftnet2-mb-backbone.md) | iSTFTNet2-MB ユニットテスト追加 (test_istftnet2_generator.py) | 0.5d | TODO |
| [AI-05](tickets/AI-05-istftnet2-training.md) | [M2](milestones/M2-istftnet2-mb-backbone.md) | iSTFTNet2-MB PoC 学習 50 epoch | 1.5d | TODO |
| [AI-06](tickets/AI-06-fly-decoder-impl.md) | [M3](milestones/M3-fly-tts-parallel-harness.md) | FLY-TTS ConvNeXt6 decoder 実装 (fly_decoder.py 新規) | 2d | TODO |
| [AI-07](tickets/AI-07-fly-training.md) | [M3](milestones/M3-fly-tts-parallel-harness.md) | FLY-TTS PoC 学習 50 epoch | 1.5d | TODO |
| [AI-08](tickets/AI-08-wavehax-vocoder-impl.md) | [M4](milestones/M4-mswavehax-dual-vocoder.md) | MS-Wavehax vocoder 実装 + dual vocoder 統合 (wavehax.py 新規) | 2.5d | TODO |
| [AI-09](tickets/AI-09-configure-optimizers-hook.md) | [M4](milestones/M4-mswavehax-dual-vocoder.md) | configure_optimizers に _collect_g_params hook 追加 | 1d | TODO |
| [AI-10](tickets/AI-10-wavehax-training.md) | [M4](milestones/M4-mswavehax-dual-vocoder.md) | MS-Wavehax vocoder-only FT 学習 30 epoch | 1d | TODO |
| [AI-11](tickets/AI-11-voice-streaming-integration.md) | [M4](milestones/M4-mswavehax-dual-vocoder.md) | voice.py に wavehax_model_path + streaming 閾値切替実装 | 1d | TODO |
| [AI-12](tickets/AI-12-benchmark-3-variants.md) | [M5](milestones/M5-runtime-abi-parity.md) | tools/benchmark/ に 3 variant 追加 + UTMOS proxy MOS | 1.5d | TODO |
| [AI-13](tickets/AI-13-runtime-smoke-snr.md) | [M5](milestones/M5-runtime-abi-parity.md) | 7 ランタイム smoke + pairwise SNR 検証 | 3d | TODO |
| [AI-14](tickets/AI-14-audio-parity-contract.md) | [M5](milestones/M5-runtime-abi-parity.md) | audio-parity-contract.toml に新 variant section 追加 | 1d | TODO |
| [AI-15](tickets/AI-15-regression-guard-ci.md) | [M5](milestones/M5-runtime-abi-parity.md) | regression guard CI gate 整備 | 1.5d | TODO |
| [AI-16](tickets/AI-16-pr537-rebase-benchmark.md) | [M6](milestones/M6-pr-rebase-integration.md) | PR #537 merge 後の bf16-mixed + TF32-on 再 benchmark | 2d | TODO |
| [AI-17](tickets/AI-17-pr222-rebase-integration.md) | [M6](milestones/M6-pr-rebase-integration.md) | PR #222 merge 後の FiLM rank-aware 化 + ONNX I/O 同期 | 3d | TODO |
| [AI-18](tickets/AI-18-adoption-report.md) | [M6](milestones/M6-pr-rebase-integration.md) | 採否判定レポート作成と統合 PR 提出 | 2d | TODO |

## ステータス凡例

- TODO: 未着手
- WIP: 着手中
- BLOCKED: PR #222 / #537 等の外部依存待ち
- DONE: 完了
- CANCELLED: 採否判定で却下

## 使い方

- 新規チケットを追加する場合は `tickets/AI-XX-<slug>.md` を作成し、 本 README の「チケット一覧」表と該当マイルストーンの `milestones/M<N>-*.md` 双方に追記する (相互リンクの非対称が `/check-runtime-parity` 相当の手動レビューを増やすため)。
- ステータス更新は本 README の表と該当チケット本体の両方で同期する。 BLOCKED 時は理由 (例: `BLOCKED (待ち: PR #222 ready)`) を一言補記する。
- マイルストーン単位の進捗集約は `milestones/M<N>-*.md` 側の Exit Criteria checklist で行う。 チケット側には作業ログと artifact パス (学習 output / ONNX / benchmark 結果) を残す。
- PR を提出する際は本文末尾に対応チケット ID を 1 行で記載する (例: `Refs: AI-03, AI-04`)。 `/create-pr` skill が `pull_request_template.md` の Risk Level / Affected Components を埋めるため、 チケット側の影響範囲記述と整合させる。
- マイルストーン横断で衝突する変更 (例: `mb_istft.py` を AI-03 と PR #222 が両方触る) は本 README の「ステータス凡例」を `BLOCKED` 扱いにし、 親計画 §3 Conflict Map の該当行を root-of-truth とする。
- 採否判定 (AI-18) で却下された PoC は CANCELLED に降格させ、 削除しない (採否判断の歴史的記録として残す)。
- 週次の `/loop /watch-pr 222` / `/loop /watch-pr 537` 結果は本 README 末尾ではなく、 AI-16 / AI-17 チケット側に追記する (index の git churn 抑制)。

## フェーズ進行と全体省察 (Project-level rethinking)

**PoC dataset 選定について。** CSS10 JA 単一話者 (14h) を選んだ最大の理由は「6lang base ckpt との emb_lang 整合」と「1 GPU での 50 epoch 完走可能性」の二点である。 一から設計するなら LJSpeech 単一話者英語 (24h、 prior art 豊富、 UTMOS reference 取得容易) も有力候補だった。 しかし英語 PoC は 6lang base ckpt の warm start 利益を全部捨てる (Q5 LR scheduling が scratch から始まる) ため、 CSS10 JA を採った。 もし PR #222 の emb_g 削除で結局 warm start が失われるリスクが顕在化したら、 LJSpeech に乗り換えて scratch 比較に切替える備えはしている (R2 mitigation)。 別案として「つくよみちゃん FT dataset (100 utt) の 10 倍水増し」も検討したが、 PoC で MOS proxy を評価するには発話多様性が決定的に不足し、 採用しなかった。

**並走戦略 (FLY-TTS 保険) について。** Q13 (iSTFTNet2-MB の zero prior art) リスクを直視し、 FLY-TTS (MOS 4.12 実証済) を Day 0 から保険として走らせる判断は、 工程の冗長性を 1.5 倍に増やすが採否判定を Day 4-5 で確定できる利益が大きい。 一から考えるなら「保険を Matcha-TTS にしてアーキテクチャ階層をもう一段下げる」案もあった。 しかし Matcha は ODE solver で CPU RTF 評価が PoC の枠を超える (Q8 ODE step 探索が必要) ため、 同じ iSTFT family で済む FLY-TTS を選んだ。 結果としてアーキテクチャ多様性は犠牲になったが、 benchmarks/audio-parity contract / ONNX export パイプラインを使い回せる工程上の利益のほうが大きい。 保険を起動せず A-1 単独に賭ける選択肢は、 失敗時に M3 を作り直す 2 週間のリスクを直接吸収できないので採らなかった。

**dual vocoder vs adaptive 構造について。** A-2 を「dec_wavehax を sibling として併設、 streaming_threshold_phonemes で session 切替」とする決定は、 PR #222 の単一 dec 前提との衝突を最小化するために導いた現実解である。 一から設計するなら **adaptive vocoder** (`MBiSTFTGenerator` 内に branch を持ち forward で動的選択) が ONNX export 単一ファイルで済み、 voice.py への streaming 閾値追加も不要となる。 ただし adaptive 構造は `infer_forward` を全 7 ランタイムで二重化し、 EMA `shadow_params` と WavLM-D の opt_g 拡張を PR #222 と二重同期させるため、 companion ONNX 案 (本計画) に対して PR rebase コストが 2-3 倍になる試算となった。 companion ONNX は配布ファイル数が増える運用負荷を、 ONNX I/O 不変による ABI 互換維持の利益で相殺している。

**6 マイルストーン分割の粒度について。** M1/M2/M3/M4 を機能名 (CSS10 / iSTFTNet2-MB / FLY-TTS / MS-Wavehax) で区切り、 M5/M6 を横断機能 (ランタイム ABI / 統合判定) で区切る現状は、 採否判定が M6 末で 1 回しか走らない一段モデルとなっている。 一から設計するなら **M2 / M3 / M4 各末で stage gate を入れる二段モデル** (Day 4 で A-1 採否、 Day 7 で MS-Wavehax 採否、 Day 14 で統合採否) も有力だった。 stage gate を 1 回に集約した現状の利点は、 「指標 (UTMOS / CPU RTF / ONNX op / 7 ランタイム smoke) を測る環境を M5 で一度組み上げれば再利用できる」点にある。 二段にすると各 stage で部分的 benchmark harness を組み、 後で結合する手戻りが出る。 ただし PoC で A-1 が早期に明確に失敗 (proxy MOS -0.3 以上) した場合に FLY-TTS への切替判断が Day 4 で必要となるため、 AI-12 の前倒し着手 (3 variant 同時 benchmark) で実質的に二段モデルの利益も部分的に取りに行っている。

**PR #222 との merge 順について。** 「A-1/A-2 PoC を先に完走させ、 PR #222 を後から rebase 吸収」とする merge 順は、 PR #222 が DRAFT + 25 日 stale + 6 軸破壊的変更という状態を直視した結果である。 一から設計するなら「PR #222 を先に reviewer として完成させる」案もあった。 これは PR #222 の Multi-scale FiLM 設計を A-1 1D-2D backbone と最初から共存可能 (rank-aware) に強制できる利益はあるが、 PR #222 の再学習 200 epoch + SECS/MCD 評価が未完なため A-1 着手が 4-6 週間遅延する。 PoC の核心は「2026-06-16 起点で 9 週間以内に採否判断を出す」ことなので、 PR #222 完成を待たず PoC を先行させ、 FiLM rank-aware 化を AI-17 で 1 回吸収する現状案を採った。 PR #222 が PoC 期間中に ready になった場合は reviewer として `_apply_film` rank-aware 化と emb_g→spk_proj 重み移行スクリプトをリクエストし、 統合コストを低減させる予備手段も §8.5 で用意している。

## 関連ドキュメント

- 親計画: [../research/implementation-plan-a1-a2-2026-06-16.md](../research/implementation-plan-a1-a2-2026-06-16.md)
- 改善調査統合: [../research/improvement-survey-2026-06-15.md](../research/improvement-survey-2026-06-15.md)
- Decoder Upgrade deep-dive: [../research/decoder-upgrades-istftnet2-and-mswavehax.md](../research/decoder-upgrades-istftnet2-and-mswavehax.md)
- 影響 PR: [#222](https://github.com/ayutaz/piper-plus/pull/222), [#537](https://github.com/ayutaz/piper-plus/pull/537)
