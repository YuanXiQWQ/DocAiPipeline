"""扫描仪路由：列出可用设备、执行扫描、返回图像文件。

仅在 Windows 桌面模式下可用，通过 WIA (Windows Image Acquisition) COM 接口
与扫描仪/多功能一体机通信。非 Windows 环境下所有端点返回 available=false。
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

from app.config import settings

router = APIRouter(prefix="/api/scan", tags=["扫描仪"])

# WIA FormatID 常量
_WIA_FORMAT_PNG = "{B96B3CAF-0728-11D3-9D7B-0000F81EF32E}"
_WIA_FORMAT_BMP = "{B96B3CAB-0728-11D3-9D7B-0000F81EF32E}"


# ------------------------------------------------------------------
# 数据模型
# ------------------------------------------------------------------


class ScannerDevice(BaseModel):
    device_id: str
    name: str


class DevicesResponse(BaseModel):
    available: bool
    devices: list[ScannerDevice] = []


class ScanResult(BaseModel):
    filename: str
    path: str


# ------------------------------------------------------------------
# WIA 工具函数
# ------------------------------------------------------------------


def _wia_available() -> bool:
    """检测 WIA COM 是否可用（仅 Windows）。"""
    try:
        import comtypes.client  # noqa: F401
        return True
    except ImportError:
        return False


def _list_wia_devices() -> list[ScannerDevice]:
    """通过 WIA COM 枚举已连接的扫描仪设备。"""
    try:
        import comtypes.client
        wia = comtypes.client.CreateObject("WIA.DeviceManager")
        devices: list[ScannerDevice] = []
        for i in range(1, wia.DeviceInfos.Count + 1):
            info = wia.DeviceInfos.Item(i)
            # Type == 1 表示扫描仪
            if info.Type == 1:
                devices.append(ScannerDevice(
                    device_id=info.DeviceID,
                    name=info.Properties("Name").Value,
                ))
        return devices
    except Exception as e:
        logger.warning(f"WIA 设备枚举失败: {e}")
        return []


def _scan_image(device_id: str) -> Path:
    """调用指定扫描仪执行扫描，返回保存的图像文件路径。"""
    import comtypes.client

    wia = comtypes.client.CreateObject("WIA.DeviceManager")

    # 查找目标设备
    target_info = None
    for i in range(1, wia.DeviceInfos.Count + 1):
        info = wia.DeviceInfos.Item(i)
        if info.DeviceID == device_id:
            target_info = info
            break

    if target_info is None:
        raise HTTPException(status_code=404, detail="扫描仪设备未找到")

    try:
        device = target_info.Connect()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"无法连接扫描仪: {e}")

    # 获取第一个扫描项（平板或 ADF）
    item = device.Items(1)

    # 执行扫描 — 返回 ImageFile COM 对象
    try:
        image = item.Transfer(_WIA_FORMAT_PNG)
    except Exception:
        # 某些扫描仪不支持 PNG，回退 BMP
        try:
            image = item.Transfer(_WIA_FORMAT_BMP)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"扫描失败: {e}")

    # 保存到 upload 目录
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    fname = f"scan_{uuid.uuid4().hex[:8]}.png"
    dest = upload_dir / fname

    image.SaveFile(str(dest))
    logger.info(f"扫描完成，图像已保存: {dest}")
    return dest


# ------------------------------------------------------------------
# API 端点
# ------------------------------------------------------------------


@router.get("/devices", response_model=DevicesResponse)
async def list_devices():
    """列出可用的扫描仪设备。非 Windows 环境返回 available=false。"""
    if not _wia_available():
        return DevicesResponse(available=False)
    devices = _list_wia_devices()
    return DevicesResponse(available=True, devices=devices)


@router.get("/file/{filename}")
async def get_scan_file(filename: str):
    """获取扫描生成的图像文件。"""
    from fastapi.responses import FileResponse

    fpath = Path(settings.upload_dir) / filename
    if not fpath.exists() or not fpath.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(str(fpath))


@router.post("/acquire", response_model=ScanResult)
async def acquire(device_id: str = ""):
    """执行扫描并返回图像文件信息。

    如果不指定 device_id，自动使用第一个可用设备。
    """
    if not _wia_available():
        raise HTTPException(status_code=501, detail="扫描仪功能仅在 Windows 桌面模式下可用")

    if not device_id:
        devices = _list_wia_devices()
        if not devices:
            raise HTTPException(status_code=404, detail="未检测到扫描仪设备")
        device_id = devices[0].device_id

    dest = _scan_image(device_id)
    return ScanResult(filename=dest.name, path=str(dest))
