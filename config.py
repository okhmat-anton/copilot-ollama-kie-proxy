import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration from environment variables"""
    
    # KIE.AI API Configuration
    kie_ai_api_key: str = ""
    kie_ai_api_url: str = "https://api.kie.ai/v1"
    
    # Proxy Service Configuration
    proxy_host: str = "127.0.0.1"
    proxy_port: int = 11434
    
    # Logging Configuration
    log_level: str = "INFO"
    log_dir: str = "./logs"
    
    # Model Configuration
    default_model: str = "claude-opus-4-6"
    
    class Config:
        env_file = ".env"
        case_sensitive = False
    
    def __post_init__(self):
        """Ensure log directory exists"""
        Path(self.log_dir).mkdir(parents=True, exist_ok=True)


settings = Settings()
