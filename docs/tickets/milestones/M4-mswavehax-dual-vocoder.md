# M4: MS-Wavehax dual vocoder PoC 動作確認

## メタ情報

- ID: M4
- 期間見積: 1.5 週
- 依存マイルストーン: M2 (iSTFTNet2-MB 1D-2D backbone PoC 動作確認)
- 含まれるチケット: [AI-08](../tickets/AI-08-wavehax-vocoder-impl.md), [AI-09](../tickets/AI-09-configure-optimizers-hook.md), [AI-10](../tickets/AI-10-wavehax-training.md), [AI-11](../tickets/AI-11-voice-streaming-integration.md)
- ステータス: TODO
- ブランチ: feat/decoder-istftnet2-mswavehax-poc
- 親計画: [../../research/implementation-plan-a1-a2-2026-06-16.md §5](../../research/implementation-plan-a1-a2-2026-06-16.md)

## フェーズの目的とゴール

A-2 MS-Wavehax を **dual vocoder の右枝** (sibling decoder) として導入し、 短文 streaming 時に MB-iSTFT-VITS よりも低 latency / 同等以上の音質で chunk を返す経路を確立する。 M2 で確立した iSTFTNet2-MB / 既存 1D MB-iSTFT の acoustic model を **freeze** したまま vocoder 部のみ 30 epoch FT し、 0.332M params の軽量 vocoder を**companion ONNX** (`tsukuyomi.wavehax.onnx`) として独立配布する。 これにより既存 ONNX I/O を一切変えず PR #222 の 7 ランタイム ABI 同期 diff に乗せる形で同期コストを 1 回に集約する設計を実証する。

本フェーズの核心は 「**枠組み流用 + 増築**」 の徹底にある。 `models.py:754` の既存 `self.dec` をそのまま残し、 `enable_wavehax` フラグ時のみ sibling として `self.dec_wavehax` を追加する。 EMA `shadow_params` と `infer_forward model_g.dec(...)` の既存経路は完全不変、 wavehax は別 ONNX session として `voice.py` から phoneme 数 (デフォルト閾値 25) に応じて切り替える。 `text_splitter.py` は decoder-agnostic を維持するため一切 touch しない (`text-splitter-contract.toml` も不変)。

合わせて AI-09 で `configure_optimizers` に `_collect_g_params` hook を導入し、 後続の PR #222 (WavLM-D + DINO の opt_d/opt_g 拡張) との衝突を構造的に回避する。 これは M6 (PR #222 rebase 取込) で rank-aware FiLM 拡張差分のみで吸収できる前提を作るための土台であり、 dual vocoder 単独動作確認だけでなく後続マイルストーンの rebase コストを直接抑える設計判断である。

## 達成判定 (Exit Criteria)

- **companion ONNX export 完了**: `uv run python -m piper_train.export_onnx --decoder-branch wavehax <ckpt> tsukuyomi.wavehax.onnx` が ONNX I/O 不変 (入力 `phoneme_ids` / `input_lengths` / `scales` / `sid|speaker_embedding`、 出力 `[B, 1, T]` float32) で成功し、 既存 `tsukuyomi.onnx` (acoustic + 1D MB-iSTFT) と pairwise 動作する
- **sub-80ms streaming chunk で MB-iSTFT 比低 p50**: `tools/benchmark/` の variant `mswavehax` を `models.yaml` に追加し、 phoneme 数 25 / Xeon E5-2650 v4 / warmup 5 + 30 runs で MB-iSTFT-1D baseline (canonical 27ms) より低い p50 を観測 (具体的 target は M5 で 7 runtime 横断 audit、 本フェーズは Python 単独で chunk-level に絞る)
- **MOS baseline ± 0.15**: UTMOS proxy (AI-12 で導入予定の `proxy_mos.py` の先取り、 200 test utt) で 1D MB-iSTFT baseline ± 0.15 以内
- **既存経路 forward-only smoke green**: `enable_wavehax=False` のデフォルト経路で `pytest src/python/tests/test_mb_istft_generator.py` および既存 `tsukuyomi.onnx` の 7 runtime smoke (M3 / M5 経由) が完全不変であることを CI で gate
- **streaming 閾値切替が動作**: `PiperVoice(wavehax_model_path=..., streaming_threshold_phonemes=25)` で `synthesize_stream` 経由の合成が phoneme 数に応じて session 切替され、 閾値超過分は既存 `self.dec` 経路 (acoustic + 1D MB-iSTFT) にフォールバックする
- **`_collect_g_params` hook が PR #222 と非衝突**: AI-09 で導入した hook が `configure_optimizers` の最終 return shape を変えず (既存 `opt_g` / `opt_d` の 2 optimizer 構造維持)、 PR #222 の WavLM-D + DINO 拡張時に「集約関数差分のみ」で取り込める形になっている (rebase dry-run を AI-09 PR body に記録)

