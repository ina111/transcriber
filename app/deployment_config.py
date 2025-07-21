"""
Deployment-aware configuration for different environments.
Handles configuration differences between local, Vercel, and other deployments.
"""

import os
from pathlib import Path
from typing import Dict, Any


def is_serverless_environment() -> bool:
    """Check if running in a serverless environment."""
    return bool(os.getenv("VERCEL_ENV") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))


def is_vercel_environment() -> bool:
    """Check if running in Vercel."""
    return bool(os.getenv("VERCEL_ENV"))


def get_temp_directory() -> str:
    """Get appropriate temp directory for the environment."""
    if is_serverless_environment():
        return "/tmp"
    else:
        # Local development
        return os.getenv("TEMP_DIR", "./temp")


def get_output_directory() -> str:
    """Get appropriate output directory for the environment."""
    if is_serverless_environment():
        # In serverless, we don't save files permanently
        return "/tmp"
    else:
        # Local development
        return os.getenv("OUTPUT_DIR", "./output")


def get_deployment_config() -> Dict[str, Any]:
    """Get deployment-specific configuration."""
    base_config = {
        "is_serverless": is_serverless_environment(),
        "is_vercel": is_vercel_environment(),
        "temp_dir": get_temp_directory(),
        "output_dir": get_output_directory(),
        "max_file_size": 50 * 1024 * 1024,  # 50MB for serverless
    }
    
    if is_vercel_environment():
        base_config.update({
            "max_duration": 300,  # 5 minutes
            "max_memory": 3008,   # MB
            "environment": "production",
        })
    else:
        base_config.update({
            "max_duration": 1800,  # 30 minutes for local
            "max_memory": 8192,    # MB
            "environment": "development",
        })
    
    return base_config


def ensure_directories():
    """Ensure required directories exist."""
    config = get_deployment_config()
    
    # Create temp directory if it doesn't exist and we're not in serverless
    temp_dir = Path(config["temp_dir"])
    if not is_serverless_environment() and not temp_dir.exists():
        temp_dir.mkdir(parents=True, exist_ok=True)
    
    # Create output directory if it doesn't exist and we're not in serverless
    output_dir = Path(config["output_dir"])
    if not is_serverless_environment() and not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)


def get_ffmpeg_path() -> str:
    """Get ffmpeg path for the environment."""
    if is_vercel_environment():
        # Try common paths for ffmpeg in Vercel
        possible_paths = [
            "/opt/ffmpeg/bin/ffmpeg",
            "/usr/bin/ffmpeg",
            "/usr/local/bin/ffmpeg"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        # If not found, return None to indicate ffmpeg is not available
        return None
    else:
        # Local development - assume ffmpeg is in PATH
        return "ffmpeg"


def handle_serverless_limitations(file_size: int) -> None:
    """Check if file size exceeds serverless limitations."""
    config = get_deployment_config()
    
    if config["is_serverless"] and file_size > config["max_file_size"]:
        raise ValueError(
            f"File size ({file_size / 1024 / 1024:.1f}MB) exceeds "
            f"serverless limit ({config['max_file_size'] / 1024 / 1024:.1f}MB)"
        )