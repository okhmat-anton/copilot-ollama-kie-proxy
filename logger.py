import logging
import os
from datetime import datetime
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from config import settings


def setup_logger(name: str, log_type: str = "general") -> logging.Logger:
    """
    Setup logger with monthly rotation for different log types.
    
    Args:
        name: Logger name (usually __name__)
        log_type: Type of log - "general", "errors", or "requests"
    
    Returns:
        Configured logger instance
    """
    
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, settings.log_level))
    
    # Create logs directory if it doesn't exist
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Define log file paths with monthly rotation
    current_year_month = datetime.now().strftime("%Y-%m")
    
    if log_type == "errors":
        log_file = log_dir / f"errors_{current_year_month}.log"
    elif log_type == "requests":
        log_file = log_dir / f"requests_{current_year_month}.log"
    else:
        log_file = log_dir / f"general_{current_year_month}.log"
    
    # Create file handler with rotation at midnight (monthly)
    handler = TimedRotatingFileHandler(
        str(log_file),
        when="midnight",
        interval=1,
        backupCount=12,  # Keep 12 months of logs
        encoding="utf-8"
    )
    
    # Create console handler for INFO and above
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # Create formatters
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_formatter = logging.Formatter(
        '%(levelname)s - %(message)s'
    )
    
    # Add formatters to handlers
    handler.setFormatter(file_formatter)
    console_handler.setFormatter(console_formatter)
    
    # Add handlers to logger
    if not logger.handlers:
        logger.addHandler(handler)
        logger.addHandler(console_handler)
    
    return logger


# Create specialized loggers
error_logger = setup_logger("ollama_proxy.errors", "errors")
request_logger = setup_logger("ollama_proxy.requests", "requests")
general_logger = setup_logger("ollama_proxy.general", "general")
