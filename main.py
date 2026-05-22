"""FastAPI-приложение: Ollama-совместимый прокси к KIE.AI.

Принимает Ollama-API запросы (/api/...) и OpenAI-API запросы (/v1/...),
проксирует их в KIE.AI (https://api.kie.ai/v1), который OpenAI-совместим.
Для /api/* выполняет двустороннюю трансформацию форматов.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from config import settings
from logger import (
    get_error_logger,
    get_logger,
    get_request_logger,
    setup_logging,
)

setup_logging()
log = get_logger()
err_log = get_error_logger()
req_log = get_request_logger()


# --------------------------------------------------------------------------- #
# HTTP-клиент / жизненный цикл приложения                                     #
# --------------------------------------------------------------------------- #

_http_client: Optional[httpx.AsyncClient] = None


def get_client() -> httpx.AsyncClient:
    if _http_client is None:
        raise RuntimeError("HTTP client is not initialized")
    return _http_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _http_client
    log.info(
        "Starting proxy on %s:%s -> %s",
        settings.proxy_host,
        settings.proxy_port,
        settings.kie_ai_api_url,
    )
    if not settings.kie_ai_api_key:
        log.warning("KIE_AI_API_KEY is empty -- upstream calls will fail")

    _http_client = httpx.AsyncClient(
        base_url=settings.kie_ai_api_url,
        timeout=httpx.Timeout(settings.upstream_timeout, connect=15.0),
        headers={
            "Authorization": f"Bearer {settings.kie_ai_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    )
    try:
        yield
    finally:
        log.info("Shutting down proxy")
        if _http_client is not None:
            await _http_client.aclose()
            _http_client = None


app = FastAPI(title="copilot-ollama-kie-proxy", lifespan=lifespan)


# --------------------------------------------------------------------------- #
# Middleware -- логирование входящих запросов                                 #
# --------------------------------------------------------------------------- #


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    if not settings.request_logging_enabled:
        return await call_next(request)

    start = time.perf_counter()
    client_ip = request.client.host if request.client else "-"
    parts = [
        f"--> {request.method} {request.url.path}",
        f"query={dict(request.query_params)}",
        f"client={client_ip}",
    ]

    if settings.request_log_headers:
        headers = {
            k: ("***" if k.lower() in ("authorization", "cookie") else v)
            for k, v in request.headers.items()
        }
        parts.append(f"headers={headers}")

    if settings.request_log_body and request.method in ("POST", "PUT", "PATCH", "DELETE"):
        try:
            body = await request.body()
            if body:
                text = body.decode("utf-8", errors="replace")
                if len(text) > settings.request_log_body_limit:
                    text = text[: settings.request_log_body_limit] + "...<truncated>"
                parts.append(f"body={text}")

                async def receive() -> Dict[str, Any]:
                    return {"type": "http.request", "body": body, "more_body": False}

                request._receive = receive  # type: ignore[attr-defined]
        except Exception as exc:
            parts.append(f"body_error={exc}")

    req_log.info(" | ".join(parts))

    try:
        response = await call_next(request)
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        err_log.exception("Unhandled error %s %s (%.1fms)", request.method, request.url.path, elapsed_ms)
        req_log.info("<-- %s %s status=500 %.1fms", request.method, request.url.path, elapsed_ms)
        return JSONResponse(status_code=500, content={"error": str(exc)})

    elapsed_ms = (time.perf_counter() - start) * 1000
    req_log.info(
        "<-- %s %s status=%s %.1fms",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


# --------------------------------------------------------------------------- #
# Утилиты                                                                     #
# --------------------------------------------------------------------------- #


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _digest_for(name: str) -> str:
    return "sha256:" + hashlib.sha256(name.encode("utf-8")).hexdigest()


def _model_details(name: str) -> Dict[str, Any]:
    # Подменяем семью на "llama" -- VSCode Copilot ищет в lookup-таблице
    # хендлеры по семье; для нераспознанных значений падает с
    # "Cannot read properties of undefined (reading 'bind')".
    return {
        "parent_model": "",
        "format": "gguf",
        "family": "llama",
        "families": ["llama"],
        "parameter_size": "70B",
        "quantization_level": "Q4_0",
    }


def _ollama_model_descriptor(name: str) -> Dict[str, Any]:
    return {
        "name": name,
        "model": name,
        "modified_at": _iso_now(),
        "size": 0,
        "digest": _digest_for(name),
        "details": _model_details(name),
    }


def _openai_model_descriptor(name: str) -> Dict[str, Any]:
    return {
        "id": name,
        "object": "model",
        "created": int(time.time()),
        "owned_by": "kie.ai",
    }


def _model_or_default(name: Optional[str]) -> str:
    return name or settings.default_model


def _strip_tag(name: str) -> str:
    # Ollama-клиенты часто шлют "model:latest"; KIE такого не знает.
    if ":" in name and not name.startswith("sha256:"):
        return name.split(":", 1)[0]
    return name


def _display_name(name: str) -> str:
    """Имя, видимое клиенту: с префиксом MODEL_NAME_PREFIX (по умолчанию `kie/`)."""
    prefix = settings.model_name_prefix
    if not prefix or not name:
        return name
    return name if name.startswith(prefix) else prefix + name


def _upstream_name(name: str) -> str:
    """Имя для запроса в KIE.AI: без префикса и без `:tag`."""
    prefix = settings.model_name_prefix
    if prefix and name.startswith(prefix):
        name = name[len(prefix):]
    return _strip_tag(name)


def _build_messages(prompt: Optional[str], messages: Optional[List[Dict[str, Any]]], system: Optional[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if system:
        out.append({"role": "system", "content": system})
    if messages:
        out.extend(messages)
    elif prompt is not None:
        out.append({"role": "user", "content": prompt})
    return out


def _extract_sampling(body: Dict[str, Any]) -> Dict[str, Any]:
    """Достаёт параметры сэмплинга из тела (учитывая Ollama `options`)."""
    opts = body.get("options") or {}
    out: Dict[str, Any] = {}

    def pick(key: str, *aliases: str) -> Any:
        for k in (key, *aliases):
            if k in body and body[k] is not None:
                return body[k]
            if k in opts and opts[k] is not None:
                return opts[k]
        return None

    temperature = pick("temperature")
    if temperature is not None:
        out["temperature"] = float(temperature)
    top_p = pick("top_p")
    if top_p is not None:
        out["top_p"] = float(top_p)
    max_tokens = pick("max_tokens", "num_predict")
    if max_tokens is not None:
        try:
            mt = int(max_tokens)
            if mt > 0:
                out["max_tokens"] = mt
        except (TypeError, ValueError):
            pass
    stop = pick("stop")
    if stop:
        out["stop"] = stop
    return out


# --------------------------------------------------------------------------- #
# OpenAI <-> Anthropic трансляция (KIE.AI отдаёт Claude в Anthropic-native)   #
# --------------------------------------------------------------------------- #

_ANTHROPIC_STOP_REASON_TO_OPENAI = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "tool_use": "tool_calls",
}


def _openai_tools_to_anthropic(tools: Any) -> Optional[List[Dict[str, Any]]]:
    if not isinstance(tools, list) or not tools:
        return None
    out: List[Dict[str, Any]] = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        if t.get("type") == "function" and isinstance(t.get("function"), dict):
            fn = t["function"]
            out.append({
                "name": fn.get("name") or "",
                "description": fn.get("description") or "",
                "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
            })
        elif "name" in t and ("input_schema" in t or "parameters" in t):
            out.append({
                "name": t["name"],
                "description": t.get("description") or "",
                "input_schema": t.get("input_schema") or t.get("parameters") or {"type": "object", "properties": {}},
            })
    return out or None


def _openai_tool_choice_to_anthropic(tc: Any) -> Optional[Dict[str, Any]]:
    if tc is None:
        return None
    if isinstance(tc, str):
        if tc == "auto":
            return {"type": "auto"}
        if tc == "required":
            return {"type": "any"}
        return None
    if isinstance(tc, dict) and tc.get("type") == "function":
        name = (tc.get("function") or {}).get("name")
        if name:
            return {"type": "tool", "name": name}
    return None


def _openai_messages_to_anthropic(messages: List[Dict[str, Any]]) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """Делит OpenAI-сообщения на (system, anthropic-messages).
    Маппит assistant.tool_calls -> tool_use, role=tool -> tool_result в user."""
    system_parts: List[str] = []
    out: List[Dict[str, Any]] = []

    def _flatten_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    parts.append(str(c.get("text") or ""))
                elif isinstance(c, str):
                    parts.append(c)
            return "".join(parts)
        return "" if content is None else str(content)

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = msg.get("content")

        if role == "system":
            text = _flatten_text(content)
            if text:
                system_parts.append(text)
            continue

        if role == "tool":
            tool_call_id = msg.get("tool_call_id") or msg.get("id") or ""
            result_content = _flatten_text(content) if not isinstance(content, str) else content
            block = {"type": "tool_result", "tool_use_id": tool_call_id, "content": result_content}
            if out and out[-1].get("role") == "user" and isinstance(out[-1].get("content"), list):
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
            continue

        if role == "assistant":
            blocks: List[Dict[str, Any]] = []
            text = _flatten_text(content)
            if text:
                blocks.append({"type": "text", "text": text})
            for tc in msg.get("tool_calls") or []:
                if not isinstance(tc, dict):
                    continue
                fn = tc.get("function") or {}
                args_raw = fn.get("arguments")
                try:
                    args = json.loads(args_raw) if isinstance(args_raw, str) and args_raw else (args_raw if isinstance(args_raw, dict) else {})
                except (json.JSONDecodeError, TypeError):
                    args = {}
                blocks.append({
                    "type": "tool_use",
                    "id": tc.get("id") or "",
                    "name": fn.get("name") or "",
                    "input": args or {},
                })
            if not blocks:
                blocks = [{"type": "text", "text": ""}]
            out.append({"role": "assistant", "content": blocks})
            continue

        # user (default)
        if isinstance(content, str):
            out.append({"role": "user", "content": content})
        elif isinstance(content, list):
            blocks = []
            for c in content:
                if isinstance(c, dict):
                    ctype = c.get("type")
                    if ctype == "text":
                        blocks.append({"type": "text", "text": c.get("text") or ""})
                    elif ctype == "image_url":
                        url = (c.get("image_url") or {}).get("url") or ""
                        if url.startswith("data:"):
                            try:
                                head, b64 = url.split(",", 1)
                                media = head.split(";")[0].split(":", 1)[1]
                                blocks.append({"type": "image", "source": {"type": "base64", "media_type": media, "data": b64}})
                            except Exception:
                                pass
                        elif url:
                            blocks.append({"type": "image", "source": {"type": "url", "url": url}})
                elif isinstance(c, str):
                    blocks.append({"type": "text", "text": c})
            out.append({"role": "user", "content": blocks or [{"type": "text", "text": ""}]})
        else:
            out.append({"role": "user", "content": "" if content is None else str(content)})

    system_text = "\n\n".join(p for p in system_parts if p) or None
    return system_text, out


def _build_anthropic_payload(
    model: str, messages: List[Dict[str, Any]], stream: bool, extra: Dict[str, Any]
) -> Dict[str, Any]:
    system, anth_msgs = _openai_messages_to_anthropic(messages)
    payload: Dict[str, Any] = {
        "model": model,
        "messages": anth_msgs,
        "stream": stream,
    }
    max_tokens = extra.get("max_tokens")
    try:
        mt = int(max_tokens) if max_tokens is not None else 0
    except (TypeError, ValueError):
        mt = 0
    payload["max_tokens"] = mt if mt > 0 else settings.default_max_tokens
    if system:
        payload["system"] = system
    for k in ("temperature", "top_p", "top_k"):
        v = extra.get(k)
        if v is not None:
            payload[k] = v
    stop = extra.get("stop")
    if stop:
        payload["stop_sequences"] = stop if isinstance(stop, list) else [stop]

    tools = _openai_tools_to_anthropic(extra.get("tools"))
    if tools:
        payload["tools"] = tools
        choice = _openai_tool_choice_to_anthropic(extra.get("tool_choice"))
        if choice:
            payload["tool_choice"] = choice
    return payload


def _anthropic_full_to_openai_full(anth: Dict[str, Any], model: str) -> Dict[str, Any]:
    blocks = anth.get("content") or []
    text_parts: List[str] = []
    tool_calls: List[Dict[str, Any]] = []
    for blk in blocks:
        if not isinstance(blk, dict):
            continue
        if blk.get("type") == "text":
            text_parts.append(str(blk.get("text") or ""))
        elif blk.get("type") == "tool_use":
            tool_calls.append({
                "id": blk.get("id") or "",
                "type": "function",
                "function": {
                    "name": blk.get("name") or "",
                    "arguments": json.dumps(blk.get("input") or {}, ensure_ascii=False),
                },
            })
    message: Dict[str, Any] = {"role": "assistant", "content": "".join(text_parts)}
    if tool_calls:
        message["tool_calls"] = tool_calls
    finish_reason = _ANTHROPIC_STOP_REASON_TO_OPENAI.get(anth.get("stop_reason") or "", "stop")
    usage = anth.get("usage") or {}
    return {
        "id": anth.get("id") or ("chatcmpl-" + uuid.uuid4().hex[:24]),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": {
            "prompt_tokens": int(usage.get("input_tokens") or 0),
            "completion_tokens": int(usage.get("output_tokens") or 0),
            "total_tokens": int(usage.get("input_tokens") or 0) + int(usage.get("output_tokens") or 0),
        },
    }


async def _anthropic_sse_to_openai_lines(
    lines: AsyncIterator[bytes], model: str
) -> AsyncIterator[str]:
    """Переводит Anthropic SSE-события в OpenAI-формат: одна строка 'data: {...}'
    или 'data: [DONE]' за итерацию -- ровно то, что ожидают downstream-генераторы
    (_ollama_chat_stream / _openai_chat_stream)."""
    completion_id = "chatcmpl-" + uuid.uuid4().hex[:24]
    created = int(time.time())
    block_kinds: Dict[int, str] = {}
    tool_indices: Dict[int, int] = {}
    next_tool_index = 0
    finish_reason: Optional[str] = None

    def _chunk(delta: Optional[Dict[str, Any]] = None, finish: Optional[str] = None) -> str:
        ch: Dict[str, Any] = {"index": 0, "delta": delta or {}, "finish_reason": finish}
        return "data: " + json.dumps(
            {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [ch],
            },
            ensure_ascii=False,
        )

    # начальный чанк с ролью
    yield _chunk(delta={"role": "assistant", "content": ""})

    async for raw in lines:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        line = raw.strip()
        if not line or not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            evt = json.loads(data)
        except json.JSONDecodeError:
            continue
        etype = evt.get("type")

        if etype == "content_block_start":
            idx = evt.get("index", 0)
            blk = evt.get("content_block") or {}
            kind = blk.get("type")
            block_kinds[idx] = kind
            if kind == "tool_use":
                tool_indices[idx] = next_tool_index
                next_tool_index += 1
                yield _chunk(delta={
                    "tool_calls": [{
                        "index": tool_indices[idx],
                        "id": blk.get("id") or "",
                        "type": "function",
                        "function": {"name": blk.get("name") or "", "arguments": ""},
                    }]
                })
        elif etype == "content_block_delta":
            idx = evt.get("index", 0)
            delta = evt.get("delta") or {}
            dtype = delta.get("type")
            if dtype == "text_delta":
                text = delta.get("text") or ""
                if text:
                    yield _chunk(delta={"content": text})
            elif dtype == "input_json_delta":
                partial = delta.get("partial_json") or ""
                if partial and idx in tool_indices:
                    yield _chunk(delta={
                        "tool_calls": [{
                            "index": tool_indices[idx],
                            "function": {"arguments": partial},
                        }]
                    })
        elif etype == "message_delta":
            stop = (evt.get("delta") or {}).get("stop_reason")
            if stop:
                finish_reason = _ANTHROPIC_STOP_REASON_TO_OPENAI.get(stop, "stop")
        elif etype == "message_stop":
            break
        elif etype == "error":
            msg = (evt.get("error") or {}).get("message") or "upstream error"
            err_log.error("Anthropic stream error: %s", msg)
            yield "data: " + json.dumps({"error": {"message": msg}}, ensure_ascii=False)
            break
        # message_start / content_block_stop / ping -- игнорируем

    yield _chunk(finish=finish_reason or "stop")
    yield "data: [DONE]"


# --------------------------------------------------------------------------- #
# Обращение к KIE.AI                                                          #
# --------------------------------------------------------------------------- #


async def _post_upstream(path: str, payload: Dict[str, Any]) -> httpx.Response:
    client = get_client()
    try:
        return await client.post(path, json=payload)
    except httpx.TimeoutException as exc:
        err_log.error("Upstream timeout on %s: %s", path, exc)
        raise HTTPException(status_code=504, detail="Upstream timeout") from exc
    except httpx.ConnectError as exc:
        err_log.error("Upstream connect error on %s: %s", path, exc)
        raise HTTPException(status_code=503, detail="Upstream unavailable") from exc
    except httpx.HTTPError as exc:
        err_log.error("Upstream HTTP error on %s: %s", path, exc)
        raise HTTPException(status_code=502, detail=f"Upstream error: {exc}") from exc


def _raise_for_upstream(resp: httpx.Response) -> None:
    if resp.is_success:
        return
    detail: Any
    try:
        detail = resp.json()
    except Exception:
        detail = resp.text[:1000]
    err_log.error("Upstream %s: %s", resp.status_code, detail)
    if 400 <= resp.status_code < 500:
        raise HTTPException(status_code=resp.status_code, detail=detail)
    raise HTTPException(status_code=502, detail={"upstream_status": resp.status_code, "body": detail})


async def _kie_chat_completion(
    model: str,
    messages: List[Dict[str, Any]],
    stream: bool,
    extra: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[AsyncIterator[bytes]], Optional[httpx.Response]]:
    """Шлёт в KIE.AI `/messages` (Anthropic-native), возвращает данные в
    OpenAI-формате -- так что downstream-конвертеры (Ollama/OpenAI) не меняются.
    `model` -- display-имя (с префиксом kie/); upstream шлётся без префикса,
    а в ответе/чанках клиенту возвращается display-имя.
    Non-stream: (openai_json, None, None). Stream: (None, lines-iter, upstream-resp)."""
    payload = _build_anthropic_payload(_upstream_name(model), messages, stream, extra)

    client = get_client()
    if not stream:
        resp = await _post_upstream("/messages", payload)
        _raise_for_upstream(resp)
        try:
            anth = resp.json()
        except json.JSONDecodeError as exc:
            err_log.error("Invalid JSON from upstream: %s", exc)
            raise HTTPException(status_code=502, detail="Invalid JSON from upstream") from exc
        return _anthropic_full_to_openai_full(anth, model), None, None

    # Streaming -- открываем долгоживущий поток
    req = client.build_request(
        "POST", "/messages", json=payload, headers={"Accept": "text/event-stream"}
    )
    try:
        resp = await client.send(req, stream=True)
    except httpx.TimeoutException as exc:
        err_log.error("Upstream stream timeout: %s", exc)
        raise HTTPException(status_code=504, detail="Upstream timeout") from exc
    except httpx.ConnectError as exc:
        err_log.error("Upstream stream connect error: %s", exc)
        raise HTTPException(status_code=503, detail="Upstream unavailable") from exc
    except httpx.HTTPError as exc:
        err_log.error("Upstream stream HTTP error: %s", exc)
        raise HTTPException(status_code=502, detail=f"Upstream error: {exc}") from exc

    if not resp.is_success:
        body = await resp.aread()
        await resp.aclose()
        detail: Any
        try:
            detail = json.loads(body.decode("utf-8", errors="replace"))
        except Exception:
            detail = body.decode("utf-8", errors="replace")[:1000]
        err_log.error("Upstream stream %s: %s", resp.status_code, detail)
        if 400 <= resp.status_code < 500:
            raise HTTPException(status_code=resp.status_code, detail=detail)
        raise HTTPException(status_code=502, detail={"upstream_status": resp.status_code, "body": detail})

    translated = _anthropic_sse_to_openai_lines(resp.aiter_lines(), model)
    return None, translated, resp


# --------------------------------------------------------------------------- #
# Парсинг SSE и трансформация в Ollama                                        #
# --------------------------------------------------------------------------- #


def _parse_sse_line(line: str) -> Optional[Dict[str, Any]]:
    """Один SSE-чанк OpenAI: `data: {...}` или `data: [DONE]`. None -> завершение."""
    if not line:
        return {}
    if not line.startswith("data:"):
        return {}
    payload = line[5:].strip()
    if payload == "[DONE]":
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return {}


def _openai_chunk_to_ollama(chunk: Dict[str, Any], model: str) -> Dict[str, Any]:
    choice = (chunk.get("choices") or [{}])[0]
    delta = choice.get("delta") or {}
    content = delta.get("content") or ""
    role = delta.get("role") or "assistant"
    return {
        "model": model,
        "created_at": _iso_now(),
        "message": {"role": role, "content": content},
        "done": False,
    }


def _openai_chunk_to_ollama_generate(chunk: Dict[str, Any], model: str) -> Dict[str, Any]:
    choice = (chunk.get("choices") or [{}])[0]
    delta = choice.get("delta") or {}
    content = delta.get("content") or ""
    return {
        "model": model,
        "created_at": _iso_now(),
        "response": content,
        "done": False,
    }


def _final_ollama_chat(model: str, total_ns: int, eval_count: int = 0) -> Dict[str, Any]:
    return {
        "model": model,
        "created_at": _iso_now(),
        "message": {"role": "assistant", "content": ""},
        "done": True,
        "done_reason": "stop",
        "total_duration": total_ns,
        "load_duration": 0,
        "prompt_eval_count": 0,
        "prompt_eval_duration": 0,
        "eval_count": eval_count,
        "eval_duration": total_ns,
    }


def _final_ollama_generate(model: str, total_ns: int, eval_count: int = 0) -> Dict[str, Any]:
    base = _final_ollama_chat(model, total_ns, eval_count)
    base.pop("message", None)
    base["response"] = ""
    return base


def _openai_full_to_ollama_chat(resp: Dict[str, Any], model: str, total_ns: int) -> Dict[str, Any]:
    choice = (resp.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    usage = resp.get("usage") or {}
    return {
        "model": model,
        "created_at": _iso_now(),
        "message": {
            "role": message.get("role") or "assistant",
            "content": message.get("content") or "",
        },
        "done": True,
        "done_reason": choice.get("finish_reason") or "stop",
        "total_duration": total_ns,
        "load_duration": 0,
        "prompt_eval_count": int(usage.get("prompt_tokens") or 0),
        "prompt_eval_duration": 0,
        "eval_count": int(usage.get("completion_tokens") or 0),
        "eval_duration": total_ns,
    }


def _openai_full_to_ollama_generate(resp: Dict[str, Any], model: str, total_ns: int) -> Dict[str, Any]:
    choice = (resp.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    usage = resp.get("usage") or {}
    return {
        "model": model,
        "created_at": _iso_now(),
        "response": message.get("content") or "",
        "done": True,
        "done_reason": choice.get("finish_reason") or "stop",
        "total_duration": total_ns,
        "load_duration": 0,
        "prompt_eval_count": int(usage.get("prompt_tokens") or 0),
        "prompt_eval_duration": 0,
        "eval_count": int(usage.get("completion_tokens") or 0),
        "eval_duration": total_ns,
    }


# --------------------------------------------------------------------------- #
# Стриминг-генераторы                                                         #
# --------------------------------------------------------------------------- #


async def _ollama_chat_stream(model: str, lines: AsyncIterator[bytes], upstream: httpx.Response, mode: str) -> AsyncIterator[bytes]:
    """mode = "chat" | "generate" -- какой формат финального чанка отдавать."""
    start = time.perf_counter_ns()
    eval_count = 0
    chunk_count = 0
    try:
        async for line in lines:
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")
            line = line.strip()
            if not line:
                continue
            if settings.dev_mode:
                preview = line if len(line) < 200 else line[:200] + "..."
                log.debug("SSE< %s", preview)
            parsed = _parse_sse_line(line)
            if parsed is None:
                break
            if not parsed:
                continue
            if mode == "chat":
                out = _openai_chunk_to_ollama(parsed, model)
            else:
                out = _openai_chunk_to_ollama_generate(parsed, model)
            content_present = (out.get("message", {}).get("content") if mode == "chat" else out.get("response"))
            if content_present:
                eval_count += 1
            chunk_count += 1
            yield (json.dumps(out, ensure_ascii=False) + "\n").encode("utf-8")
        total_ns = time.perf_counter_ns() - start
        final = (
            _final_ollama_chat(model, total_ns, eval_count)
            if mode == "chat"
            else _final_ollama_generate(model, total_ns, eval_count)
        )
        yield (json.dumps(final, ensure_ascii=False) + "\n").encode("utf-8")
        if settings.dev_mode:
            log.debug("SSE stream done: model=%s chunks=%d eval=%d", model, chunk_count, eval_count)
    except (asyncio.CancelledError, GeneratorExit):
        raise
    except Exception as exc:
        err_log.exception("Stream forwarding failed: %s", exc)
        err_payload = {
            "model": model,
            "created_at": _iso_now(),
            "done": True,
            "error": str(exc),
        }
        yield (json.dumps(err_payload, ensure_ascii=False) + "\n").encode("utf-8")
    finally:
        await upstream.aclose()


async def _openai_chat_stream(lines: AsyncIterator[bytes], upstream: httpx.Response) -> AsyncIterator[bytes]:
    """Пропускаем SSE OpenAI как есть, добавляя финальный [DONE], если апстрим его не прислал."""
    saw_done = False
    try:
        async for line in lines:
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")
            stripped = line.strip()
            if not stripped:
                yield b"\n"
                continue
            if settings.dev_mode:
                preview = stripped if len(stripped) < 200 else stripped[:200] + "..."
                log.debug("SSE< %s", preview)
            if stripped.startswith("data:") and stripped[5:].strip() == "[DONE]":
                saw_done = True
            yield (stripped + "\n\n").encode("utf-8")
        if not saw_done:
            yield b"data: [DONE]\n\n"
    except (asyncio.CancelledError, GeneratorExit):
        raise
    except Exception as exc:
        err_log.exception("OpenAI stream forwarding failed: %s", exc)
        payload = json.dumps({"error": {"message": str(exc), "type": "proxy_error"}})
        yield f"data: {payload}\n\n".encode("utf-8")
        yield b"data: [DONE]\n\n"
    finally:
        await upstream.aclose()


# --------------------------------------------------------------------------- #
# Ollama-совместимые эндпоинты                                                #
# --------------------------------------------------------------------------- #


@app.get("/")
async def root() -> Dict[str, Any]:
    return {
        "service": "copilot-ollama-kie-proxy",
        "ollama_compat_version": settings.ollama_compat_version,
        "upstream": settings.kie_ai_api_url,
        "default_model": settings.default_model,
    }


@app.get("/health")
@app.get("/api/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/version")
async def api_version() -> Dict[str, str]:
    return {"version": settings.ollama_compat_version}


@app.get("/api/tags")
async def api_tags() -> Dict[str, Any]:
    return {"models": [_ollama_model_descriptor(_display_name(m)) for m in settings.available_models]}


@app.get("/api/ps")
async def api_ps() -> Dict[str, Any]:
    """Список «запущенных» моделей -- возвращаем все доступные (заглушка)."""
    return {"models": [_ollama_model_descriptor(_display_name(m)) for m in settings.available_models]}


def _model_capabilities(name: str) -> List[str]:
    """Capabilities, как их возвращает реальная Ollama в /api/show.

    NB: объявлять `tools` для BYOK-провайдера в VSCode Copilot Chat 0.48.x
    нельзя -- расширение пытается прибиндить свои внутренние тулы к модели
    и падает в конструкторе `Yoe` с
        TypeError: Cannot read properties of undefined (reading 'bind')
    (см. runWithToolCalling -> Array.forEach -> new Yoe в extension.js).
    Это баг расширения; обойти можно только не отдавая `tools`. Цена --
    отсутствие agent mode для этой модели в Copilot."""
    return ["completion"]


def _show_payload(name: str) -> Dict[str, Any]:
    return {
        "license": "Proprietary -- via KIE.AI",
        "modelfile": (
            f"# Modelfile for {name}\n"
            f"FROM {name}\n"
            "TEMPLATE \"\"\"{{ if .System }}{{ .System }}\n\n{{ end }}"
            "{{ range .Messages }}{{ .Role }}: {{ .Content }}\n{{ end }}\"\"\"\n"
        ),
        "parameters": "stop \"<|im_end|>\"\nstop \"</s>\"\n",
        "template": "{{ .Prompt }}",
        "details": _model_details(name),
        "model_info": {
            "general.architecture": "llama",
            "general.basename": name,
            "llama.context_length": settings.model_context_length,
            "llama.embedding_length": 0,
        },
        "context_length": settings.model_context_length,
        "capabilities": _model_capabilities(name),
        "modified_at": _iso_now(),
    }


@app.post("/api/show")
async def api_show(request: Request) -> Dict[str, Any]:
    name: Optional[str] = None
    ctype = request.headers.get("content-type", "")
    body_bytes = await request.body()
    if body_bytes:
        if "application/json" in ctype:
            try:
                data = json.loads(body_bytes.decode("utf-8"))
                if isinstance(data, dict):
                    name = data.get("name") or data.get("model")
            except json.JSONDecodeError:
                pass
        elif "application/x-www-form-urlencoded" in ctype or "multipart/form-data" in ctype:
            form = await request.form()
            name = form.get("name") or form.get("model")  # type: ignore[assignment]
    if not name:
        name = request.query_params.get("name") or request.query_params.get("model")
    name = _model_or_default(name)
    return _show_payload(name)


async def _handle_ollama_chat(body: Dict[str, Any]) -> Response:
    model = _model_or_default(body.get("model"))
    messages = body.get("messages") or []
    if not isinstance(messages, list):
        raise HTTPException(status_code=400, detail="`messages` must be a list")
    stream = bool(body.get("stream", True))
    sampling = _extract_sampling(body)

    log.info(
        "CHAT model=%s msgs=%d stream=%s sampling=%s",
        model,
        len(messages),
        stream,
        sampling,
    )

    if not stream:
        start = time.perf_counter_ns()
        full, _, _ = await _kie_chat_completion(model, messages, False, sampling)
        assert full is not None
        return JSONResponse(_openai_full_to_ollama_chat(full, model, time.perf_counter_ns() - start))

    _, lines, upstream = await _kie_chat_completion(model, messages, True, sampling)
    assert lines is not None and upstream is not None
    return StreamingResponse(
        _ollama_chat_stream(model, lines, upstream, mode="chat"),
        media_type="application/x-ndjson",
    )


@app.post("/api/chat")
@app.post("/api/chat/completions")
async def api_chat(request: Request) -> Response:
    body = await _json_body(request)
    return await _handle_ollama_chat(body)


@app.post("/api/generate")
async def api_generate(request: Request) -> Response:
    body = await _json_body(request)
    model = _model_or_default(body.get("model"))
    prompt = body.get("prompt")
    system = body.get("system")
    if prompt is None:
        raise HTTPException(status_code=400, detail="`prompt` is required")
    messages = _build_messages(prompt=prompt, messages=None, system=system)
    stream = bool(body.get("stream", True))
    sampling = _extract_sampling(body)

    log.info("GENERATE model=%s stream=%s sampling=%s", model, stream, sampling)

    if not stream:
        start = time.perf_counter_ns()
        full, _, _ = await _kie_chat_completion(model, messages, False, sampling)
        assert full is not None
        return JSONResponse(_openai_full_to_ollama_generate(full, model, time.perf_counter_ns() - start))

    _, lines, upstream = await _kie_chat_completion(model, messages, True, sampling)
    assert lines is not None and upstream is not None
    return StreamingResponse(
        _ollama_chat_stream(model, lines, upstream, mode="generate"),
        media_type="application/x-ndjson",
    )


@app.post("/api/embeddings")
@app.post("/api/embed")
async def api_embeddings(request: Request) -> Dict[str, Any]:
    raise HTTPException(status_code=501, detail="Embeddings are not supported by Claude via KIE.AI")


@app.post("/api/pull")
async def api_pull(request: Request) -> Response:
    body = await _json_body(request, allow_empty=True)
    name = body.get("name") or body.get("model") or settings.default_model
    stream = bool(body.get("stream", True))
    log.info("PULL (stub) model=%s stream=%s", name, stream)

    if not stream:
        return JSONResponse({"status": "success"})

    async def gen() -> AsyncIterator[bytes]:
        for status in ("pulling manifest", "verifying sha256 digest", "writing manifest", "success"):
            yield (json.dumps({"status": status}) + "\n").encode("utf-8")

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.post("/api/create")
async def api_create() -> Dict[str, str]:
    return {"status": "success"}


@app.post("/api/copy")
async def api_copy() -> Dict[str, str]:
    return {"status": "success"}


@app.delete("/api/delete")
async def api_delete() -> Dict[str, str]:
    return {"status": "success"}


@app.head("/api/blobs/{digest}")
async def api_blob_head(digest: str) -> Response:
    return Response(status_code=200)


@app.post("/api/blobs/{digest}")
async def api_blob_post(digest: str) -> Response:
    return Response(status_code=201)


# --------------------------------------------------------------------------- #
# OpenAI-совместимые эндпоинты                                                #
# --------------------------------------------------------------------------- #


@app.get("/v1/models")
async def v1_models() -> Dict[str, Any]:
    return {
        "object": "list",
        "data": [_openai_model_descriptor(_display_name(m)) for m in settings.available_models],
    }


@app.get("/v1/models/{model}")
async def v1_model(model: str) -> Dict[str, Any]:
    return _openai_model_descriptor(model)


@app.post("/v1/chat/completions")
async def v1_chat_completions(request: Request) -> Response:
    body = await _json_body(request)
    model = _model_or_default(body.get("model"))
    messages = body.get("messages") or []
    if not isinstance(messages, list):
        raise HTTPException(status_code=400, detail="`messages` must be a list")
    stream = bool(body.get("stream", False))

    # Передаём все параметры, кроме служебных
    extra = {
        k: v
        for k, v in body.items()
        if k not in ("model", "messages", "stream") and v is not None
    }

    log.info("V1 CHAT model=%s msgs=%d stream=%s", model, len(messages), stream)

    if not stream:
        full, _, _ = await _kie_chat_completion(model, messages, False, extra)
        assert full is not None
        # Подменяем модель в ответе на запрошенную (с тегом, если был)
        full["model"] = model
        return JSONResponse(full)

    _, lines, upstream = await _kie_chat_completion(model, messages, True, extra)
    assert lines is not None and upstream is not None
    return StreamingResponse(
        _openai_chat_stream(lines, upstream),
        media_type="text/event-stream",
    )


@app.post("/v1/completions")
async def v1_completions(request: Request) -> Response:
    body = await _json_body(request)
    model = _model_or_default(body.get("model"))
    prompt = body.get("prompt")
    if prompt is None:
        raise HTTPException(status_code=400, detail="`prompt` is required")
    if isinstance(prompt, list):
        prompt = "\n".join(str(p) for p in prompt)
    stream = bool(body.get("stream", False))
    extra = {
        k: v
        for k, v in body.items()
        if k not in ("model", "prompt", "stream", "suffix", "echo", "logprobs", "best_of")
        and v is not None
    }
    messages = [{"role": "user", "content": str(prompt)}]
    log.info("V1 COMPLETIONS model=%s stream=%s", model, stream)

    if not stream:
        full, _, _ = await _kie_chat_completion(model, messages, False, extra)
        assert full is not None
        choice = (full.get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content") or ""
        return JSONResponse(
            {
                "id": "cmpl-" + uuid.uuid4().hex[:24],
                "object": "text_completion",
                "created": int(time.time()),
                "model": model,
                "choices": [
                    {
                        "text": text,
                        "index": 0,
                        "logprobs": None,
                        "finish_reason": choice.get("finish_reason") or "stop",
                    }
                ],
                "usage": full.get("usage") or {},
            }
        )

    _, lines, upstream = await _kie_chat_completion(model, messages, True, extra)
    assert lines is not None and upstream is not None

    async def gen() -> AsyncIterator[bytes]:
        completion_id = "cmpl-" + uuid.uuid4().hex[:24]
        created = int(time.time())
        try:
            async for line in lines:
                if isinstance(line, bytes):
                    line = line.decode("utf-8", errors="replace")
                line = line.strip()
                if not line:
                    continue
                parsed = _parse_sse_line(line)
                if parsed is None:
                    break
                if not parsed:
                    continue
                choice = (parsed.get("choices") or [{}])[0]
                delta = choice.get("delta") or {}
                content = delta.get("content") or ""
                out = {
                    "id": completion_id,
                    "object": "text_completion",
                    "created": created,
                    "model": model,
                    "choices": [
                        {
                            "text": content,
                            "index": 0,
                            "logprobs": None,
                            "finish_reason": choice.get("finish_reason"),
                        }
                    ],
                }
                yield f"data: {json.dumps(out, ensure_ascii=False)}\n\n".encode("utf-8")
            yield b"data: [DONE]\n\n"
        finally:
            await upstream.aclose()

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/v1/embeddings")
async def v1_embeddings(request: Request) -> Dict[str, Any]:
    raise HTTPException(status_code=501, detail="Embeddings are not supported by Claude via KIE.AI")


# --------------------------------------------------------------------------- #
# Вспомогательное                                                             #
# --------------------------------------------------------------------------- #


async def _json_body(request: Request, allow_empty: bool = False) -> Dict[str, Any]:
    raw = await request.body()
    if not raw:
        if allow_empty:
            return {}
        raise HTTPException(status_code=400, detail="Empty request body")
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")
    return data


# Catch-all -- ловим всё, что не подошло к маршрутам выше, чтобы видеть в логах,
# какие эндпоинты ещё дёргают клиенты (VSCode/Copilot и т.п.). Регистрируется
# ПОСЛЕ всех специализированных маршрутов, поэтому в их работу не вмешивается.
@app.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def catch_all(full_path: str, request: Request) -> JSONResponse:
    body_preview = ""
    try:
        raw = await request.body()
        if raw:
            txt = raw.decode("utf-8", errors="replace")
            body_preview = txt if len(txt) <= 512 else txt[:512] + "...<truncated>"
    except Exception:
        body_preview = "<unreadable>"
    log.warning(
        "UNHANDLED %s /%s query=%s body=%s",
        request.method,
        full_path,
        dict(request.query_params),
        body_preview,
    )
    if request.method == "OPTIONS":
        return JSONResponse(status_code=204, content=None)
    return JSONResponse(status_code=404, content={"error": f"Not found: {request.method} /{full_path}"})


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail if not isinstance(exc.detail, str) else exc.detail},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    err_log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"error": str(exc)})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.proxy_host,
        port=settings.proxy_port,
        log_level=settings.log_level.lower(),
    )
