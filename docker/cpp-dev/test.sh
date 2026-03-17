#!/bin/bash
set -e

echo "=== C++ Train Container Test ==="
echo ""

# Test 1: Check build tools
echo "--- Build Tools Test ---"
tools=(gcc g++ clang clang++ cmake ninja-build ccache)
all_found=true

for tool in "${tools[@]}"; do
    if command -v "$tool" &> /dev/null; then
        echo "✓ $tool: $(which $tool)"
    else
        echo "✗ $tool: not found"
        all_found=false
    fi
done

if [ "$all_found" = true ]; then
    echo "✓ All build tools available"
else
    echo "✗ Some build tools missing"
    exit 1
fi

echo ""

# Test 2: Check libraries
echo "--- Library Test ---"
libs=(
    "HTSEngine"
    "OpenJTalk"
    "sndfile"
    "openblas"
)

for lib in "${libs[@]}"; do
    if ldconfig -p | grep -q "$lib"; then
        echo "✓ $lib"
    else
        # Check alternative locations
        if find /usr/local/lib -name "*${lib}*" 2>/dev/null | grep -q .; then
            echo "✓ $lib (in /usr/local/lib)"
        else
            echo "ℹ $lib not in ldconfig cache"
        fi
    fi
done

echo ""

# Test 3: Check phonemizers (eSpeak-ng and piper-phonemize no longer needed)
echo "--- Phonemizer Test ---"
if command -v open_jtalk &> /dev/null; then
    echo "✓ open_jtalk available"
else
    echo "ℹ open_jtalk not in PATH"
fi
echo "ℹ eSpeak-ng/piper-phonemize removed (GPL-free, self-contained G2P)"

echo ""

# Test 4: Simple build test
echo "--- Build Test ---"
cat > /tmp/test_build.cpp << 'EOF'
#include <iostream>
#include <vector>

int main() {
    std::cout << "C++ build test successful!" << std::endl;
    return 0;
}
EOF

if clang++ -std=c++17 -O2 /tmp/test_build.cpp -o /tmp/test_build && /tmp/test_build; then
    echo "✓ C++ compilation test passed"
else
    echo "✗ C++ compilation test failed"
    exit 1
fi

rm -f /tmp/test_build.cpp /tmp/test_build

echo ""

# Test 5: CMake test
echo "--- CMake Test ---"
mkdir -p /tmp/cmake_test && cd /tmp/cmake_test
cat > CMakeLists.txt << 'EOF'
cmake_minimum_required(VERSION 3.16)
project(test)
message(STATUS "CMake test successful!")
EOF

if cmake . &> /dev/null; then
    echo "✓ CMake test passed"
else
    echo "✗ CMake test failed"
    exit 1
fi

cd / && rm -rf /tmp/cmake_test

echo ""
echo "=== Summary ==="
echo "All tests passed!"