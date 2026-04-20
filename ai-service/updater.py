"""DocAI Pipeline 独立更新器。

在主程序退出后执行文件覆盖，再重新启动 exe。
由 launcher.py 在检测到待应用更新时以子进程方式调用。
带有 tkinter 闪屏窗口和进度条，让用户在更新过程中有视觉反馈。

用法（由 launcher 自动调用）：
    python updater.py <app_dir> <exe_path> <pid>

参数：
    app_dir   — 应用根目录（即 exe 所在目录）
    exe_path  — 主程序 exe 的完整路径
    pid       — 主程序进程 ID（等待其退出后再操作）
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

UPDATE_STAGING = "update_staging"

# 不覆盖的文件/目录（用户数据 + 正在运行的更新器自身）
PROTECTED = {
    "user_settings.json", "desktop_prefs.json", "output",
    UPDATE_STAGING, "update.log",
    "updater.exe",  # 更新器正在运行，无法覆盖自身
}

LOG_FILE = "update.log"

# ── UI 状态（线程间通信） ──
_ui_state: dict = {"message": "正在准备更新…", "progress": 0, "done": False}


# ------------------------------------------------------------------
# 日志
# ------------------------------------------------------------------

def _log(msg: str) -> None:
    """写日志到文件（此时无法使用 loguru）。"""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


# ------------------------------------------------------------------
# 更新逻辑
# ------------------------------------------------------------------

def _wait_for_exit(pid: int, timeout: float = 30.0) -> bool:
    """等待指定进程退出。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
            time.sleep(0.5)
        except OSError:
            return True
    return False


def _apply(app_dir: Path) -> bool:
    """将 update_staging/extracted/ 中的内容覆盖到应用目录。"""
    staging = app_dir / UPDATE_STAGING / "extracted"
    if not staging.exists():
        _log(f"暂存目录不存在: {staging}")
        return False

    _log(f"开始应用更新: {staging}")

    # extracted/ 下可能有一层子目录（如 DocAI-Pipeline/）
    children = list(staging.iterdir())
    src = children[0] if len(children) == 1 and children[0].is_dir() else staging

    # 先统计要复制的项目数量
    items = [item for item in src.iterdir() if item.name not in PROTECTED]
    total = max(len(items), 1)

    success = True
    for i, item in enumerate(items):
        dest = app_dir / item.name
        _ui_state["message"] = f"正在更新: {item.name}"
        _ui_state["progress"] = int(20 + 65 * i / total)  # 20%-85%
        try:
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(str(item), str(dest))
            else:
                shutil.copy2(str(item), str(dest))
        except (OSError, PermissionError) as e:
            _log(f"覆盖失败 {item.name}: {e}")
            success = False

    if success:
        _log("更新文件已全部覆盖")
    else:
        _log("部分文件覆盖失败")

    # 清理 staging
    _ui_state["message"] = "正在清理临时文件…"
    _ui_state["progress"] = 90
    try:
        shutil.rmtree(str(app_dir / UPDATE_STAGING))
        _log("暂存目录已清理")
    except OSError as e:
        _log(f"清理暂存目录失败: {e}")

    return success


