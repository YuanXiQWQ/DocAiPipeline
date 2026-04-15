"""应用配置：从环境变量 → .env → 用户设置 JSON 加载。

优先级：用户设置 JSON > 环境变量 > .env > 默认值
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic_settings import BaseSettings

# 用户设置文件路径
_USER_SETTINGS_FILE = Path("user_settings.json")

# 支持的模型列表（前端设置页面展示用）
AVAILABLE_MODELS = [
    {
        "id": "gpt-4.1-mini",
        "name": "GPT-4.1 Mini",
        "provider": "OpenAI",
        "pricing_url": "https://platform.openai.com/docs/pricing",
        "description": "高性价比，推荐用于日常文档处理",
    },
    {
        "id": "gpt-4.1",
        "name": "GPT-4.1",
        "provider": "OpenAI",
        "pricing_url": "https://platform.openai.com/docs/pricing",
        "description": "最高精度，适合复杂手写识别",
    },
    {
        "id": "gpt-4o",
        "name": "GPT-4o",
        "provider": "OpenAI",
        "pricing_url": "https://platform.openai.com/docs/pricing",
        "description": "多模态旗舰模型",
    },
    {
        "id": "gpt-4o-mini",
        "name": "GPT-4o Mini",
        "provider": "OpenAI",
        "pricing_url": "https://platform.openai.com/docs/pricing",
        "description": "轻量多模态，成本最低",
    },
]


class Settings(BaseSettings):
    # OpenAI / VLM 模型配置
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_base_url: str = ""

    # YOLO 模型
    yolo_model_path: str = "models/yolo_customs_doc.pt"

    # 服务器
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    # 路径
    output_dir: str = "output"
    upload_dir: str = "uploads"

    # 语言（预留多语言支持）
    language: str = "zh-CN"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

    def ensure_dirs(self) -> None:
        """确保必要的目录存在，不存在则创建。"""
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        Path(self.upload_dir).mkdir(parents=True, exist_ok=True)
        Path(self.yolo_model_path).parent.mkdir(parents=True, exist_ok=True)

    def load_user_settings(self) -> None:
        """从 user_settings.json 加载用户配置覆盖当前值。"""
        if not _USER_SETTINGS_FILE.exists():
            return
        try:
            data = json.loads(_USER_SETTINGS_FILE.read_text("utf-8"))
            # 只覆盖用户可配置的字段
            for key in ("openai_api_key", "openai_model", "openai_base_url", "language"):
                if key in data and data[key]:
                    setattr(self, key, data[key])
        except (json.JSONDecodeError, OSError):
            pass

    def save_user_settings(self, data: dict[str, str]) -> None:
        """保存用户配置到 user_settings.json。"""
        # 读取现有配置
        existing: dict[str, str] = {}
        if _USER_SETTINGS_FILE.exists():
            try:
                existing = json.loads(_USER_SETTINGS_FILE.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        # 合并更新
        for key in ("openai_api_key", "openai_model", "openai_base_url", "language"):
            if key in data:
                existing[key] = data[key]
                setattr(self, key, data[key])
        _USER_SETTINGS_FILE.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_user_settings(self) -> dict[str, str]:
        """返回用户可配置的当前值（隐藏 API Key 中间部分）。"""
        key = self.openai_api_key
        if len(key) > 12:
            masked = key[:6] + "***" + key[-4:]
        elif key:
            masked = "***"
        else:
            masked = ""
        return {
            "openai_api_key_masked": masked,
            "openai_api_key_set": bool(key),
            "openai_model": self.openai_model,
            "openai_base_url": self.openai_base_url,
            "language": self.language,
        }


settings = Settings()
settings.load_user_settings()
