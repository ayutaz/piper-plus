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

# === Voice files should NOT be present (HTS voice dependency removed) ===
echo ""
echo "Checking that voice files are absent..."
if [ -d "assets/voice" ] && [ "$(find assets/voice -type f 2>/dev/null | wc -l)" -gt 0 ]; then
    echo -e "  ${RED}FAIL${NC}: Voice files found in assets/voice (should be removed)"
    FAILED=1
else
    echo -e "  ${GREEN}OK${NC}: No voice files in assets/"
fi

if grep -q '"voices"' assets/assets.json 2>/dev/null; then
    echo -e "  ${RED}FAIL${NC}: assets.json still contains \"voices\" section"
    FAILED=1
else
    echo -e "  ${GREEN}OK${NC}: assets.json does not contain \"voices\" section"
fi

# === WASM binary size regression check ===
echo ""
echo "Checking WASM binary size..."
WASM_FILE="dist/openjtalk.wasm"
if [ -f "$WASM_FILE" ]; then
    WASM_SIZE=$(wc -c < "$WASM_FILE")
else
    WASM_SIZE=0
fi
MAX_SIZE=5242880  # 5MB threshold — based on pre-removal baseline (~3MB dict + ~1.5MB WASM).
                  # Voice re-introduction would add ~2MB, exceeding this limit.
                  # Increase if new features legitimately grow the binary.
if [ -n "$WASM_SIZE" ] && [ "$WASM_SIZE" -gt "$MAX_SIZE" ]; then
    echo -e "  ${RED}FAIL${NC}: WASM binary too large (${WASM_SIZE} bytes > ${MAX_SIZE})"
    FAILED=1
else
    echo -e "  ${GREEN}OK${NC}: WASM binary size within limits (${WASM_SIZE:-0} bytes)"
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