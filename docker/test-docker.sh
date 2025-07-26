#!/bin/bash
set -e

# Docker smoke tests for Piper TTS environments

echo "=== Piper Docker Environment Tests ==="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test result tracking
TESTS_PASSED=0
TESTS_FAILED=0

# Helper function to run test
run_test() {
    local test_name="$1"
    local test_command="$2"
    
    echo -n "Testing $test_name... "
    
    if eval "$test_command" > /tmp/test_output.log 2>&1; then
        echo -e "${GREEN}PASSED${NC}"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}FAILED${NC}"
        echo "Error output:"
        cat /tmp/test_output.log
        ((TESTS_FAILED++))
    fi
}

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker is not installed or not in PATH${NC}"
    exit 1
fi

# Check if docker compose is available
if ! docker compose version &> /dev/null; then
    echo -e "${YELLOW}Warning: docker compose not found, skipping compose tests${NC}"
    SKIP_COMPOSE=1
fi

echo "1. Building Docker images..."
echo ""

# Build Python training image
run_test "Python training image build" \
    "docker build -t piper-python-train:test -f docker/python-train/Dockerfile docker/python-train"

# Build Python inference image
run_test "Python inference image build" \
    "docker build -t piper-python-inference:test -f docker/python-inference/Dockerfile docker/python-inference"

# Build C++ training image
run_test "C++ training image build" \
    "docker build -t piper-cpp-train:test -f docker/cpp-train/Dockerfile docker/cpp-train"

# Build C++ inference image (depends on cpp-train)
run_test "C++ inference image build" \
    "docker build -t piper-cpp-inference:test --build-arg BUILDER_IMAGE=piper-cpp-train:test -f docker/cpp-inference/Dockerfile ."

echo ""
echo "2. Running container health checks..."
echo ""

# Test Python training container
run_test "Python training container startup" \
    "docker run --rm piper-python-train:test python -c 'import torch; import piper_train; print(\"OK\")'"

# Test Python inference container
run_test "Python inference container startup" \
    "docker run --rm piper-python-inference:test python -c 'import torch; import onnxruntime; print(\"OK\")'"

# Test C++ training container
run_test "C++ training container startup" \
    "docker run --rm piper-cpp-train:test bash -c 'which cmake && which ninja && echo OK'"

# Test C++ inference container
run_test "C++ inference container health" \
    "docker run --rm --entrypoint /bin/bash piper-cpp-inference:test -c 'ldconfig -p | grep -q onnxruntime && echo OK'"

echo ""
echo "3. Testing functionality..."
echo ""

# Test Python environment can import required packages
run_test "Python package imports" \
    "docker run --rm piper-python-train:test python -c '
import numpy
import torch
import librosa
import soundfile
print(\"All imports successful\")
'"

# Test CUDA availability (if NVIDIA runtime is available)
if docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi &> /dev/null; then
    run_test "CUDA availability in Python" \
        "docker run --rm --gpus all piper-python-train:test python -c 'import torch; print(f\"CUDA available: {torch.cuda.is_available()}\")'"
else
    echo -e "${YELLOW}Skipping CUDA tests (no NVIDIA GPU/runtime available)${NC}"
fi

# Test build tools in C++ environment
run_test "C++ build tools" \
    "docker run --rm piper-cpp-train:test bash -c '
cmake --version && \
ninja --version && \
clang++ --version | head -n1
'"

echo ""
echo "4. Testing docker-compose..."
echo ""

if [ -z "$SKIP_COMPOSE" ]; then
    # Test docker compose configuration
    run_test "docker compose config validation" \
        "docker compose config > /dev/null"
    
    # Test building with docker compose
    run_test "docker compose build (python-inference only)" \
        "docker compose build --no-cache python-inference"
else
    echo -e "${YELLOW}Skipping docker-compose tests${NC}"
fi

echo ""
echo "5. Cleanup test images..."
echo ""

# Remove test images
docker rmi -f piper-python-train:test piper-python-inference:test \
    piper-cpp-train:test piper-cpp-inference:test 2>/dev/null || true

echo ""
echo "=== Test Summary ==="
echo -e "Tests passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Tests failed: ${RED}$TESTS_FAILED${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
fi