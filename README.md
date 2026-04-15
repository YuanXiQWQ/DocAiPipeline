# DocAI Pipeline

简体中文 | [English](README_EN.md)

> 基于多模态大模型 (VLM) 的文档自动识别与智能归档系统 — 覆盖原木进口→加工→打包全生命周期单据。

## 功能概览

| 文档类型           | 输入       | 输出           | 状态 |
|----------------|----------|--------------|----|
| 进口单据（报关/税款/发票） | PDF 扫描件  | 纸质发票记录表      | ✅  |
| 原木检尺单          | PDF / 图片 | 原木出入库表       | ✅  |
| 原木领用出库表        | PDF / 图片 | 原木出入库表（出库）   | ✅  |
| 刨切木方入池表        | PDF / 图片 | 刨切入池与上机表     | ✅  |
| 刨切木方上机表        | PDF / 图片 | 刨切入池与上机表（上机） | ✅  |
| 表板打包报表         | PDF / 图片 | 表板统计表        | ✅  |

**核心流程**：上传文档 → VLM 自动分类 → 结构化识别 → 人工复核 → Excel 自动填充 → 下载

## 项目结构

```
DocAiPipeline/
├── ai-service/                  # Python 后端 (FastAPI)
│   ├── app/
│   │   ├── routers/             # API 路由 (process, fill)
│   │   ├── preprocessing/       # PDF→图像、去噪、校正、增强
│   │   ├── detection/           # YOLO 单据检测
│   │   ├── extraction/          # VLM 抽取器 (VLM/Log/Factory)
│   │   ├── validation/          # 规则校验
│   │   ├── export/              # Excel 填充器 (6种)
│   │   ├── config.py            # 配置管理
│   │   ├── schemas.py           # Pydantic 数据模型
│   │   ├── pipeline.py          # 进口单据管线编排
│   │   └── main.py              # FastAPI 入口
│   ├── requirements.txt
│   └── .env.example
├── web/                          # React 前端 (Vite + TS + TailwindCSS)
│   ├── src/
│   │   ├── App.tsx              # 主应用（上传→识别→复核→导出）
│   │   └── api.ts               # API 服务层
│   └── package.json
├── build_desktop.py               # 一键构建桌面 .exe 脚本
├── docker-compose.yml             # Docker 一键部署
└── 文档/                          # 项目规划与样例数据
```

## 快速开始

### 方式一：本地开发（推荐用于测试）

**前置条件**：Python 3.11+、Node.js 18+、OpenAI API Key

```bash
# 1. 后端
cd ai-service
pip install -r requirements.txt
cp .env.example .env              # 编辑 .env，填入 OPENAI_API_KEY
python -m app.main                # → http://localhost:8000

# 2. 前端（新终端窗口）
cd web
npm install
npm run dev                       # → http://localhost:5173
```

打开 `http://localhost:5173` 即可测试完整流程。

### 方式二：桌面应用（推荐非技术用户）

**前置条件**：Python 3.11–3.12、Node.js 18+

> ⚠️ Python 3.13+ 下 pywebview 依赖的 pythonnet 尚未适配，构建脚本会自动回退为浏览器模式。
> 要获得原生窗口体验，请使用 **Python 3.11 或 3.12** 构建。

```bash
# 一键构建（Windows，指定 Python 3.12）
py -3.12 build_desktop.py

# 如果系统默认 Python 已是 3.11–3.12，也可以直接：
# python build_desktop.py

# 产出: dist/DocAI-Pipeline.exe
# 双击运行，浏览器自动打开，系统托盘显示图标
# 首次运行会自动弹出设置面板，请填入 OpenAI API Key
```

也可以直接用启动器脚本运行（不打包）：

```bash
cd ai-service
python launcher.py               # → http://127.0.0.1:8000
```

### 方式三：Docker 一键部署

```bash
# 创建 .env 文件
echo "OPENAI_API_KEY=sk-your-key" > .env

# 启动
docker compose up --build

# → 前端: http://localhost:3000
# → 后端: http://localhost:8000
# → API 文档: http://localhost:8000/docs
```

## API 接口

| 方法     | 路径                          | 说明                   |
|--------|-----------------------------|----------------------|
| `GET`  | `/health`                   | 健康检查                 |
| `POST` | `/api/classify`             | VLM 文档分类（6 种类型）      |
| `POST` | `/api/process`              | 统一文档处理（自动/手动分类 → 识别） |
| `POST` | `/api/fill`                 | 识别结果 → Excel 自动填充    |
| `GET`  | `/api/templates`            | 列出已上传的 Excel 模板      |
| `POST` | `/api/templates/{doc_type}` | 上传 Excel 模板          |
| `GET`  | `/api/download/{filename}`  | 下载填充后的文件             |

完整 API 文档：启动后端后访问 `http://localhost:8000/docs`

## 技术栈

- **AI 后端**：Python, FastAPI, OpenCV, PyMuPDF, Ultralytics YOLO, OpenAI VLM (gpt-4.1-mini)
- **Excel 引擎**：openpyxl（保留公式、格式与数据透视表）
- **Web 前端**：React 19, TypeScript, Vite, TailwindCSS v4, Lucide Icons
- **部署**：Docker Compose / PyInstaller 桌面 .exe / 本地开发

## 许可证

本项目仅供内部使用。
