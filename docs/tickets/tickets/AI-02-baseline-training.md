# AI-02: 既存 1D MB-iSTFT baseline 学習 50 epoch

## メタ情報

- ID: AI-02
- 親マイルストーン: [M1](../milestones/M1-css10-ja-dataset.md)
- 工数見積: 1.5 日
- 依存チケット: [AI-01](AI-01-css10-dataset-prep.md)
- 後続チケット: AI-08 (MS-Wavehax vocoder-only FT の acoustic freeze 元)、 AI-12 (`tools/benchmark/` における 3 variant 比較対象)
- ステータス: TODO
- ブランチ: feat/decoder-istftnet2-mswavehax-poc
- 親計画 §: [§6 Action Items / §4 PoC 設計 / §5 Milestones](../../research/implementation-plan-a1-a2-2026-06-16.md)

## タスク目的とゴール

AI-01 で整備された CSS10 JA single-speaker dataset (`/data/piper/dataset-css10-ja-poc/processed/`) を入力として、 既存 1D MB-iSTFT 経路 (`decoder_type='mb_istft_1d'`) を 50 epoch 学習し、 後続 PoC 系列 (M2 iSTFTNet2-MB / M3 FLY-TTS / M4 MS-Wavehax) すべてが参照する baseline ckpt を確保する。 親計画 §6 AI-02 が指定する要件は二点に絞られる: (1) 6lang MB-iSTFT base ckpt から warm start すること、 (2) `noise_scale=0.667` を明示固定して PR #222 の default 変更影響を排除すること。

本チケットの最終成果物は二系統に渡って下流に流れ込む。 一系統目は AI-08 (MS-Wavehax vocoder-only FT) であり、 ここでは本 baseline ckpt の acoustic model 部分 (`enc_p` / `flow` / `dp` / `posterior`) を freeze しながら sibling `dec_wavehax` のみ学習する。 acoustic model の品質が下流の vocoder FT 上限を決めるため、 50 epoch で発散していないこと・WandB audio log で品質が baseline 想定 (UTMOS proxy MOS が dev `multilingual-test-medium.onnx` と同等以上) であることが受入要件となる。 二系統目は AI-12 (`tools/benchmark/` の 3 variant 比較) であり、 親計画 §4.6 が定める「CPU RTF (Xeon E5-2650 v4 / 25 phoneme 英文) baseline 27ms」 「proxy MOS baseline ± 0.1」 の比較対照として本 ckpt の ONNX export 版が使われる。

副次的な狙いとして、 親計画 §2.2 PR #537 が未 merge である現行 dev (torch 2.2 / py3.11 / CUDA 12.6) で baseline を確定しておくことで、 後続 M6 AI-16 の bf16-mixed + TF32-on 再 benchmark との差分軸を「環境差 1 軸のみ」 に閉じ込め、 `audio-parity-contract.toml` の tolerance 拡張議論を干渉なく行えるようにする。

## 実装内容の詳細

学習スクリプト・モデルコード本体には**コード変更を加えない**。 AI-03 (M2) で `mb_istft.py` に `decoder_type` 分岐を追加する前段階のため、 本チケットは既存 default 経路 (= 現在の `MBiSTFTGenerator.forward` 単一実装) を素のまま使う。 設定面と学習引数のみで baseline を確保する。

### 編集対象ファイル (新規・最小)

- 新規: `/data/piper/output-css10-ja-poc/baseline-1d/training.sh` (約 30 行)
  - Template B (CLAUDE.md §学習テンプレート) を CSS10 JA 用に固定した shell script。 引数固定で再現性を確保。
