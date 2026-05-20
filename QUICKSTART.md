# Quick Start Guide

## Installation (One-time setup)

```bash
# 1. Navigate to project
cd /Users/boss/PycharmProjects/copilot-ollama-kie-proxy

# 2. Install dependencies
make install

# 3. Setup configuration
make env-setup

# 4. Edit .env with your KIE.AI API key
nano .env
```

## Running the Service

### Start Server
```bash
make start
```
Service will be available at: `http://127.0.0.1:11434`

### In Development Mode (with auto-reload)
```bash
make start
```

### In Production Mode (4 workers)
```bash
make start-prod
```

### Stop Server
```bash
make stop
```

### Restart Server
```bash
make restart
```

## Testing

### Quick Tests
```bash
make test-health      # Test if service is running
make test-tags        # List available models
```

### Full API Test Suite
```bash
bash test_api.sh
```

### Using Python Client
```bash
python client_example.py
```

### Manual Testing with curl
```bash
# Health check
curl http://127.0.0.1:11434/health

# List models
curl http://127.0.0.1:11434/api/tags

# Chat completion
curl -X POST http://127.0.0.1:11434/api/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-opus-4-6", "messages": [{"role": "user", "content": "Hello"}]}'

# Streaming response
curl -X POST http://127.0.0.1:11434/api/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-opus-4-6", "messages": [{"role": "user", "content": "Tell me a story"}], "stream": true}'
```

## Logs

### View All Logs
```bash
make logs
```

### View Error Logs
```bash
make logs-errors
```

### View Request Logs
```bash
make logs-requests
```

### Log Files Location
```
logs/
├── general_2026-05.log    # General app logs
├── errors_2026-05.log     # Error logs
└── requests_2026-05.log   # Request/response logs
```

## Cleanup

### Clean Cache
```bash
make clean
```

### Clean Logs
```bash
make clean-logs
```

## Docker Deployment

### Start with Docker Compose
```bash
docker-compose up -d
```

### Stop Docker Compose
```bash
docker-compose down
```

### View Docker Logs
```bash
docker-compose logs -f
```

## Help

### Show All Available Commands
```bash
make help
```

### View Full Documentation
- [README.md](README.md) - Main documentation
- [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment guide
- [technical_requirements.txt](technical_requirements.txt) - Technical specs

## API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` | Health check |
| GET | `/api/version` | Get service version |
| GET | `/api/tags` | List available models |
| POST | `/api/generate` | Text generation |
| POST | `/api/chat/completions` | Chat completions |
| POST | `/api/pull` | Pull model (stub) |
| DELETE | `/api/delete` | Delete model (stub) |
| HEAD | `/api/blobs/{digest}` | Check blob |

## Troubleshooting

### Service won't start
```bash
# Check if port 11434 is available
lsof -i :11434

# Verify .env is configured
cat .env | grep KIE_AI_API_KEY

# View error logs
make logs-errors
```

### Connection refused
```bash
# Make sure service is running
make test-health

# If not running, start it
make start
```

### API key error
```bash
# Verify API key in .env
nano .env

# Key should look like: KIE_AI_API_KEY=sk_...
```

### Permission denied on scripts
```bash
chmod +x *.sh
```

## Environment Variables

```bash
KIE_AI_API_KEY         # Your KIE.AI API key (required)
KIE_AI_API_URL         # KIE.AI API URL (default: https://api.kie.ai/v1)
PROXY_HOST             # Listen address (default: 127.0.0.1)
PROXY_PORT             # Listen port (default: 11434)
LOG_LEVEL              # Logging level (default: INFO)
LOG_DIR                # Log files directory (default: ./logs)
DEFAULT_MODEL          # Default model (default: claude-opus-4-6)
```

## Common Tasks

### Change Log Level
Edit `.env`:
```bash
LOG_LEVEL=DEBUG
```

### Change Listen Port
Edit `.env`:
```bash
PROXY_PORT=8080
```

### Change Backend URL
Edit `.env`:
```bash
KIE_AI_API_URL=https://custom-kie-api.example.com/v1
```

### Add Custom Models
Edit `main.py` in the `get_tags()` function to add models.

### Deploy to Production
See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed instructions.

## File Structure

```
copilot-ollama-kie-proxy/
├── main.py                      # Main FastAPI application
├── config.py                    # Configuration management
├── logger.py                    # Logging setup
├── client_example.py            # Example async client
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment template
├── .env                         # Local configuration (git ignored)
├── Makefile                     # Development commands
├── Dockerfile                   # Docker image definition
├── docker-compose.yml           # Docker compose config
├── start.sh                     # Start script
├── test_api.sh                  # API test suite
├── ollama-kie-proxy.service     # Systemd service
├── .gitignore                   # Git ignore rules
├── README.md                    # Main documentation
├── DEPLOYMENT.md                # Deployment guide
├── technical_requirements.txt   # Technical specs
└── logs/                        # Log directory (auto-created)
    ├── general_2026-05.log
    ├── errors_2026-05.log
    └── requests_2026-05.log
```

## Quick Links

- 🐍 Python async framework: [FastAPI](https://fastapi.tiangolo.com/)
- 📚 Ollama API docs: [Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md)
- 🎯 KIE.AI docs: [KIE.AI Documentation](https://docs.kie.ai/)
- 🐳 Docker: [Docker Documentation](https://docs.docker.com/)
- 🔄 Uvicorn: [Uvicorn Documentation](https://www.uvicorn.org/)

## Next Steps

1. ✅ Installation complete
2. ⏭️  Configure `.env` with your API key
3. ▶️  Start service: `make start`
4. 🧪 Test endpoints: `bash test_api.sh`
5. 📖 Read [DEPLOYMENT.md](DEPLOYMENT.md) for production setup
