# DocAI Pipeline

[简体中文](README.md) | English

> VLM-powered document recognition and intelligent archiving system — covering the full lifecycle of timber import →
> processing → packaging.

## Features

| Document Type                          | Input       | Output                       |
|----------------------------------------|-------------|------------------------------|
| Import Documents (customs/tax/invoice) | Scanned PDF | Invoice Ledger               |
| Log Measurement Sheet                  | PDF / Image | Log Inventory Sheet          |
| Log Output (Dispatch) Sheet            | PDF / Image | Log Inventory Sheet (output) |
| Soak Pool Entry Sheet                  | PDF / Image | Slicing Pool & Machine Sheet |
| Slicing Machine Sheet                  | PDF / Image | Slicing Pool & Machine Sheet |
| Packing Report                         | PDF / Image | Veneer Statistics Sheet      |

**Core Flow**: Upload → VLM Auto-classify → Structured Extraction → Human Review → Excel Auto-fill → Download

**Additional Features**:

- **Dashboard** — Import / log inventory / factory processing stats with date filter, detail editing, and revision
  history
- **History** — Paginated search with filters, review reload, and full extraction detail view
- **Scanner Integration** — Import documents directly from WIA scanners on desktop (Windows)
- **Multi-language** — 中文 / English / Srpski
- **Desktop App** — PyInstaller package with native window + system tray + auto-start + auto-update

## Project Structure

```
DocAiPipeline/
├── ai-service/                  # Python Backend (FastAPI)
│   ├── app/
│   │   ├── routers/             # API routes
│   │   │   ├── process.py       #   Document processing & batch (SSE)
│   │   │   ├── fill.py          #   Excel filling & template management
│   │   │   ├── summary.py       #   Dashboard & detail CRUD
│   │   │   ├── history_router.py#   History queries
│   │   │   └── scanner.py       #   WIA scanner integration
│   │   ├── preprocessing/       # PDF→Image, denoise, deskew, enhance
│   │   ├── detection/           # YOLO document detection & multi-doc split
│   │   ├── extraction/          # VLM extractors (VLM/Log/Factory)
│   │   ├── validation/          # Rule-based validation
│   │   ├── export/              # Excel fillers (Invoice/Log/Factory)
│   │   ├── config.py            # Configuration & model list
│   │   ├── schemas.py           # Pydantic data models
│   │   ├── pipeline.py          # Import document pipeline
│   │   ├── db.py                # SQLite connection management & schema
│   │   ├── history.py           # Processing history persistence (SQLite)
│   │   ├── summary_store.py     # Summary entry CRUD (SQLite)
│   │   ├── summary_writer.py    # Processing results → summary entry conversion
│   │   └── main.py              # FastAPI entry & settings/platform/update APIs
│   ├── launcher.py              # Desktop launcher (uvicorn + pywebview + tray)
│   ├── docai.spec               # PyInstaller build config
│   ├── evaluate.py              # Accuracy evaluation script
│   ├── requirements.txt
│   └── .env.example
├── web/                         # React Frontend (Vite + TS + TailwindCSS)
│   ├── src/
│   │   ├── App.tsx              # Main app (upload→extract→review→export)
│   │   ├── DashboardPanel.tsx   # Dashboard (stat cards + detail editing)
│   │   ├── HistoryPanel.tsx     # History queries
│   │   ├── SettingsPanel.tsx    # Settings panel (auto-save)
│   │   ├── api.ts               # API service layer
│   │   ├── i18n.ts              # Lightweight i18n engine
│   │   └── lang/                # Translation files (zh-CN / en / sr)
│   └── package.json
├── build_desktop.py             # One-click desktop .exe build script
├── docker-compose.yml           # Docker one-click deployment
└── 文档/                         # Project plans & sample data
```

## Quick Start

### Option 1: Local Development (recommended for testing)

**Prerequisites**: Python 3.11+, Node.js 18+, OpenAI API Key

```bash
# 1. Backend
cd ai-service
pip install -r requirements.txt
cp .env.example .env              # Edit .env, set OPENAI_API_KEY

# Option A: API server only (browser access)
python -m app.main                # → http://localhost:8000

# Option B: API + webview native window (same as desktop)
python launcher.py                # → native window opens automatically

# 2. Frontend hot-reload (only needed for Option A)
cd web
npm install
npm run dev                       # → http://localhost:5173
```

- **Option A**: `python -m app.main` starts the API only; use `npm run dev` for the frontend in browser
- **Option B**: `python launcher.py` starts API + pywebview native window (with system tray), identical to the packaged
  desktop app

### Option 2: Desktop App (recommended for non-technical users)

**Prerequisites**: Python 3.11–3.12, Node.js 18+

