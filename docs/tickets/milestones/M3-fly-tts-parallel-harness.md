# M3: FLY-TTS 並走 harness 構築

## メタ情報

- ID: M3
- 期間見積: 2 週
- 依存マイルストーン: M1 (CSS10 JA PoC データセット整備)
- 含まれるチケット: [AI-06](../tickets/AI-06-fly-decoder-impl.md), [AI-07](../tickets/AI-07-fly-training.md)
- ステータス: TODO
- ブランチ: feat/decoder-istftnet2-mswavehax-poc
- 親計画: [../../research/implementation-plan-a1-a2-2026-06-16.md §5](../../research/implementation-plan-a1-a2-2026-06-16.md)

## フェーズの目的とゴール

本フェーズは A-1 (iSTFTNet2-MB 1D-2D backbone) の失敗時に即時切替可能な保険ラインを Day 4 評価までに整える。 親計画 §1 Executive Summary は Q13 (iSTFTNet2 specific MOS は zero prior art) を A-1 最大の不確実性と位置付けており、 50 epoch を投じた後に proxy MOS -0.3 以上の劣化または CPU RTF の退化が判明する事態を前提に保険を確保する必要がある。 FLY-TTS は Guo et al. (Interspeech 2024) によって LJSpeech 上で **MOS 4.12** が実証されており、 アーキテクチャも ConvNeXt × 6 + 単一帯域 iSTFT の極めて軽量 (0.63M params) な構成であるため、 zero prior art リスクが A-1 より大幅に低い唯一の即時代替候補である。

本フェーズの設計は、 親計画 §4.5 と §7 R3 で明示された「Day 5 までに ONNX export + 7 ランタイム smoke 完了」「A-1 失敗時は Day 4 評価で即時 FLY-TTS 100 epoch 延長に切替」という時間制約に従う。 すなわち FLY-TTS は A-1 と同等の完成度 (forward + 学習 + ONNX export + smoke) まで一通り通すが、 採否判断は M5 (benchmark) に委ね、 本フェーズ単体での採用は意図しない。 A-1 採用が確定した場合は本フェーズの成果物は archive 扱いとし、 失敗時のみ M6 統合判定で FLY-TTS 100 epoch 延長に切替える。

並走の独立性も本フェーズ固有の重要なゴールである。 親計画 §3 Conflict Map で `fly_decoder.py` 新規ファイルは PR #222 / #537 とも衝突 NONE と確定しており、 既存 `mb_istft.py` を一切 touch しないため、 M2 (iSTFTNet2-MB) の実装と完全並行で進行できる。 これにより 1 GPU 直列スケジュール内でも FLY-TTS の GPU 枠を A-1 baseline 学習の合間 (CPU 前処理 / WandB upload 時間) に挿し込む形で時間効率を最大化する。

## 達成判定 (Exit Criteria)

親計画 §5 milestone 3 の Exit Criteria 列を展開し、 各項目に検証コマンドと CI gate を追記する。

- **proxy MOS が CSS10 JA baseline ± 0.1 以内** — `uv run python tools/benchmark/proxy_mos.py --variant fly-convnext6 --test-utt 200 --baseline css10-ja-1d-baseline` で計測。 既存 1D MB-iSTFT (M1 で確立した baseline) との差分を絶対値で評価。 CI gate `audio-parity-baseline` (AI-15 で導入予定) に [fly_convnext6] section を仮置きし、 expected_mos_delta_max = 0.1 で fail-fast。
- **CPU RTF が baseline × 0.85 以下** — `uv run python tools/benchmark/run_bench.py --variant fly-convnext6 --device cpu --warmup 5 --runs 30 --phoneme-count 25` で Xeon E5-2650 v4 (README.md canonical 環境) の p50 を測定。 baseline 27ms に対し target 22.95ms 以下。 measurement は audio-parity-contract.toml の expected_p50_ms gate に新 variant section として追加する。
- **ONNX op coverage が Conv1d + LayerNorm のみ** — `uv run python scripts/audit_onnx_ops.py docs/checkpoints/css10-ja/fly-convnext6.onnx --allow-ops Conv1d,LayerNorm,Gelu,Reshape,Transpose,Add,Mul` で audit。 Conv2d / ConvTranspose2d / 特殊 op が 0 件であることを assert。 これは FLY-TTS が PQMF / 2D conv 不使用で構成されることの構造的保証。
- **7 ランタイム smoke が pairwise SNR ≥ 30 dB** — M5 の検証範囲だが、 本フェーズでは Python のみで forward + ONNX export を確認し、 export 済み ONNX を `tools/benchmark/models.yaml` に登録するところまでを担当。 Rust/C#/Go/WASM/C++/C-API の smoke は M5 に委譲し本フェーズの Exit Criteria には含めない。

