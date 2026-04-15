# DocAI Pipeline

[简体中文](README.md) | English

> VLM-powered document recognition and intelligent archiving system — covering the full lifecycle of timber import →
> processing → packaging.

## Features

| Document Type                          | Input       | Output                       | Status |
|----------------------------------------|-------------|------------------------------|--------|
| Import Documents (customs/tax/invoice) | Scanned PDF | Invoice Ledger               | ✅      |
| Log Measurement Sheet                  | PDF / Image | Log Inventory Sheet          | ✅      |
| Log Output (Dispatch) Sheet            | PDF / Image | Log Inventory Sheet (output) | ✅      |
| Soak Pool Entry Sheet                  | PDF / Image | Slicing Pool & Machine Sheet | ✅      |
| Slicing Machine Sheet                  | PDF / Image | Slicing Pool & Machine Sheet | ✅      |
| Packing Report                         | PDF / Image | Veneer Statistics Sheet      | ✅      |

**Core Flow**: Upload → VLM Auto-classify → Structured Extraction → Human Review → Excel Auto-fill → Download

## Project Structure

```
DocAiPipeline/
├── ai-service/                  # Python Backend (FastAPI)
│   ├── app/
│   │   ├── routers/             # API routes (process, fill)
│   │   ├── preprocessing/       # PDF→Image, denoise, deskew, enhance
│   │   ├── detection/           # YOLO document detection
│   │   ├── extraction/          # VLM extractors (VLM/Log/Factory)
│   │   ├── validation/          # Rule-based validation
│   │   ├── export/              # Excel fillers (6 types)
│   │   ├── config.py            # Configuration
│   │   ├── schemas.py           # Pydantic data models
│   │   ├── pipeline.py          # Import document pipeline
│   │   └── main.py              # FastAPI entry point
│   ├── requirements.txt
│   └── .env.example
├── web/                          # React Frontend (Vite + TS + TailwindCSS)
│   ├── src/
│   │   ├── App.tsx              # Main app (upload→extract→review→export)
│   │   └── api.ts               # API service layer
│   └── package.json
├── build_desktop.py               # One-click desktop .exe build script
├── docker-compose.yml             # Docker one-click deployment
└── 文档/                          # Project plans & sample data
```

## Quick Start

### Option 1: Local Development (recommended for testing)

**Prerequisites**: Python 3.11+, Node.js 18+, OpenAI API Key

```bash
# 1. Backend
cd ai-service
pip install -r requirements.txt
cp .env.example .env              # Edit .env, set OPENAI_API_KEY
python -m app.main                # → http://localhost:8000

# 2. Frontend (new terminal)
cd web
npm install
npm run dev                       # → http://localhost:5173
```

Open `http://localhost:5173` to test the full workflow.

### Option 2: Desktop App (recommended for non-technical users)

**Prerequisites**: Python 3.11–3.12, Node.js 18+

> ⚠️ pywebview's dependency pythonnet does not yet support Python 3.13+. The build script will
> automatically fall back to browser mode. For native window experience, use **Python 3.11 or 3.12**.

```bash
# One-click build (Windows, specify Python 3.12)
py -3.12 build_desktop.py

# Or if your default Python is already 3.11–3.12:
# python build_desktop.py

# Output: dist/DocAI-Pipeline.exe
# Double-click to run, browser opens automatically, system tray icon appears
# First run will auto-open settings panel — enter your OpenAI API Key
```

You can also run the launcher script directly (without packaging):

```bash
cd ai-service
python launcher.py               # → http://127.0.0.1:8000
```

### Option 3: Docker Deployment

```bash
# Create .env file
echo "OPENAI_API_KEY=sk-your-key" > .env

# Start
docker compose up --build

# → Frontend: http://localhost:3000
# → Backend:  http://localhost:8000
# → API Docs: http://localhost:8000/docs
```

## API Endpoints

| Method | Path                        | Description                                            |
|--------|-----------------------------|--------------------------------------------------------|
| `GET`  | `/health`                   | Health check                                           |
| `POST` | `/api/classify`             | VLM document classification (6 types)                  |
| `POST` | `/api/process`              | Unified document processing (auto/manual → extraction) |
| `POST` | `/api/fill`                 | Extraction results → Excel auto-fill                   |
| `GET`  | `/api/templates`            | List uploaded Excel templates                          |
| `POST` | `/api/templates/{doc_type}` | Upload Excel template                                  |
| `GET`  | `/api/download/{filename}`  | Download filled file                                   |

Full API docs: visit `http://localhost:8000/docs` after starting the backend.

## Tech Stack

- **AI Backend**: Python, FastAPI, OpenCV, PyMuPDF, Ultralytics YOLO, OpenAI VLM (gpt-4.1-mini)
- **Excel Engine**: openpyxl (preserves formulas, formatting, and pivot tables)
- **Web Frontend**: React 19, TypeScript, Vite, TailwindCSS v4, Lucide Icons
- **Deployment**: Docker Compose / PyInstaller desktop .exe / Local dev

## License

This project is for internal use only.
