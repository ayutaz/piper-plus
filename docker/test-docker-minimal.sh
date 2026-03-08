#!/bin/bash
set -e

# Minimal Docker tests for CI stability

echo "=== Minimal Docker Tests ==="
echo ""

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "Docker is not installed or not in PATH"
    exit 1
fi

echo "1. Testing basic Docker functionality..."
docker run --rm hello-world

echo ""
echo "2. Testing Ubuntu base image..."
docker run --rm ubuntu:22.04 echo "Ubuntu test passed"

echo ""
echo "3. Testing Python base image..."
docker run --rm python:3.11-slim python -c "print('Python test passed')"

echo ""
echo "All minimal tests passed!"
exit 0