- 新規: `/data/piper/output-css10-ja-poc/baseline-1d/config-override.json` (約 10 行)
  - `noise_scale: 0.667` を明示固定 (PR #222 が default を変更する前提のため記録として残す)
  - `decoder_type: "mb_istft_1d"` を将来の AI-03 merge 後でも default として明示
- 既存 touch しない: `src/python/piper_train/__main__.py`、 `vits/mb_istft.py`、 `vits/models.py`、 `vits/lightning.py`、 `export_onnx.py`
  - G-1.2 baseline 編集禁止 gate と G-1.9 後方互換 gate の両方に該当。 本チケットで触ると AI-03 / AI-15 の `[mb_istft_1d]` audio parity 不変性を侵す

### 学習コマンド (CLAUDE.md Template B を 1 GPU / CSS10 JA 用に派生)

```bash
export WANDB_API_KEY=$(grep WANDB_API_KEY /data/piper/.env | cut -d= -f2) && \
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
nohup /data/piper/.venv/bin/python -m piper_train \
    --dataset-dir /data/piper/dataset-css10-ja-poc/processed \
    --prosody-dim 16 \
    --accelerator gpu --devices 1 --precision 32-true \
    --max_epochs 50 --batch-size 4 --samples-per-speaker 4 \
    --checkpoint-epochs 10 --quality medium \
    --base_lr 2e-5 --disable_auto_lr_scaling \
    --ema-decay 0.9995 --max-phoneme-ids 400 --no-wavlm \
    --val-every-n-epochs 10 --audio-log-epochs 10 \
    --resume-from-multispeaker-checkpoint \
        /data/piper/output-multilingual-6lang-mb-istft/last.ckpt \
    --default_root_dir /data/piper/output-css10-ja-poc/baseline-1d \
    > /data/piper/output-css10-ja-poc/baseline-1d/training.log 2>&1 &
```

主要引数の根拠 (CLAUDE.md Template B との差分):

- `--devices 1`: 1 GPU 直列スケジュール (親計画 §4.4)、 V100 想定で `--precision 32-true` 必須
- `--max_epochs 50`: 親計画 §4.4 baseline 50ep / 推定 ~36h
- `--no-wavlm`: V100 推奨設定。 WavLM-D は GPU +1-2GB 消費するため CSS10 JA 14h scale では費用対効果が薄い
- `--val-every-n-epochs 10` / `--audio-log-epochs 10`: 親計画 §4.4 推定時間内に validation overhead を抑える
- `--resume-from-multispeaker-checkpoint`: emb_g 除去 + emb_lang 補正 + freeze-dp 自動有効化 (CLAUDE.md §転移学習)、 6lang base からの warm start

### ONNX export (学習完了後、 AI-12 比較対照確保のため)

```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
    /data/piper/output-css10-ja-poc/baseline-1d/checkpoints/epoch=49-step=*.ckpt \
    /data/piper/output-css10-ja-poc/baseline-1d/css10-ja-baseline-1d.onnx
```

- FP16 default、 stochastic default、 emb_lang 自動統一 (シングルスピーカー多言語で自動有効)。 AI-12 の `tools/benchmark/models.yaml` の `css10-ja-1d-baseline` entry にこの ONNX を登録する

### PR #222 / #537 conflict 回避策 (親計画 §3 Conflict Map 該当抜粋)

- `src/python/piper_train/vits/mb_istft.py` (Conflict Map: A-1/A-2 用途で HIGH vs PR #222): 本チケットでは触らないため衝突なし。 AI-03 が `decoder_type` 分岐を入れる前提を尊重し、 baseline ckpt は「分岐前の単一実装で生成された ckpt」 として正本性を確保する
- `src/python/piper_train/vits/models.py` (Conflict Map: HIGH vs PR #222): 同様に touch しない。 PR #222 の spk_proj 統合点が現行 emb_g 経路と異なる構造を取るため、 baseline ckpt は emb_g 経路で生成された ckpt として保存し、 PR #222 merge 後の emb_g→spk_proj 重み移行スクリプト (R2 mitigation 依頼項目) の入力となる
- `src/python_run/piper/text_splitter.py` (Conflict Map: 編集禁止): 本チケットは推論側を触らないため自然に維持
- `docs/spec/audio-parity-contract.toml`: 本チケットでは編集しない (M5 AI-14 で新 variant を併載するまで `[mb_istft_1d]` section は不変)。 本チケット完了時点で baseline benchmark 数値を worklog に保存するのみ

### 設定 default 値 / 新規 CLI フラグ

- 新規 CLI フラグなし (既存 `--resume-from-multispeaker-checkpoint` / `--no-wavlm` / `--prosody-dim 16` のみ使用)
- 設定 default 不変: `decoder_type` は AI-03 で導入されるが、 本チケット段階では default 経路 = 現行 `MBiSTFTGenerator.forward` 一択であり「`mb_istft_1d` 相当」 として扱う

## エージェントチームの役割と人数

| 役割 | 人数 | 責任範囲 |
|------|-----|---------|
| ML Training Engineer | 1 | 学習スクリプト確定・1 epoch sanity 実行・50 epoch 本実行・WandB run 監視。 必要スキル: PyTorch Lightning / DDP 経験 / WandB CLI / NCCL tuning |
| Benchmark Engineer | 1 | 学習完了 ckpt の ONNX export・Xeon E5-2650 v4 上での RTF 測定・UTMOS proxy MOS 測定。 必要スキル: ONNX Runtime / onnxsim / UTMOS v2 wrapper / CPU 性能計測 (warmup 5 + 30 runs) |
| QA / Worklog Steward | 1 | Exit Criteria の機械検査 (ckpt 存在 / WandB media artifact / loss 曲線非発散) と worklog 記録 (`/data/piper/output-css10-ja-poc/baseline-1d/README.md`)。 必要スキル: GH CLI / WandB API / 親計画 §7 Risk Register の追跡 |

3 名構成とする根拠: 本チケットは「学習実行 + ベンチマーク取得 + 記録」 の三段で完結し、 コード変更が伴わないため Lead Implementer は不要。 ML Training Engineer が GPU 占有時間 ~36h の watch を担い、 並行して Benchmark Engineer が AI-12 用の比較対象 ONNX を仕上げ、 QA が後続 (AI-08 / AI-12) への引き継ぎ事項を worklog に固定する。 3 名のうち ML Training Engineer と QA は M1 内 (AI-01 → AI-02) で連続稼働し、 Benchmark Engineer は学習完了後の最終 1 日のみの稼働で済む。

## 提供範囲 (Scope)

### 含むもの

- CSS10 JA single-speaker dataset (`/data/piper/dataset-css10-ja-poc/processed/`) を入力とした 1D MB-iSTFT baseline 50 epoch 学習
- `decoder_type='mb_istft_1d'` 相当の default 経路 + `noise_scale=0.667` 固定
- 6lang base ckpt (`/data/piper/output-multilingual-6lang-mb-istft/last.ckpt`) からの warm start (emb_g 除去 + emb_lang 補正 + freeze-dp 自動)
- 学習成果物 `/data/piper/output-css10-ja-poc/baseline-1d/` 一式 (checkpoints / training.log / WandB run URL)
- 学習完了後の ONNX export (`css10-ja-baseline-1d.onnx`、 FP16 + stochastic + emb_lang 自動統一)
- Xeon E5-2650 v4 上での CPU RTF 測定 (25 phoneme 英文 / warmup 5 + 30 runs) と UTMOS proxy MOS 測定 (200 test utt)
- worklog (`/data/piper/output-css10-ja-poc/baseline-1d/README.md`) に benchmark 数値 + WandB URL + PR #222/#537 状態スナップショット記録

### 含まないもの (Out of Scope)

- `mb_istft.py` への `decoder_type` 分岐実装 → AI-03 (M2) で対応
- `test_istftnet2_generator.py` / その他ユニットテスト → AI-04 (M2) で TDD として先行
- `audio-parity-contract.toml` への新 variant section 追加 (`[istftnet2_mb_1d2d]` 等) → AI-14 (M5) で実施。 `[mb_istft_1d]` section も本チケットでは編集しない
- 7 ランタイム smoke 検証 → AI-13 (M5) で実施
- PR #222 / #537 merge 後の再 benchmark → AI-16 / AI-17 (M6) で実施
- `--from-scratch` fall back baseline の本学習 → 親計画 R2 mitigation として worklog にコマンド併記のみ。 PR #222 merge 後に warm start 経路が破壊された場合に AI-08 担当が起動する
- FLY-TTS baseline 学習 → AI-07 (M3) で独立に実施。 dataset path だけ共有

## テスト項目

### Unit Tests

本チケットはコード変更を伴わないため Python unit test は追加しない。 ただし以下 3 点を pre-flight smoke として実行する。

- `src/python/tests/test_export_onnx.py` 全件 green を学習開始前に確認 (export 経路の現状 baseline 確保)
  - 検証コマンド: `uv sync --extra dev && uv run --no-sync pytest src/python/tests/test_export_onnx.py --no-cov`
  - assert: 既存 ~20 test 全て green、 学習中の ONNX export で同一経路を使うため
- `src/python/tests/test_speaker_embedding.py` 全件 green (warm start 経路で emb_g 経路が壊れていないことの確認)
  - assert: 既存 test 全 green、 `--resume-from-multispeaker-checkpoint` で emb_g 除去が走る前提が壊れていないこと
- `src/python/tests/test_freeze_dp.py` 全件 green (warm start で freeze-dp 自動有効化が壊れていないこと)
  - assert: 既存 test 全 green、 親計画 §6 AI-02 が前提とする freeze-dp 自動有効が壊れていないこと

### E2E Tests

- 1 epoch sanity 実行: 上記学習コマンドを `--max_epochs 1` で実行
  - assert: `training.log` に `Epoch 0 completed` 出現、 WandB に `media/audio/*` artifact が log されること、 GPU OOM なし、 NaN loss なし
- 50 epoch 本学習: `--max_epochs 50`、 推定 ~36h
  - assert: `epoch=49-step=*.ckpt` が `/data/piper/output-css10-ja-poc/baseline-1d/checkpoints/` に存在、 WandB loss 曲線が plateau 付近で発散していない (`g_total_loss < 50.0` を 45 epoch 以降維持)
- ONNX export round trip: 学習完了 ckpt → ONNX → 推論 smoke
  - 検証コマンド: `uv run python -m piper_train.infer_onnx --model css10-ja-baseline-1d.onnx --config config.json --text "こんにちは" --language ja --speaker-id 0 --noise-scale 0.667 --output-dir /tmp/baseline-smoke/`
  - assert: 出力 wav が `[1, 1, T]` float32 相当 (sample rate 22050 で 約 1-2s)、 `numpy.isnan(audio).any() == False`
- WandB audio log 健全性: 10 epoch ごとの audio sample
  - assert: epoch 10/20/30/40/50 の audio sample がすべて log されている、 spectrogram に black silence のみのフレームなし
- CPU RTF 測定 (Xeon E5-2650 v4 / 25 phoneme 英文 "Hello, this is a test sentence for benchmark."): warmup 5 + 30 runs
  - assert: p50 ≤ 30ms (親計画 §4.6 README 27ms baseline ± 10% 許容、 後続 AI-05 / AI-07 / AI-10 の target × 0.7 = 18ms 比較対象として記録)
- UTMOS proxy MOS 測定 (200 test utt、 `tools/benchmark/proxy_mos.py` 想定経路、 ただし AI-12 で本実装、 本チケットでは暫定 `pip install utmos` 経由)
  - assert: MOS が dev `multilingual-test-medium.onnx` の MOS と ± 0.15 以内 (CSS10 JA dataset 由来の天井差を考慮した暫定 tolerance)

### 受入基準 (Acceptance Criteria)

親計画 §5 M1 Exit Criteria と §4.6 Benchmarks 目標値から本チケット該当分を引用。

- `/data/piper/output-css10-ja-poc/baseline-1d/checkpoints/epoch=49-step=*.ckpt` が存在
- `--resume-from-multispeaker-checkpoint` 起動時のログに emb_g 除去 + emb_lang 補正の行が出ている
- WandB run URL が worklog に記録され、 epoch 10/20/30/40/50 の audio sample がすべて log されている
- 学習完了 ckpt から ONNX export が成功 (`css10-ja-baseline-1d.onnx`、 FP16 default)
- CPU RTF (Xeon E5-2650 v4 / 25 phoneme 英文) p50 が 27ms ± 10% 範囲内 (README canonical 値の再現確認、 環境差 1 epoch ± で許容)
- UTMOS proxy MOS が dev `multilingual-test-medium.onnx` の MOS と ± 0.15 以内
- `audio-parity-contract.toml` の `[mb_istft_1d]` section は本チケット完了時点で touch されていない (git diff で確認)

## 懸念事項とレビュー項目

### 懸念事項 (リスク)

親計画 §7 Risk Register から本チケット該当分。

- **R2 (HIGH likelihood / MEDIUM impact): PR #222 の emb_g 完全削除 + Flow dilation 1→2 で 6lang MB-iSTFT base ckpt が resume 不能になる懸念。**
  - 本チケットでの mitigation: 現行 dev (torch 2.2 / py3.11 / CUDA 12.6) で実施。 PR #222 が merge される前に baseline ckpt を確保することが本チケットの最重要使命の一つ。 `--from-scratch` fall back baseline の学習コマンドを worklog に併記
- **R6 (MEDIUM likelihood / HIGH impact): `audio-parity-contract.toml` の baseline regression を A-1/A-2 が誤って書き換える。**
  - 本チケットでの mitigation: 本チケットでは contract に一切手を入れない。 baseline 数値の取得のみ。 git diff で `docs/spec/audio-parity-contract.toml` が untouched であることを完了時に確認
- **R8 (MEDIUM likelihood / LOW impact): 1 GPU 直列スケジュールで本チケット (1.5 day) が他作業と GPU 競合し M2/M3 の着手を遅延させる。**
  - 本チケットでの mitigation: GPU 競合が予見される場合は CSS10 JA 14h を 7h subset に絞り epoch 数を 100 に倍増する代替プロトコルを worklog に明記。 AI-03 (M2) と AI-06 (M3) は GPU を使わない実装作業のため、 本チケットの GPU 学習と並行着手可能であることも worklog に残す

### チケット固有の細かい懸念

- **6lang base ckpt の path drift:** CLAUDE.md には `/data/piper/output-multilingual-6lang-mb-istft/multilingual-6lang-mb-istft-scratch-75epoch.onnx` の **ONNX** path のみが記載されており、 resume 用 `.ckpt` path は明示されていない。 学習開始前に `ls /data/piper/output-multilingual-6lang-mb-istft/*.ckpt` で実在を確認し、 `last.ckpt` または `epoch=74-step=*.ckpt` のいずれかを worklog に固定する
- **WandB API key 漏洩:** Template B 同様 `WANDB_API_KEY` を環境変数で渡す。 training.sh に直接 export せず `.env` 経由を維持
- **NaN loss / DP 学習失敗:** CLAUDE.md トラブルシューティングが示す「推論音声が『ピー』音」 = DP 学習失敗のリスク。 `--samples-per-speaker 4` / `--disable_auto_lr_scaling` / `--base_lr 2e-5` を Template B どおり維持
- **6lang base からの phoneme set drift:** CSS10 JA は単一話者だが phoneme set は 6lang の 173 symbol セットを継承する必要がある。 AI-01 で `prepare_multilingual_dataset.py --language ja --single-speaker` が 173 symbol を維持していることを worklog で確認 (`config.json` の `num_symbols` を再確認)

### レビュー項目 (チェックリスト)

- [ ] default decoder_type 不変 (G-1.9 後方互換) — 本チケットは `decoder_type` 分岐を導入しないため自然に充足
- [ ] `[mb_istft_1d]` audio parity 不変 (G-1.2 baseline 編集禁止) — `git diff docs/spec/audio-parity-contract.toml` が empty
- [ ] ONNX I/O 不変 (PR #222 二重同期回避) — 本チケットの ONNX export は既存経路を素のまま使用
- [ ] PR #537 merge 後の TF32 / bf16-mixed 影響を audio-parity-contract tolerance に反映済み — 本チケットは PR #537 merge **前**で実施、 M6 AI-16 で再 benchmark との差分を吸収する前提を worklog に記載
- [ ] WandB run URL が worklog に記録されている
- [ ] 50 epoch 完了 ckpt の SHA256 を worklog に記録 (AI-08 / AI-12 で参照する正本ハッシュ)
- [ ] `noise_scale=0.667` が config-override.json に明示されている (PR #222 default 変更影響排除の証跡)
- [ ] `--no-wavlm` 使用根拠 (V100 推奨 / CSS10 JA scale での費用対効果) を worklog に記載
- [ ] CSS10 JA 14h → 7h subset への切替プロトコル (R8 mitigation) が worklog に併記されている
- [ ] PR #222 / #537 状態スナップショット (DRAFT / mergeable / updatedAt) が完了時点で worklog に記録されている

## 一から作り直すとしたら (Ticket-level rethinking)

本チケットを一から設計するなら、 「baseline 50 epoch 学習を M1 に同梱する」 という構造そのものを問い直す余地がある。 現計画は M1 を「データ整備 + baseline 確保」 の 2 段として AI-01 → AI-02 を直列に並べているが、 別案として「M1 は AI-01 のみに圧縮し、 baseline 学習は M1.5 として独立 milestone 化」 すれば AI-03 (M2) / AI-06 (M3) と並走可能になる。 この場合、 GPU を 1 GPU しか確保できない前提では実装作業 (GPU 不要) と GPU 学習を並走させられるため wall clock は 1.5 day 短縮できる。 一方、 baseline ckpt を warm start として AI-05 / AI-08 が利用する依存関係が崩れて baseline 確保完了まで M2 / M3 の学習工程は待たされるため、 トータルの直列クリティカルパスは変わらない。 つまり「M1 同梱 vs M1.5 独立」 は実装/学習の並走性のトレードオフであり、 現計画は実装者の認知負荷最小化 (= M1 完了 = 全データと baseline 揃う) を優先した合理的選択である。

TDD アプローチについても本チケットは特殊で、 コード変更ゼロのためユニットテストを増やさないが、 別案として「learning rate scheduler の挙動 unit test を `src/python/tests/test_warm_start_lr.py` に新規追加する」 案も考えられる。 これは将来 AI-08 (MS-Wavehax FT、 `--freeze-acoustic --wavehax-lr 2e-4`) で学習率切り替え経路が増えるため、 baseline 段階で warm start 時の lr 挙動を test で固定しておくと AI-08 の TDD 起点になる。 ただし本チケットの 1.5 day 工数では収まらないため、 AI-09 (`configure_optimizers` hook) と統合するのが合理的で、 本チケットでは見送る。

アーキテクチャ観点では、 「baseline は ckpt として保存するだけでなく、 ONNX export まで本チケット完了条件に含める」 という現計画の選択は AI-12 (M5) との結合度を高める一方で、 ONNX export が失敗した場合に本チケットが完了扱いにならないリスクを抱える。 別案として「ckpt 保存のみで完了とし、 ONNX export は AI-12 の前段に別チケット化」 すれば本チケットの完了判定がよりシンプルになるが、 ONNX export 経路自体に問題があった場合 (例: emb_lang 自動統一が CSS10 JA single-speaker で trigger されない) の発見が AI-12 まで遅延するため、 早期失敗指標としての ONNX export 同梱は計画的に正しい。 現実解として本チケットでは ONNX export を **smoke レベル** (round trip 推論で 1 wav 出力できれば OK) に留め、 AI-12 で benchmark grade の評価に上げる二段構えとする。

最後に「6lang base からの warm start」 vs 「from-scratch 50 epoch」 のトレードオフも再考の価値がある。 from-scratch にすれば PR #222 merge 後の emb_g 削除影響を排除できるが、 50 epoch では収束しないため epoch 数を 200 に増やす必要があり、 GPU 時間が 4 倍になる。 現計画の warm start 採用は GPU 時間最小化の現実解であり、 R2 mitigation として `--from-scratch` baseline コマンドを worklog に併記する形で「保険」 を残す折衷案が合理的。

## 後続タスクへの連絡事項

本チケット完了時点で次の成果物と注意点を後続 AI-08 / AI-12 に引き渡す。

- **baseline ckpt パス (AI-08 acoustic freeze 元):** `/data/piper/output-css10-ja-poc/baseline-1d/checkpoints/epoch=49-step=*.ckpt`
  - AI-08 (MS-Wavehax dual vocoder 統合): 本 ckpt を `--freeze-acoustic` 対象の acoustic model として読み込む。 `enc_p` / `flow` / `dp` / `posterior_encoder` を freeze、 sibling `self.dec_wavehax` のみ学習対象
  - SHA256 を worklog `/data/piper/output-css10-ja-poc/baseline-1d/README.md` に記録 (AI-08 で正本確認用)
- **baseline ONNX パス (AI-12 benchmark 比較対象):** `/data/piper/output-css10-ja-poc/baseline-1d/css10-ja-baseline-1d.onnx`
  - AI-12: `tools/benchmark/models.yaml` に `css10-ja-1d-baseline` entry として登録、 `proxy_mos.py` + CPU RTF 測定の baseline reference
- **暫定 decoder_type default 値:** `mb_istft_1d` (AI-03 で `mb_istft.py` に分岐が入った後の default 想定値)。 リリース時に切替判断 (親計画 §1 が示す「採否判定」 は M6 AI-18 で実施)
- **noise_scale 固定値:** baseline 学習で `noise_scale=0.667` を固定済み。 AI-08 / AI-12 / M2 AI-05 / M3 AI-07 / M4 AI-10 すべてで同値を維持 (PR #222 default 変更影響排除のため M1 全期間で固定)
- **CSS10 JA dataset 共通パス:** `/data/piper/dataset-css10-ja-poc/processed/` (split 比率 train 6,200 / val 200 / test 200 固定、 `lid=0` 固定)
- **PR #222 / #537 状態スナップショット:** worklog 末尾に AI-02 完了時点の両 PR 状態 (DRAFT / mergeable / updatedAt) を gh CLI で取得して固定。 M6 (AI-16 / AI-17) での rebase 戦略の起点
- **PR #222 rebase 時の注意:** baseline ckpt は emb_g 経路で生成された ckpt である。 PR #222 merge 後に emb_g → spk_proj 重み移行スクリプト (R2 mitigation 依頼項目) を通す前提。 移行スクリプトが未提供の場合は `--from-scratch` fall back に切替 (worklog にコマンド併記済み)
- **`audio-parity-contract.toml` の M5 までの不変性:** 本チケット完了時点で `[mb_istft_1d]` section は untouched。 M5 AI-14 で `[istftnet2_mb_1d2d]` / `[mswavehax]` / `[fly_convnext6]` を新 section として併載する際、 本チケットで取得した CPU RTF p50 / proxy MOS を M5 比較対照値として worklog から引用する
- **R8 fall back プロトコル:** CSS10 JA 14h → 7h subset に絞り epoch 数 100 で代替する学習コマンドを worklog に併記済み。 後続で GPU 競合が起きた場合の即時切替先

## 関連ドキュメント

- 親マイルストーン: [../milestones/M1-css10-ja-dataset.md](../milestones/M1-css10-ja-dataset.md)
- 親計画 §6: [../../research/implementation-plan-a1-a2-2026-06-16.md](../../research/implementation-plan-a1-a2-2026-06-16.md)
- 改善調査: [../../research/improvement-survey-2026-06-15.md](../../research/improvement-survey-2026-06-15.md)
- Deep-dive (vocoder 詳細 / Phase 4 risk 評価): [../../research/decoder-upgrades-istftnet2-and-mswavehax.md](../../research/decoder-upgrades-istftnet2-and-mswavehax.md)
- 既存仕様: [../../spec/audio-parity-contract.toml](../../spec/audio-parity-contract.toml) — 本チケットでは編集しない、 `[mb_istft_1d]` section 不変
- CLAUDE.md Template B (single-speaker FT) — 本チケットの学習コマンドの母型
- CLAUDE.md §転移学習 — `--resume-from-multispeaker-checkpoint` の emb_g 除去 + emb_lang 補正 + freeze-dp 自動有効化仕様
- CLAUDE.md §トラブルシューティング — DP 学習失敗 / GPU OOM / V100 学習速度低下の対処
- 影響 PR:
  - [#222 Zero-shot TTS (CAM++ + DINO)](https://github.com/ayutaz/piper-plus/pull/222) — 本チケットでは merge 前に baseline を確保
  - [#537 Python 3.13 + CUDA 12.8 + Ubuntu 24.04 統一](https://github.com/ayutaz/piper-plus/pull/537) — 本チケットでは merge 前の torch 2.2 / py3.11 環境で実施、 M6 AI-16 で bf16-mixed + TF32-on 再 benchmark
- 6lang base ckpt: `/data/piper/output-multilingual-6lang-mb-istft/` (CLAUDE.md §現在の状態 参照)
