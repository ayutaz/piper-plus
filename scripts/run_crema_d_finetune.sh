#!/usr/bin/env bash
# Phase 5 P5-T02: CREMA-D emotion fine-tune driver.
#
# Two stages are supported:
#   stage5a — style conditioning only (Phase 1 + Phase 2 ONNX compatible).
#   stage5b — style conditioning + PE-A emotion loss (Phase 4 gated).
#
# stage5a is the Phase 5 default. Run stage5b only after stage5a has converged
# AND P3-T02 has produced ``style_bank_crema_d.npz``.
#
# Usage:
#   scripts/run_crema_d_finetune.sh stage5a
#   scripts/run_crema_d_finetune.sh stage5b \
#     /data/piper/output-emotion-fine-tune-v1/lightning_logs/version_0/checkpoints/best.ckpt
#
# Environment:
#   WANDB_API_KEY must be readable; the script sources /data/piper/.env when
#   present, or falls back to the existing environment variable.
#
# Relevant tickets:
#   docs/research/implementation-plan/tickets/phase-5/P5-T02-finetune-stage-5a.md
#
set -euo pipefail

STAGE="${1:-stage5a}"
STAGE5A_RESUME_CKPT="${2:-}"

DATASET_DIR="${PIPER_EMOTION_DATASET_DIR:-/data/piper/dataset-crema-d-emotion}"
BASE_CHECKPOINT="${PIPER_BASE_CKPT:-/data/piper/output-multilingual-6lang/lightning_logs/version_0/checkpoints/epoch=74-step=504712.ckpt}"
STAGE5A_OUTPUT="${PIPER_EMOTION_OUTPUT_V1:-/data/piper/output-emotion-fine-tune-v1}"
STAGE5B_OUTPUT="${PIPER_EMOTION_OUTPUT_V2:-/data/piper/output-emotion-fine-tune-v2}"
STYLE_BANK="${PIPER_STYLE_BANK:-/data/piper/style_bank_crema_d.npz}"

# Load WANDB_API_KEY from /data/piper/.env if the file exists; otherwise fall
# back to whatever is already exported.
if [[ -f /data/piper/.env ]]; then
    WANDB_API_KEY=$(grep '^WANDB_API_KEY=' /data/piper/.env | cut -d= -f2- || true)
fi
export WANDB_API_KEY
export WANDB_PROJECT="${WANDB_PROJECT:-piper-plus-emotion-finetune}"

# NCCL options inherit the settings from CLAUDE.md's 6lang base training.
export NCCL_DEBUG=WARN
export NCCL_P2P_DISABLE=1
export NCCL_IB_DISABLE=1

common_args=(
    --dataset-dir "${DATASET_DIR}"
    --prosody-dim 16
    --style-vector-dim 256
    --style-condition-mode global
    --style-condition-dropout 0.1
    --accelerator gpu --devices 1 --precision 32-true
    --max_epochs 200 --batch-size 4 --samples-per-speaker 2
    --checkpoint-epochs 20 --quality medium
    --base_lr 2e-5 --disable_auto_lr_scaling
    --ema-decay 0.9995
    --max-phoneme-ids 400
    --no-wavlm --freeze-dp
    --val-every-n-epochs 20
    --audio-log-epochs 20
)

case "${STAGE}" in
    stage5a)
        export WANDB_NOTES="Phase 5a: Style conditioning only, CREMA-D, 200 epochs"
        LOG_FILE="/data/piper/training_emotion_v1.log"
        nohup /data/piper/.venv/bin/python -m piper_train \
            "${common_args[@]}" \
            --load_weights_from_checkpoint "${BASE_CHECKPOINT}" \
            --default_root_dir "${STAGE5A_OUTPUT}" \
            > "${LOG_FILE}" 2>&1 &
        echo "stage5a launched, tail -f ${LOG_FILE}"
        ;;
    stage5b)
        if [[ -z "${STAGE5A_RESUME_CKPT}" ]]; then
            echo "stage5b requires a stage5a best-checkpoint as the 2nd argument" >&2
            echo "example: $0 stage5b /data/piper/output-emotion-fine-tune-v1/.../best.ckpt" >&2
            exit 64
        fi
        if [[ ! -f "${STYLE_BANK}" ]]; then
            echo "stage5b requires style bank at ${STYLE_BANK}" >&2
            echo "Run Phase 3 P3-T02 build_pea_style_bank.py first." >&2
            exit 65
        fi
        export WANDB_NOTES="Phase 5b: Style + PE-A loss, warmup 2k steps"
        LOG_FILE="/data/piper/training_emotion_v2.log"
        nohup /data/piper/.venv/bin/python -m piper_train \
            "${common_args[@]}" \
            --pea-emotion-style-bank "${STYLE_BANK}" \
            --pea-emotion-loss-weight 0.1 \
            --pea-emotion-centroid-weight 0.1 \
            --pea-emotion-margin-weight 0.05 \
            --pea-emotion-loss-every-n-steps 4 \
            --pea-emotion-warmup-steps 2000 \
            --load_weights_from_checkpoint "${STAGE5A_RESUME_CKPT}" \
            --default_root_dir "${STAGE5B_OUTPUT}" \
            > "${LOG_FILE}" 2>&1 &
        echo "stage5b launched, tail -f ${LOG_FILE}"
        ;;
    *)
        echo "Unknown stage '${STAGE}'. Valid: stage5a, stage5b" >&2
        exit 64
        ;;
esac