> ⚠️ pywebview's dependency pythonnet does not yet support Python 3.13+. The build script will
> automatically fall back to browser mode. For native window experience, use **Python 3.11 or 3.12**.

```bash
# One-click build (Windows, specify Python 3.12)
py -3.12 build_desktop.py

# Or if your default Python is already 3.11–3.12:
# python build_desktop.py

# Output: dist/DocAI-Pipeline/DocAI-Pipeline.exe
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

### Document Processing

| Method | Path                   | Description                               |
|--------|------------------------|-------------------------------------------|
| `POST` | `/api/classify`        | VLM document classification (6 types)     |
| `POST` | `/api/process`         | Single document processing                |
| `POST` | `/api/process-batch`   | Batch processing (SSE real-time progress) |
| `GET`  | `/api/crop/{filename}` | Get cropped image (for review)            |

### Excel Filling

| Method | Path                        | Description                          |
|--------|-----------------------------|--------------------------------------|
| `POST` | `/api/fill`                 | Extraction results → Excel auto-fill |
| `GET`  | `/api/templates`            | List uploaded Excel templates        |
| `POST` | `/api/templates/{doc_type}` | Upload Excel template                |
| `GET`  | `/api/download/{filename}`  | Download filled file                 |

### History

| Method   | Path                 | Description                             |
|----------|----------------------|-----------------------------------------|
| `GET`    | `/api/history`       | Paginated list (filter by type/keyword) |
| `GET`    | `/api/history/stats` | History statistics                      |
| `GET`    | `/api/history/{id}`  | Single record detail                    |
| `DELETE` | `/api/history/{id}`  | Delete record                           |

### Dashboard

| Method   | Path                                | Description                      |
|----------|-------------------------------------|----------------------------------|
| `GET`    | `/api/summary`                      | Summary stats (date filter)      |
| `GET`    | `/api/summary/entries`              | Detail entry list                |
| `POST`   | `/api/summary/entries`              | Create manual entry              |
| `PUT`    | `/api/summary/entries/{id}`         | Update entry (auto revision log) |
| `DELETE` | `/api/summary/entries/{id}`         | Soft-delete entry                |
| `POST`   | `/api/summary/entries/{id}/restore` | Restore soft-deleted entry       |
| `GET`    | `/api/summary/entries/{id}`         | Single entry detail              |
| `GET`    | `/api/summary/exchange-rates`       | Live exchange rates              |

### Settings & System

| Method | Path                     | Description                              |
|--------|--------------------------|------------------------------------------|
| `GET`  | `/api/settings`          | Get user settings & available models     |
| `PUT`  | `/api/settings`          | Update settings (API Key/model/language) |
| `POST` | `/api/settings/test-key` | Test API Key validity                    |
| `GET`  | `/api/platform`          | Platform detection (desktop vs web)      |
| `GET`  | `/health`                | Health check                             |

### Desktop-only

| Method | Path                   | Description                        |
|--------|------------------------|------------------------------------|
| `GET`  | `/api/scan/devices`    | List available scanners            |
| `POST` | `/api/scan/acquire`    | Acquire scan                       |
| `GET`  | `/api/autostart`       | Get auto-start status              |
| `PUT`  | `/api/autostart`       | Set auto-start                     |
| `GET`  | `/api/close-behavior`  | Get close window behavior          |
| `PUT`  | `/api/close-behavior`  | Set close window behavior          |
| `POST` | `/api/reset-window`    | Reset window size                  |
| `GET`  | `/api/version`         | Check for updates                  |
| `GET`  | `/api/auto-update`     | Get auto-update preference         |
| `PUT`  | `/api/auto-update`     | Set auto-update preference         |
| `POST` | `/api/update/download` | Trigger background update download |
| `GET`  | `/api/update/status`   | Get update download status         |

Full API docs: visit `http://localhost:8000/docs` after starting the backend.

## Tech Stack

- **AI Backend**: Python, FastAPI, OpenCV, PyMuPDF, Ultralytics YOLO, OpenAI VLM (gpt-4.1-mini)
- **Storage**: SQLite (WAL mode, auto-migration from legacy JSON)
- **Excel Engine**: openpyxl (preserves formulas, formatting, and pivot tables)
- **Web Frontend**: React 19, TypeScript, Vite, TailwindCSS v4, Lucide Icons
- **Desktop**: PyInstaller (onedir) + pywebview + pystray system tray
- **CI/CD**: GitHub Actions → auto build → Release publish
- **Deployment**: Docker Compose / PyInstaller desktop .exe / Local dev

## License

This project is for internal use only. Open-source licensed
under [GNU AGPL v3.0](https://gnu.ac.cn/licenses/agpl-3.0.html#license-text)
