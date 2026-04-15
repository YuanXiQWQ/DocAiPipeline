"""DocAI Pipeline 桌面应用一键构建脚本。

步骤：
1. 构建前端（npm run build）
2. 复制前端产物到 ai-service/web_dist
3. 运行 PyInstaller 打包
4. 输出 dist/DocAI-Pipeline.exe

用法：
    python build_desktop.py

前置条件：
    - Node.js + npm（用于构建前端）
    - Python ≤3.12 + pip install pyinstaller pystray Pillow pywebview（用于打包）
    - 已安装 ai-service/requirements.txt 中的所有依赖

注意：Python 3.13+ 下 pywebview 的依赖 pythonnet 尚未适配，
      构建产物将自动回退为浏览器模式。
      要获得原生窗口体验，请使用 Python 3.11 或 3.12 构建。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

# ------------------------------------------------------------------
# 路径
# ------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
AI_DIR = ROOT / "ai-service"
WEB_DIST_SRC = WEB_DIR / "dist"
WEB_DIST_DST = AI_DIR / "web_dist"
SPEC_FILE = AI_DIR / "docai.spec"
OUTPUT_DIR = ROOT / "dist"


def _run(cmd: list[str], cwd: Path, label: str) -> None:
    """运行子进程，失败时退出。"""
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"  命令: {' '.join(cmd)}")
    print(f"  目录: {cwd}")
    print(f"{'='*60}\n")
    result = subprocess.run(cmd, cwd=str(cwd), shell=True)
    if result.returncode != 0:
        print(f"\n[X] {label} 失败（退出码 {result.returncode}）")
        sys.exit(result.returncode)


def step_build_frontend() -> None:
    """步骤 1：构建前端。"""
    if not (WEB_DIR / "package.json").exists():
        print("[X] 未找到 web/package.json，请确认项目结构完整")
        sys.exit(1)

    # 安装依赖（如果 node_modules 不存在）
    if not (WEB_DIR / "node_modules").exists():
        _run(["npm", "install"], WEB_DIR, "安装前端依赖")

    _run(["npm", "run", "build"], WEB_DIR, "构建前端（vite build）")

    if not (WEB_DIST_SRC / "index.html").exists():
        print("[X] 前端构建产物未生成（web/dist/index.html 不存在）")
        sys.exit(1)

    print("[OK] 前端构建完成")


def step_copy_frontend() -> None:
    """步骤 2：复制前端产物到 ai-service/web_dist。"""
    if WEB_DIST_DST.exists():
        shutil.rmtree(WEB_DIST_DST)
    shutil.copytree(WEB_DIST_SRC, WEB_DIST_DST)
    print(f"[OK] 前端产物已复制到 {WEB_DIST_DST}")


def step_pyinstaller() -> None:
    """步骤 3：PyInstaller 打包。"""
    if not SPEC_FILE.exists():
        print(f"[X] 未找到 spec 文件: {SPEC_FILE}")
        sys.exit(1)

    _run(
        [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", str(SPEC_FILE)],
        AI_DIR,
        "PyInstaller 打包",
    )

    exe_path = AI_DIR / "dist" / "DocAI-Pipeline.exe"
    if not exe_path.exists():
        print("[X] 打包失败：未生成 .exe 文件")
        sys.exit(1)

    # 移动到项目根目录 dist/
    OUTPUT_DIR.mkdir(exist_ok=True)
    final_path = OUTPUT_DIR / "DocAI-Pipeline.exe"
    if final_path.exists():
        final_path.unlink()
    shutil.move(str(exe_path), str(final_path))

    print(f"\n{'='*60}")
    print(f"  [OK] 构建完成！")
    print(f"  输出文件: {final_path}")
    print(f"  文件大小: {final_path.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"{'='*60}")


def step_cleanup() -> None:
    """步骤 4：清理临时文件。"""
    for d in [AI_DIR / "build", AI_DIR / "dist"]:
        if d.exists():
            shutil.rmtree(d)
    # 保留 web_dist（spec 文件引用它）
    print("[OK] 临时文件已清理")


def step_check_python() -> None:
    """步骤 0：检查 Python 版本与 pywebview 可用性。"""
    ver = sys.version_info
    print(f"   Python: {ver.major}.{ver.minor}.{ver.micro}")

    if ver >= (3, 13):
        print()
        print("[!] 警告：Python 3.13+ 下 pywebview 的依赖 pythonnet 尚未适配。")
        print("    构建产物将回退为浏览器模式（功能完整，但没有原生窗口）。")
        print("    如需原生窗口，请使用 Python 3.11 或 3.12。")
        print()
    else:
        # Python ≤ 3.12：确保 pywebview 已安装
        try:
            import webview  # noqa: F401
            print("   pywebview: 已安装 → 原生窗口模式")
        except ImportError:
            print("   pywebview: 未安装，正在自动安装…")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "pywebview>=5.0"],
            )
            print("   pywebview: 安装完成")


def main() -> None:
    print("[BUILD] DocAI Pipeline 桌面应用构建脚本")
    print(f"   项目根目录: {ROOT}")

    step_check_python()
    step_build_frontend()
    step_copy_frontend()
    step_pyinstaller()
    step_cleanup()


if __name__ == "__main__":
    main()
