"""DocAI Pipeline 桌面启动器。

功能：
1. 启动 FastAPI 后端（内嵌前端静态文件）
2. 在 pywebview 原生窗口中显示前端界面
3. 系统托盘图标（右键退出）
4. 关闭窗口/托盘时优雅停止服务

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
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 860


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
    """获取应用根目录（兼容 PyInstaller onedir/onefile 模式）。

    - onedir 模式：_MEIPASS == exe 所在目录
    - onefile 模式：_MEIPASS == 临时解压目录
    - 开发模式：脚本所在目录
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


# ------------------------------------------------------------------
# 托盘图标（可选，pystray 不可用时降级为控制台模式）
# ------------------------------------------------------------------


def _run_tray(
        host: str,
        port: int,
        shutdown_event: threading.Event,
        webview_window: Any | None = None,
) -> None:
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
        # 如果有 webview 窗口，尝试显示它；否则打开浏览器
        if webview_window is not None:
            # noinspection PyBroadException
            try:
                webview_window.show()  # type: ignore[union-attr]
                return
            except Exception:
                pass
        webbrowser.open(url)

    def on_quit(_icon: Any, _item: Any) -> None:
        shutdown_event.set()
        _icon.stop()
        # 关闭 webview 窗口
        if webview_window is not None:
            # noinspection PyBroadException
            try:
                webview_window.destroy()  # type: ignore[union-attr]
            except Exception:
                pass

    menu = pystray.Menu(
        pystray.MenuItem(f"打开 {APP_NAME}", on_open, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", on_quit),
    )

    icon = pystray.Icon(APP_NAME, image, APP_NAME, menu)
    logger.info("系统托盘图标已启动")
    icon.run()  # 阻塞，直到 icon.stop()


# ------------------------------------------------------------------
# 桌面偏好（关闭行为 / 窗口尺寸）
# ------------------------------------------------------------------

_PREFS_FILE = "desktop_prefs.json"


def _load_prefs() -> dict:
    """读取桌面偏好设置。"""
    import json
    p = Path(_PREFS_FILE)
    if p.exists():
        try:
            return json.loads(p.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


# ------------------------------------------------------------------
# Splash 闪屏窗口（tkinter，无额外依赖）
# ------------------------------------------------------------------

_splash_state: dict[str, Any] = {}  # 保持 tkinter 对象引用防止 GC


def _show_splash(base: Path) -> tuple[Any, Any]:
    """显示启动闪屏窗口，返回 (root, destroy_fn)。"""
    try:
        import tkinter as tk
    except ImportError:
        return None, lambda: None

    root = tk.Tk()
    root.overrideredirect(True)  # 无标题栏
    root.attributes("-topmost", True)

    # 窗口尺寸与居中
    sw, sh = 420, 260
    x = (root.winfo_screenwidth() - sw) // 2
    y = (root.winfo_screenheight() - sh) // 2
    root.geometry(f"{sw}x{sh}+{x}+{y}")

    # 背景：渐变蓝色（用 Canvas 模拟）
    canvas = tk.Canvas(root, width=sw, height=sh, highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    # 绘制渐变背景（从深蓝到浅蓝）
    for i in range(sh):
        ratio = i / sh
        r = int(30 + 190 * ratio)
        g = int(64 + 160 * ratio)
        b = int(175 + 60 * ratio)
        color = f"#{r:02x}{g:02x}{b:02x}"
        canvas.create_line(0, i, sw, i, fill=color)

    # 尝试加载图标
    icon_path = base / "icon.ico"
    photo = None
    if icon_path.exists():
        try:
            from PIL import Image, ImageTk
            img = Image.open(str(icon_path))
            img = img.resize((64, 64), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            canvas.create_image(sw // 2, 70, image=photo)
        except (ImportError, OSError, ValueError):  # Pillow/tkinter 异常
            pass

    # 应用名称
    canvas.create_text(sw // 2, 130, text=APP_NAME,
                       font=("Segoe UI", 22, "bold"), fill="white")
    # 作者
    canvas.create_text(sw // 2, 165, text="by YuanXiQWQ",
                       font=("Segoe UI", 11), fill="#d0e0f0")
    # 加载提示
    _loading_text = canvas.create_text(
        sw // 2, 220, text="正在启动服务…",
        font=("Segoe UI", 9), fill="#c0d8f0")

    # 保持引用防止被 GC，用 dict 避免访问 protected 成员
    _splash_state["photo"] = photo
    _splash_state["loading_text_id"] = _loading_text
    _splash_state["canvas"] = canvas

    root.update()
    return root, lambda: root.destroy()


def _update_splash_text(root: Any, text: str) -> None:
    """更新闪屏窗口的加载提示文字。"""
    canvas = _splash_state.get("canvas")
    text_id = _splash_state.get("loading_text_id")
    if canvas is None or text_id is None:
        return
    try:
        canvas.itemconfig(text_id, text=text)  # type: ignore[union-attr]
        root.update()
    except (AttributeError, RuntimeError):
        pass


# ------------------------------------------------------------------
# 启动时应用已下载的更新
# ------------------------------------------------------------------

_UPDATE_STAGING = "update_staging"


def _apply_pending_update(base: Path) -> None:
    """如果 update_staging/extracted/ 存在，将其内容覆盖到应用目录。

    覆盖时跳过用户数据文件（*.db, *.json 配置等）。
    """
    import shutil as _shutil

    staging = base / _UPDATE_STAGING / "extracted"
    if not staging.exists():
        return

    logger.info(f"检测到待应用的更新: {staging}")

    # extracted/ 下可能有一层子目录（如 DocAI-Pipeline/）
    children = list(staging.iterdir())
    src = children[0] if len(children) == 1 and children[0].is_dir() else staging

    # 保护列表：不覆盖用户数据
    _protected = {"user_settings.json", "desktop_prefs.json", "output", "update_staging"}

    try:
        for item in src.iterdir():
            if item.name in _protected:
                continue
            dest = base / item.name
            if item.is_dir():
                if dest.exists():
                    _shutil.rmtree(dest)
                _shutil.copytree(str(item), str(dest))
            else:
                _shutil.copy2(str(item), str(dest))
        logger.info("更新文件已覆盖到应用目录")
    except (OSError, PermissionError) as e:
        logger.error(f"应用更新失败: {e}")

    # 清理 staging
    try:
        _shutil.rmtree(str(base / _UPDATE_STAGING))
    except OSError:
        pass


# ------------------------------------------------------------------
# 启动时自动检测更新
# ------------------------------------------------------------------


def _auto_check_and_download(host: str, port: int) -> None:
    """在后台线程中检测并下载更新。"""
    import urllib.error
    import urllib.request
    import json as _json
    try:
        # 等一下让服务完全启动
        time.sleep(3)
        # noinspection HttpUrlsUsage
        url = f"http://{host}:{port}/api/update/download"  # noqa: S310
        req = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
            result = _json.loads(resp.read())
            logger.info(f"自动更新检测: {result.get('message', '')}")
    except (OSError, urllib.error.URLError, ValueError) as e:
        logger.debug(f"自动更新检测失败: {e}")


# ------------------------------------------------------------------
# 主流程
# ------------------------------------------------------------------


def main() -> None:
    # PyInstaller console=False 模式下 sys.stdout/stderr 为 None，
    # uvicorn 的日志 formatter 会调用 stream.isatty() 导致 AttributeError。
    # 将 None 流替换为 devnull 以避免崩溃。
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115

    # 设置工作目录为 ai-service 根（确保 .env / user_settings.json 可被找到）
    base = _base_dir()
    os.chdir(base)

    # 应用上次下载好的更新（覆盖文件）
    _apply_pending_update(base)

    # 显示 Splash 闪屏
    splash_root, splash_destroy = _show_splash(base)

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

    # 读取桌面偏好
    prefs = _load_prefs()
    win_w = prefs.get("window_width", WINDOW_WIDTH)
    win_h = prefs.get("window_height", WINDOW_HEIGHT)

    # 启动 uvicorn（在子线程中）
    if splash_root:
        _update_splash_text(splash_root, "正在启动后端服务…")

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

    # 等待服务就绪
    if splash_root:
        _update_splash_text(splash_root, "正在加载模型…")

    if not _wait_for_server(host, port):
        logger.error("服务启动超时！")
        splash_destroy()
        return

    logger.info(f"服务已就绪: {url}")

    if splash_root:
        _update_splash_text(splash_root, "正在打开应用窗口…")

    # 尝试导入 pywebview
    try:
        import webview as _webview  # pywebview
        _has_webview = True
    except ImportError:
        _webview = None  # type: ignore[assignment]
        _has_webview = False

    # 关闭 Splash（主窗口即将出现）
    splash_destroy()

    # 自动更新（用户启用时，后台静默检测+下载）
    if prefs.get("auto_update", False):
        update_thread = threading.Thread(
            target=_auto_check_and_download,
            args=(host, port),
            daemon=True,
        )
        update_thread.start()

    if _has_webview:
        # pywebview 原生窗口模式
        assert _webview is not None
        _wv_window = _webview.create_window(
            APP_NAME,
            url,
            width=win_w,
            height=win_h,
            min_size=(800, 600),
            confirm_close=True,  # 允许 closing 事件取消关闭
        )

        def _on_closing() -> bool:
            """窗口关闭事件：根据用户偏好决定最小化还是退出。"""
            # 每次关闭时重新读取偏好（用户可能刚改过）
            _cb = _load_prefs().get("close_behavior", "minimize_to_tray")
            if _cb == "minimize_to_tray":
                assert _wv_window is not None
                _wv_window.hide()
            else:
                # exit 模式：直接销毁窗口
                shutdown_event.set()
                assert _wv_window is not None
                _wv_window.destroy()
            return False  # 始终取消默认确认对话框

        def _on_closed() -> None:
            """窗口真正关闭后触发。"""
            shutdown_event.set()

        assert _wv_window is not None
        _wv_window.events.closing += _on_closing
        _wv_window.events.closed += _on_closed

        # 启动托盘（后台线程）
        tray_thread = threading.Thread(
            target=_run_tray,
            args=(host, port, shutdown_event, _wv_window),
            daemon=True,
        )
        tray_thread.start()

        # webview.start() 会阻塞主线程直到窗口关闭
        # Windows 上优先使用 EdgeChromium（系统自带 WebView2）
        logger.info("正在打开应用窗口…")
        # noinspection PyBroadException
        try:
            _webview.start(gui="edgechromium")
        except Exception:
            # 若 edgechromium 不可用，尝试默认后端
            _webview.start()

    else:
        # 回退到浏览器模式
        logger.warning("pywebview 未安装，回退到浏览器模式")
        webbrowser.open(url)

        # 启动托盘（后台线程）
        tray_thread = threading.Thread(
            target=_run_tray,
            args=(host, port, shutdown_event),
            daemon=True,
        )
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
