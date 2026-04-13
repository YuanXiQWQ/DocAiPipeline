"""FastAPI 应用入口点。

统一 API 路由：
- /health — 健康检查
- /api/classify — VLM 文档分类
- /api/process — 统一文档处理（自动/手动分类 → 识别）
- /api/fill — Excel 填充
- /api/templates — 模板管理
- /api/download — 文件下载
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
from fastapi.responses import FileResponse
from loguru import logger

from app.config import settings
from app.pipeline import Pipeline
from app.routers import fill, process
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
    logger.info("DocAI Pipeline service started")
    logger.info(f"Output dir: {settings.output_dir}")
    logger.info(f"VLM model: {settings.openai_model}")
    yield


app = FastAPI(
    title="DocAI Pipeline",
    description="报关单自动识别与智能归档系统 — AI Service",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS（允许前端跨域访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(process.router)
app.include_router(fill.router)


# ------------------------------------------------------------------
# 基础端点
# ------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查。"""
    return HealthResponse()


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=settings.debug)
