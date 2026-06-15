# M2: iSTFTNet2-MB 1D-2D backbone PoC 動作確認

## メタ情報

- ID: M2
- 期間見積: 2 週
- 依存マイルストーン: M1 (CSS10 JA PoC データセット整備)
- 含まれるチケット: [AI-03](../tickets/AI-03-istftnet2-backbone-impl.md), [AI-04](../tickets/AI-04-istftnet2-unit-tests.md), [AI-05](../tickets/AI-05-istftnet2-training.md)
- ステータス: TODO
- ブランチ: feat/decoder-istftnet2-mswavehax-poc
- 親計画: [../../research/implementation-plan-a1-a2-2026-06-16.md §5](../../research/implementation-plan-a1-a2-2026-06-16.md)

## フェーズの目的とゴール

A-1 (iSTFTNet2-MB 1D-2D backbone) の PoC を CSS10 JA 単一話者で完走させ、 既存 1D MB-iSTFT baseline と同等以上の合成品質を保ちつつ CPU RTF を baseline 27ms → target 18ms (× 0.7) まで縮められるかを実機検証することが本フェーズのゴールである。 計画 §1 Executive Summary が示すように iSTFTNet2-MB は zero prior art (Q13) のため 50 epoch 投資後の proxy MOS / RTF 退化が最大のリスクであり、 M2 は「投資判断のための一次データ取得」を担う。

設計上の核心は「既存 1D 経路を default に温存したまま 2D backbone を sibling として追加する」ことである (計画 §4.2)。 `MBiSTFTGenerator.forward` を `_forward_1d` と `_forward_1d2d` に分離し `decoder_type` config で切替えることで、 6lang base ckpt からの warm start を維持し、 同時に PR #222 (Multi-scale FiLM 改造) との HIGH conflict を「`_apply_film` の rank-aware 化のみ」に局所化する。 これは M6 での PR #222 rebase コストを最小化するための前倒し投資でもある。

2D 化のもう一つの設計制約は mobile EP (iOS CoreML MLProgram / Android NNAPI) での CPU fallback 回避である。 `ConvTranspose2d` の使用は `ups[0]/[1]` の 2 段のみに局所化し、 F 軸拡大は pixel-shuffle (Reshape+Transpose) で実装する (計画 §4.2 / Risk R7)。 これにより ONNX op set audit で `Conv2d / Reshape / Transpose` のみを許可する CI gate が成立し、 将来の mobile EP smoke 拡張時に backbone 再設計を回避できる。

## 達成判定 (Exit Criteria)

計画 §5 Milestone 2 の Exit Criteria を以下に展開する。

- `src/python/tests/test_istftnet2_generator.py` が green であること。 検証: `uv run --no-sync pytest src/python/tests/test_istftnet2_generator.py --no-cov` がローカル / CI 両方で pass。
- `decoder_type` を未指定 (default = `mb_istft_1d`) にした場合に 6lang MB-iSTFT base ckpt (`/data/piper/output-multilingual-6lang-mb-istft/multilingual-6lang-mb-istft-scratch-75epoch.onnx` 由来 ckpt) から resume できること。 検証: smoke 学習 1 epoch + WandB audio log で既存 baseline と聴感差分なし、 `scripts/check_a1_a2_isolation.py` (AI-15 で skeleton 整備) が default 経路への regression を機械 check。
- UTMOS proxy MOS が CSS10 JA 200 test utt で baseline ± 0.1 以内であること。 検証: M5 で導入する `tools/benchmark/proxy_mos.py` を本フェーズで先行利用し、 50 epoch ckpt の ONNX export + UTMOS v2 wrapper でスコア計測。
- Xeon E5-2650 v4 / 25 phoneme 英文での CPU 推論 p50 が 20ms 未満であること (target は §4.6 で 18ms、 Exit gate は 20ms と +2ms の安全幅)。 検証: README.md canonical 環境 (warmup 5 + 30 runs) で再測定し `tools/benchmark/` の time 系列を WandB に upload。

## Deliverable

- `src/python/piper_train/vits/mb_istft.py` に `decoder_type` 分岐を追加 (`_forward_1d` 温存 + `_forward_1d2d` 新規実装、 0.83M ± 0.05M params)。 `Conv2d / ConvTranspose2d` import を `mb_istft.py:14` 付近に追加。
- `src/python/tests/test_istftnet2_generator.py` 新規 (既存 `test_mb_istft_generator.py` は touch しない、 G-1.9 後方互換 gate)。
- CSS10 JA 50 epoch 学習 ckpt 一式 (`/data/piper/output-css10-ja-istftnet2-mb-poc/` 配下に `best.ckpt` / 最終 epoch ckpt / WandB run id を含む)。
- 上記 ckpt からの ONNX export (`/data/piper/output-css10-ja-istftnet2-mb-poc/istftnet2-mb-1d2d-50epoch.onnx`) と forward smoke ログ。

