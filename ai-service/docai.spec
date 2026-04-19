# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec 文件 — DocAI Pipeline 桌面应用。

构建命令：
    cd ai-service
    pyinstaller docai.spec

产出：dist/DocAI-Pipeline/
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
    # 应用图标（系统托盘 + 窗口图标 + 闪屏）
    (str(BASE / "icon.ico"), "."),
    (str(BASE / "icon.png"), "."),
]

# 版本号文件（CI 构建时生成）
version_file = BASE / "VERSION"
if version_file.exists():
    datas.append((str(version_file), "."))

# 可选：YOLO 模型文件（如果存在）
yolo_model = BASE / "models" / "yolo_customs_doc.pt"
if yolo_model.exists():
    datas.append((str(yolo_model), "models"))

# 内置数据统计 Excel 模板
excel_template = BASE / "models" / "数据统计_模板.xlsx"
if excel_template.exists():
    datas.append((str(excel_template), "models"))

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
    # pystray（托盘图标）
    "pystray",
    "pystray._win32",
    # 新增路由
    "app.routers.history_router",
    "app.routers.summary",
    "app.routers.scanner",
    "app.routers.template_lib",
    "app.history",
    "app.db",
    "app.summary_store",
    "app.summary_writer",
    # 其他
    "encodings",
    "encodings.idna",
    # 扫描仪 COM
    "comtypes",
    "comtypes.client",
]

# Python ≤3.12 且 pywebview 已安装时，才打包 webview
if sys.version_info < (3, 13):
    try:
        import webview  # noqa: F401
        hiddenimports += [
            "webview",
            "webview.platforms",
            "webview.platforms.edgechromium",
            "webview.platforms.winforms",
            "webview.platforms.mshtml",
            "clr_loader",
            "clr_loader.ffi",
            "pythonnet",
        ]
    except ImportError:
        pass

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
        "matplotlib",
        "scipy",
        "notebook",
        "jupyter",
        "tensorboard",
        "torch.utils.tensorboard",
        "sympy",
        "IPython",
        "jedi",
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
    [],                          # onedir 模式：binaries/datas 由 COLLECT 处理
    exclude_binaries=True,       # ← 关键：不嵌入二进制文件
    name="DocAI-Pipeline",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,  # 无控制台窗口（桌面应用）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(BASE / "icon.ico"),
)

# ------------------------------------------------------------------
# 独立更新器 updater.exe（onefile 模式，体积极小，仅依赖标准库）
# 主程序无法覆盖自身的 exe/dll，因此委托给这个独立进程。
# ------------------------------------------------------------------

updater_a = Analysis(
    [str(BASE / "updater.py")],
    pathex=[str(BASE)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

updater_pyz = PYZ(updater_a.pure, updater_a.zipped_data, cipher=block_cipher)

updater_exe = EXE(
    updater_pyz,
    updater_a.scripts,
    updater_a.binaries,
    updater_a.zipfiles,
    updater_a.datas,
    [],
    name="updater",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(BASE / "icon.ico"),
)

# onedir 模式：所有文件收集到 dist/DocAI-Pipeline/ 目录
# updater.exe 也放进同一目录
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    updater_exe,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="DocAI-Pipeline",
)
