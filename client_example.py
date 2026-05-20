"""
Example client for testing the Ollama-KIE.AI proxy
"""

import asyncio
import httpx
import json


class OllamaProxyClient:
    """Simple async client for the Ollama proxy"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:11434"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=60.0)
    
    async def close(self):
        """Close the client"""
        await self.client.aclose()
    
    async def health(self) -> dict:
        """Check service health"""
        response = await self.client.get(f"{self.base_url}/health")
        return response.json()
    
    async def list_models(self) -> dict:
        """List available models"""
        response = await self.client.get(f"{self.base_url}/api/tags")
        return response.json()
    
    async def generate(
        self,
        prompt: str,
        model: str = "claude-opus-4-6",
        stream: bool = False,
        temperature: float = 0.7,
        top_p: float = 0.9
    ) -> dict | str:
        """Generate text completion"""
        
        request_data = {
            "model": model,
            "prompt": prompt,
            "stream": stream,
            "temperature": temperature,
            "top_p": top_p
        }
        
        if stream:
            full_response = ""
            async with self.client.stream(
                "POST",
                f"{self.base_url}/api/generate",
                json=request_data
            ) as response:
                async for line in response.aiter_lines():
                    if line:
                        chunk = json.loads(line)
                        full_response += chunk.get("response", "")
                        print(chunk.get("response", ""), end="", flush=True)
            return full_response
        else:
            response = await self.client.post(
                f"{self.base_url}/api/generate",
                json=request_data
            )
            return response.json()
    
    async def chat(
        self,
        messages: list[dict],
        model: str = "claude-opus-4-6",
        stream: bool = False,
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = 2048
    ) -> dict | str:
        """Chat completion"""
        
        request_data = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens
        }
        
        if stream:
            full_response = ""
            async with self.client.stream(
                "POST",
                f"{self.base_url}/api/chat/completions",
                json=request_data
            ) as response:
                async for line in response.aiter_lines():
                    if line:
                        chunk = json.loads(line)
                        full_response += chunk.get("response", "")
                        print(chunk.get("response", ""), end="", flush=True)
            return full_response
        else:
            response = await self.client.post(
                f"{self.base_url}/api/chat/completions",
                json=request_data
            )
            return response.json()
    
    async def version(self) -> dict:
        """Get service version"""
        response = await self.client.get(f"{self.base_url}/api/version")
        return response.json()


async def main():
    """Example usage"""
    
    client = OllamaProxyClient()
    
    try:
        # Check health
        print("🏥 Checking service health...")
        health = await client.health()
        print(f"✓ Health: {health['status']}\n")
        
        # Get version
        print("📦 Getting service info...")
        version = await client.version()
        print(f"✓ Version: {version['version']}")
        print(f"✓ Backend: {version['backend']}\n")
        
        # List models
        print("📋 Available models:")
        models = await client.list_models()
        for model in models['models']:
            print(f"  - {model['name']}")
        print()
        
        # Chat example (non-streaming)
        print("💬 Chat completion (non-streaming):")
        print("-" * 50)
        response = await client.chat(
            messages=[
                {"role": "user", "content": "What is Python?"}
            ],
            stream=False
        )
        print(response['response'])
        print("-" * 50)
        print()
        
        # Chat example (streaming)
        print("💬 Chat completion (streaming):")
        print("-" * 50)
        await client.chat(
            messages=[
                {"role": "user", "content": "Tell me a short joke about programming"}
            ],
            stream=True
        )
        print("\n" + "-" * 50)
        print()
        
        # Generate example
        print("✍️  Text generation (non-streaming):")
        print("-" * 50)
        response = await client.generate(
            prompt="The future of AI is",
            stream=False
        )
        print(response['response'])
        print("-" * 50)
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await client.close()


if __name__ == "__main__":
    print("Ollama-KIE.AI Proxy Client Example")
    print("=" * 50)
    print()
    asyncio.run(main())
