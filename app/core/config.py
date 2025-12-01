"""
Configuration settings for the Background Remover API
"""

from pydantic import Field
from pydantic_settings import BaseSettings
from typing import List, Optional
import os


class Settings(BaseSettings):
    """Application settings"""

    # Environment
    ENVIRONMENT: str = Field(
        default="production", description="Environment (development, production)"
    )
    DEBUG: bool = Field(default=False, description="Debug mode")

    # API Configuration
    API_HOST: str = Field(default="0.0.0.0", description="API host")
    API_PORT: int = Field(default=8000, description="API port")
    ALLOWED_ORIGINS: List[str] = Field(
        default=["*"], description="Allowed CORS origins"
    )

    # Authentication
    API_KEY: Optional[str] = Field(
        default=None, description="API key for authentication"
    )

    # File Upload Limits
    MAX_FILE_SIZE: int = Field(
        default=10 * 1024 * 1024, description="Maximum file size in bytes"  # 10MB
    )
    MAX_FILES_BATCH: int = Field(
        default=5, description="Maximum files in batch processing"
    )
    ALLOWED_EXTENSIONS: List[str] = Field(
        default=["jpg", "jpeg", "png", "webp", "bmp"],
        description="Allowed image file extensions",
    )

    # REMBG Model Configuration
    REMBG_MODEL: str = Field(
        default="isnet-general-use",
        description="REMBG model name (u2net, u2net_human_seg, silueta, etc.)",
    )
    MODEL_CACHE_DIR: Optional[str] = Field(
        default=None, description="Directory to cache downloaded models"
    )
    MODEL_IDLE_TIMEOUT: int = Field(
        default=60,
        description="Model idle timeout in seconds (unload after inactivity)",
    )

    MAX_CONCURRENT_REQUESTS: int = Field(
        default=4, description="Maximum concurrent background removal requests"
    )
    REQUEST_TIMEOUT: int = Field(default=30, description="Request timeout in seconds")

    # Output Configuration
    DEFAULT_OUTPUT_FORMAT: str = Field(
        default="PNG", description="Default output format (PNG, JPEG, WEBP)"
    )
    OUTPUT_QUALITY: int = Field(
        default=95, description="Output quality for JPEG/WEBP (1-100)"
    )

    # Logging
    LOG_LEVEL: str = Field(
        default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR)"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Set model cache directory if not specified
        if not self.MODEL_CACHE_DIR:
            self.MODEL_CACHE_DIR = os.path.join(os.getcwd(), ".model_cache")

        # Ensure cache directory exists
        os.makedirs(self.MODEL_CACHE_DIR, exist_ok=True)


# Global settings instance
settings = Settings()
