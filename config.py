import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()


class Settings:
    """Application configuration from environment variables"""
    
    def __init__(self):
        # KIE.AI API Configuration
        self.kie_ai_api_key = os.getenv("KIE_AI_API_KEY", "")
        self.kie_ai_api_url = os.getenv("KIE_AI_API_URL", "https://api.kie.ai/v1")
        
        # Proxy Service Configuration
        self.proxy_host = os.getenv("PROXY_HOST", "127.0.0.1")
        self.proxy_port = int(os.getenv("PROXY_PORT", "11434"))
        
        # Logging Configuration
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.log_dir = os.getenv("LOG_DIR", "./logs")
        
        # Model Configuration
        self.default_model = os.getenv("DEFAULT_MODEL", "claude-opus-4-6")
        # Ollama compatibility version returned by /api/version
        self.ollama_compat_version = os.getenv("OLLAMA_COMPAT_VERSION", "0.8.0")
        
        # Ensure log directory exists
        Path(self.log_dir).mkdir(parents=True, exist_ok=True)


settings = Settings()