## チケット一覧と進捗

| ID | 概要 | 工数 | 依存 | ステータス |
|----|------|------|------|-----------|
| [AI-03](../tickets/AI-03-istftnet2-backbone-impl.md) | iSTFTNet2-MB 1D-2D backbone 実装 (`decoder_type` 分岐 + `_forward_1d2d` 新規、 Conv2d/ConvTranspose2d import、 PQMF/iSTFT/subband_conv_post 流用) | 3d | AI-01 | TODO |
| [AI-04](../tickets/AI-04-istftnet2-unit-tests.md) | `test_istftnet2_generator.py` 新規 (TDD 先行、 forward shape / params count / default 経路 regression を網羅) | 0.5d | AI-03 | TODO |
| [AI-05](../tickets/AI-05-istftnet2-training.md) | iSTFTNet2-MB PoC 学習 50 epoch (CSS10 JA、 6lang base ckpt の 1D 部分のみ warm start、 `decoder_type='istftnet2_mb_1d2d'`) | 1.5d | AI-03, AI-04 | TODO |

## このフェーズで考慮すべき主要リスク

- **R1 (PR #222 Multi-scale FiLM との HIGH conflict)**: `_apply_film` が channel-axis split (dim=1) 前提で 4D `[B,C,F,T]` で破綻する可能性。 本フェーズでの mitigation は「`_forward_1d` を default に温存」+ 「`_forward_1d2d` を独立 method として隔離」することで A-1 を PR #222 より先行 merge 可能な形に保つこと。 M6 (PR #222 rebase) で `_apply_film` rank-aware 化を最小差分で吸収する設計余地を残す。
- **R2 (6lang base ckpt resume の warm start 喪失)**: PR #222 の emb_g 削除 + Flow dilation 変更で base ckpt が resume 不能になる前に PoC を完走させる必要がある。 本フェーズでは PR #222 merge 前の現行 dev (torch 2.2 / py3.11) で実施し、 `--from-scratch` 並走を fall back として Day 0 から準備する。 AI-05 の学習開始前に warm start ロード成功を smoke で確認する。
- **R3 (Q13 zero prior art による 50 epoch 投資失敗)**: proxy MOS -0.3 以上の劣化や CPU RTF 退化が起きると A-1 採用は不能となる。 M3 (FLY-TTS 並走 harness) が同時進行で保険を確保するが、 M2 単体では Day 4 評価で中間 ckpt (25 epoch 相当) の proxy MOS と forward 時間を一次確認し、 早期失敗指標として「proxy MOS が baseline -0.2 未満かつ p50 が baseline 比 +10% 以上」なら学習打ち切りを判断する。
- **R7 (mobile EP CPU fallback 検証未実施)**: 本フェーズでは mobile EP smoke は範囲外だが、 ONNX op audit を AI-03 のレビューチェックリストに含め、 `ConvTranspose2d` が `ups[0]/[1]` の 2 段のみに局所化されていること / F 軸拡大が pixel-shuffle のみで実装されていることを export 時の onnx graph 上で目視確認する。 ここで漏れると M5 の 7 ランタイム ABI 検証でやり直しが発生する。

## 一から作り直すとしたら (Phase-level rethinking)

このフェーズを一から組むとしたら、 最初に再考すべきは「学習 50 epoch を Exit gate に含めるかどうか」だろう。 現計画は AI-05 で 50 epoch 完走を要求するが、 これは Q13 zero prior art への投資判断を「データを取ってから決める」スタイルに振っている。 別案として「AI-03 + AI-04 完了時点で 5 epoch sanity + ONNX export + CPU RTF 計測のみを M2 Exit にし、 50 epoch 学習は M5 のベンチマーク収集フェーズに統合する」設計があり得る。 これなら M2 を 1 週で締め、 R3 の早期失敗を Day 3-4 で確定できる。 現計画が 50 epoch を M2 に含めるのは M3 (FLY-TTS) と並走させて GPU 時間を共有する意図だが、 1 GPU 直列なら 5 epoch sanity 分離の方が情報価値が高い。

次に再考すべきは TDD 順序である。 計画は AI-03 (実装) → AI-04 (テスト) と順序付けているが、 §8 Immediate Next Steps では「`test_istftnet2_generator.py` を TDD で先に書く」と矛盾する記述がある。 一から作るなら AI-04 を AI-03 の依存に逆転させ、 forward shape contract (`[B,1,T]` 不変、 params 0.83M ± 0.05M、 default `_forward_1d` の出力 byte-for-byte 一致) を先に red test として固定する方が安全である。 既存 `test_mb_istft_generator.py` を touch しない制約と組み合わせれば、 1D 経路 regression を test で守りつつ 2D 経路を埋める red-green サイクルが成立する。

データセット選択も再考の余地がある。 CSS10 JA を選んだのは 6lang base ckpt との互換性 (ja=0) と 14h subset の手頃さだが、 既存 つくよみちゃん FT データセット (`/data/piper/dataset-tsukuyomi-finetune-6lang`、 100 utt) を smoke 用に併用する選択肢がある。 100 utt なら 5 epoch sanity が 30 分以内で回り、 AI-03 完成直後に forward path の異常を即時検出できる。 CSS10 JA 14h はベンチマーク用に温存し、 開発ループは つくよみちゃん 100 utt + CSS10 JA 200 val/test の二段構成にする方が R3 早期検出に資する。

最後にアーキテクチャ観点での代替案として、 2D backbone を `_forward_1d2d` という新 method ではなく「`MBiSTFTGenerator2D` 別クラス + factory function」で隔離する設計もある。 現計画の method 分岐方式は params 流用 (`conv_pre` / `subband_conv_post` / `OnnxISTFT` / `PQMF`) が簡潔になる利点があるが、 PR #222 の Multi-scale FiLM が `__init__` レベルで `cond_layers` を差し込む構造なので、 class 分離の方が PR #222 rebase 時の `__init__` 衝突を完全回避できる。 method 分岐 vs class 分離は実装着手前に AI-03 設計レビューで再確認する余地がある。

## 後続マイルストーンへの連絡事項

- **M4 (MS-Wavehax dual vocoder PoC) への引き渡し**: AI-10 は本フェーズで得た A-1 baseline ckpt (`/data/piper/output-css10-ja-istftnet2-mb-poc/best.ckpt` 想定) を acoustic model として freeze し vocoder-only FT を 30 epoch 走らせる。 引き渡し時には (a) ckpt 絶対パス、 (b) `decoder_type='istftnet2_mb_1d2d'` で export した ONNX、 (c) `subband_conv_post` 出力の中間 tensor shape (wavehax 入力契約) を M4 着手前に確定する。 仮置きパスとして `/data/piper/output-css10-ja-istftnet2-mb-poc/` を本フェーズで採用する旨を M4 ticket 本文にも明記する。
- **M5 (7 ランタイム ABI 検証 + audio-parity 再 baseline) への引き渡し**: AI-12 の `tools/benchmark/models.yaml` に追加する `istftnet2-mb` entry の ONNX 配置場所 (上記 M4 と同じパス) と、 AI-14 で追加する `audio-parity-contract.toml [istftnet2_mb_1d2d]` section の p50 / SNR 期待値を本フェーズ Exit 時点の計測値で確定する。 特に CPU p50 が 20ms 未満かどうかは M5 の expected_p50_ms gate に直接転記される。
- **PR #222 / #537 監視継続**: 本フェーズ完了時点で PR #222 が ready 化していたら M6 着手前に reviewer として `_apply_film` rank-aware 化と emb_g→spk_proj 重み移行スクリプトをリクエストする。 PR #537 が merge 済みなら M6 の bf16-mixed + pytest 9 再 benchmark を AI-16 に組み込む。
- **暫定設定の明示**: 本フェーズは PR #537 merge 前の現行 dev (torch 2.2 / py3.11 / CUDA 12.6) で実施するため、 学習 hparam の `--precision 32-true` / `--no-wavlm` / `noise_scale=0.667` 固定値を ckpt メタデータに記録する。 M6 で PR #537 merge 後の bf16-mixed 再 baseline で tolerance 拡張する際の参照点となる。

## 関連ドキュメント

- 親計画: [../../research/implementation-plan-a1-a2-2026-06-16.md](../../research/implementation-plan-a1-a2-2026-06-16.md)
- 改善調査: [../../research/improvement-survey-2026-06-15.md](../../research/improvement-survey-2026-06-15.md)
- Deep-dive: [../../research/decoder-upgrades-istftnet2-and-mswavehax.md](../../research/decoder-upgrades-istftnet2-and-mswavehax.md)
- 既存 spec: [../../spec/audio-parity-contract.toml](../../spec/audio-parity-contract.toml) (`[mb_istft_1d]` 編集禁止、 `[istftnet2_mb_1d2d]` は M5 で追加)
- 論文: [iSTFTNet2 (arXiv 2308.07117)](https://arxiv.org/pdf/2308.07117) Kaneko et al., Interspeech 2023, NTT
- 影響 PR: [#222 Zero-shot TTS](https://github.com/ayutaz/piper-plus/pull/222) (M6 で rebase 統合判定)
