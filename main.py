import json
import asyncio
import httpx
from typing import Any, AsyncGenerator
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from config import settings
from logger import general_logger, error_logger, request_logger

# Initialize FastAPI app
app = FastAPI(title="Ollama-KIE.AI Proxy", version="1.0.0")

# HTTP client session
http_client: httpx.AsyncClient | None = None


# ============================================================================
# Request/Response Models
# ============================================================================

class Message(BaseModel):
    """Chat message model"""
    role: str
    content: str


class ChatRequest(BaseModel):
    """Chat completion request"""
    model: str
    messages: list[Message]
    stream: bool = False
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 2048


class GenerateRequest(BaseModel):
    """Generate completion request"""
    model: str
    prompt: str
    stream: bool = False
    temperature: float = 0.7
    top_p: float = 0.9


class TagsResponse(BaseModel):
    """Available models response"""
    models: list[dict]


# ============================================================================
# Logging Helpers
# ============================================================================

async def log_request(method: str, path: str, details: dict):
    """Log incoming request"""
    timestamp = datetime.now().isoformat()
    request_logger.info(
        f"[{timestamp}] {method} {path} | Model: {details.get('model', 'N/A')} | "
        f"Stream: {details.get('stream', False)}"
    )


async def log_error(error_type: str, message: str, details: dict = None):
    """Log error"""
    timestamp = datetime.now().isoformat()
    error_logger.error(
        f"[{timestamp}] {error_type}: {message} | Details: {details or {}}"
    )


# ============================================================================
# KIE.AI API Integration
# ============================================================================

async def get_http_client() -> httpx.AsyncClient:
    """Get or create HTTP client"""
    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(
            timeout=60.0,
            headers={
                "Authorization": f"Bearer {settings.kie_ai_api_key}",
                "Content-Type": "application/json"
            }
        )
    return http_client


async def transform_ollama_to_kie(
    model: str,
    messages: list[dict] | None = None,
    prompt: str | None = None,
    **kwargs
) -> dict:
    """Transform Ollama format request to KIE.AI format"""
    
    kie_request = {
        "model": model,
        "temperature": kwargs.get("temperature", 0.7),
        "top_p": kwargs.get("top_p", 0.9),
    }
    
    if messages:
        kie_request["messages"] = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in messages
        ]
    elif prompt:
        kie_request["messages"] = [
            {"role": "user", "content": prompt}
        ]
    
    if "max_tokens" in kwargs:
        kie_request["max_tokens"] = kwargs["max_tokens"]
    
    return kie_request


async def transform_kie_to_ollama(
    kie_response: dict,
    is_streaming: bool = False
) -> dict:
    """Transform KIE.AI response to Ollama format"""
    
    if is_streaming:
        return {
            "model": kie_response.get("model", settings.default_model),
            "created_at": datetime.now().isoformat(),
            "response": kie_response.get("choices", [{}])[0].get("delta", {}).get("content", ""),
            "done": kie_response.get("choices", [{}])[0].get("finish_reason") == "stop"
        }
    else:
        content = kie_response.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {
            "model": kie_response.get("model", settings.default_model),
            "created_at": datetime.now().isoformat(),
            "response": content,
            "done": True,
            "context": [],
            "total_duration": kie_response.get("usage", {}).get("total_tokens", 0) * 1000
        }


async def stream_kie_response(
    url: str,
    request_data: dict,
    model: str
) -> AsyncGenerator[str, None]:
    """Stream responses from KIE.AI API"""
    
    try:
        client = await get_http_client()
        request_data["stream"] = True
        
        async with client.stream("POST", url, json=request_data) as response:
            if response.status_code != 200:
                error_msg = f"KIE.AI API error: {response.status_code}"
                await log_error("API_ERROR", error_msg, {"url": url})
                raise HTTPException(status_code=response.status_code, detail=error_msg)
            
            async for line in response.aiter_lines():
                if line:
                    try:
                        kie_chunk = json.loads(line)
                        ollama_chunk = await transform_kie_to_ollama(kie_chunk, is_streaming=True)
                        yield f"{json.dumps(ollama_chunk)}\n"
                    except json.JSONDecodeError:
                        continue
    
    except httpx.RequestError as e:
        await log_error("REQUEST_ERROR", str(e), {"url": url})
        raise HTTPException(status_code=503, detail="Backend service unavailable")


# ============================================================================
# API Endpoints - Model Management
# ============================================================================

@app.get("/api/tags")
async def list_models(background_tasks: BackgroundTasks) -> dict:
    """List available models (Ollama compatible)"""
    
    await log_request("GET", "/api/tags", {})
    
    try:
        return {
            "models": [
                {
                    "name": "claude-opus-4-6:latest",
                    "modified_at": datetime.now().isoformat(),
                    "size": 0,
                    "digest": "sha256:claude-opus-4-6"
                }
            ]
        }
    except Exception as e:
        background_tasks.add_task(log_error, "TAGS_ERROR", str(e), {})
        raise HTTPException(status_code=500, detail="Failed to list models")


