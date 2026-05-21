"""
Ollama-compatible proxy for KIE.AI API
Full Ollama API compatibility with async streaming support
"""

import json
import asyncio
import httpx
from typing import Any
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from config import settings
from logger import general_logger, error_logger, request_logger

# Initialize FastAPI app
app = FastAPI(title="Ollama", version="0.1.0")

# HTTP client session
http_client: httpx.AsyncClient | None = None


# ============================================================================
# Request/Response Models (Ollama Compatible)
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
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    top_k: int = Field(default=40, ge=1)


class GenerateRequest(BaseModel):
    """Generate completion request"""
    model: str
    prompt: str
    stream: bool = False
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    top_k: int = Field(default=40, ge=1)


class PullRequest(BaseModel):
    """Pull/download model request"""
    name: str
    insecure: bool = False


class DeleteRequest(BaseModel):
    """Delete model request"""
    name: str


class EmbeddingsRequest(BaseModel):
    """Embeddings request"""
    model: str
    input: str | list[str]


# ============================================================================
# Logging Helpers
# ============================================================================

async def log_request(method: str, path: str, details: dict = None):
    """Log incoming request"""
    timestamp = datetime.now().isoformat()
    model = (details or {}).get('model', 'N/A')
    stream = (details or {}).get('stream', False)
    request_logger.info(
        f"[{timestamp}] {method} {path} | Model: {model} | Stream: {stream}"
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
    
    return kie_request


async def transform_kie_to_ollama(
    kie_response: dict,
    is_streaming: bool = False
) -> dict:
    """Transform KIE.AI response to Ollama format"""
    
    if is_streaming:
        content = ""
        finish_reason = None
        
        if "choices" in kie_response and len(kie_response["choices"]) > 0:
            choice = kie_response["choices"][0]
            if "delta" in choice:
                content = choice["delta"].get("content", "")
            if "finish_reason" in choice:
                finish_reason = choice["finish_reason"]
        
        return {
            "model": kie_response.get("model", settings.default_model),
            "created_at": datetime.now().isoformat(),
            "message": {
                "role": "assistant",
                "content": content
            },
            "done": finish_reason == "stop",
            "done_reason": finish_reason or "null"
        }
    else:
        content = ""
        if "choices" in kie_response and len(kie_response["choices"]) > 0:
            choice = kie_response["choices"][0]
            if "message" in choice:
                content = choice["message"].get("content", "")
            elif "text" in choice:
                content = choice["text"]
        
        return {
            "model": kie_response.get("model", settings.default_model),
            "created_at": datetime.now().isoformat(),
            "message": {
                "role": "assistant",
                "content": content
            },
            "done": True,
            "done_reason": "stop"
        }


async def stream_kie_response(
    url: str,
    request_data: dict,
    model: str
):
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
# Lifecycle Events
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    global http_client
    
    if not settings.kie_ai_api_key:
        raise ValueError("KIE_AI_API_KEY environment variable is not set")
    
    general_logger.info(
        f"Ollama-compatible proxy starting"
    )
    general_logger.info(f"Backend: {settings.kie_ai_api_url}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global http_client
    
    if http_client:
        await http_client.aclose()
    
    general_logger.info("Ollama-compatible proxy shutting down")


# ============================================================================
# API Endpoints - System Information
# ============================================================================

@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint"""
    return {"status": "Ollama is running"}


@app.get("/api/version")
async def api_version():
    """Get API version (Ollama compatible)"""
    # Return an Ollama-compatible version string. Allow override via env var.
    return {"version": settings.ollama_compat_version}


@app.get("/api/tags")
async def list_models():
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
        await log_error("TAGS_ERROR", str(e), {})
        raise HTTPException(status_code=500, detail="Failed to list models")


# ============================================================================
# API Endpoints - Model Management
# ============================================================================

@app.post("/api/pull")
async def pull_model(request: PullRequest, background_tasks: BackgroundTasks):
    """Pull model (stub - no actual download needed)"""
    
    await log_request("POST", "/api/pull", {"model": request.name})
    
    return {
        "status": "success",
        "digest": f"sha256:{request.name}",
        "total": 0
    }


@app.delete("/api/delete")
async def delete_model(request: DeleteRequest, background_tasks: BackgroundTasks):
    """Delete model (stub implementation)"""
    
    await log_request("DELETE", "/api/delete", {"model": request.name})
    
    return {"status": "success"}


@app.head("/api/blobs/{digest}")
async def check_blob(digest: str):
    """Check blob existence"""
    return {}


# ============================================================================
# API Endpoints - Chat/Completions
# ============================================================================

@app.post("/api/chat", response_model=None)
async def chat(request: ChatRequest, background_tasks: BackgroundTasks):
    """Chat endpoint - main Ollama chat API"""
    
    await log_request("POST", "/api/chat", {
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
            top_k=request.top_k
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


@app.post("/api/chat/completions", response_model=None)
async def chat_completions(request: ChatRequest, background_tasks: BackgroundTasks):
    """Chat completions endpoint (OpenAI compatible)"""
    
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
            top_k=request.top_k
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
# API Endpoints - Generate (Legacy)
# ============================================================================

@app.post("/api/generate", response_model=None)
async def generate(request: GenerateRequest, background_tasks: BackgroundTasks):
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
            top_p=request.top_p,
            top_k=request.top_k
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


# ============================================================================
# API Endpoints - Embeddings
# ============================================================================

@app.post("/api/embeddings", response_model=None)
async def embeddings(request: EmbeddingsRequest, background_tasks: BackgroundTasks):
    """Generate embeddings"""
    
    await log_request("POST", "/api/embeddings", {
        "model": request.model
    })
    
    try:
        # For now, return dummy embeddings
        # In production, call KIE.AI embeddings API if available
        return {
            "embedding": [0.1] * 1536,
            "model": request.model
        }
    except Exception as e:
        background_tasks.add_task(log_error, "EMBEDDINGS_ERROR", str(e), {})
        raise HTTPException(status_code=500, detail="Embeddings generation failed")


# ============================================================================
# API Endpoints - Health/Status
# ============================================================================

@app.get("/health", include_in_schema=False)
@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat()
    }


# ============================================================================
# OpenAI Compatible Endpoints (/v1/* prefix)
# ============================================================================

@app.get("/v1/models", include_in_schema=False)
async def openai_list_models():
    """List available models (OpenAI compatible endpoint)"""
    
    await log_request("GET", "/v1/models", {})
    
    try:
        return {
            "object": "list",
            "data": [
                {
                    "id": "claude-opus-4-6",
                    "object": "model",
                    "owned_by": "kie-ai",
                    "created": int(datetime.now().timestamp()),
                    "permission": []
                }
            ]
        }
    except Exception as e:
        await log_error("V1_MODELS_ERROR", str(e), {})
        raise HTTPException(status_code=500, detail="Failed to list models")


@app.get("/v1/models/{model}", include_in_schema=False)
async def openai_get_model(model: str):
    """Get model information (OpenAI compatible endpoint)"""
    
    await log_request("GET", f"/v1/models/{model}", {})
    
    try:
        return {
            "id": model,
            "object": "model",
            "owned_by": "kie-ai",
            "created": int(datetime.now().timestamp()),
            "permission": []
        }
    except Exception as e:
        await log_error("V1_MODEL_ERROR", str(e), {"model": model})
        raise HTTPException(status_code=500, detail="Failed to get model info")


@app.post("/v1/chat/completions", include_in_schema=False)
async def openai_chat_completions(request: ChatRequest, background_tasks: BackgroundTasks):
    """Chat completions endpoint (OpenAI compatible /v1/ prefix)"""
    
    await log_request("POST", "/v1/chat/completions", {
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
            top_k=request.top_k
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
                background_tasks.add_task(log_error, "V1_CHAT_ERROR", error_msg, {})
                raise HTTPException(status_code=response.status_code, detail=error_msg)
            
            kie_response = response.json()
            ollama_response = await transform_kie_to_ollama(kie_response)
            return ollama_response
    
    except Exception as e:
        background_tasks.add_task(log_error, "V1_CHAT_EXCEPTION", str(e), {})
        raise HTTPException(status_code=500, detail="Chat failed")


@app.post("/v1/completions", include_in_schema=False)
async def openai_completions(request: GenerateRequest, background_tasks: BackgroundTasks):
    """Completions endpoint (OpenAI compatible /v1/ prefix)"""
    
    await log_request("POST", "/v1/completions", {
        "model": request.model,
        "stream": request.stream
    })
    
    try:
        kie_request = await transform_ollama_to_kie(
            model=request.model,
            prompt=request.prompt,
            temperature=request.temperature,
            top_p=request.top_p,
            top_k=request.top_k
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
                background_tasks.add_task(log_error, "V1_COMPLETIONS_ERROR", error_msg, {})
                raise HTTPException(status_code=response.status_code, detail=error_msg)
            
            kie_response = response.json()
            ollama_response = await transform_kie_to_ollama(kie_response)
            return ollama_response
    
    except Exception as e:
        background_tasks.add_task(log_error, "V1_COMPLETIONS_EXCEPTION", str(e), {})
        raise HTTPException(status_code=500, detail="Completions failed")


@app.post("/v1/embeddings", include_in_schema=False)
async def openai_embeddings(request: EmbeddingsRequest, background_tasks: BackgroundTasks):
    """Embeddings endpoint (OpenAI compatible /v1/ prefix)"""
    
    await log_request("POST", "/v1/embeddings", {"model": request.model})
    
    try:
        # Normalize input to list
        if isinstance(request.input, str):
            inputs = [request.input]
        else:
            inputs = request.input
        
        client = await get_http_client()
        url = f"{settings.kie_ai_api_url}/embeddings"
        
        kie_request = {
            "model": request.model,
            "input": inputs
        }
        
        response = await client.post(url, json=kie_request)
        
        if response.status_code != 200:
            error_msg = f"KIE.AI API error: {response.status_code}"
            background_tasks.add_task(log_error, "V1_EMBEDDINGS_ERROR", error_msg, {})
            raise HTTPException(status_code=response.status_code, detail=error_msg)
        
        return response.json()
    
    except Exception as e:
        background_tasks.add_task(log_error, "V1_EMBEDDINGS_EXCEPTION", str(e), {})
        raise HTTPException(status_code=500, detail="Embeddings generation failed")


# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Custom HTTP exception handler"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """General exception handler"""
    error_msg = str(exc)
    await log_error("UNHANDLED_EXCEPTION", error_msg, {})
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )


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
