"""应用配置：从环境变量加载。"""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # OpenAI / VLM 模型配置
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # YOLO 模型
    yolo_model_path: str = "models/yolo_customs_doc.pt"

    # 服务器
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    # 路径
    output_dir: str = "output"
    upload_dir: str = "uploads"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

    def ensure_dirs(self) -> None:
        """确保必要的目录存在，不存在则创建。"""
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        Path(self.upload_dir).mkdir(parents=True, exist_ok=True)
        Path(self.yolo_model_path).parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
