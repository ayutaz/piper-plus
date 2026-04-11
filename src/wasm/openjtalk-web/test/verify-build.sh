#!/bin/bash
set -e

echo "=== OpenJTalk WebAssembly Build Verification ==="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if files exist
echo "Checking build artifacts..."

check_file() {
    if [ -f "$1" ]; then
        SIZE=$(ls -lh "$1" | awk '{print $5}')
        echo -e "  ${GREEN}✓${NC} $1 (${SIZE})"
        return 0
    else
        echo -e "  ${RED}✗${NC} $1 - Not found"
        return 1
    fi
}

# Required files
FAILED=0
check_file "dist/openjtalk.js" || FAILED=1
check_file "dist/openjtalk.wasm" || FAILED=1
check_file "dist/load-dictionary.js" || FAILED=1

echo ""
echo "Checking dictionary files..."
check_file "assets/dict/char.bin" || FAILED=1
check_file "assets/dict/matrix.bin" || FAILED=1
check_file "assets/dict/sys.dic" || FAILED=1
check_file "assets/dict/unk.dic" || FAILED=1

# Check WASM module exports using wasm-objdump if available
if command -v wasm-objdump &> /dev/null; then
    echo ""
    echo "Checking WASM exports..."
    EXPORTS=$(wasm-objdump -x dist/openjtalk.wasm | grep "Export" | grep -E "(openjtalk_|get_version|test_function)" | wc -l)
    echo "  Found $EXPORTS OpenJTalk-related exports"
fi

# Summary
echo ""
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ All build artifacts verified successfully!${NC}"
    echo ""
    echo "To test in browser:"
    echo "  1. Run: python3 -m http.server 8080"
    echo "  2. Open: http://localhost:8080/demo/index.html"
    exit 0
else
    echo -e "${RED}❌ Some files are missing${NC}"
    echo "Run: ./build/build-with-wasm-openjtalk.sh"
    exit 1
fi