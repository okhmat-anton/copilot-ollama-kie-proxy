"""
Test script for OpenAI SDK compatibility with the Ollama-KIE.AI proxy
"""

import asyncio
import httpx
from datetime import datetime


async def test_openai_endpoints():
    """Test OpenAI-compatible endpoints"""
    
    base_url = "http://127.0.0.1:11434"
    client = httpx.AsyncClient(timeout=10.0)
    
    tests = [
        ("GET /v1/models", f"{base_url}/v1/models", "get"),
        ("GET /v1/models/claude-opus-4-6", f"{base_url}/v1/models/claude-opus-4-6", "get"),
        ("GET /api/version", f"{base_url}/api/version", "get"),
        ("GET /api/tags", f"{base_url}/api/tags", "get"),
        ("GET /health", f"{base_url}/health", "get"),
    ]
    
    print("=" * 60)
    print("OpenAI Compatibility Test Suite")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}\n")
    
    for test_name, url, method in tests:
        try:
            if method == "get":
                response = await client.get(url)
            else:
                response = await client.post(url)
            
            status = "✓ PASS" if response.status_code == 200 else "✗ FAIL"
            print(f"{status} | {test_name}")
            print(f"  Status: {response.status_code}")
            
            try:
                data = response.json()
                # Print first 100 chars of response
                json_str = str(data)[:100]
                print(f"  Response: {json_str}...")
            except:
                print(f"  Response: {response.text[:100]}...")
            
            print()
        
        except Exception as e:
            print(f"✗ FAIL | {test_name}")
            print(f"  Error: {str(e)}")
            print()
    
    await client.aclose()
    
    print("=" * 60)
    print("Test suite completed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_openai_endpoints())
