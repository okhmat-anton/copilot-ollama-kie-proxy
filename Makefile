.PHONY: install start stop restart clean logs help

# Variables
PYTHON := python3
PIP := pip3
VENV := venv
PORT := 11434

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	$(PIP) install -r requirements.txt
	@echo "✓ Dependencies installed"

venv: ## Create virtual environment
	$(PYTHON) -m venv $(VENV)
	@echo "✓ Virtual environment created"

venv-activate: ## Activate virtual environment
	@echo "Run: source $(VENV)/bin/activate"

env-setup: ## Create .env file from .env.example
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "✓ .env created. Please update it with your KIE.AI API key"; \
	else \
		echo "✓ .env already exists"; \
	fi

start: env-setup ## Start the proxy service
	@echo "Starting Ollama-KIE.AI Proxy on http://127.0.0.1:$(PORT)..."
	$(PYTHON) -m uvicorn main:app --host 127.0.0.1 --port $(PORT) --reload

start-prod: env-setup ## Start proxy in production mode
	@echo "Starting Ollama-KIE.AI Proxy (production) on http://127.0.0.1:$(PORT)..."
	$(PYTHON) -m uvicorn main:app --host 0.0.0.0 --port $(PORT) --workers 4

stop: ## Stop the proxy service (manual termination)
	@pkill -f "uvicorn main:app" || echo "✓ Proxy service stopped"

restart: stop start ## Restart the proxy service

clean: ## Clean up cache and logs
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache 2>/dev/null || true
	@echo "✓ Cache cleaned"

clean-logs: ## Clean all log files
	rm -rf logs/
	@echo "✓ Log files cleaned"

logs: ## View recent log entries
	@if [ -d logs ]; then \
		tail -f logs/*.log 2>/dev/null || echo "No log files found"; \
	else \
		echo "Log directory not found"; \
	fi

logs-errors: ## View error logs
	@if [ -f logs/errors_*.log ]; then \
		tail -f logs/errors_*.log; \
	else \
		echo "No error logs found"; \
	fi

logs-requests: ## View request logs
	@if [ -f logs/requests_*.log ]; then \
		tail -f logs/requests_*.log; \
	else \
		echo "No request logs found"; \
	fi

test-health: ## Test health check endpoint
	@echo "Testing health endpoint..."
	@curl -s http://127.0.0.1:$(PORT)/health | python -m json.tool || echo "Service not running"

test-tags: ## Test list models endpoint
	@echo "Testing list models endpoint..."
	@curl -s http://127.0.0.1:$(PORT)/api/tags | python -m json.tool || echo "Service not running"

requirements: ## Generate/update requirements.txt from installed packages
	$(PIP) freeze > requirements.txt
	@echo "✓ requirements.txt updated"

lint: ## Run Python linter
	@command -v pylint >/dev/null 2>&1 && pylint main.py config.py logger.py || \
		echo "pylint not installed. Run: pip install pylint"

format: ## Format Python code
	@command -v black >/dev/null 2>&1 && black main.py config.py logger.py || \
		echo "black not installed. Run: pip install black"

all: install env-setup ## Install dependencies and setup environment
	@echo "✓ All setup complete. Run 'make start' to begin"
