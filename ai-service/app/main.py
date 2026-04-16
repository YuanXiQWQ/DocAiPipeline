"""FastAPI 应用入口点。

统一 API 路由：
- /health — 健康检查
- /api/classify — VLM 文档分类
- /api/process — 统一文档处理（自动/手动分类 → 识别）
- /api/fill — Excel 填充
- /api/templates — 模板管理
- /api/download — 文件下载
- /api/history — 处理历史记录查询
- /api/history/stats — 历史数据统计
- /process — 兼容旧版进口单据端点
"""

from __future__ import annotations

import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.config import AVAILABLE_MODELS, settings
from app.db import init_db
from app.pipeline import Pipeline
from app.routers import fill, history_router, process, scanner, summary
from app.schemas import HealthResponse, PipelineResult

# 懒加载管线（模型较重）
_pipeline: Pipeline | None = None


def _get_pipeline() -> Pipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = Pipeline()
    assert _pipeline is not None
    return _pipeline


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """应用生命周期：启动时初始化目录与日志。"""
    settings.ensure_dirs()
    init_db()
    logger.info("DocAI Pipeline service started")
    logger.info(f"Output dir: {settings.output_dir}")
    logger.info(f"VLM model: {settings.openai_model}")
    yield


def _read_version() -> str:
    """从 VERSION 文件读取版本号（CI 构建时写入），开发模式回退 'dev'。"""
    import sys
    # PyInstaller onedir: _MEIPASS 就是 exe 所在目录
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent.parent  # ai-service/
    vf = base / "VERSION"
    if vf.exists():
        return vf.read_text(encoding="utf-8").strip()
    return "dev"


app = FastAPI(
    title="DocAI Pipeline",
    description="报关单自动识别与智能归档系统 — AI Service",
    version=_read_version(),
    lifespan=lifespan,
)

# CORS（允许前端跨域访问）
app.add_middleware(
    CORSMiddleware,  # type: ignore[arg-type]
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(process.router)
app.include_router(fill.router)
app.include_router(history_router.router)
app.include_router(summary.router)
app.include_router(scanner.router)


# ------------------------------------------------------------------
# 基础端点
# ------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查。"""
    return HealthResponse()


# ------------------------------------------------------------------
# 用户设置
# ------------------------------------------------------------------


@app.get("/api/settings")
async def get_settings():
    """获取当前用户设置（API Key 脱敏）和可用模型列表。"""
    return {
        "settings": settings.get_user_settings(),
        "available_models": AVAILABLE_MODELS,
    }


@app.put("/api/settings")
async def update_settings(body: dict):
    """更新用户设置。

    可更新字段：openai_api_key, openai_model, openai_base_url, language
    """
    settings.save_user_settings(body)
    logger.info(f"用户设置已更新: {list(body.keys())}")
    return {"message": "设置已保存", "settings": settings.get_user_settings()}


# ------------------------------------------------------------------
# 平台检测（桌面 exe vs Web 部署）
# ------------------------------------------------------------------

APP_VERSION = app.version


def _is_desktop() -> bool:
    """是否以 PyInstaller 打包的桌面模式运行。"""
    import sys
    return getattr(sys, "frozen", False)


@app.get("/api/platform")
async def get_platform():
    """返回当前运行模式，前端据此显示/隐藏桌面专属功能。"""
    return {
        "desktop": _is_desktop(),
        "version": APP_VERSION,
    }


# ------------------------------------------------------------------
# 开机自启（桌面专属）
# ------------------------------------------------------------------

# Windows 注册表路径
_AUTOSTART_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_AUTOSTART_APP_NAME = "DocAI-Pipeline"


def _get_exe_path() -> str | None:
    """获取当前可执行文件路径（仅 PyInstaller 打包后有效）。"""
    import sys

    if getattr(sys, "frozen", False):
        return sys.executable
    return None


def _is_autostart_enabled() -> bool:
    """检查是否已启用开机自启。"""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_REG_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, _AUTOSTART_APP_NAME)
            return True
    except (FileNotFoundError, OSError, ImportError):
        return False


def _set_autostart(enabled: bool) -> bool:
    """设置或移除开机自启注册表项。"""
    try:
        import winreg

        exe = _get_exe_path()
        if not exe and enabled:
            return False
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled and exe:
                winreg.SetValueEx(key, _AUTOSTART_APP_NAME, 0, winreg.REG_SZ, exe)
            else:
                try:
                    winreg.DeleteValue(key, _AUTOSTART_APP_NAME)
                except FileNotFoundError:
                    pass
        return True
    except (OSError, ImportError):
        return False


