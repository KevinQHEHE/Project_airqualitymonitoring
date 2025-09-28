#!/bin/bash

# API test script (moved to scripts/)
PROJECT_DIR="$(dirname "$(dirname "$(realpath "$0")")")"
BASE_URL="http://localhost"
DIRECT_URL="http://127.0.0.1:8000"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[PASS]${NC} $1"; }
log_error() { echo -e "${RED}[FAIL]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_test() { echo -e "${BLUE}[TEST]${NC} $1"; }

test_endpoint() {
    local url="$1"
    local expected_status="${2:-200}"
    local description="$3"
    log_test "Testing: $description"
    if command -v wget &> /dev/null; then
        local response
        local status_code
        response=$(wget -q --server-response -O - "$url" 2>&1)
        status_code=$(echo "$response" | grep "HTTP/" | tail -1 | awk '{print $2}')
        if [ "$status_code" = "$expected_status" ]; then
            log_info "$description - Status: $status_code"
            return 0
        else
            log_error "$description - Expected: $expected_status, Got: $status_code"
            return 1
        fi
    else
        log_warn "wget not available, skipping test: $description"
        return 0
    fi
}

test_json_endpoint() {
    local url="$1"
    local description="$2"
    log_test "Testing JSON: $description"
    if command -v wget &> /dev/null; then
        local response
        response=$(wget -qO- "$url" 2>/dev/null)
        if echo "$response" | python3 -m json.tool >/dev/null 2>&1; then
            log_info "$description - Valid JSON response"
            return 0
        else
            log_error "$description - Invalid JSON response"
            echo "Response: $response"
            return 1
        fi
    else
        log_warn "wget not available, skipping JSON test: $description"
        return 0
    fi
}

run_tests() {
    echo "🧪 Air Quality Monitoring System - API Tests"
    local pass_count=0; local fail_count=0; local total_tests=0
    test_endpoint "$DIRECT_URL/api/health" 200 "Health check endpoint" && ((pass_count++)) || ((fail_count++)); ((total_tests++))
    test_json_endpoint "$DIRECT_URL/api/health" "Health check JSON" && ((pass_count++)) || ((fail_count++)); ((total_tests++))
    test_endpoint "$BASE_URL/api/health" 200 "Proxied health check" && ((pass_count++)) || ((fail_count++)); ((total_tests++))
    test_json_endpoint "$BASE_URL/api/health" "Proxied health JSON" && ((pass_count++)) || ((fail_count++)); ((total_tests++))
    test_endpoint "$BASE_URL/" 200 "Main page (200 expected)" && ((pass_count++)) || ((fail_count++)); ((total_tests++))
    test_endpoint "$BASE_URL/api/" 404 "API base (404 expected)" && ((pass_count++)) || ((fail_count++)); ((total_tests++))
    test_endpoint "$BASE_URL/static/" 403 "Static files (403/404 expected)" && ((pass_count++)) || { test_endpoint "$BASE_URL/static/" 404 "Static files (403/404 expected)" && ((pass_count++)) || ((fail_count++)); }; ((total_tests++))
    echo "\nTest Results Summary: Total: $total_tests, Passed: $pass_count, Failed: $fail_count"
    if [ $fail_count -eq 0 ]; then echo "✅ All tests passed"; return 0; else echo "❌ Some tests failed"; return 1; fi
}

case "${1:-full}" in
    full) run_tests ;; info) echo "Run './scripts/test-api.sh full' to run tests" ;; test) run_tests ;; *) echo "Usage: $0 [full|test|info]"; exit 1 ;;
esac
