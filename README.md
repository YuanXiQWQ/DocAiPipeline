# DocAI Pipeline

简体中文 | [English](README_EN.md)

> 基于多模态大模型 (VLM) 的文档自动识别与智能归档系统 — 覆盖原木进口→加工→打包全生命周期单据。

## 功能概览

| 文档类型           | 输入       | 输出           |
|----------------|----------|--------------|
| 进口单据（报关/税款/发票） | PDF 扫描件  | 纸质发票记录表      |
| 原木检尺单          | PDF / 图片 | 原木出入库表       |
| 原木领用出库表        | PDF / 图片 | 原木出入库表（出库）   |
| 刨切木方入池表        | PDF / 图片 | 刨切入池与上机表     |
| 刨切木方上机表        | PDF / 图片 | 刨切入池与上机表（上机） |
| 表板打包报表         | PDF / 图片 | 表板统计表        |

**核心流程**：上传文档 → VLM 自动分类 → 结构化识别 → 人工复核 → Excel 自动填充 → 下载

**附加功能**：

- **数据汇总看板** — 进口/原木入出库/工厂加工统计，支持日期筛选、明细编辑、修订历史追溯
- **历史数据查询** — 分页/筛选/搜索，可加载复核和查看识别结果详情
- **扫描仪集成** — 桌面端直接从 WIA 扫描仪导入文档（Windows）
- **多语言支持** — 中文 / English / Srpski 三语切换
- **桌面应用** — PyInstaller 打包，原生窗口 + 系统托盘 + 开机自启 + 自动更新

## 项目结构

```
DocAiPipeline/
├── ai-service/                  # Python 后端 (FastAPI)
│   ├── app/
│   │   ├── routers/             # API 路由
│   │   │   ├── process.py       #   文档处理 & 批量处理（SSE）
│   │   │   ├── fill.py          #   Excel 填充 & 模板管理
│   │   │   ├── summary.py       #   数据汇总 & 明细 CRUD
│   │   │   ├── history_router.py#   历史记录查询
│   │   │   └── scanner.py       #   WIA 扫描仪集成
│   │   ├── preprocessing/       # PDF→图像、去噪、校正、增强
│   │   ├── detection/           # YOLO 单据检测 & 多文档分割
│   │   ├── extraction/          # VLM 抽取器 (VLM/Log/Factory)
│   │   ├── validation/          # 规则校验
│   │   ├── export/              # Excel 填充器 (Invoice/Log/Factory)
│   │   ├── config.py            # 配置管理 & 模型列表
│   │   ├── schemas.py           # Pydantic 数据模型
│   │   ├── pipeline.py          # 进口单据管线编排
│   │   ├── db.py                # SQLite 连接管理 & 建表
│   │   ├── history.py           # 处理历史持久化 (SQLite)
│   │   ├── summary_store.py     # 汇总明细 CRUD (SQLite)
│   │   ├── summary_writer.py    # 处理结果→汇总明细自动转换
│   │   └── main.py              # FastAPI 入口 & 设置/平台/更新 API
│   ├── launcher.py              # 桌面启动器（uvicorn + pywebview + 托盘）
│   ├── docai.spec               # PyInstaller 打包配置
│   ├── evaluate.py              # 准确率评估脚本
│   ├── requirements.txt
│   └── .env.example
├── web/                         # React 前端 (Vite + TS + TailwindCSS)
│   ├── src/
│   │   ├── App.tsx              # 主应用（上传→识别→复核→导出）
│   │   ├── DashboardPanel.tsx   # 数据汇总看板（统计卡片+明细编辑）
│   │   ├── HistoryPanel.tsx     # 历史记录查询
│   │   ├── SettingsPanel.tsx    # 设置面板（自动保存）
│   │   ├── api.ts               # API 服务层
│   │   ├── i18n.ts              # 轻量 i18n 引擎
│   │   └── lang/                # 翻译文件 (zh-CN / en / sr)
│   └── package.json
├── build_desktop.py             # 一键构建桌面 .exe 脚本
├── docker-compose.yml           # Docker 一键部署
└── 文档/                         # 项目规划与样例数据
```

## 快速开始

### 方式一：本地开发（推荐用于测试）

**前置条件**：Python 3.11+、Node.js 18+、OpenAI API Key

```bash
# 1. 后端
cd ai-service
pip install -r requirements.txt
cp .env.example .env              # 编辑 .env，填入 OPENAI_API_KEY

# 方式 A：仅启动 API 服务（浏览器访问）
python -m app.main                # → http://localhost:8000

# 方式 B：启动 API + webview 原生窗口（与桌面端一致）
python launcher.py                # → 自动弹出原生窗口

# 2. 前端热重载（方式 A 时需要，方式 B 不需要）
cd web
npm install
npm run dev                       # → http://localhost:5173
```

- **方式 A**：`python -m app.main` 只启动 API，需配合前端 `npm run dev` 在浏览器中访问
- **方式 B**：`python launcher.py` 会启动 API + pywebview 原生窗口（含系统托盘），与打包后的桌面端体验一致

### 方式二：桌面应用（推荐非技术用户）

