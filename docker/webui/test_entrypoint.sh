#!/bin/bash
set -e

# Tests for docker/webui/entrypoint.sh
# Run from repository root: bash docker/webui/test_entrypoint.sh

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

TESTS_PASSED=0
TESTS_FAILED=0

run_test() {
    local test_name="$1"
    local test_command="$2"

    echo -n "Testing $test_name... "
    if eval "$test_command" > /tmp/entrypoint_test.log 2>&1; then
        echo -e "${GREEN}PASSED${NC}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        echo -e "${RED}FAILED${NC}"
        cat /tmp/entrypoint_test.log
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
}

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENTRYPOINT="$SCRIPT_DIR/entrypoint.sh"

# 1. entrypoint.sh exists and is executable
run_test "entrypoint.sh exists" "test -f '$ENTRYPOINT'"
run_test "entrypoint.sh is executable" "test -x '$ENTRYPOINT' || chmod +x '$ENTRYPOINT' && test -x '$ENTRYPOINT'"

# 2. entrypoint.sh has LF line endings (not CRLF — Docker requirement)
run_test "LF line endings" "! grep -qU $'\r' '$ENTRYPOINT'"

# 3. Starts with bash shebang
run_test "bash shebang" "head -1 '$ENTRYPOINT' | grep -q '#!/bin/bash'"

# 4. Uses set -e for fail-fast
run_test "set -e present" "grep -q 'set -e' '$ENTRYPOINT'"

# 5. Uses exec to replace shell process
run_test "exec used for app launch" "grep -q 'exec python' '$ENTRYPOINT'"

# 6. References PIPER_MODEL env var
run_test "PIPER_MODEL check" "grep -q 'PIPER_MODEL' '$ENTRYPOINT'"

# 7. References PIPER_MODEL_DIR with default
run_test "PIPER_MODEL_DIR default /models" "grep -q 'PIPER_MODEL_DIR:-/models' '$ENTRYPOINT'"

# 8. Passes model-dir and output-dir to app.py
run_test "passes --model-dir" "grep -q '\-\-model-dir' '$ENTRYPOINT'"
run_test "passes --output-dir" "grep -q '\-\-output-dir' '$ENTRYPOINT'"

# 9. Forwards extra args via \$@
run_test "forwards extra args" 'grep -q '\''"$@"'\'' "$ENTRYPOINT"'

# 10. Python download snippet uses resolve_model_path and download_model
run_test "uses resolve_model_path" "grep -q 'resolve_model_path' '$ENTRYPOINT'"
run_test "uses download_model" "grep -q 'download_model' '$ENTRYPOINT'"

# 11. Dockerfile references entrypoint.sh
DOCKERFILE="$SCRIPT_DIR/Dockerfile"
run_test "Dockerfile copies entrypoint.sh" "grep -q 'entrypoint.sh' '$DOCKERFILE'"
run_test "Dockerfile sets ENTRYPOINT" "grep -q 'ENTRYPOINT' '$DOCKERFILE'"

# 12. docker-compose.yml passes PIPER_MODEL
COMPOSE="$SCRIPT_DIR/docker-compose.yml"
run_test "compose passes PIPER_MODEL" "grep -q 'PIPER_MODEL' '$COMPOSE'"
run_test "compose passes PIPER_MODEL_DIR" "grep -q 'PIPER_MODEL_DIR' '$COMPOSE'"

echo ""
echo "=== Summary ==="
echo -e "Passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Failed: ${RED}$TESTS_FAILED${NC}"

if [ "$TESTS_FAILED" -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
fi
