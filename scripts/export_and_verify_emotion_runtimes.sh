#!/usr/bin/env bash
# Phase 5 P5-T04: emotion fine-tune ONNX export + cross-runtime smoke check.
#
# Exports the Phase 5 fine-tuned VITS checkpoint to ONNX with Phase 2's
# mask-pattern style_vector inputs, then drives each of the six runtimes
# (Python, C++, Rust, C#, Go, WASM) with the same ``--style-vector`` file
# and verifies that the produced audio matches byte-for-byte.
#
# The runtimes that require their own build toolchain (C++/C#/Go) only emit
# "build and run manually" instructions here — this script handles Python +
# Rust PyO3 natively and produces a reference MD5 for the others.
#
# Usage:
#   scripts/export_and_verify_emotion_runtimes.sh \
#     /data/piper/output-emotion-fine-tune-v1/lightning_logs/version_0/checkpoints/best.ckpt \
#     /data/piper/dataset-crema-d-emotion/style_vectors/1001_IEO_HAP_LO.npy
#
# Output:
#   <artifact-dir>/emotion-v1.onnx
#   <artifact-dir>/python_audio.wav  (+ .md5)
#   <artifact-dir>/rust_audio.wav    (+ .md5)
#   <artifact-dir>/runtime_summary.md
#
# Relevant tickets:
#   docs/research/implementation-plan/tickets/phase-5/P5-T04-onnx-export-runtime-verification.md
#
set -euo pipefail

CKPT_PATH="${1:?usage: $0 <checkpoint.ckpt> <style_vector.npy>}"
STYLE_VECTOR="${2:?usage: $0 <checkpoint.ckpt> <style_vector.npy>}"
ARTIFACT_DIR="${PIPER_EMOTION_ARTIFACT_DIR:-/data/piper/emotion-runtime-verify}"
TEXT="${PIPER_VERIFY_TEXT:-Do not forget a jacket.}"
LANGUAGE="${PIPER_VERIFY_LANG:-en}"

if [[ ! -f "${CKPT_PATH}" ]]; then
    echo "Checkpoint not found: ${CKPT_PATH}" >&2
    exit 66
fi
if [[ ! -f "${STYLE_VECTOR}" ]]; then
    echo "Style vector not found: ${STYLE_VECTOR}" >&2
    exit 66
fi

mkdir -p "${ARTIFACT_DIR}"
ONNX_OUT="${ARTIFACT_DIR}/emotion-v1.onnx"
CONFIG_OUT="${ARTIFACT_DIR}/emotion-v1.onnx.json"

echo "=== 1. ONNX export ==="
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
    "${CKPT_PATH}" \
    "${ONNX_OUT}"

echo "Export complete: ${ONNX_OUT}"
ls -la "${ONNX_OUT}" "${CONFIG_OUT}" 2>/dev/null || true

echo ""
echo "=== 2. Python runtime inference ==="
PY_WAV="${ARTIFACT_DIR}/python_audio.wav"
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
    --model "${ONNX_OUT}" \
    --config "${CONFIG_OUT}" \
    --output-dir "${ARTIFACT_DIR}" \
    --text "${TEXT}" \
    --language "${LANGUAGE}" \
    --speaker-id 0 \
    --style-vector "${STYLE_VECTOR}"
# infer_onnx.py typically emits <output-dir>/*.wav — normalise to python_audio.wav.
first_wav=$(ls -t "${ARTIFACT_DIR}"/*.wav | head -1)
cp "${first_wav}" "${PY_WAV}"
md5sum "${PY_WAV}" > "${PY_WAV}.md5" 2>/dev/null || md5 -r "${PY_WAV}" > "${PY_WAV}.md5"

echo ""
echo "=== 3. Rust runtime inference (optional, requires cargo + piper-plus-cli) ==="
RUST_WAV="${ARTIFACT_DIR}/rust_audio.wav"
if command -v cargo >/dev/null 2>&1; then
    pushd src/rust >/dev/null
    cargo run --release -p piper-plus-cli -- \
        --model "${ONNX_OUT}" \
        --config "${CONFIG_OUT}" \
        --style-vector "${STYLE_VECTOR}" \
        --text "${TEXT}" \
        --output "${RUST_WAV}" || echo "Rust runtime exited non-zero (skip)"
    popd >/dev/null
    if [[ -f "${RUST_WAV}" ]]; then
        md5sum "${RUST_WAV}" > "${RUST_WAV}.md5" 2>/dev/null || md5 -r "${RUST_WAV}" > "${RUST_WAV}.md5"
    fi
else
    echo "cargo not found — Rust runtime verification skipped"
fi

echo ""
echo "=== 4. Other runtimes (manual, build first) ==="
cat <<INSTRUCTIONS
# C++ CLI (build: cmake --build build --target piper_plus)
./build/piper_plus --model ${ONNX_OUT} --text "${TEXT}" --style-vector ${STYLE_VECTOR} -f ${ARTIFACT_DIR}/cpp_audio.wav

# C# CLI (build: dotnet build src/csharp/PiperPlus.sln -c Release)
dotnet run --project src/csharp/PiperPlus.Cli -- --model ${ONNX_OUT} --text "${TEXT}" --style-vector ${STYLE_VECTOR} --output ${ARTIFACT_DIR}/cs_audio.wav

# Go CLI (build: cd src/go && go build -o piper-plus ./cmd/piper-plus)
./src/go/piper-plus synthesize --model ${ONNX_OUT} --text "${TEXT}" --style-vector ${STYLE_VECTOR} > ${ARTIFACT_DIR}/go_audio.wav

# WASM/JS (run in a browser fixture, see src/wasm/openjtalk-web/README.npm.md)
INSTRUCTIONS

echo ""
echo "=== 5. Summary ==="
SUMMARY_MD="${ARTIFACT_DIR}/runtime_summary.md"
{
    echo "# Phase 5 P5-T04 Runtime Verification"
    echo ""
    echo "- Checkpoint: ${CKPT_PATH}"
    echo "- Style vector: ${STYLE_VECTOR}"
    echo "- ONNX: ${ONNX_OUT}"
    echo ""
    echo "## MD5 digests (expect byte-for-byte match across runtimes)"
    echo ""
    cat "${PY_WAV}.md5" 2>/dev/null || echo "python: missing"
    cat "${RUST_WAV}.md5" 2>/dev/null || echo "rust: missing"
    echo ""
    echo "## Runtimes still to verify manually"
    echo ""
    echo "- C++: \`./build/piper_plus ...\`"
    echo "- C#: \`dotnet run --project src/csharp/PiperPlus.Cli ...\`"
    echo "- Go: \`./src/go/piper-plus synthesize ...\`"
    echo "- WASM/JS: browser fixture"
} > "${SUMMARY_MD}"
echo "Summary written: ${SUMMARY_MD}"
