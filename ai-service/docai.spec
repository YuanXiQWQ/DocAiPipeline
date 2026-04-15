# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec 文件 — DocAI Pipeline 桌面应用。

构建命令：
    cd ai-service
    pyinstaller docai.spec

产出：dist/DocAI-Pipeline.exe（单文件）
"""

import sys
from pathlib import Path

block_cipher = None

# 项目根目录（ai-service/）
BASE = Path(SPECPATH)

# 需要收集的数据文件
datas = [
    # 前端构建产物（构建脚本会先将 web/dist 复制到 ai-service/web_dist）
    (str(BASE / "web_dist"), "web_dist"),
    # .env.example 作为默认配置参考
    (str(BASE / ".env.example"), "."),
    # 应用图标（系统托盘用）
    (str(BASE / "icon.ico"), "."),
]

# 可选：YOLO 模型文件（如果存在）
yolo_model = BASE / "models" / "yolo_customs_doc.pt"
if yolo_model.exists():
    datas.append((str(yolo_model), "models"))

# 需要收集的隐式导入（PyInstaller 无法自动检测的模块）
hiddenimports = [
    # FastAPI 及其依赖
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    # multipart 表单
    "multipart",
    # 应用模块
    "app",
    "app.main",
    "app.config",
    "app.pipeline",
    "app.schemas",
    "app.routers.process",
    "app.routers.fill",
    "app.extraction",
    "app.export",
    "app.detection",
    "app.preprocessing",
    "app.validation",
    # 数据处理
    "openpyxl",
    "pandas",
    "numpy",
    "cv2",
    "PIL",
    # OpenAI
    "openai",
    # pywebview（原生窗口）
    "webview",
    # pystray（托盘图标）
    "pystray",
    "pystray._win32",
    # 新增路由
    "app.routers.history_router",
    "app.routers.summary",
    "app.history",
    # 其他
    "encodings",
    "encodings.idna",
]

a = Analysis(
    [str(BASE / "launcher.py")],
    pathex=[str(BASE)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的大包，减小体积
        "tkinter",
        "matplotlib",
        "scipy",
        "notebook",
        "jupyter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="DocAI-Pipeline",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 无控制台窗口（桌面应用）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(BASE / "icon.ico"),
)
