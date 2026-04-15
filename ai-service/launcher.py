"""DocAI Pipeline 桌面启动器。

功能：
1. 启动 FastAPI 后端（内嵌前端静态文件）
2. 自动打开浏览器
3. 系统托盘图标（右键退出）
4. 关闭托盘时优雅停止服务

用法：
- 开发模式：python launcher.py
- 打包后：DocAI-Pipeline.exe（PyInstaller 单文件）
"""

from __future__ import annotations

import os
import sys
import socket
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

import uvicorn
from loguru import logger


# ------------------------------------------------------------------
# 常量
# ------------------------------------------------------------------

APP_NAME = "DocAI Pipeline"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
ICON_FILE = "icon.ico"

# ------------------------------------------------------------------
# 工具函数
# ------------------------------------------------------------------


def _find_free_port(start: int = DEFAULT_PORT, max_try: int = 20) -> int:
    """从 start 开始查找可用端口。"""
    for offset in range(max_try):
        port = start + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((DEFAULT_HOST, port))
                return port
            except OSError:
                continue
    return start


def _wait_for_server(host: str, port: int, timeout: float = 30.0) -> bool:
    """等待服务器就绪。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def _base_dir() -> Path:
    """获取应用根目录（兼容 PyInstaller 打包后的临时目录）。"""
    if getattr(sys, "frozen", False):
        # PyInstaller 打包后，_MEIPASS 是解压临时目录
        return Path(getattr(sys, "_MEIPASS"))  # PyInstaller 打包后的临时目录
    return Path(__file__).resolve().parent


# ------------------------------------------------------------------
# 托盘图标（可选，pystray 不可用时降级为控制台模式）
# ------------------------------------------------------------------


def _run_tray(host: str, port: int, shutdown_event: threading.Event) -> None:
    """运行系统托盘图标。需要 pystray 和 Pillow。"""
    try:
        import pystray
        from PIL import Image
    except ImportError:
        logger.warning("pystray/Pillow 未安装，跳过系统托盘（使用 Ctrl+C 退出）")
        return

    # noinspection HttpUrlsUsage
    url = f"http://{host}:{port}"  # noqa: S310 — localhost 不需要 HTTPS

    # 加载图标
    icon_path = _base_dir() / ICON_FILE
    if icon_path.exists():
        image = Image.open(str(icon_path))
    else:
        # 生成一个简单的绿色方块作为默认图标
        image = Image.new("RGB", (64, 64), color=(16, 185, 129))

    def on_open(_icon: Any, _item: Any) -> None:
        webbrowser.open(url)

    def on_quit(_icon: Any, _item: Any) -> None:
        shutdown_event.set()
        _icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(f"打开 {APP_NAME}", on_open, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", on_quit),
    )

    icon = pystray.Icon(APP_NAME, image, APP_NAME, menu)
    logger.info("系统托盘图标已启动")
    icon.run()  # 阻塞，直到 icon.stop()


# ------------------------------------------------------------------
# 主流程
# ------------------------------------------------------------------


def main() -> None:
    # 设置工作目录为 ai-service 根（确保 .env / user_settings.json 可被找到）
    base = _base_dir()
    os.chdir(base)

    # 查找可用端口
    port = _find_free_port(DEFAULT_PORT)
    host = DEFAULT_HOST
    # noinspection HttpUrlsUsage
    url = f"http://{host}:{port}"  # noqa: S310 — localhost 不需要 HTTPS

    logger.info(f"{APP_NAME} 正在启动…")
    logger.info(f"工作目录: {base}")
    logger.info(f"服务地址: {url}")

    # 关闭信号
    shutdown_event = threading.Event()

    # 启动 uvicorn（在子线程中）
    config = uvicorn.Config(
        "app.main:app",
        host=host,
        port=port,
        log_level="info",
        # 桌面模式关闭 reload，避免文件监控问题
        reload=False,
    )
    server = uvicorn.Server(config)

    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    # 等待服务就绪后打开浏览器
    if _wait_for_server(host, port):
        logger.info(f"服务已就绪，正在打开浏览器: {url}")
        webbrowser.open(url)
    else:
        logger.error("服务启动超时！")

    # 启动系统托盘（阻塞主线程直到退出）
    tray_thread = threading.Thread(target=_run_tray, args=(host, port, shutdown_event), daemon=True)
    tray_thread.start()

    # 等待退出信号（托盘退出或 Ctrl+C）
    try:
        while not shutdown_event.is_set():
            shutdown_event.wait(timeout=1.0)
    except KeyboardInterrupt:
        logger.info("收到 Ctrl+C，正在关闭…")
        shutdown_event.set()

    # 优雅关闭 uvicorn
    logger.info("正在停止服务…")
    server.should_exit = True
    server_thread.join(timeout=5)
    logger.info(f"{APP_NAME} 已退出")


if __name__ == "__main__":
    main()
