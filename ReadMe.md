# Ollama-KIE.AI Proxy

A lightweight, asynchronous Python proxy service that emulates the Ollama API and proxies requests to the [KIE.AI API](https://docs.kie.ai/market/claude/claude-opus-4-6). This enables seamless integration of KIE.AI's advanced language models with any Ollama-compatible client.

## Features

✨ **Full Ollama API Compatibility**
- `/api/tags` - List available models
- `/api/generate` - Text generation with streaming support
- `/api/chat/completions` - Chat completions with message history
- `/api/pull`, `/api/delete` - Model management (stub implementations)
- `/api/version`, `/health` - System endpoints

🚀 **Async/Await Architecture**
- Built with FastAPI and asyncio for high concurrency
- Streaming support for real-time responses
- Connection pooling for efficient backend communication

📊 **Comprehensive Logging**
- Separate log files for errors and requests
- Automatic monthly log rotation
- Structured logging with timestamps and request details

🔐 **Security**
- Environment-based configuration
- API key management via `.env`
- HTTPS support for production deployment

## Requirements

- Python 3.9+
- pip (Python package manager)
- A valid KIE.AI API key
- make (for using convenient commands)

## Installation

1. **Clone or create the project directory:**
```bash
cd /Users/boss/PycharmProjects/copilot-ollama-kie-proxy
```

2. **Install dependencies:**
```bash
make install
```

Or manually:
```bash
pip3 install -r requirements.txt
```

3. **Setup environment configuration:**
```bash
make env-setup
```

This creates a `.env` file from `.env.example`. Edit it with your KIE.AI API key:
```bash
nano .env
```

Example `.env` file:
```
KIE_AI_API_KEY=your_actual_kie_ai_api_key_here
KIE_AI_API_URL=https://api.kie.ai/v1
PROXY_HOST=127.0.0.1
PROXY_PORT=11434
LOG_LEVEL=INFO
LOG_DIR=./logs
DEFAULT_MODEL=claude-opus-4-6
```

## Quick Start

### Start the Service

**Development mode (with auto-reload):**
```bash
make start
```

**Production mode (4 workers):**
```bash
make start-prod
```

The proxy will start on `http://127.0.0.1:11434`

### Test the Service

**Health check:**
```bash
make test-health
```

**List available models:**
```bash
make test-tags
```

**Manual health check:**
```bash
curl http://127.0.0.1:11434/health
```

### Stop the Service

```bash
make stop
```

### Restart the Service

```bash
make restart
```

## Usage Examples

### Using with curl

**Chat completion:**
```bash
curl -X POST http://127.0.0.1:11434/api/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-opus-4-6",
    "messages": [
      {"role": "user", "content": "Hello, how are you?"}
    ],
    "stream": false
  }'
```

**Streaming chat completion:**
```bash
curl -X POST http://127.0.0.1:11434/api/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-opus-4-6",
    "messages": [
      {"role": "user", "content": "Tell me a story"}
    ],
    "stream": true
  }'
```

**Text generation:**
```bash
curl -X POST http://127.0.0.1:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-opus-4-6",
    "prompt": "Write a haiku about programming",
    "stream": false
  }'
```

### Using with Python

```python
import asyncio
import aiohttp
import json

async def chat():
    async with aiohttp.ClientSession() as session:
        async with session.post(
            'http://127.0.0.1:11434/api/chat/completions',
            json={
                'model': 'claude-opus-4-6',
                'messages': [{'role': 'user', 'content': 'Hello!'}],
                'stream': False
            }
        ) as resp:
            data = await resp.json()
            print(data['response'])

asyncio.run(chat())
```

### Using with Ollama-compatible clients

Any tool that supports Ollama can be pointed to this proxy:
- LLaMA.cpp web UI
- Ollama Python library
- LangChain/LlamaIndex
- Custom applications

Configure the client to use: `http://127.0.0.1:11434`

## Logging

### View logs in real-time

**All logs:**
```bash
make logs
```

**Error logs only:**
```bash
make logs-errors
```

**Request logs only:**
```bash
make logs-requests
```

### Log Files Structure

Logs are automatically organized by month:

```
logs/
├── general_2026-05.log     # General application logs
├── errors_2026-05.log      # Error and exception logs
└── requests_2026-05.log    # Request/response logs
```

New log files are created automatically at the start of each month.

### Log Levels

Configured via `LOG_LEVEL` environment variable:
- `DEBUG` - Detailed diagnostic information
- `INFO` - General informational messages (default)
- `WARNING` - Warning messages
- `ERROR` - Error messages only

## API Endpoints

### Model Management

- `GET /api/tags` - List available models
- `POST /api/pull` - Pull a model (stub)
- `DELETE /api/delete` - Delete a model (stub)
- `HEAD /api/blobs/{digest}` - Check blob existence

### Model Inference

- `POST /api/generate` - Text generation with streaming support
  - Request: `{model, prompt, stream, temperature, top_p}`
  - Response: `{model, response, done, created_at}`

- `POST /api/chat/completions` - Chat completions with message history
  - Request: `{model, messages, stream, temperature, top_p, max_tokens}`
  - Response: `{model, response, done, created_at}`

### System

- `GET /api/version` - Service version and backend info
- `GET /health` - Health check endpoint

## Configuration

### Environment Variables (`.env` file)

```
# KIE.AI API Configuration
KIE_AI_API_KEY=<your-api-key>              # Required: Your KIE.AI API key
KIE_AI_API_URL=https://api.kie.ai/v1       # KIE.AI API endpoint

# Proxy Service Configuration
PROXY_HOST=127.0.0.1                       # Listen address
PROXY_PORT=11434                           # Listen port

# Logging Configuration
LOG_LEVEL=INFO                             # DEBUG, INFO, WARNING, ERROR
LOG_DIR=./logs                             # Log directory path

# Model Configuration
DEFAULT_MODEL=claude-opus-4-6              # Default model name
```

## Available Make Commands

```bash
make help              # Show all available commands
make install           # Install dependencies
make venv              # Create virtual environment
make env-setup         # Create .env from .env.example
make start             # Start proxy (development)
make start-prod        # Start proxy (production)
make stop              # Stop the service
make restart           # Restart the service
make clean             # Clean cache and temp files
make clean-logs        # Remove all log files
make logs              # View all logs
make logs-errors       # View error logs
make logs-requests     # View request logs
make test-health       # Test health endpoint
make test-tags         # Test list models endpoint
make requirements      # Update requirements.txt
make lint              # Run Python linter
make format            # Format Python code
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'fastapi'"
Install dependencies:
```bash
make install
```

### "KIE_AI_API_KEY environment variable is not set"
Create and configure `.env` file:
```bash
make env-setup
# Edit .env with your API key
nano .env
```

### "Connection refused" error
Make sure the proxy is running:
```bash
make start
```

Check if port 11434 is available:
```bash
lsof -i :11434
```

### Service crashes with authentication error
Verify your KIE.AI API key in `.env` is correct and active.

### No response from backend
Check that:
1. `KIE_AI_API_URL` in `.env` is correct
2. Your network connection is stable
3. KIE.AI API is accessible from your location

## Architecture

```
Client Request
    ↓
[Ollama Format] → FastAPI Server → Transform Request
    ↓
[KIE.AI Format] → HTTP Client → KIE.AI API
    ↓
[KIE.AI Response] → Transform Response → [Ollama Format]
    ↓
Client Response
```

## Supported Models

- `claude-opus-4-6` - Claude Opus 4.6 via KIE.AI

See [KIE.AI Documentation](https://docs.kie.ai/market/claude/claude-opus-4-6) for more details.

## Performance Considerations

- **Connection Pooling**: HTTP client maintains persistent connections
- **Streaming**: Efficient streaming for large responses
- **Async Operations**: Concurrent request handling
- **Timeouts**: 60-second default timeout for requests

## Security Notes

⚠️ **Important:**
- Never commit `.env` files to version control
- Keep your API key secure
- Rotate API keys regularly
- Use HTTPS in production (configure your reverse proxy)
- Limit network exposure of the proxy service

## Development

### Code Structure

- `main.py` - FastAPI application and endpoints
- `config.py` - Configuration management
- `logger.py` - Logging setup with monthly rotation
- `requirements.txt` - Python dependencies
- `Makefile` - Development commands
- `.env.example` - Configuration template

### Adding New Endpoints

1. Add new model classes in `main.py`
2. Define transformation functions
3. Create endpoint with `@app.post()` or `@app.get()`
4. Add proper logging
5. Test with curl or Python client

## License

MIT License - Feel free to use and modify

## Support

For issues with:
- **KIE.AI API**: See [KIE.AI Documentation](https://docs.kie.ai/)
- **Ollama API compatibility**: See [Ollama API docs](https://github.com/ollama/ollama/blob/main/docs/api.md)
- **FastAPI**: See [FastAPI Documentation](https://fastapi.tiangolo.com/)

## Changelog

### Version 1.0.0
- Initial release
- Full Ollama API compatibility
- KIE.AI integration
- Async/await architecture
- Monthly log rotation
- Make commands for easy management
