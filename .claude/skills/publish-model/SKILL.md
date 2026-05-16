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
