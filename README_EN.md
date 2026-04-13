# DocAI Pipeline

[简体中文](README.md) | English

> Multimodal document understanding system for automated customs declaration recognition and intelligent archiving.

## Project Structure

```
DocAiPipeline/
├── ai-service/              # Python AI Service (FastAPI)
│   ├── app/
│   │   ├── preprocessing/   # PDF→Image, denoise, deskew, contrast, sharpen
│   │   ├── detection/       # YOLO document detection (fallback: full-page)
│   │   ├── extraction/      # VLM end-to-end field extraction (gpt-4.1-mini)
│   │   ├── validation/      # Rule-based validation (amounts/currency/dates/HS codes)
│   │   ├── export/          # Excel/CSV/JSON export + Invoice template auto-fill
│   │   ├── config.py        # Configuration
│   │   ├── schemas.py       # Data models
│   │   ├── pipeline.py      # Pipeline orchestrator
│   │   └── main.py          # FastAPI entry point
│   ├── requirements.txt
│   └── .env.example
├── 文档/                     # Proposals, sample data, project plan
└── README.md
```

## Quick Start

### 1. Install Dependencies

```bash
cd ai-service
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and fill in your OpenAI API Key
```

### 3. Start the Service

```bash
cd ai-service
python -m app.main
```

The service will start at `http://localhost:8000`.

### 4. API Usage

- **Health Check**: `GET /health`
- **Process Document**: `POST /process` (upload a PDF file)
- **Download Result**: `GET /download/{filename}`

API Docs: `http://localhost:8000/docs`

## Processing Pipeline

```
PDF Input → Preprocess (denoise/deskew/enhance/sharpen) → YOLO Detection → VLM Extraction → Validation → Export
                                                                                                          ↓
                                                                          Excel/CSV/JSON + Invoice Template Auto-fill
```

## Tech Stack

- **AI Service**: Python, FastAPI, OpenCV, PyMuPDF, Ultralytics YOLO, OpenAI VLM (gpt-4.1-mini)
- **Excel Processing**: openpyxl (preserves formulas and formatting)
- **Frontend**: React Web review interface (planned)

## License

This project is for internal use only.