@app.post("/api/pull")
async def pull_model(request: Request, background_tasks: BackgroundTasks) -> dict:
    """Pull model (stub - no actual download needed)"""
    
    body = await request.json()
    await log_request("POST", "/api/pull", {"model": body.get("name")})
    
    return {"status": "success"}


@app.delete("/api/delete")
async def delete_model(request: Request, background_tasks: BackgroundTasks) -> dict:
    """Delete model (stub implementation)"""
    
    body = await request.json()
    await log_request("DELETE", "/api/delete", {"model": body.get("name")})
    
    return {"status": "success"}


@app.head("/api/blobs/{digest}")
async def check_blob(digest: str) -> dict:
    """Check blob existence"""
    return {"exists": True}


# ============================================================================
# API Endpoints - Model Inference
# ============================================================================

@app.post("/api/generate")
async def generate(
    request: GenerateRequest,
    background_tasks: BackgroundTasks
) -> StreamingResponse | dict:
    """Generate text completion (Ollama compatible)"""
    
    await log_request("POST", "/api/generate", {
        "model": request.model,
        "stream": request.stream
    })
    
    try:
        kie_request = await transform_ollama_to_kie(
            model=request.model,
            prompt=request.prompt,
            temperature=request.temperature,
            top_p=request.top_p
        )
        
        url = f"{settings.kie_ai_api_url}/completions"
        
        if request.stream:
            return StreamingResponse(
                stream_kie_response(url, kie_request, request.model),
                media_type="application/x-ndjson"
            )
        else:
            client = await get_http_client()
            response = await client.post(url, json=kie_request)
            
            if response.status_code != 200:
                error_msg = f"KIE.AI API error: {response.status_code}"
                background_tasks.add_task(log_error, "GENERATE_ERROR", error_msg, {})
                raise HTTPException(status_code=response.status_code, detail=error_msg)
            
            kie_response = response.json()
            ollama_response = await transform_kie_to_ollama(kie_response)
            return ollama_response
    
    except Exception as e:
        background_tasks.add_task(log_error, "GENERATE_EXCEPTION", str(e), {})
        raise HTTPException(status_code=500, detail="Generation failed")


@app.post("/api/chat/completions")
async def chat_completions(
    request: ChatRequest,
    background_tasks: BackgroundTasks
) -> StreamingResponse | dict:
    """Chat endpoint (Ollama compatible)"""
    
    await log_request("POST", "/api/chat/completions", {
        "model": request.model,
        "stream": request.stream,
        "messages_count": len(request.messages)
    })
    
    try:
        messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]
        
        kie_request = await transform_ollama_to_kie(
            model=request.model,
            messages=messages,
            temperature=request.temperature,
            top_p=request.top_p,
            max_tokens=request.max_tokens
        )
        
        url = f"{settings.kie_ai_api_url}/chat/completions"
        
        if request.stream:
            return StreamingResponse(
                stream_kie_response(url, kie_request, request.model),
                media_type="application/x-ndjson"
            )
        else:
            client = await get_http_client()
            response = await client.post(url, json=kie_request)
            
            if response.status_code != 200:
                error_msg = f"KIE.AI API error: {response.status_code}"
                background_tasks.add_task(log_error, "CHAT_ERROR", error_msg, {})
                raise HTTPException(status_code=response.status_code, detail=error_msg)
            
            kie_response = response.json()
            ollama_response = await transform_kie_to_ollama(kie_response)
            return ollama_response
    
    except Exception as e:
        background_tasks.add_task(log_error, "CHAT_EXCEPTION", str(e), {})
        raise HTTPException(status_code=500, detail="Chat failed")


# ============================================================================
# API Endpoints - System
# ============================================================================

@app.get("/api/version")
async def get_version() -> dict:
    """Get service version"""
    return {
        "version": "1.0.0",
        "backend": "KIE.AI",
        "models": ["claude-opus-4-6"]
    }


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }


# ============================================================================
# Lifecycle Events
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    global http_client
    
    if not settings.kie_ai_api_key:
        raise ValueError("KIE_AI_API_KEY environment variable is not set")
    
    general_logger.info(
        f"Ollama-KIE.AI Proxy starting on {settings.proxy_host}:{settings.proxy_port}"
    )
    general_logger.info(f"Backend URL: {settings.kie_ai_api_url}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global http_client
    
    if http_client:
        await http_client.aclose()
    
    general_logger.info("Ollama-KIE.AI Proxy shutting down")


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host=settings.proxy_host,
        port=settings.proxy_port,
        reload=False,
        log_config=None  # Use our custom logger
    )