## Deliverable

- **`src/python/piper_train/vits/wavehax.py`** (新規) — spectral envelope + harmonic-aware shift + complex residual + `OnnxISTFT(n_fft=64, hop=16)` を実装、 0.332M params
- **`src/python/piper_train/vits/models.py`** — `models.py:754` 直後の sibling 追加 (`enable_wavehax` フラグ条件下のみ `self.dec_wavehax` を生やす)、 既存 `self.dec` / `infer_forward` / EMA `shadow_params` は完全不変
- **`src/python/piper_train/vits/lightning.py`** — `_collect_g_params` hook 追加 (AI-09)、 `configure_optimizers` の return 構造 (`[opt_g, opt_d]`) は不変、 hook は G の trainable parameters 列挙を集約関数化するのみ
- **`/data/piper/output-css10-ja-mswavehax-poc/`** — vocoder-only FT 30 epoch ckpt (acoustic model freeze、 `--wavehax-lr 2e-4`)、 WandB log 付き
- **`tsukuyomi.wavehax.onnx`** (companion ONNX) — `/data/piper/output-css10-ja-mswavehax-poc/wavehax.onnx` として export、 既存 ONNX I/O 完全不変
- **`src/python_run/piper/voice.py`** — `PiperVoice.__init__` に `wavehax_model_path: Path | None = None` と `streaming_threshold_phonemes: int = 25` を optional named arg として追加、 `synthesize_stream` 内で `split_sentences` 後に phoneme 数で session 切替
- **`src/python/piper_train/__main__.py`** — CLI `--enable-wavehax` / `--freeze-acoustic` / `--wavehax-lr` フラグ追加
- **`src/python/tests/test_wavehax_vocoder.py`** (新規) — wavehax forward smoke、 ONNX export I/O 不変 assert、 dual vocoder sibling 構造 assert
- **streaming benchmark log** — `tools/benchmark/results/mswavehax-css10-ja.json` に Python 単独 chunk-level p50 / p95 を記録

## チケット一覧と進捗

| ID | 概要 | 工数 | 依存 | ステータス |
|----|------|------|------|-----------|
| [AI-08](../tickets/AI-08-wavehax-vocoder-impl.md) | MS-Wavehax vocoder 実装 + dual vocoder 統合 (wavehax.py 新規) | 2.5d | AI-02 (M1 baseline ckpt) | TODO |
| [AI-09](../tickets/AI-09-configure-optimizers-hook.md) | configure_optimizers に `_collect_g_params` hook 追加 | 1d | AI-08 | TODO |
| [AI-10](../tickets/AI-10-wavehax-training.md) | MS-Wavehax vocoder-only FT 学習 30 epoch | 1d | AI-09 | TODO |
| [AI-11](../tickets/AI-11-voice-streaming-integration.md) | voice.py に `wavehax_model_path` + streaming 閾値切替実装 | 1d | AI-10 | TODO |

## このフェーズで考慮すべき主要リスク

