# DocAI Pipeline

基于多模态文档理解的报关单自动识别与智能归档系统

## 项目结构

```
DocAiPipeline/
├── ai-service/              # Python AI 服务 (FastAPI)
│   ├── app/
│   │   ├── preprocessing/   # PDF→图像、去噪、校正、对比度增强
│   │   ├── detection/       # YOLO 单据检测与裁切
│   │   ├── extraction/      # VLM 端到端字段抽取
│   │   ├── validation/      # 规则校验（金额/币种/日期等）
│   │   ├── export/          # Excel/CSV/JSON 导出
│   │   ├── config.py        # 配置管理
│   │   ├── schemas.py       # 数据模型
│   │   ├── pipeline.py      # 管线编排
│   │   └── main.py          # FastAPI 入口
│   ├── requirements.txt
│   └── .env.example
├── 文档/                     # 提案与样例数据
└── README.md
```

## 快速开始

### 1. 安装依赖

```bash
cd ai-service
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的 OpenAI API Key
```

### 3. 启动服务

```bash
cd ai-service
python -m app.main
```

服务将在 `http://localhost:8000` 启动。

### 4. API 使用

- **健康检查**: `GET /health`
- **处理文档**: `POST /process` (上传 PDF 文件)
- **下载结果**: `GET /download/{filename}`

API 文档: `http://localhost:8000/docs`

## 处理管线

```
PDF 输入 → 预处理(去噪/校正) → YOLO 单据检测 → VLM 字段抽取 → 规则校验 → Excel/CSV/JSON 导出
```

## 技术栈

- **AI 服务**: Python, FastAPI, OpenCV, PyMuPDF, Ultralytics YOLO, OpenAI VLM
- **后端编排**: Java + Spring Boot (后续)
- **前端**: React Web 复核界面 (后续)