**前置条件**：Python 3.11–3.12、Node.js 18+

> ⚠️ Python 3.13+ 下 pywebview 依赖的 pythonnet 尚未适配，构建脚本会自动回退为浏览器模式。
> 要获得原生窗口体验，请使用 **Python 3.11 或 3.12** 构建。

```bash
# 一键构建（Windows，指定 Python 3.12）
py -3.12 build_desktop.py

# 如果系统默认 Python 已是 3.11–3.12，也可以直接：
# python build_desktop.py

# 产出: dist/DocAI-Pipeline/DocAI-Pipeline.exe
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

### 文档处理

| 方法     | 路径                     | 说明                  |
|--------|------------------------|---------------------|
| `POST` | `/api/classify`        | VLM 文档分类（6 种类型）     |
| `POST` | `/api/process`         | 单文档处理（自动/手动分类 → 识别） |
| `POST` | `/api/process-batch`   | 批量处理（SSE 实时进度推送）    |
| `GET`  | `/api/crop/{filename}` | 获取裁切图像（复核展示）        |

### Excel 填充

| 方法     | 路径                          | 说明                |
|--------|-----------------------------|-------------------|
| `POST` | `/api/fill`                 | 识别结果 → Excel 自动填充 |
| `GET`  | `/api/templates`            | 列出已上传的 Excel 模板   |
| `POST` | `/api/templates/{doc_type}` | 上传 Excel 模板       |
| `GET`  | `/api/download/{filename}`  | 下载填充后的文件          |

### 历史记录

| 方法       | 路径                   | 说明                 |
|----------|----------------------|--------------------|
| `GET`    | `/api/history`       | 分页查询（支持类型筛选/关键字搜索） |
| `GET`    | `/api/history/stats` | 历史数据统计             |
| `GET`    | `/api/history/{id}`  | 单条记录详情             |
| `DELETE` | `/api/history/{id}`  | 删除记录               |

### 数据汇总

| 方法       | 路径                                  | 说明              |
|----------|-------------------------------------|-----------------|
| `GET`    | `/api/summary`                      | 汇总统计（支持日期筛选）    |
| `GET`    | `/api/summary/entries`              | 明细行列表           |
| `POST`   | `/api/summary/entries`              | 手动新增明细行         |
| `PUT`    | `/api/summary/entries/{id}`         | 编辑明细行（自动记录修订历史） |
| `DELETE` | `/api/summary/entries/{id}`         | 软删除明细行          |
| `POST`   | `/api/summary/entries/{id}/restore` | 恢复软删除           |
| `GET`    | `/api/summary/entries/{id}`         | 单条明细详情          |
| `GET`    | `/api/summary/exchange-rates`       | 实时汇率查询          |

### 设置与系统

| 方法     | 路径                       | 说明                   |
|--------|--------------------------|----------------------|
| `GET`  | `/api/settings`          | 获取用户设置 & 可用模型列表      |
| `PUT`  | `/api/settings`          | 更新设置（API Key/模型/语言等） |
| `POST` | `/api/settings/test-key` | 测试 API Key 有效性       |
| `GET`  | `/api/platform`          | 平台检测（桌面 vs Web）      |
| `GET`  | `/health`                | 健康检查                 |

### 桌面专属

| 方法     | 路径                     | 说明       |
|--------|------------------------|----------|
| `GET`  | `/api/scan/devices`    | 列出可用扫描仪  |
| `POST` | `/api/scan/acquire`    | 执行扫描     |
| `GET`  | `/api/autostart`       | 获取开机自启状态 |
| `PUT`  | `/api/autostart`       | 设置开机自启   |
| `GET`  | `/api/close-behavior`  | 获取关闭窗口行为 |
| `PUT`  | `/api/close-behavior`  | 设置关闭窗口行为 |
| `POST` | `/api/reset-window`    | 重置窗口大小   |
| `GET`  | `/api/version`         | 检查更新     |
| `GET`  | `/api/auto-update`     | 获取自动更新偏好 |
| `PUT`  | `/api/auto-update`     | 设置自动更新偏好 |
| `POST` | `/api/update/download` | 触发后台下载更新 |
| `GET`  | `/api/update/status`   | 获取更新下载状态 |

完整 API 文档：启动后端后访问 `http://localhost:8000/docs`

## 技术栈

- **AI 后端**：Python, FastAPI, OpenCV, PyMuPDF, Ultralytics YOLO, OpenAI VLM (gpt-4.1-mini)
- **存储**：SQLite（WAL 模式，自动从旧版 JSON 迁移）
- **Excel 引擎**：openpyxl（保留公式、格式与数据透视表）
- **Web 前端**：React 19, TypeScript, Vite, TailwindCSS v4, Lucide Icons
- **桌面端**：PyInstaller (onedir) + pywebview + pystray 系统托盘
- **CI/CD**：GitHub Actions → 自动构建 → Release 发布
- **部署**：Docker Compose / PyInstaller 桌面 .exe / 本地开发

## 许可证

本项目仅供内部使用。开源许可采用 [GNU AGPL v3.0](https://gnu.ac.cn/licenses/agpl-3.0.html#license-text)
