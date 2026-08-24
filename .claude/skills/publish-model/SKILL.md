---
name: publish-model
description: 学習済み Lightning checkpoint (.ckpt) を ONNX export → sanity check → RTF benchmark → HuggingFace upload まで連鎖実行する read-mostly skill。 export 仕様 (FP16 / EMA / emb_lang unify / opset 15) を `docs/spec/onnx-export-contract.toml` から取得し、 全 7 ランタイムでの load 可否を gate する。
argument-hint: "<ckpt-path> [--output <onnx-path>] [--repo <hf-repo>] [--skip-benchmark]"
disable-model-invocation: true
allowed-tools: Bash(uv run *) Bash(ls *) Bash(stat *) Bash(sha256sum *) Bash(file *) Bash(git diff *) Bash(git status *) Read Edit Grep
---

# Model Publish Pipeline Skill

Lightning checkpoint から HuggingFace 公開までを 1 つの skill に集約。 現状 4 ステップ手動運用 (export → infer test → RTF bench → HF push) で、 工程間の引き継ぎミスが頻発する。

memory `feedback_merge_caution.md` に従い、 publish (HuggingFace への push) は確認後に明示実行。 デフォルトは export + sanity + bench までで停止。

## 引数

- `$1` (必須): checkpoint パス、 例 `/data/piper/output-tsukuyomi-finetune-6lang-v2/last.ckpt`
- `--output PATH`: 出力 ONNX パス (デフォルト: checkpoint 隣に `.onnx`)
- `--repo OWNER/REPO`: HuggingFace repo 名 (デフォルト: `ayousanz/<voice-key>`)
- `--skip-benchmark`: フェーズ 4 を skip
- `--apply`: フェーズ 5 (HuggingFace upload) も実行

## 現在の状態

- ブランチ: !`git rev-parse --abbrev-ref HEAD`
- 引数: $ARGUMENTS

## フェーズ 1: 事前検査

```bash
# Checkpoint 存在 / サイズ確認
ls -la "$1"
file "$1"  # PyTorch Lightning checkpoint であることを確認

# Contract gate (drift 検出して bump 前 fail)
uv run python scripts/check_onnx_export_contract.py 2>&1 | tail -3
uv run python scripts/check_phoneme_set_version.py 2>&1 | tail -3
```

## フェーズ 2: ONNX export

CLAUDE.md の推奨設定 (FP16 + EMA + stochastic + emb_lang 自動統一) を使う:

```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
    "$CKPT_PATH" "$OUTPUT_ONNX"
```

> **EMA の適用判断 (v11 実測、2026-08-25)**: EMA は**収束済み run でのみ**
> default 適用する。早期打ち切り・未収束 ckpt では EMA shadow が raw weights
> より大幅に劣化する (v11 ep9 torch A/B: raw 14.9dB vs EMA 6.2dB — decay lag
> + 崩壊汚染)。打ち切り ckpt や途中 epoch を export する場合は **`--no-ema`
> を付け、迷ったら EMA 有無の両方を export して フェーズ 3.5 の帯域検査 +
> comb-HNR で良い方を採る**。

出力後の verification:

```bash
# ONNX checker / shape inference
uv run python -c "import onnx; m=onnx.load('$OUTPUT_ONNX'); onnx.checker.check_model(m); onnx.shape_inference.infer_shapes(m)"

# Size 確認 (FP16 で ~50% 削減されているか)
ls -la "$OUTPUT_ONNX"
```

## フェーズ 3: Inference sanity check

```bash
# JSONL 1 行入力で推論テスト
echo '{"phoneme_ids": [1, 2, 3, 4, 5], "speaker_id": 0}' | \
    CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
        --model "$OUTPUT_ONNX" --output-dir /tmp/sanity

# 出力 wav の sanity 確認
ls -la /tmp/sanity/*.wav
```

無音 / クリップ / 形状不一致を catch。

## フェーズ 3.5: 帯域スペクトル検査 + 聴感確認 (multi-speaker / zero-shot モデルは必須)

> **Why (2026-08 教訓):** UTMOS / HNR 等の既製指標は PQMF 帯域境界のエイリアスノイズ
> (5-9kHz「がびがび」) に**全盲**だった。zero-shot v8/v8.1 はこの検査なしで
> SECS/UTMOS 合格 → ユーザー聴感で初めて発覚。詳細:
> `docs/design/zero-shot-noise-root-cause-pqmf.md` (§1 症状 7 / §4 経緯)。

1. 実テキスト 2-3 文で合成 (zero-shot なら holdout 参照音声で `--reference-audio`)
2. **平均スペクトル比較**: 合成音の active-frame 平均スペクトルを参照原音 (と、あれば
   単一話者 FT モデルの合成) と重ね描き。**PQMF 帯域境界 2756/5512/8268 Hz 近傍
   (@22.05kHz) に +5dB 以上の非構造エネルギー超過があれば要調査** — エイリアス
   ノイズの疑い