@app.get("/api/autostart")
async def get_autostart():
    """获取开机自启状态。"""
    return {"enabled": _is_autostart_enabled()}


@app.put("/api/autostart")
async def update_autostart(body: dict):
    """设置开机自启。"""
    enabled = body.get("enabled", False)
    ok = _set_autostart(enabled)
    if not ok and enabled:
        raise HTTPException(status_code=400, detail="仅桌面应用模式支持开机自启")
    return {"enabled": _is_autostart_enabled()}


# ------------------------------------------------------------------
# 版本与更新检查
# ------------------------------------------------------------------

GITHUB_REPO = "YuanXiQWQ/DocAiPipeline"


@app.get("/api/version")
async def check_version():
    """获取当前版本并检查 GitHub 最新 Release。"""
    import httpx

    result: dict = {"current": APP_VERSION, "has_update": False}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            if resp.status_code == 200:
                data = resp.json()
                latest_tag = data.get("tag_name", "").lstrip("v")
                result["latest"] = latest_tag
                result["release_url"] = data.get("html_url", "")
                if latest_tag and latest_tag != APP_VERSION:
                    result["has_update"] = True
    except Exception as e:
        logger.warning(f"检查更新失败: {e}")
    return result


# ------------------------------------------------------------------
# 兼容旧版端点（Phase 1 进口单据）
# ------------------------------------------------------------------


@app.post("/process", response_model=PipelineResult)
async def process_legacy(file: UploadFile = File(...)):
    """兼容旧版：上传 PDF → 进口单据管线处理。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix}. Accepted: PDF, JPG, PNG, TIFF",
        )

    settings.ensure_dirs()
    upload_id = uuid.uuid4().hex[:8]
    save_path = Path(settings.upload_dir) / f"{upload_id}_{file.filename}"
    with open(save_path, "wb") as buf:
        shutil.copyfileobj(file.file, buf)  # type: ignore[arg-type]

    logger.info(f"Received file: {file.filename} → {save_path}")

    try:
        pipeline = _get_pipeline()
        result = pipeline.process(save_path)
        return result
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/download/{filename}")
async def download_legacy(filename: str):
    """兼容旧版：下载导出文件。"""
    file_path = Path(settings.output_dir) / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    return FileResponse(path=str(file_path), filename=filename)


# ------------------------------------------------------------------
# 前端静态文件托管（桌面模式 / 生产构建）
# ------------------------------------------------------------------

# 查找前端构建产物目录（支持多种相对路径）
_FRONTEND_CANDIDATES = [
    Path(__file__).resolve().parent.parent / "web_dist",  # PyInstaller 打包后
    Path(__file__).resolve().parent.parent.parent / "web" / "dist",  # 开发目录
]
_frontend_dir: Path | None = None
for _candidate in _FRONTEND_CANDIDATES:
    if _candidate.is_dir() and (_candidate / "index.html").exists():
        _frontend_dir = _candidate
        break

if _frontend_dir is not None:
    # 挂载静态资源（JS/CSS/图片等）
    app.mount("/assets", StaticFiles(directory=str(_frontend_dir / "assets")), name="frontend-assets")
    # 挂载 public 下的静态文件（favicon 等）
    for _static_file in _frontend_dir.iterdir():
        if _static_file.is_file() and _static_file.name != "index.html":
            pass  # 由 SPA 回退路由处理

    # SPA 回退：所有未匹配的 GET 请求返回 index.html
    _index_html = (_frontend_dir / "index.html").read_text("utf-8")


    @app.get("/{path:path}", response_class=HTMLResponse, include_in_schema=False)
    async def _spa_fallback(path: str):
        """SPA 回退：将前端路由交给 index.html 处理。"""
        # 先检查是否是静态文件
        static_file = _frontend_dir / path  # type: ignore[operator]
        if static_file.is_file():
            return FileResponse(str(static_file))
        return HTMLResponse(_index_html)


    logger.info(f"前端静态文件已挂载: {_frontend_dir}")
else:
    logger.info("未找到前端构建产物，仅提供 API 服务（前端需单独启动）")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=settings.debug)
