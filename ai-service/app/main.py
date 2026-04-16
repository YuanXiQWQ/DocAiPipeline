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

import os
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


@app.post("/api/settings/test-key")
async def test_api_key(body: dict):
    """测试 API Key 是否有效，向 OpenAI 发送一个最小请求。

    请求体可选字段：
    - api_key: 要测试的 Key（为空则测试当前已保存的 Key）
    """
    import httpx

    key = (body.get("api_key") or "").strip() or settings.openai_api_key
    if not key:
        return {"ok": False, "code": "no_key", "message": "API Key 未设置"}

    base = (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
    url = f"{base}/models"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {key}"})

        if resp.status_code == 200:
            return {"ok": True, "code": "ok", "message": "API Key 有效"}
        elif resp.status_code == 401:
            return {"ok": False, "code": "invalid_key",
                    "message": "API Key 无效或已过期，请检查 Key 是否正确"}
        elif resp.status_code == 403:
            return {"ok": False, "code": "permission_denied",
                    "message": "API Key 权限不足，请确认 Key 的访问权限"}
        elif resp.status_code == 429:
            return {"ok": False, "code": "rate_limit",
                    "message": "请求过于频繁或账户额度已用完，请检查 OpenAI 账户余额"}
        else:
            return {"ok": False, "code": f"http_{resp.status_code}",
                    "message": f"API 返回异常状态码 {resp.status_code}"}
    except httpx.ConnectError:
        return {"ok": False, "code": "connect_error",
                "message": "无法连接到 API 服务器，请检查网络或 Base URL 设置"}
    except httpx.TimeoutException:
        return {"ok": False, "code": "timeout",
                "message": "连接超时，请检查网络连接或 Base URL 是否正确"}
    except Exception as e:
        return {"ok": False, "code": "unknown", "message": f"测试失败：{e}"}


# ------------------------------------------------------------------
# 平台检测（桌面 exe vs Web 部署）
# ------------------------------------------------------------------

APP_VERSION = app.version


def _is_desktop() -> bool:
    """是否以桌面模式运行（PyInstaller 打包 或 launcher.py 启动）。"""
    import sys
    return getattr(sys, "frozen", False) or os.environ.get("DOCAI_DESKTOP") == "1"


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
# 关闭行为与窗口控制（桌面专属）
# ------------------------------------------------------------------


@app.get("/api/close-behavior")
async def get_close_behavior():
    """获取关闭窗口时的行为（minimize_to_tray / exit）。"""
    data = _load_desktop_prefs()
    return {"behavior": data.get("close_behavior", "minimize_to_tray")}


@app.put("/api/close-behavior")
async def set_close_behavior(body: dict):
    """设置关闭窗口行为。"""
    behavior = body.get("behavior", "minimize_to_tray")
    if behavior not in ("minimize_to_tray", "exit"):
        raise HTTPException(status_code=400, detail="无效的关闭行为")
    data = _load_desktop_prefs()
    data["close_behavior"] = behavior
    _save_desktop_prefs(data)
    return {"behavior": behavior}


@app.post("/api/reset-window")
async def reset_window():
    """重置窗口大小为默认值。"""
    data = _load_desktop_prefs()
    data["window_width"] = 1280
    data["window_height"] = 860
    _save_desktop_prefs(data)
    return {"message": "窗口大小已重置，重启应用后生效"}


def _desktop_prefs_path() -> Path:
    return Path("desktop_prefs.json")


def _load_desktop_prefs() -> dict:
    import json
    p = _desktop_prefs_path()
    if p.exists():
        try:
            return json.loads(p.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_desktop_prefs(data: dict) -> None:
    import json
    _desktop_prefs_path().write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


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
                if latest_tag and _is_newer(latest_tag, APP_VERSION):
                    result["has_update"] = True
    except Exception as e:
        logger.warning(f"检查更新失败: {e}")
    return result


def _is_newer(latest: str, current: str) -> bool:
    """语义版本号比较，判断 latest 是否比 current 新。"""
    try:
        from packaging.version import Version
        return Version(latest) > Version(current)
    except (ImportError, ValueError, TypeError):
        pass
    # 回退简单元组比较
    def _parts(v: str) -> tuple[int, ...]:
        return tuple(int(x) for x in v.split(".") if x.isdigit())
    try:
        return _parts(latest) > _parts(current)
    except (ValueError, TypeError):
        return latest != current


# ------------------------------------------------------------------
# 自动更新（后台下载 + 重启时覆盖）
# ------------------------------------------------------------------

# 更新状态：idle / downloading / ready / error
_update_state: dict = {"status": "idle", "progress": 0, "message": "", "version": ""}
_UPDATE_DIR = "update_staging"


@app.get("/api/auto-update")
async def get_auto_update():
    """获取自动更新偏好。"""
    data = _load_desktop_prefs()
    return {"enabled": data.get("auto_update", False)}


@app.put("/api/auto-update")
async def set_auto_update(body: dict):
    """设置自动更新偏好。"""
    enabled = body.get("enabled", False)
    data = _load_desktop_prefs()
    data["auto_update"] = bool(enabled)
    _save_desktop_prefs(data)
    return {"enabled": data["auto_update"]}


@app.get("/api/update/status")
async def get_update_status():
    """获取当前更新状态。"""
    return _update_state.copy()


@app.post("/api/update/download")
async def trigger_update_download():
    """触发后台下载最新版本。"""
    import asyncio
    if _update_state["status"] == "downloading":
        return {"message": "正在下载中"}
    # 先检查是否有更新
    version_info = await check_version()
    if not version_info.get("has_update"):
        return {"message": "已是最新版本"}

    # 后台下载
    asyncio.create_task(_download_update())
    return {"message": "开始下载更新"}


async def _download_update() -> None:
    """后台下载最新 Release 的 zip 文件到 update_staging/。"""
    import httpx
    import zipfile

    _update_state["status"] = "downloading"
    _update_state["progress"] = 0
    _update_state["message"] = "正在获取更新信息…"
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            # 获取最新 Release
            resp = await client.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            if resp.status_code != 200:
                _update_state.update(status="error", message="获取 Release 信息失败")
                return
            data = resp.json()
            tag = data.get("tag_name", "").lstrip("v")
            _update_state["version"] = tag

            # 查找 zip 资产
            assets: list[dict] = data.get("assets", [])
            zip_asset: dict | None = next(
                (a for a in assets if str(a.get("name", "")).endswith(".zip")),
                None,
            )
            if zip_asset is None:
                _update_state.update(status="error", message="未找到可下载的 zip 文件")
                return

            download_url = str(zip_asset["browser_download_url"])
            total_size = int(zip_asset.get("size", 0))

            # 准备目录
            staging = Path(_UPDATE_DIR)
            staging.mkdir(parents=True, exist_ok=True)
            asset_name = str(zip_asset["name"])
            zip_path = staging / asset_name

            # 流式下载
            _update_state["message"] = f"正在下载 {asset_name}…"
            async with client.stream("GET", download_url) as stream:
                downloaded = 0
                with open(zip_path, "wb") as f:
                    async for chunk in stream.aiter_bytes(chunk_size=65536):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            _update_state["progress"] = int(downloaded * 100 / total_size)

            # 解压到 staging/extracted/
            extract_dir = staging / "extracted"
            if extract_dir.exists():
                shutil.rmtree(extract_dir)
            with zipfile.ZipFile(str(zip_path), "r") as zf:
                zf.extractall(str(extract_dir))
            zip_path.unlink()  # 删除 zip，只保留解压结果

            _update_state.update(
                status="ready",
                progress=100,
                message=f"更新 {tag} 已就绪，将在应用重启后生效",
            )
            logger.info(f"更新 {tag} 已下载就绪: {extract_dir}")
    except (OSError, httpx.HTTPError, zipfile.BadZipFile, KeyError) as e:
        logger.warning(f"下载更新失败: {e}")
        _update_state.update(status="error", message=f"下载失败: {e}")


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
