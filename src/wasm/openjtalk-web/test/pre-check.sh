#!/bin/bash
set -e

echo "=== OpenJTalk WebAssembly Pre-flight Check ==="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

FAILED=0

# Function to check file
check_file() {
    if [ -f "$1" ]; then
        SIZE=$(stat -f%z "$1" 2>/dev/null || stat -c%s "$1" 2>/dev/null)
        echo -e "  ${GREEN}✓${NC} $1 (${SIZE} bytes)"
        
        # Additional checks for specific files
        if [[ "$1" == *.wasm ]]; then
            # Check if it's a valid WASM file
            if file "$1" | grep -q "WebAssembly"; then
                echo -e "    ${GREEN}✓${NC} Valid WebAssembly binary"
            else
                echo -e "    ${RED}✗${NC} Invalid WebAssembly binary"
                FAILED=1
            fi
        fi
        
        # Check dictionary files
        if [[ "$1" == *.bin ]] || [[ "$1" == *.dic ]]; then
            if [ $SIZE -eq 0 ]; then
                echo -e "    ${RED}✗${NC} File is empty!"
                FAILED=1
            fi
        fi
        
        return 0
    else
        echo -e "  ${RED}✗${NC} $1 - Not found"
        FAILED=1
        return 1
    fi
}

# 1. Check build files
echo -e "${BLUE}1. Checking build files...${NC}"
check_file "dist/openjtalk.js"
check_file "dist/openjtalk.wasm"

# Check if the JS module exports the right format
echo -e "\n${BLUE}2. Checking JS module format...${NC}"
if grep -q "export default" dist/openjtalk.js; then
    echo -e "  ${GREEN}✓${NC} ES6 module format detected"
else
    echo -e "  ${RED}✗${NC} ES6 module format not found"
    FAILED=1
fi

# Check for required functions in JS
echo -e "\n${BLUE}3. Checking exported functions in JS...${NC}"
FUNCTIONS=("_openjtalk_initialize" "_openjtalk_synthesis_labels" "_openjtalk_clear" "_openjtalk_free_string" "_get_version" "_test_function")
for func in "${FUNCTIONS[@]}"; do
    if grep -q "$func" dist/openjtalk.js; then
        echo -e "  ${GREEN}✓${NC} $func found"
    else
        echo -e "  ${RED}✗${NC} $func not found"
        FAILED=1
    fi
done

# 4. Check dictionary files
echo -e "\n${BLUE}4. Checking dictionary files...${NC}"
DICT_FILES=("char.bin" "matrix.bin" "sys.dic" "unk.dic" "left-id.def" "pos-id.def" "rewrite.def" "right-id.def")
DICT_TOTAL_SIZE=0
for file in "${DICT_FILES[@]}"; do
    if check_file "assets/dict/$file"; then
        SIZE=$(stat -f%z "assets/dict/$file" 2>/dev/null || stat -c%s "assets/dict/$file" 2>/dev/null)
        DICT_TOTAL_SIZE=$((DICT_TOTAL_SIZE + SIZE))
    fi
done
echo -e "  Total dictionary size: $((DICT_TOTAL_SIZE / 1024 / 1024)) MB"

# 5. Check permissions
echo -e "\n${BLUE}5. Checking file permissions...${NC}"
if [ -r "dist/openjtalk.wasm" ] && [ -r "dist/openjtalk.js" ]; then
    echo -e "  ${GREEN}✓${NC} Files are readable"
else
    echo -e "  ${RED}✗${NC} Files are not readable"
    FAILED=1
fi

# 6. Test HTTP serving
echo -e "\n${BLUE}6. Testing HTTP serving capability...${NC}"
# Check if Python is available
if command -v python3 &> /dev/null; then
    echo -e "  ${GREEN}✓${NC} Python3 available for HTTP server"
else
    echo -e "  ${YELLOW}!${NC} Python3 not found"
fi

# 7. Check for common issues
echo -e "\n${BLUE}7. Checking for common issues...${NC}"

# Check if WASM file has the right magic number
if xxd -l 4 -p dist/openjtalk.wasm 2>/dev/null | grep -q "0061736d"; then
    echo -e "  ${GREEN}✓${NC} WASM magic number correct"
else
    echo -e "  ${RED}✗${NC} WASM magic number incorrect"
    FAILED=1
fi

# Check environment flag in build
if grep -q "ENVIRONMENT.*web.*worker" dist/openjtalk.js; then
    echo -e "  ${GREEN}✓${NC} Built for web/worker environment"
else
    echo -e "  ${YELLOW}!${NC} Environment flags not found"
fi

# 8. Memory estimation
echo -e "\n${BLUE}8. Memory requirements...${NC}"
WASM_SIZE=$(stat -f%z "dist/openjtalk.wasm" 2>/dev/null || stat -c%s "dist/openjtalk.wasm" 2>/dev/null)
ESTIMATED_MEMORY=$((WASM_SIZE * 3 + DICT_TOTAL_SIZE + 33554432)) # WASM + dict + initial heap
echo -e "  Estimated memory needed: $((ESTIMATED_MEMORY / 1024 / 1024)) MB"

# 9. Quick syntax check
echo -e "\n${BLUE}9. Checking for syntax errors...${NC}"
if node -c dist/openjtalk.js 2>/dev/null; then
    echo -e "  ${GREEN}✓${NC} No syntax errors in JS file"
else
    echo -e "  ${RED}✗${NC} Syntax errors found in JS file"
    FAILED=1
fi

# Summary
echo -e "\n${BLUE}=== Summary ===${NC}"
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ All pre-flight checks passed!${NC}"
    echo ""
    echo "Ready for browser testing at:"
    echo "  http://localhost:8081/demo/index.html"
else
    echo -e "${RED}❌ Some checks failed. Please fix the issues above.${NC}"
fi

exit $FAILED