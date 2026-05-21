"""
Example: Using OpenAI SDK with Ollama-KIE.AI Proxy

This example demonstrates how to use the OpenAI Python SDK
with the Ollama-KIE.AI proxy for complete OpenAI compatibility.

To use this example:
1. Ensure the proxy is running: make start
2. Install OpenAI SDK: pip install openai
3. Set KIE_AI_API_KEY environment variable
4. Run this script: python openai_sdk_example.py
"""

import os
import sys
from typing import Generator


def example_basic_chat():
    """Example: Basic chat completion"""
    print("\n" + "="*60)
    print("Example 1: Basic Chat Completion")
    print("="*60)
    
    try:
        from openai import OpenAI
    except ImportError:
        print("❌ OpenAI SDK not installed. Install with: pip install openai")
        return
    
    # Initialize client pointing to local proxy
    client = OpenAI(
        base_url='http://127.0.0.1:11434/v1/',
        api_key='ollama',  # required but ignored by proxy
    )
    
    try:
        response = client.chat.completions.create(
            model='claude-opus-4-6',
            messages=[
                {
                    'role': 'system',
                    'content': 'You are a helpful assistant.'
                },
                {
                    'role': 'user',
                    'content': 'What is 2+2?'
                }
            ],
            temperature=0.7,
            max_tokens=100
        )
        
        print(f"✓ Request successful")
        print(f"Model: {response.model}")
        print(f"Response: {response.choices[0].message.content}")
        
    except Exception as e:
        print(f"❌ Error: {e}")


def example_streaming_chat():
    """Example: Streaming chat completion"""
    print("\n" + "="*60)
    print("Example 2: Streaming Chat Completion")
    print("="*60)
    
    try:
        from openai import OpenAI
    except ImportError:
        print("❌ OpenAI SDK not installed. Install with: pip install openai")
        return
    
    client = OpenAI(
        base_url='http://127.0.0.1:11434/v1/',
        api_key='ollama',
    )
    
    try:
        print("Streaming response (simulated):")
        
        # Note: Streaming with the proxy follows Ollama streaming format,
        # which is NDJSON. The OpenAI SDK may need format adaptation.
        stream = client.chat.completions.create(
            model='claude-opus-4-6',
            messages=[
                {'role': 'user', 'content': 'Tell me a joke'}
            ],
            stream=True,
            temperature=0.8
        )
        
        # Collect streamed chunks
        full_response = ""
        for chunk in stream:
            if hasattr(chunk.choices[0], 'delta') and hasattr(chunk.choices[0].delta, 'content'):
                content = chunk.choices[0].delta.content
                if content:
                    print(content, end='', flush=True)
                    full_response += content
        
        print(f"\n✓ Streaming complete")
        
    except Exception as e:
        print(f"Note: Streaming format may need adjustment: {e}")


def example_list_models():
    """Example: List available models"""
    print("\n" + "="*60)
    print("Example 3: List Available Models")
    print("="*60)
    
    try:
        from openai import OpenAI
    except ImportError:
        print("❌ OpenAI SDK not installed. Install with: pip install openai")
        return
    
    client = OpenAI(
        base_url='http://127.0.0.1:11434/v1/',
        api_key='ollama',
    )
    
    try:
        models = client.models.list()
        
        print(f"✓ Retrieved {len(models.data)} model(s):")
        for model in models.data:
            print(f"  - {model.id}")
            print(f"    Owner: {model.owned_by}")
            print(f"    Created: {model.created}")
        
    except Exception as e:
        print(f"❌ Error: {e}")


def example_embeddings():
    """Example: Generate embeddings"""
    print("\n" + "="*60)
    print("Example 4: Generate Embeddings")
    print("="*60)
    
    try:
        from openai import OpenAI
    except ImportError:
        print("❌ OpenAI SDK not installed. Install with: pip install openai")
        return
    
    client = OpenAI(
        base_url='http://127.0.0.1:11434/v1/',
        api_key='ollama',
    )
    
    try:
        response = client.embeddings.create(
            model='claude-opus-4-6',
            input='Hello, world!'
        )
        
        print(f"✓ Embeddings generated")
        print(f"Model: {response.model}")
        print(f"Number of embeddings: {len(response.data)}")
        if response.data:
            print(f"First embedding dimensions: {len(response.data[0].embedding)}")
        
    except Exception as e:
        print(f"❌ Error: {e}")


def check_api_health():
    """Check if proxy API is healthy"""
    print("\n" + "="*60)
    print("Checking Proxy Health")
    print("="*60)
    
    import httpx
    
    try:
        with httpx.Client() as client:
            # Check /v1/models endpoint
            response = client.get('http://127.0.0.1:11434/v1/models', timeout=5)
            
            if response.status_code == 200:
                print("✓ Proxy is running and responding")
                print(f"  Status: {response.status_code}")
                return True
            else:
                print(f"❌ Proxy returned status {response.status_code}")
                return False
                
    except Exception as e:
        print(f"❌ Cannot connect to proxy: {e}")
        print("Make sure the proxy is running: make start")
        return False


if __name__ == '__main__':
    print("\nOllama-KIE.AI Proxy - OpenAI SDK Examples")
    print("="*60)
    
    # Check proxy health first
    if not check_api_health():
        sys.exit(1)
    
    # Run examples
    example_list_models()
    example_basic_chat()
    example_streaming_chat()
    example_embeddings()
    
    print("\n" + "="*60)
    print("Examples completed!")
    print("="*60)
