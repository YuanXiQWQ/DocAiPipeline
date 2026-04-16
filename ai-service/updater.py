"""DocAI Pipeline 独立更新器。

在主程序退出后执行文件覆盖，再重新启动 exe。
由 launcher.py 在检测到待应用更新时以子进程方式调用。

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
import time
from pathlib import Path

UPDATE_STAGING = "update_staging"

# 不覆盖的用户数据
PROTECTED = {"user_settings.json", "desktop_prefs.json", "output", UPDATE_STAGING}

LOG_FILE = "update.log"


def _log(msg: str) -> None:
    """写日志到文件（此时无法使用 loguru）。"""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def _wait_for_exit(pid: int, timeout: float = 30.0) -> bool:
    """等待指定进程退出。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)  # 检测进程是否存在（不发送信号）
            time.sleep(0.5)
        except OSError:
            return True  # 进程已退出
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

    success = True
    for item in src.iterdir():
        if item.name in PROTECTED:
            continue
        dest = app_dir / item.name
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
    try:
        shutil.rmtree(str(app_dir / UPDATE_STAGING))
        _log("暂存目录已清理")
    except OSError as e:
        _log(f"清理暂存目录失败: {e}")

    return success


def main() -> None:
    if len(sys.argv) < 4:
        print(f"用法: {sys.argv[0]} <app_dir> <exe_path> <pid>")
        sys.exit(1)

    app_dir = Path(sys.argv[1])
    exe_path = sys.argv[2]
    pid = int(sys.argv[3])

    os.chdir(app_dir)

    _log(f"更新器启动: app_dir={app_dir}, exe={exe_path}, pid={pid}")

    # 等待主程序退出
    _log(f"等待主程序 (PID={pid}) 退出…")
    if not _wait_for_exit(pid, timeout=30):
        _log("主程序未在30秒内退出，强制继续")

    # 额外等待，确保文件句柄释放
    time.sleep(1.0)

    # 应用更新
    ok = _apply(app_dir)

    # 重新启动主程序
    _log(f"重新启动: {exe_path}")
    try:
        subprocess.Popen(
            [exe_path],
            cwd=str(app_dir),
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    except OSError as e:
        _log(f"启动失败: {e}")
        sys.exit(1)

    _log("更新器完成" if ok else "更新器完成（有错误）")


if __name__ == "__main__":
    main()