加えて本フェーズ固有の Exit Criteria として **`fly_decoder.py` の単体テスト (`src/python/tests/test_fly_decoder.py`) が green** であることを要求する。 forward shape `[B, 1, T]` と ONNX export 互換性の 2 観点を最低限カバーする。

## Deliverable

親計画 §5 milestone 3 の Deliverable 列を展開し、 成果物のフルパスを明示する。

- `src/python/piper_train/vits/fly_decoder.py` (新規、 約 200 LoC) — ConvNeXt × 6 (DepthwiseConv1d k=7 + LayerNorm + Conv1d 1×1 expand 4× + GELU + project) + Conv1d(256→1026) + 既存 `stft_onnx.py:OnnxISTFT` 追加 instance (n_fft=1024, hop=256)。 PQMF 完全不使用 + sub-band loss 無効。 既存 `mb_istft.py` / `stft_onnx.py:OnnxISTFT` クラス本体は touch しない (新 instance を生やすのみ)。
- `src/python/tests/test_fly_decoder.py` (新規) — forward shape / ONNX export smoke / parameter count assert (0.63M ± 0.05M) の 3 観点。
- 学習成果物 `/data/piper/output-css10-ja-fly-convnext6/` — 50 epoch の checkpoint (`checkpoint_epoch=50.ckpt`)、 WandB run、 学習 log。
- ONNX 成果物 `/data/piper/output-css10-ja-fly-convnext6/fly-convnext6.onnx` — `export_onnx.py` 経由で export。 ONNX I/O は既存 baseline と不変 (PR #222 二重同期回避)。
- `tools/benchmark/models.yaml` に `fly-convnext6` entry 追加 — M5 (benchmark) で参照可能にする。
- `docs/checkpoints/css10-ja/fly-convnext6.md` (任意、 PR 本文側で代替可) — params 数、 学習時間、 epoch 50 時点の loss curve サマリ、 op audit 結果。

## チケット一覧と進捗

| ID | 概要 | 工数 | 依存 | ステータス |
|----|------|------|------|-----------|
| [AI-06](../tickets/AI-06-fly-decoder-impl.md) | FLY-TTS ConvNeXt6 decoder 実装 (`fly_decoder.py` 新規、 ~200 LoC、 ConvNeXt × 6 + Conv1d(256→1026) + OnnxISTFT(n_fft=1024, hop=256)、 PQMF 不使用) | 2d | AI-01 (M1) | TODO |
| [AI-07](../tickets/AI-07-fly-training.md) | FLY-TTS PoC 学習 50 epoch (`--c-sub-stft 0.0` で sub-band loss 無効、 CSS10 JA で 6lang base ckpt の cond 部分のみ warm start) | 1.5d | AI-06 | TODO |

## このフェーズで考慮すべき主要リスク

親計画 §7 Risk Register から本フェーズに関係する 3 件を抜粋し、 本フェーズ固有の mitigation 観点を追記する。

- **R3 (HIGH × MEDIUM): Q13 iSTFTNet2-MB zero prior art** — そもそも本フェーズの存在理由が R3 mitigation である。 親計画は「FLY-TTS を同 CSS10 JA で並走、 Day 5 までに ONNX export + 7 ランタイム smoke 完了」を要求しており、 本フェーズはこのタイムラインを保証する。 本フェーズでの追加 mitigation として、 AI-07 の 50 epoch 学習は M2 の AI-05 (iSTFTNet2-MB PoC 学習) と GPU 占有衝突しない時間帯 (例: A-1 学習中の night batch、 A-1 epoch 間隔の checkpoint upload 時間) に挿し込むスケジュール最適化を行う。
- **R8 (MEDIUM × LOW): 1 GPU 直列スケジュールでの GPU 占有衝突** — 親計画は「FLY-TTS 並走は A-1 PoC 結果 (Day 4 評価) 次第で条件起動とし default で blocking しない」と整理しているが、 本マイルストーンでは Day 4 評価より前に AI-06 (実装) は完了させ、 AI-07 (50 epoch 学習) のみ Day 4 評価結果に応じて延長 / 短縮可能とする戦略を採る。 すなわち AI-06 (実装と forward smoke) は GPU を要しないため CPU タスクとして M2 と完全並走させ、 AI-07 の 50 epoch を A-1 不調時に 100 epoch まで延長する余地を残す。
- **R6 (MEDIUM × HIGH): audio-parity-contract.toml の baseline 誤書き換え** — 本フェーズで `[fly_convnext6]` section を新設するが、 `[mb_istft_1d]` は absolutely touch しない (G-1.2 gate)。 AI-15 (M5) で導入予定の `scripts/check_audio_parity_baseline.py` を本フェーズで先行 skeleton 化することを推奨 (親計画 §8 Immediate Next Steps #4 と整合)。

## 一から作り直すとしたら (Phase-level rethinking)

本フェーズの設計を一から問い直すと、 最も検討すべきは「**並走を本当に default で実施すべきか**」という根本判断である。 親計画 §7 R8 は「FLY-TTS 並走は A-1 PoC 結果 (Day 4 評価) 次第で条件起動とし default で blocking しない」と既に integration-first ではなく gated 起動の余地を残しているが、 本マイルストーンではこれを「実装は default、 学習は conditional」と分離した。 別の選択肢として「実装も conditional (A-1 の Day 4 評価が黄信号の時点で着手) にする」案がある。 これは GPU/開発者リソースの完全節約になる一方、 A-1 失敗判明から FLY-TTS 100 epoch 完走までのリードタイムが 3-4 日伸び、 M5 (benchmark) と M6 (統合判定) のスケジュールが圧迫される。 採否判断の柔軟性とリードタイム短縮のバランスで現案を選んだが、 GPU 競合が深刻な現場では conditional 起動案も合理的である。

早期失敗指標の設計も再考の余地がある。 現案では 50 epoch 完走後の proxy MOS のみで判断するが、 ConvNeXt × 6 は 1 GPU で 1 epoch あたり ~38 分 (CSS10 JA 14h subset、 batch=4) と短いため、 **10 epoch 時点で WandB validation loss が baseline の 1.5x を超えていたら abort** という early stopping を入れる選択肢があった。 これは 50 epoch 投資前に hopeless ケースを切り捨て、 A-4/A-5 (Matcha/StyleTTS2) ライン昇格の判断を 2 日早める。 実装計画には反映していないが、 AI-07 着手時に WandB watcher として追加することを推奨する。

**TDD vs integration-first** の方法論選択も再考対象である。 現案は AI-06 内で test_fly_decoder.py を「forward shape + ONNX export smoke + params count」の 3 観点で先行 (TDD 寄り) と暗黙に想定したが、 FLY-TTS は ConvNeXt block の組み合わせが論文と完全一致するか否かが最大のリスク (Guo et al. 2024 の official code release は未確認のため peer reproducibility が低い) であり、 unit test より先に **「LJSpeech で論文値 MOS 4.12 が再現できるか」 を 10 epoch 学習で先に確認する integration-first** が真の早期失敗指標になる可能性がある。 ただしこれは CSS10 JA 14h ではなく LJSpeech 24h を別途用意する必要があり、 M1 (CSS10 JA 整備) の前提を崩すため現案では採用していない。

最後にアーキテクチャ観点として、 **FLY-TTS ではなく Vocos (Siuzdak et al., ICLR 2024) を保険ラインに採用する** 案もあり得た。 Vocos は ConvNeXt + ISTFT という極めて類似した構造を持ちつつ、 公式実装が GitHub に存在し peer reproducibility が高い。 ただし Vocos は元来 GAN vocoder 単体評価のため VITS のような end-to-end TTS への組み込みは追加検証が必要で、 親計画 §4.5 で示された「A-1 失敗時の即時切替」要件 (Day 4 評価から 5 日以内の結論) に間に合わない可能性が高い。 FLY-TTS は元論文が VITS-style 統合を前提としており、 本フェーズの目的に対しては正解だったと判断するが、 zero prior art リスクは Vocos より高いことは認識しておく必要がある。

## 後続マイルストーンへの連絡事項

本マイルストーン完了時点で次のマイルストーン (主に M5 benchmark、 副次的に M2/M6) に引き渡すべき具体的成果物と注意点を以下に示す。

- **ONNX checkpoint パス**: `/data/piper/output-css10-ja-fly-convnext6/fly-convnext6.onnx` を M5 (AI-12) に渡す。 `tools/benchmark/models.yaml` の `fly-convnext6` entry はこのパスを参照するよう設定済み (本フェーズで追加)。
- **学習成果物パス**: `/data/piper/output-css10-ja-fly-convnext6/checkpoint_epoch=50.ckpt` は M2 (AI-05) の `decoder_type='istftnet2_mb_1d2d'` PoC 学習結果と比較する際に proxy MOS 測定のソースとなる。 ckpt は 50 epoch 完了直後の EMA 適用済み状態を保持。
- **`audio-parity-contract.toml` の追加箇所**: 本フェーズで `[fly_convnext6]` section を **仮置き** で追加する (expected_mos_delta_max = 0.1, expected_p50_ms = 23.0)。 確定値は M5 (AI-14) で benchmark 結果を反映して書き換える。 仮置き flag として `# tentative: confirmed in M5` コメントを各値に付ける。
- **`tools/benchmark/models.yaml` の追加 entry**: `fly-convnext6` entry を本フェーズで追加 (variant=fly_convnext6, decoder_type=fly_convnext6)。 M5 で `css10-ja-1d-baseline` (M1 由来) / `istftnet2-mb` (M2 由来) と並べて 3 variant 同時 benchmark する前提を満たす。
- **GPU 占有スケジュール記録**: AI-07 の 50 epoch 学習に費やした実 GPU 時間を WandB の run summary に記録 (`training_wallclock_hours`)。 M6 (AI-18) で「A-1 baseline 学習 36h / A-1 PoC 学習 40h / FLY-TTS 学習 32h」の合計 GPU 時間を集計する際の data source となる。
- **採否判定への引き渡し**: 本フェーズ単体で採否判定を行わない。 M5 benchmark 結果を待って M6 (AI-18) の 4 指標 (UTMOS / CPU RTF / ONNX op coverage / 7 ランタイム smoke) で「A-1 採用 / FLY-TTS 切替 / 1D 継続」のいずれかを決定する。 本フェーズの成果物は「FLY-TTS 切替」が選択された場合に M6 の 100 epoch 延長 base ckpt として再利用される。
- **暫定設定の明示**: `[fly_convnext6]` audio-parity section が tentative であること、 7 ランタイム smoke (Rust/C#/Go/WASM/C++/C-API) が本フェーズ範囲外で M5 に持ち越されることの 2 点を M5 kick-off 時に明示。

## 関連ドキュメント

- 親計画: [../../research/implementation-plan-a1-a2-2026-06-16.md](../../research/implementation-plan-a1-a2-2026-06-16.md) §1 Executive Summary / §4.5 FLY-TTS 並走 / §5 Milestones / §7 R3 R6 R8
- 改善調査: [../../research/improvement-survey-2026-06-15.md](../../research/improvement-survey-2026-06-15.md) §A-1 / §H Track 7
- Deep-dive: [../../research/decoder-upgrades-istftnet2-and-mswavehax.md](../../research/decoder-upgrades-istftnet2-and-mswavehax.md) §2.5 Q13 zero prior art / §5 推奨実装フェーズ
- 関連 spec:
  - [../../spec/audio-parity-contract.toml](../../spec/audio-parity-contract.toml) — `[fly_convnext6]` section を本フェーズで仮置き追加
  - [../../spec/ort-session-contract.toml](../../spec/ort-session-contract.toml) — Conv1d + LayerNorm のみの op set を前提
- 関連論文:
  - [FLY-TTS PDF (Guo et al., Interspeech 2024)](https://www.isca-archive.org/interspeech_2024/guo24c_interspeech.pdf) ConvNeXt × 6 + iSTFT、 MOS 4.12 (LJSpeech)
  - [arXiv 2306.00814](https://arxiv.org/abs/2306.00814) Vocos (Siuzdak et al., ICLR 2024) — 採用しなかった代替案
- 並走対象: M2 ([M2-istftnet2-mb-1d2d-backbone.md](M2-istftnet2-mb-1d2d-backbone.md)) — 本フェーズと完全並走可能
- 後続: M5 ([M5-runtime-abi-audio-parity-rebaseline.md](M5-runtime-abi-audio-parity-rebaseline.md)) で 7 ランタイム smoke と benchmark を確定