3. スペクトログラム目視: 有声部の倍音間がノイズで埋まっていないか
4. **SECS は cross-utterance で測る** (zero-shot モデル必須): 参照 (条件付け) に
   使った発話と**同じ発話**との cosine は、SCL (InfoNCE) が生成音の CAM++
   embedding を条件 embedding に一致させるよう学習しているため、話者が似て
   いなくても高く出る (Goodhart)。必ず**参照とは別の同一話者発話** (できれば
   複数の平均) との cosine を報告し、あわせて同一話者 ceiling (実発話同士) と
   別話者 floor (近い声質の別話者) も測って相対位置を示す。2026-08-12 事例:
   same-utt 0.775 (見かけ好成績) → cross-utt 0.73 で別話者 floor すれすれ =
   聴感「似ていない」と一致 (`zero-shot-v8-dataset-scaling-plan.md` §3.19)。
5. **明瞭度 CER** (v11 教訓、2026-08-25): SECS / comb-HNR / seen-ID は
   「発話として読めているか」に全盲 — 聞き取れないモデルが指標上良好に
   見えた実測あり。合成 wav に `piper_train.tools.eval_cer` を掛け、
   **CER median ≤ 0.30** (whisper-small、契約 `zs-eval-contract.md` §7) を
   確認する。統計は median (whisper は不明瞭音声で幻覚繰り返し → mean 膨張)。
   測定は `piper_train.tools.eval_zs_secs` を **`--require-encoder2`** (第 2 encoder
   必須 gate、未指定 exit 2) + **`--baseline-json <前回 eval JSON>`** (encoder Δ から
   goodhart_flag 自動判定) 付きで実行する (契約: `docs/spec/zs-eval-contract.md`)。
5. **ユーザーに聴感確認を依頼** (自動指標のみで publish 判断しない)

判定に迷う場合は `--skip` せず停止してユーザー判断を仰ぐ。

## フェーズ 4: RTF benchmark (optional)

```bash
uv run python tools/benchmark/run_benchmark.py \
    --model "$OUTPUT_ONNX" --warmup 5 --runs 30 \
    --output /tmp/rtf_$(basename "$OUTPUT_ONNX" .onnx).json
```

baseline (README.md の Benchmark 表、 Xeon E5-2650 v4 / 25 phoneme 英文 / 27ms) と比較し、 ±30% 以内なら OK、 大きい drift があれば warning。

## フェーズ 5: HuggingFace upload (apply モードでのみ)

```bash
# config.json も同送 (model_resolution_vectors.json で alias を canonical 化)
uv run python scripts/upload_model_to_hf.py \
    --onnx "$OUTPUT_ONNX" \
    --config "$OUTPUT_ONNX.json" \
    --repo "$HF_REPO" \
    --license cc-by-nc-sa-4.0
```

upload 後、 `docs/spec/model-sha256-manifest.toml` に新 entry を追加するための diff 提案 (sha256sum 値含む)。

## フェーズ 6: 7-runtime load 確認 (optional / 軽量検証)

各 runtime で「model を load できるか」 だけ確認 (full inference は時間がかかる):

```bash
# Python
uv run python -c "from piper import PiperVoice; v = PiperVoice.load('$OUTPUT_ONNX', '$OUTPUT_ONNX.json'); print('Python: OK')"

# Rust
(cd src/rust && cargo run --release --bin piper-plus -- --model $OUTPUT_ONNX --text 'test' --output-file /tmp/r.wav 2>&1 | tail -3)

# Go / C# / C++ / WASM はオプション
```

## 注意

- **memory feedback_training_cost**: 学習時間は見送り理由にならない。 benchmark で出る drift は publish 中止の理由にもならない (regression 報告)。
- **memory feedback_data_asset_distribution**: 新 voice 追加時は 7 manifest 同期が必要。 publish 後 `check-new-runtime-asset` skill を呼ぶ。
- **memory feedback_merge_caution**: HuggingFace push は `--apply` 指定時のみ。 default は dry-run。
- **`--skip-benchmark`** は CI 環境で RTF 測定が無意味な場合のみ使う (ローカル開発機推奨)。

## 使用例

```text
# 通常のリリース前 publish
/publish-model /data/piper/output-tsukuyomi-finetune-6lang-v2/last.ckpt

# Benchmark をスキップして export + sanity だけ
/publish-model /data/piper/last.ckpt --skip-benchmark

# 確認後 HuggingFace へ実 publish
/publish-model /data/piper/last.ckpt --repo ayousanz/piper-plus-newvoice --apply
```

## 期待効果

- 学習完了 → 公開までの **4-step 手動運用を 1 skill 化**
- ONNX export 仕様 drift (opset / FP16 / EMA / emb_lang) の **commit-before-export catch**
- RTF benchmark の **regression early detection**
- model SHA256 manifest 更新の **markdown diff 自動生成**
- 7-runtime load 可否の **publish 前 sanity**
