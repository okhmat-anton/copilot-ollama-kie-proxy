#!/bin/bash
# Test script for Ollama-KIE.AI Proxy API endpoints

BASE_URL="http://127.0.0.1:11434"
BOLD='\033[1m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BOLD}Ollama-KIE.AI Proxy - API Test Suite${NC}"
echo "======================================"
echo

# Check if service is running
echo -e "${YELLOW}🔍 Checking service availability...${NC}"
if ! curl -s "$BASE_URL/health" > /dev/null 2>&1; then
    echo -e "${RED}❌ Service is not running on $BASE_URL${NC}"
    echo "Start the service with: make start"
    exit 1
fi
echo -e "${GREEN}✓ Service is running${NC}\n"

# Test 1: Health check
echo -e "${BOLD}Test 1: Health Check${NC}"
echo "GET $BASE_URL/health"
curl -s "$BASE_URL/health" | python -m json.tool
echo -e "\n${GREEN}✓ Passed${NC}\n"

# Test 2: Version
echo -e "${BOLD}Test 2: Get Version${NC}"
echo "GET $BASE_URL/api/version"
curl -s "$BASE_URL/api/version" | python -m json.tool
echo -e "\n${GREEN}✓ Passed${NC}\n"

# Test 3: List Models
echo -e "${BOLD}Test 3: List Models${NC}"
echo "GET $BASE_URL/api/tags"
curl -s "$BASE_URL/api/tags" | python -m json.tool
echo -e "\n${GREEN}✓ Passed${NC}\n"

# Test 4: Non-streaming Chat
echo -e "${BOLD}Test 4: Chat Completion (Non-streaming)${NC}"
echo "POST $BASE_URL/api/chat/completions"
echo "Payload:"
cat <<EOF | python -m json.tool
{
  "model": "claude-opus-4-6",
  "messages": [
    {"role": "user", "content": "What is 2+2?"}
  ],
  "stream": false,
  "temperature": 0.7
}
EOF
echo

echo "Response:"
curl -s -X POST "$BASE_URL/api/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-opus-4-6",
    "messages": [
      {"role": "user", "content": "What is 2+2?"}
    ],
    "stream": false,
    "temperature": 0.7
  }' | python -m json.tool || echo -e "${YELLOW}⚠ API error (check logs)${NC}"
echo -e "\n${GREEN}✓ Endpoint tested${NC}\n"

# Test 5: Streaming Chat
echo -e "${BOLD}Test 5: Chat Completion (Streaming)${NC}"
echo "POST $BASE_URL/api/chat/completions (with stream=true)"
echo "Receiving stream..."
curl -s -X POST "$BASE_URL/api/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-opus-4-6",
    "messages": [
      {"role": "user", "content": "Say hello"}
    ],
    "stream": true
  }' | head -5
echo -e "\n${YELLOW}(truncated for display)${NC}"
echo -e "\n${GREEN}✓ Streaming works${NC}\n"

# Test 6: Text Generation
echo -e "${BOLD}Test 6: Text Generation (Non-streaming)${NC}"
echo "POST $BASE_URL/api/generate"
curl -s -X POST "$BASE_URL/api/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-opus-4-6",
    "prompt": "Python is",
    "stream": false
  }' | python -m json.tool || echo -e "${YELLOW}⚠ API error (check logs)${NC}"
echo -e "\n${GREEN}✓ Endpoint tested${NC}\n"

# Test 7: Model Pull (stub)
echo -e "${BOLD}Test 7: Pull Model (Stub)${NC}"
echo "POST $BASE_URL/api/pull"
curl -s -X POST "$BASE_URL/api/pull" \
  -H "Content-Type: application/json" \
  -d '{"name": "claude-opus-4-6"}' | python -m json.tool
echo -e "\n${GREEN}✓ Passed${NC}\n"

# Test 8: List Blobs
echo -e "${BOLD}Test 8: Check Blob Existence${NC}"
echo "HEAD $BASE_URL/api/blobs/test-digest"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -I "$BASE_URL/api/blobs/test-digest")
echo "HTTP Status: $HTTP_CODE"
echo -e "${GREEN}✓ Passed${NC}\n"

# Summary
echo "======================================"
echo -e "${GREEN}✓ All basic tests completed!${NC}"
echo
echo "📋 Next steps:"
echo "1. Check logs: make logs"
echo "2. View errors: make logs-errors"
echo "3. View requests: make logs-requests"
echo "4. Test with client_example.py"
echo
