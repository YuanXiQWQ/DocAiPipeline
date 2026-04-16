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
import socket
import sys
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
ICON_PNG = "icon.png"
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
        if _splash_cancelled():
            return False
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

_splash_state: dict[str, Any] = {"cancelled": False}  # 保持 tkinter 对象引用防止 GC


def _splash_cancelled() -> bool:
    """用户是否在闪屏阶段取消了启动。"""
    return bool(_splash_state.get("cancelled"))


def _show_splash(base: Path) -> tuple[Any, Any]:
    """显示启动闪屏窗口，返回 (root, destroy_fn)。"""
    try:
        import tkinter as tk
    except ImportError:
        return None, lambda: None

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)

    sw, sh = 620, 360
    x = (root.winfo_screenwidth() - sw) // 2
    y = (root.winfo_screenheight() - sh) // 2
    root.geometry(f"{sw}x{sh}+{x}+{y}")

    canvas = tk.Canvas(root, width=sw, height=sh, highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    # ── 背景渐变（浅薰衣草 → 淡紫白，整体偏浅） ──
    for i in range(sh):
        ratio = i / sh
        r = int(235 + 15 * ratio)   # eb → fa
        g = int(218 + 25 * ratio)   # da → f3
        b = int(250 + 5 * ratio)    # fa → ff
        canvas.create_line(0, i, sw, i, fill=f"#{r:02x}{g:02x}{b:02x}")

    # ── 直线几何装饰（对角色块） ──
    # 左上三角：淡紫色
    canvas.create_polygon(
        0, 0, sw * 0.45, 0, 0, sh * 0.55,
        fill="#e4d0f8", outline="",
    )
    # 右下三角：浅紫色
    canvas.create_polygon(
        sw, sh, sw * 0.5, sh, sw, sh * 0.35,
        fill="#dcc5f5", outline="",
    )
    # ── 图标 + 标题 + 作者（居中） ──
    icon_size = 88
    group_gap = 28
    center_y = sh * 0.5

    # 精确测量标题文字宽度
    import tkinter.font as tkfont
    title_font = tkfont.Font(family="Segoe UI", size=28, weight="bold")
    text_w = title_font.measure(APP_NAME)
    group_w = icon_size + group_gap + text_w
    group_left = (sw - group_w) // 2

    icon_cx = group_left + icon_size // 2
    icon_cy = int(center_y)

    photo = None
    icon_path = base / ICON_PNG
    if not icon_path.exists():
        icon_path = base / ICON_FILE
    if icon_path.exists():
        try:
            from PIL import Image, ImageTk, ImageDraw

            img = Image.open(str(icon_path)).convert("RGBA")
            img = img.resize((icon_size, icon_size), Image.Resampling.LANCZOS)

            # 圆角蒙版
            mask = Image.new("L", (icon_size, icon_size), 0)
            draw = ImageDraw.Draw(mask)
            draw.rounded_rectangle(
                [0, 0, icon_size - 1, icon_size - 1],
                radius=18, fill=255,
            )
            img.putalpha(mask)

            photo = ImageTk.PhotoImage(img)
            canvas.create_image(icon_cx, icon_cy, image=photo)
        except (ImportError, OSError, ValueError):
            pass

    # 文字区左边缘
    text_x = group_left + icon_size + group_gap

    # 应用名称
    canvas.create_text(
        text_x, icon_cy - 14, text=APP_NAME, anchor="w",
        font=("Segoe UI", 28, "bold"), fill="#4a1a7a",
    )
    # 作者
    canvas.create_text(
        text_x, icon_cy + 24, text="by YuanXiQWQ", anchor="w",
        font=("Segoe UI", 13), fill="#8b5fbf",
    )

    # ── 右上角关闭按钮（纯 × 线条） ──
    btn_size = 28
    btn_margin = 8
    bx1, by1 = sw - btn_margin - btn_size, btn_margin
    bx2, by2 = sw - btn_margin, btn_margin + btn_size
    pad = 6
    canvas.create_line(bx1 + pad, by1 + pad, bx2 - pad, by2 - pad, fill="#8b5fbf", width=2, tags="close_btn")
    canvas.create_line(bx1 + pad, by2 - pad, bx2 - pad, by1 + pad, fill="#8b5fbf", width=2, tags="close_btn")

    def _on_close_click(_evt: Any) -> None:
        _splash_state["cancelled"] = True
        root.destroy()

    canvas.tag_bind("close_btn", "<Button-1>", _on_close_click)

    # 保持引用
    _splash_state["photo"] = photo
    _splash_state["canvas"] = canvas

    root.update()

    def _safe_destroy() -> None:
        try:
            root.destroy()
        except (RuntimeError, Exception):
            pass

    return root, _safe_destroy


def _update_splash_text(root: Any, _text: str) -> None:
    """刷新闪屏窗口（保持窗口响应）。"""
    try:
        root.update()
    except (AttributeError, RuntimeError):
        pass


# ------------------------------------------------------------------
# 启动时应用已下载的更新
# ------------------------------------------------------------------

_UPDATE_STAGING = "update_staging"


def _apply_pending_update(base: Path) -> bool:
    """如果 update_staging/extracted/ 存在，启动独立更新器进程来覆盖文件。

    主程序无法覆盖自身的 exe/dll，因此委托给外部更新器：
    updater.py 等待主程序退出 → 覆盖文件 → 重新启动 exe。

    Returns:
        True — 已启动更新器，调用方应立即退出
        False — 无待应用更新，正常继续
    """
    import subprocess as _sp

    staging = base / _UPDATE_STAGING / "extracted"
    if not staging.exists():
        return False

    logger.info(f"检测到待应用的更新: {staging}")

    # 定位更新器脚本（打包后与 exe 同目录，开发模式在脚本旁）
    updater = base / "updater.py"
    if not updater.exists():
        logger.error(f"更新器脚本不存在: {updater}")
        return False

    # 定位 exe 或 python 解释器
    exe_path = sys.executable  # 打包后就是 DocAI-Pipeline.exe
    pid = os.getpid()

    # 确定 Python 解释器路径（打包模式下 updater.py 是纯脚本，需要用 Python 运行）
    if getattr(sys, "frozen", False):
        # onedir 模式：使用打包自带的 python（在 _internal/ 下）或系统 Python
        # 由于打包后没有独立 python.exe，将 updater 打包为独立 exe 更可靠
        # 这里改用 updater.exe（由 spec 打包）
        updater_exe = base / "updater.exe"
        if updater_exe.exists():
            cmd = [str(updater_exe), str(base), exe_path, str(pid)]
        else:
            # 回退：尝试用系统 Python 运行脚本
            cmd = ["python", str(updater), str(base), exe_path, str(pid)]
    else:
        cmd = [sys.executable, str(updater), str(base), exe_path, str(pid)]

    logger.info(f"启动更新器: {' '.join(cmd)}")
    try:
        _sp.Popen(
            cmd,
            cwd=str(base),
            creationflags=_sp.DETACHED_PROCESS | _sp.CREATE_NEW_PROCESS_GROUP,
        )
        return True
    except OSError as e:
        logger.error(f"启动更新器失败: {e}")
        return False


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

    # 标记桌面模式（让后端 API 识别）
    os.environ["DOCAI_DESKTOP"] = "1"

    # 设置工作目录为 ai-service 根（确保 .env / user_settings.json 可被找到）
    base = _base_dir()
    os.chdir(base)

    # 应用上次下载好的更新（委托给独立更新器进程）
    if _apply_pending_update(base):
        logger.info("已启动更新器，主程序即将退出")
        return

    # 显示 Splash 闪屏
    splash_root, splash_destroy = _show_splash(base)

    if _splash_cancelled():
        logger.info("用户在闪屏阶段取消了启动")
        return

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

    if _splash_cancelled():
        logger.info("用户在闪屏阶段取消了启动")
        server.should_exit = True
        return

    if not _wait_for_server(host, port):
        logger.error("服务启动超时！")
        splash_destroy()
        return

    if _splash_cancelled():
        logger.info("用户在闪屏阶段取消了启动")
        server.should_exit = True
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
        # 窗口图标：pywebview(Windows) 只支持 .ico 格式
        _icon_path = base / ICON_FILE
        _wv_window = _webview.create_window(
            APP_NAME,
            url,
            width=win_w,
            height=win_h,
            min_size=(800, 600),
            confirm_close=False,
        )

        def _on_closing() -> bool:
            """窗口关闭事件：根据用户偏好决定最小化还是退出。"""
            if shutdown_event.is_set():
                return True  # 已在退出流程中（托盘退出等），允许关闭
            _cb = _load_prefs().get("close_behavior", "minimize_to_tray")
            if _cb == "minimize_to_tray":
                assert _wv_window is not None
                _wv_window.hide()
                return False  # 取消关闭，改为隐藏
            else:
                shutdown_event.set()
                return True  # 允许 pywebview 正常关闭窗口

        def _on_closed() -> None:
            """窗口真正关闭后触发。"""
            shutdown_event.set()

        def _bring_to_front_win32() -> None:
            """等待窗口就绪后通过 Win32 API 强制前置。"""
            try:
                time.sleep(1.0)
                if _wv_window is None:
                    return
                import ctypes
                from ctypes import wintypes, WinDLL

                user32 = WinDLL("user32", use_last_error=True)
                kernel32 = WinDLL("kernel32", use_last_error=True)
                pid = os.getpid()
                target_hwnd = None

                # 遍历所有顶级窗口，找到属于当前进程且标题含 APP_NAME 的窗口
                WNDENUMPROC = ctypes.WINFUNCTYPE(  # noqa: N806
                    wintypes.BOOL, wintypes.HWND, wintypes.LPARAM,
                )

                def _enum_cb(hwnd: Any, _lp: Any) -> bool:
                    nonlocal target_hwnd
                    wnd_pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wnd_pid))
                    if wnd_pid.value == pid and user32.IsWindowVisible(hwnd):
                        length = user32.GetWindowTextLengthW(hwnd)
                        if length > 0:
                            buf = ctypes.create_unicode_buffer(length + 1)
                            user32.GetWindowTextW(hwnd, buf, length + 1)
                            if APP_NAME in buf.value:
                                target_hwnd = hwnd
                                return False
                    return True

                user32.EnumWindows(WNDENUMPROC(_enum_cb), 0)
                if not target_hwnd:
                    return

                # 获取前台窗口线程和目标窗口线程
                fg_hwnd = user32.GetForegroundWindow()
                fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None)
                cur_tid = kernel32.GetCurrentThreadId()
                target_tid = user32.GetWindowThreadProcessId(target_hwnd, None)

                # 将当前线程附加到前台窗口线程，获取前台设置权限
                attached_fg = False
                attached_target = False
                if fg_tid != cur_tid:
                    attached_fg = bool(user32.AttachThreadInput(cur_tid, fg_tid, True))
                if target_tid != cur_tid:
                    attached_target = bool(user32.AttachThreadInput(cur_tid, target_tid, True))

                try:
                    # 模拟按键释放前台锁
                    user32.keybd_event(0, 0, 2, 0)  # KEYEVENTF_KEYUP
                    user32.ShowWindow(target_hwnd, 9)  # SW_RESTORE
                    user32.BringWindowToTop(target_hwnd)
                    user32.SetForegroundWindow(target_hwnd)
                    user32.SetFocus(target_hwnd)
                finally:
                    if attached_fg:
                        user32.AttachThreadInput(cur_tid, fg_tid, False)
                    if attached_target:
                        user32.AttachThreadInput(cur_tid, target_tid, False)
            except (AttributeError, RuntimeError, OSError, ValueError):
                pass

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
        _icon_str = str(_icon_path) if _icon_path.exists() else None
        # noinspection PyBroadException
        try:
            _webview.start(func=_bring_to_front_win32, gui="edgechromium", icon=_icon_str)
        except Exception:
            # 若 edgechromium 不可用，尝试默认后端
            _webview.start(func=_bring_to_front_win32, icon=_icon_str)

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

    # 强制终止进程，确保 YOLO/torch/SQLite 等残留线程不会阻止退出
    os._exit(0)


if __name__ == "__main__":
    main()
