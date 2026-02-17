#!/bin/bash
# benchmark_optimizations.sh - Phase 1 最適化効果の測定
#
# 使い方: ./benchmark_optimizations.sh
#
# バイリンガルデータセットで5 epoch学習し、最適化の前後でit/sを比較する。
# GPU: V100 x4, FP32, WavLMなし

set -euo pipefail

DATASET_DIR="/data/piper/dataset-bilingual-ja-en"
BASE_CMD="/data/piper/.venv/bin/python -m piper_train"
MAX_EPOCHS=5
BATCH_SIZE=20
LOG_DIR="/data/piper/benchmark_results"

export NCCL_DEBUG=WARN
export NCCL_P2P_DISABLE=1
export NCCL_IB_DISABLE=1

mkdir -p "$LOG_DIR"

run_benchmark() {
    local name="$1"
    shift
    local output_dir="$LOG_DIR/output_${name}"
    local log_file="$LOG_DIR/${name}.log"

    echo "============================================"
    echo "  Benchmark: $name"
    echo "  Output: $output_dir"
    echo "  Log: $log_file"
    echo "============================================"

    rm -rf "$output_dir"
    mkdir -p "$output_dir"

    $BASE_CMD \
        --dataset-dir "$DATASET_DIR" \
        --prosody-dim 16 \
        --accelerator gpu --devices 4 --precision 32-true \
        --max_epochs "$MAX_EPOCHS" --batch-size "$BATCH_SIZE" --samples-per-speaker 2 \
        --checkpoint-epochs 0 --quality medium \
        --base_lr 2e-4 --disable_auto_lr_scaling \
        --ema-decay 0.9995 \
        --max-phoneme-ids 400 \
        --no-wavlm \
        --default_root_dir "$output_dir" \
        "$@" \
        2>&1 | tee "$log_file"

    # Extract it/s from log
    local its
    its=$(grep -oP '\d+\.\d+ it/s' "$log_file" | tail -5 | awk '{sum+=$1; n++} END {if(n>0) printf "%.2f", sum/n; else print "N/A"}')
    echo ""
    echo ">>> $name: avg it/s = $its (last 5 reports)"
    echo "$name: $its it/s" >> "$LOG_DIR/summary.txt"
    echo ""
}

echo "Phase 1 Optimization Benchmark" > "$LOG_DIR/summary.txt"
echo "Date: $(date -Iseconds)" >> "$LOG_DIR/summary.txt"
echo "---" >> "$LOG_DIR/summary.txt"

# Baseline: num_workers=0, no compile, no fused (current defaults before optimization)
run_benchmark "baseline" \
    --num-workers 0 --no-pin-memory

# Optimized (num_workers=0): fused AdamW + torch.compile, num_workers=0
run_benchmark "optimized_nw0" \
    --num-workers 0 --no-pin-memory \
    --compile

# Optimized (num_workers=2): fused AdamW + torch.compile, num_workers=2
run_benchmark "optimized_nw2" \
    --num-workers 2 \
    --compile

echo ""
echo "============================================"
echo "  Benchmark Summary"
echo "============================================"
cat "$LOG_DIR/summary.txt"
