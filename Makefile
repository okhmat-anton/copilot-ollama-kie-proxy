SHELL := /bin/bash

VENV         := venv
PY           := $(VENV)/bin/python
PIP          := $(VENV)/bin/pip
UVICORN      := $(VENV)/bin/uvicorn

LOG_DIR      := logs
RUN_DIR      := .run
PID_FILE     := $(RUN_DIR)/proxy.pid
STDOUT_LOG   := $(LOG_DIR)/uvicorn.out.log
STDERR_LOG   := $(LOG_DIR)/uvicorn.err.log

PROXY_HOST   ?= $(shell grep -E '^PROXY_HOST=' .env 2>/dev/null | cut -d= -f2)
PROXY_PORT   ?= $(shell grep -E '^PROXY_PORT=' .env 2>/dev/null | cut -d= -f2)
PROXY_HOST   := $(if $(PROXY_HOST),$(PROXY_HOST),127.0.0.1)
PROXY_PORT   := $(if $(PROXY_PORT),$(PROXY_PORT),11777)

.PHONY: help venv install env-setup start start-dev stop restart status logs test clean clean-venv

help:
	@echo "Targets:"
	@echo "  venv         create ./$(VENV) if missing"
	@echo "  install      create venv and install requirements.txt"
	@echo "  env-setup    copy .env.example -> .env if .env is missing"
	@echo "  start        run uvicorn in background"
	@echo "  start-dev    run uvicorn in FOREGROUND with DEV_MODE=true + DEBUG logs"
	@echo "               (every incoming request and SSE chunk goes to stdout)"
	@echo "  stop         stop the background uvicorn"
	@echo "  restart      stop + start"
	@echo "  status       show PID and listening status"
	@echo "  logs         tail -f all logs"
	@echo "  test         run curl smoke tests"
	@echo "  clean        remove logs and runtime files (keeps venv)"
	@echo "  clean-venv   remove ./$(VENV)"

venv:
	@if [[ ! -d "$(VENV)" ]]; then \
		echo "Creating venv in ./$(VENV)"; \
		python3 -m venv $(VENV); \
		$(PIP) install --upgrade pip wheel setuptools >/dev/null; \
	else \
		echo "venv already exists at ./$(VENV)"; \
	fi

install: venv
	$(PIP) install -r requirements.txt

env-setup:
	@if [[ -f .env ]]; then \
		echo ".env already exists -- skipping"; \
	else \
		cp .env.example .env; \
		echo "Created .env from .env.example -- fill in KIE_AI_API_KEY"; \
	fi

start:
	@mkdir -p $(LOG_DIR) $(RUN_DIR)
	@if [[ -f $(PID_FILE) ]] && kill -0 $$(cat $(PID_FILE)) 2>/dev/null; then \
		echo "Already running (PID $$(cat $(PID_FILE)))"; \
		exit 0; \
	fi
	@if [[ ! -x "$(UVICORN)" ]]; then \
		echo "uvicorn missing -- run 'make install' first" >&2; exit 1; \
	fi
	@nohup $(UVICORN) main:app --host $(PROXY_HOST) --port $(PROXY_PORT) \
		>$(STDOUT_LOG) 2>$(STDERR_LOG) & echo $$! > $(PID_FILE)
	@sleep 1
	@if kill -0 $$(cat $(PID_FILE)) 2>/dev/null; then \
		echo "Started PID $$(cat $(PID_FILE)) on $(PROXY_HOST):$(PROXY_PORT)"; \
	else \
		echo "Failed to start -- see $(STDERR_LOG)" >&2; \
		rm -f $(PID_FILE); exit 1; \
	fi

start-dev:
	@mkdir -p $(LOG_DIR) $(RUN_DIR)
	@if [[ -f $(PID_FILE) ]] && kill -0 $$(cat $(PID_FILE)) 2>/dev/null; then \
		echo "Background instance is running (PID $$(cat $(PID_FILE))). Run 'make stop' first." >&2; \
		exit 1; \
	fi
	@if [[ ! -x "$(UVICORN)" ]]; then \
		echo "uvicorn missing -- run 'make install' first" >&2; exit 1; \
	fi
	@echo "===> start-dev (foreground)  $(PROXY_HOST):$(PROXY_PORT)"
	@echo "     DEV_MODE=true  LOG_LEVEL=DEBUG  -- requests + SSE chunks стримятся в этот терминал"
	@echo "     Ctrl-C для остановки"
	@echo
	DEV_MODE=true LOG_LEVEL=DEBUG \
	$(UVICORN) main:app \
		--host $(PROXY_HOST) --port $(PROXY_PORT) \
		--log-level debug --no-access-log \
		--reload

stop:
	@if [[ -f $(PID_FILE) ]]; then \
		PID=$$(cat $(PID_FILE)); \
		if kill -0 $$PID 2>/dev/null; then \
			kill $$PID; \
			for i in 1 2 3 4 5; do \
				kill -0 $$PID 2>/dev/null || break; \
				sleep 1; \
			done; \
			kill -0 $$PID 2>/dev/null && kill -9 $$PID || true; \
			echo "Stopped PID $$PID"; \
		else \
			echo "Stale pid file, no process for PID $$PID"; \
		fi; \
		rm -f $(PID_FILE); \
	else \
		echo "Not running (no pid file)"; \
	fi

restart: stop start

status:
	@if [[ -f $(PID_FILE) ]] && kill -0 $$(cat $(PID_FILE)) 2>/dev/null; then \
		echo "Running -- PID $$(cat $(PID_FILE)) on $(PROXY_HOST):$(PROXY_PORT)"; \
	else \
		echo "Not running"; \
	fi

logs:
	@mkdir -p $(LOG_DIR)
	@tail -n 100 -F $(LOG_DIR)/*.log 2>/dev/null || true

test:
	@echo "--> GET /api/version"
	@curl -s http://$(PROXY_HOST):$(PROXY_PORT)/api/version && echo
	@echo "--> GET /api/tags"
	@curl -s http://$(PROXY_HOST):$(PROXY_PORT)/api/tags && echo
	@echo "--> GET /health"
	@curl -s http://$(PROXY_HOST):$(PROXY_PORT)/health && echo
	@echo "--> GET /v1/models"
	@curl -s http://$(PROXY_HOST):$(PROXY_PORT)/v1/models && echo
	@echo "--> POST /api/chat (stream=false)"
	@curl -s -X POST http://$(PROXY_HOST):$(PROXY_PORT)/api/chat \
		-H "Content-Type: application/json" \
		-d '{"model":"claude-opus-4-6","messages":[{"role":"user","content":"ping"}],"stream":false}' && echo

clean:
	rm -rf $(LOG_DIR) $(RUN_DIR)
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +

clean-venv:
	rm -rf $(VENV)