def _update_worker(app_dir: Path, exe_path: str, pid: int) -> None:
    """后台线程：执行等待→覆盖→重启的完整流程。"""
    _log(f"更新器启动: app_dir={app_dir}, exe={exe_path}, pid={pid}")

    # 阶段 1：等待主程序退出 (0% → 15%)
    _ui_state["message"] = "正在等待应用关闭…"
    _ui_state["progress"] = 5
    _log(f"等待主程序 (PID={pid}) 退出…")
    if not _wait_for_exit(pid, timeout=30):
        _log("主程序未在30秒内退出，强制继续")
    _ui_state["progress"] = 15

    # 额外等待，确保文件句柄释放
    _ui_state["message"] = "正在释放文件…"
    time.sleep(1.0)
    _ui_state["progress"] = 20

    # 阶段 2：应用更新 (20% → 90%)
    _ui_state["message"] = "正在应用更新…"
    ok = _apply(app_dir)

    # 阶段 3：重新启动 (90% → 100%)
    _ui_state["message"] = "正在重新启动应用…"
    _ui_state["progress"] = 95
    _log(f"重新启动: {exe_path}")
    try:
        subprocess.Popen(
            [exe_path],
            cwd=str(app_dir),
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    except OSError as e:
        _log(f"启动失败: {e}")

    _ui_state["progress"] = 100
    _ui_state["message"] = "更新完成！" if ok else "更新完成（部分文件失败）"
    _log("更新器完成" if ok else "更新器完成（有错误）")
    time.sleep(0.8)
    _ui_state["done"] = True


# ------------------------------------------------------------------
# Tkinter 闪屏 UI
# ------------------------------------------------------------------

def _run_splash(app_dir: Path, exe_path: str, pid: int) -> None:
    """显示更新闪屏窗口，同时在后台线程执行更新。"""
    try:
        import tkinter as tk
    except ImportError:
        # 无 tkinter 时直接在当前线程执行
        _update_worker(app_dir, exe_path, pid)
        return

    root = tk.Tk()
    root.overrideredirect(True)

    sw, sh = 480, 200
    x = (root.winfo_screenwidth() - sw) // 2
    y = (root.winfo_screenheight() - sh) // 2
    root.geometry(f"{sw}x{sh}+{x}+{y}")

    # 聚焦到前台
    root.lift()
    root.focus_force()

    # ── 拖拽支持 ──
    _drag = {"x": 0, "y": 0}

    def _on_press(e: tk.Event) -> None:  # type: ignore[type-arg]
        _drag["x"] = e.x
        _drag["y"] = e.y

    def _on_drag(e: tk.Event) -> None:  # type: ignore[type-arg]
        root.geometry(f"+{root.winfo_x() + e.x - _drag['x']}+{root.winfo_y() + e.y - _drag['y']}")

    root.bind("<Button-1>", _on_press)
    root.bind("<B1-Motion>", _on_drag)

    canvas = tk.Canvas(root, width=sw, height=sh, highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    # ── 背景渐变（浅紫 → 白） ──
    for i in range(sh):
        r = int(245 + (252 - 245) * i / sh)
        g = int(238 + (248 - 238) * i / sh)
        b = int(255 + (255 - 255) * i / sh)
        color = f"#{r:02x}{g:02x}{b:02x}"
        canvas.create_line(0, i, sw, i, fill=color)

    # ── 标题 ──
    canvas.create_text(
        sw // 2, 50,
        text="DocAI Pipeline",
        font=("Segoe UI", 20, "bold"),
        fill="#9333ea",
    )

    # ── 状态文字 ──
    status_text = canvas.create_text(
        sw // 2, 95,
        text="正在准备更新…",
        font=("Segoe UI", 11),
        fill="#7c3aed",
    )

    # ── 进度条（简单矩形，避免圆角拼接间隙） ──
    bar_x, bar_y, bar_w, bar_h = 40, 130, sw - 80, 14
    # 背景槽
    canvas.create_rectangle(bar_x, bar_y, bar_x + bar_w, bar_y + bar_h,
                            fill="#e9d5ff", outline="#ddd6fe", width=1)
    # 前景（动态更新）
    bar_fg = canvas.create_rectangle(bar_x, bar_y, bar_x, bar_y + bar_h,
                                     fill="#bd7fff", outline="")

    # ── 百分比文字 ──
    pct_text = canvas.create_text(
        sw // 2, 162,
        text="0%",
        font=("Segoe UI", 10),
        fill="#a78bfa",
    )

    def _draw_progress(pct: int) -> None:
        """更新进度条前景宽度。"""
        if pct <= 0:
            canvas.coords(bar_fg, bar_x, bar_y, bar_x, bar_y + bar_h)
            return
        filled_w = max(2, int(bar_w * min(pct, 100) / 100))
        canvas.coords(bar_fg, bar_x, bar_y, bar_x + filled_w, bar_y + bar_h)

    def _poll() -> None:
        """每 100ms 轮询后台线程状态并更新 UI。"""
        canvas.itemconfig(status_text, text=_ui_state["message"])
        canvas.itemconfig(pct_text, text=f"{_ui_state['progress']}%")
        _draw_progress(_ui_state["progress"])
        if _ui_state["done"]:
            # noinspection PyTypeChecker
            root.after(300, lambda: root.destroy())
        else:
            # noinspection PyTypeChecker
            root.after(100, lambda: _poll())

    # 启动后台更新线程
    worker = threading.Thread(
        target=_update_worker,
        args=(app_dir, exe_path, pid),
        daemon=True,
    )
    worker.start()

    # 开始轮询
    # noinspection PyTypeChecker
    root.after(100, lambda: _poll())
    root.mainloop()


# ------------------------------------------------------------------
# 入口
# ------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 4:
        _log(f"用法: {sys.argv[0]} <app_dir> <exe_path> <pid>")
        sys.exit(1)

    app_dir = Path(sys.argv[1])
    exe_path = sys.argv[2]
    pid = int(sys.argv[3])

    os.chdir(app_dir)

    _run_splash(app_dir, exe_path, pid)


if __name__ == "__main__":
    main()
