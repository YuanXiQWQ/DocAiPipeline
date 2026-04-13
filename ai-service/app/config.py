"""Application configuration loaded from environment variables."""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # OpenAI / VLM
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # YOLO
    yolo_model_path: str = "models/yolo_customs_doc.pt"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    # Paths
    output_dir: str = "output"
    upload_dir: str = "uploads"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

    def ensure_dirs(self) -> None:
        """Create necessary directories if they don't exist."""
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        Path(self.upload_dir).mkdir(parents=True, exist_ok=True)
        Path(self.yolo_model_path).parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
