#!/bin/bash
# C++ / Python phoneme_ids regression test
# Usage: regression_test.sh --model /path/to/model.onnx
#
# 8 test texts to verify that C++ piper output exactly matches
# the Python training pipeline (pyopenjtalk-plus + japanese.py).

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Parse arguments
MODEL=""
while [[ $# -gt 0 ]]; do
  case $1 in
    --model) MODEL="$2"; shift 2 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

if [ -z "$MODEL" ]; then
  # Try default paths
  if ls /app/models/*.onnx 1>/dev/null 2>&1; then
    MODEL=$(ls /app/models/*.onnx | head -1)
  elif ls /models/*.onnx 1>/dev/null 2>&1; then
    MODEL=$(ls /models/*.onnx | head -1)
  else
    echo "Usage: $0 --model /path/to/model.onnx"
    exit 1
  fi
fi

echo "=== C++/Python Phoneme IDs Regression Test ==="
echo "Model: $MODEL"
echo ""

# Test cases: text -> expected phoneme_ids (from Python pyopenjtalk-plus pipeline)
# These expected values were verified against Python on 2026-03-10
# using the pyopenjtalk-plus + japanese.py phonemizer

PASS_COUNT=0
FAIL_COUNT=0
TOTAL=8

run_test() {
  local test_num="$1"
  local text="$2"
  local expected_ids="$3"
  local expected_count="$4"

  # Run piper with --debug and extract phoneme IDs
  local output
  output=$(echo "$text" | piper --model "$MODEL" --output_file /dev/null --debug 2>&1)

  local actual_ids
  actual_ids=$(echo "$output" | grep "Converted.*phoneme id" | sed 's/.*phoneme id(s): //' | sed 's/[[:space:]]*$//')

  local actual_count
  actual_count=$(echo "$output" | grep "Converted.*phoneme" | sed 's/.*Converted \([0-9]*\) phoneme.*/\1/')

  if [ "$actual_ids" = "$expected_ids" ]; then
    echo -e "${GREEN}PASS${NC} [${test_num}/8] (${actual_count} ids) ${text}"
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    echo -e "${RED}FAIL${NC} [${test_num}/8] ${text}"
    echo "  Expected (${expected_count} ids): ${expected_ids}"
    echo "  Actual   (${actual_count} ids): ${actual_ids}"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
}

# Test 1: Greeting (prosody marks + multiple accent phrases)
run_test 1 \
  "こんにちは、今日は良い天気ですね。" \
  "1, 32, 14, 8, 27, 57, 11, 46, 11, 63, 10, 0, 33, 14, 9, 8, 14, 63, 10, 64, 14, 9, 8, 11, 38, 13, 9, 8, 28, 32, 11, 40, 13, 48, 17, 57, 13, 2," \
  38

# Test 2: Simple question (EOS=?)
run_test 2 \
  "本当ですか？" \
  "1, 54, 14, 8, 27, 38, 14, 14, 40, 13, 9, 48, 17, 32, 10, 3," \
  16

# Test 3: Emphatic question (EOS=?!) -- fullwidth characters
run_test 3 \
  "本当？！" \
  "1, 54, 14, 8, 27, 38, 14, 14, 4," \
  9

# Test 4: Declarative question (EOS=?.)
run_test 4 \
  "そうなの？。" \
  "1, 48, 14, 9, 8, 14, 57, 10, 57, 14, 5," \
  11

# Test 5: N_m variant (sanpo: N before p)
run_test 5 \
  "さんぽに行きましょう。" \
  "1, 48, 10, 9, 8, 26, 42, 14, 57, 11, 11, 8, 32, 11, 59, 10, 49, 14, 9, 14, 2," \
  21

# Test 6: N_n variant (annai: N before n)
run_test 6 \
  "あんないします。" \
  "1, 10, 8, 27, 57, 10, 11, 49, 11, 59, 10, 9, 48, 17, 2," \
  15

# Test 7: N_ng variant (ginkou: N before k)
run_test 7 \
  "ぎんこうに行きます。" \
  "1, 35, 11, 8, 28, 32, 14, 14, 57, 11, 11, 8, 32, 11, 59, 10, 9, 48, 17, 2," \
  20

# Test 8: General sentence (hon wo yomimashita)
run_test 8 \
  "本を読みました。" \
  "1, 54, 14, 9, 8, 29, 14, 64, 14, 8, 59, 11, 59, 10, 9, 49, 16, 38, 10, 2," \
  20

# Summary
echo ""
echo "=== Results ==="
if [ $FAIL_COUNT -eq 0 ]; then
  echo -e "${GREEN}ALL ${PASS_COUNT}/${TOTAL} TESTS PASSED${NC}"
  exit 0
else
  echo -e "${RED}${FAIL_COUNT}/${TOTAL} TESTS FAILED${NC} (${PASS_COUNT} passed)"
  exit 1
fi