- **R4 (companion ONNX の ABI 破壊誤認 / 二重同期)**: A-2 の `voice.py` 引数追加と 7 ランタイム `PiperVoice __init__` 拡張が ABI 破壊と誤認される、 もしくは PR #222 rebase 後の ONNX I/O 変更と二重同期になる可能性がある。 本フェーズでは Python 側で **optional named arg** (default None) を徹底し、 既存 caller を一切壊さない。 7 ランタイム同期は M5 で行うが、 companion ONNX は **同 contract に固定** (入力 4 + 出力 1 の既存形式不変) して PR #222 の 7 ランタイム同期 diff に乗せられる形で 1 回完了させる前提を Python 側でも崩さない。
- **R5 (PR #537 TF32-on + bf16-mixed + NumPy 2.x の torch.fft 互換性)**: MS-Wavehax は `torch.fft` と wavelet ops に依存し、 PR #537 merge 後の bf16-mixed default で 1e-3 magnitude drift が増幅する可能性がある。 本フェーズは PR #537 merge **前**の現行 dev (torch 2.2 / py3.11 / CUDA 12.6) で完走し、 PR #537 merge 後は M6 / AI-16 で torch 2.11 sandbox FFT op 互換 check + 5 epoch sanity 再学習に切り出す。 本フェーズ単独では blocking しない。
- **R6 (`audio-parity-contract.toml` baseline 誤書換)**: 本フェーズで `[mswavehax]` section を追加する誘惑があるが、 contract 編集は M5 / AI-14 に集約する。 本フェーズでは `[mb_istft_1d]` baseline を絶対に touch しない。 `enable_wavehax=False` の default 経路が完全に不変であることを CI gate で機械 check する。
- **R8 (1 GPU 占有他作業との衝突)**: vocoder-only FT 30 epoch は 1 GPU で ~12h と見積もり (CLAUDE.md Template B、 batch 4 / `--precision 32-true` / `--no-wavlm`)。 M1 baseline + M2 iSTFTNet2 と連続で GPU を占有するため、 他学習との競合時は CSS10 JA 14h を 7h subset (`/data/piper/dataset-css10-ja-poc-half/`) に絞り epoch 数を維持して代替する。 acoustic freeze で勾配計算が vocoder 部のみに局所化されるため batch を上げる余地もある (V100 でも 8 程度まで)。

## 一から作り直すとしたら (Phase-level rethinking)

本フェーズの設計を一から考え直すなら、 まず **「dual vocoder の必要性」 を M4 着手前に厳しく検証する流れ** を採用したい。 現行計画は M2 完了直後に M4 (dual vocoder) に進むが、 M2 の iSTFTNet2-MB が CPU RTF 目標 (18ms / × 0.7) を満たしていれば streaming 閾値で session を切り替える必然性は薄れる。 「M2 evaluation gate」 を新設し、 iSTFTNet2-MB の Xeon p50 が 20ms を切った時点で **M4 は条件起動 (skip 可)** に格下げする選択肢を検討したい。 これは companion ONNX の配布コストと 7 ランタイム ABI 説明コスト (M5 で 4 variant 説明する負担) を最初から削減できる。

次に、 **vocoder-only FT を 30 epoch で済ませる前提を疑う**。 MS-Wavehax 論文 (Yoneyama et al., Interspeech 2025) は MOS gain を主張するが Q13 (iSTFTNet2 zero prior art) と同様、 piper-plus の CSS10 JA / 0.332M params 軽量設定で MOS が baseline ± 0.15 に収まる保証はない。 本気でやるなら 30 epoch を `freeze-acoustic` ON で 15 epoch + OFF で 15 epoch の **2 段 FT** に分けて、 後半は acoustic も微調整する選択肢を試したい。 ただし PR #222 rebase 後の emb_g 削除と衝突するため、 後半段は PR #222 merge 後の M6 に回す方が無難であり、 結果として「現行 30 epoch / freeze 一貫」 はリスク管理として妥当との結論に戻る。

第三に、 **`_collect_g_params` hook を AI-09 で別チケット化する判断を見直したい**。 本来 AI-08 の dual vocoder 統合と同一 PR にまとめれば configure_optimizers の差分が atomic になり review burden が減る。 別チケットに切ったのは PR #222 rebase 時の merge granularity を細かくする狙いだが、 実運用では hook 単独 PR の review 観点が薄く、 「hook を入れる動機」 を別途説明する必要が生じる。 一から作るなら AI-08 + AI-09 を 1 PR (3.5d) に統合し、 PR body の Risk Level セクションで PR #222 rebase 計画を明示する形が現実的だと思う。

最後に、 **TDD で書く順序**。 現行計画は AI-08 (実装 2.5d) → AI-09 (hook) → AI-10 (学習) → AI-11 (voice.py) の順だが、 `test_wavehax_vocoder.py` の forward smoke と companion ONNX export I/O 不変 assert を **AI-08 着手前** に書く方が、 sibling 統合点 (`models.py:754`) の周辺で既存 `self.dec` 経路を壊さない設計を実装中に常時 verify できる。 また `voice.py` の streaming 閾値切替 (AI-11) はそれ単体でモック ONNX (small Conv1d だけの dummy) で TDD 可能で、 AI-10 の学習完了を待たず先行着手できる (`/data/piper/output-css10-ja-mswavehax-poc/wavehax.onnx` を dummy で代替し integration はあとで差し替え)。 早期失敗指標としては 「AI-08 着手 1d 経過時点で `models.py` の sibling 追加が `infer_forward` 既存経路を壊していない」 ことを最小 unit test で常時 green に保つことが最重要であり、 これが崩れた段階で AI-10 / AI-11 を起動しない gate を skill `/precheck` で機械 check する形にしたい。

## 後続マイルストーンへの連絡事項

M5 (7 runtime smoke / audio-parity 再 baseline) に引き渡す具体的成果物と前提:

- **companion ONNX のパス**: `/data/piper/output-css10-ja-mswavehax-poc/wavehax.onnx` を canonical とする。 M5 / AI-12 で `tools/benchmark/models.yaml` に `mswavehax` entry を追加する際はこの絶対パスを使用 (Python 単独 benchmark は本フェーズで完了済み、 7 runtime 横断は M5 で実施)
- **既存 ONNX (`tsukuyomi.onnx`) は不変**: 本フェーズは acoustic + 1D MB-iSTFT の既存 ONNX を一切触らない。 M5 で 4 variant (`mb_istft_1d` / `istftnet2_mb_1d2d` / `fly_convnext6` / `mswavehax`) を並べる際の baseline は既存 ONNX をそのまま使う
- **`PiperVoice` API 仕様**: `wavehax_model_path: Path | None = None` (default None で既存挙動)、 `streaming_threshold_phonemes: int = 25` (本フェーズで確定値、 M5 で 7 runtime ABI 拡張時は同じ default を使用)。 M5 / AI-13 の Rust `new_with_wavehax` / Go option pattern / C# optional named arg / C-API 新 entry はこの API を直訳する形で実装
- **`audio-parity-contract.toml` の `[mswavehax]` section は未追加**: 本フェーズでは absolutely touch せず、 M5 / AI-14 で追加する。 contract のテンプレ案 (期待 SNR ≥ 30dB / 出力 shape `[1,1,T]` float32 / streaming chunk p50 規定) を AI-14 担当者へ引き渡すために `docs/tickets/notes/M4-handoff-to-M5.md` (本フェーズ完了時に作成、 暫定) を残す
- **`_collect_g_params` hook の構造**: M6 / AI-17 (PR #222 rebase) で WavLM-D + DINO の opt_d/opt_g 拡張時に hook を 1 行差分 (集約対象に `dec.spk_proj.parameters()` 追加) で取り込む想定。 hook 内のループ順序 (`yield from self.net_g.dec.parameters()` 直後に `if hasattr(self.net_g, "dec_wavehax"): yield from self.net_g.dec_wavehax.parameters()`) は変更しないことを M6 担当者に明示
- **暫定設定の明示**: `streaming_threshold_phonemes=25` は CSS10 JA / Xeon E5-2650 v4 / 1D MB-iSTFT 27ms 基準で決めた値。 M5 で 7 runtime benchmark を取った結果 (特に ARM / WASM の RTF) によっては 20 / 30 への再調整が必要。 M5 完了後に AI-14 と同時に最終値を `voice.py` の default に反映する
- **PR #222 / #537 状況**: 本フェーズ完了時点で両 PR が未 merge である前提。 もし M4 完走中に PR #537 が merge された場合 (CONFLICTING → CLEAN 遷移)、 M6 / AI-16 に進む前に bf16-mixed + TF32-on で `wavehax.py` の `torch.fft` 5 epoch sanity を**先行**して取得し、 M5 の 7 runtime smoke を bf16 で行うか fp32 で行うか判断する材料にする

## 関連ドキュメント

- 親計画: [../../research/implementation-plan-a1-a2-2026-06-16.md](../../research/implementation-plan-a1-a2-2026-06-16.md)
- 改善調査: [../../research/improvement-survey-2026-06-15.md](../../research/improvement-survey-2026-06-15.md)
- Deep-dive: [../../research/decoder-upgrades-istftnet2-and-mswavehax.md](../../research/decoder-upgrades-istftnet2-and-mswavehax.md)
- 既存仕様:
  - [`docs/spec/audio-parity-contract.toml`](../../spec/audio-parity-contract.toml) — M5 / AI-14 で `[mswavehax]` section 追加予定 (本フェーズでは編集禁止)
  - [`docs/spec/text-splitter-contract.toml`](../../spec/text-splitter-contract.toml) — **編集禁止** (decoder-agnostic 維持)
  - [`docs/spec/ort-session-contract.toml`](../../spec/ort-session-contract.toml) — companion ONNX session 設定の参照元
- 影響 PR:
  - [#222 Zero-shot TTS (CAM++ + DINO)](https://github.com/ayutaz/piper-plus/pull/222) — `_collect_g_params` hook で rebase 衝突回避
  - [#537 Python 3.13 + CUDA 12.8 + Ubuntu 24.04 統一](https://github.com/ayutaz/piper-plus/pull/537) — merge 後 M6 / AI-16 で `torch.fft` 再 benchmark
- 論文:
  - [arXiv 2506.03554](https://arxiv.org/html/2506.03554) MS-Wavehax (Yoneyama et al., Interspeech 2025)
  - [arXiv 2210.15975](https://arxiv.org/abs/2210.15975) MB-iSTFT-VITS (Kawamura et al., ICASSP 2023, 既存実装の枠組み)
