# Government Scheme Navigator

An AI-powered multilingual assistant that helps Indian citizens discover government welfare schemes and check their eligibility using official scheme documents.

---

## Features (Planned)

- **Multilingual support** — queries in Hindi, Tamil, Telugu, Bengali, and more
- **Semantic search** over official government scheme documents (PDF/HTML)
- **Deterministic eligibility engine** — the LLM never makes final decisions
- **Transparent reasoning** — every eligibility result cites source documents
- **REST API** via FastAPI

---

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI + Uvicorn |
| Embeddings | Sentence Transformers (multilingual) |
| Vector Store | ChromaDB |
| PDF Parsing | PyMuPDF (fitz) |
| Data Validation | Pydantic v2 |
| Testing | pytest |
| Linting | Ruff |
| Config | pydantic-settings + `.env` |

---

## Project Structure

```
government-scheme-navigator/
├── AGENTS.md           # Architecture & coding rules
├── README.md           # This file
├── pyproject.toml      # Project metadata & dependencies
├── .env.example        # Environment variable template
├── .gitignore
├── data/
│   ├── raw/            # Source PDFs (read-only at runtime)
│   └── processed/      # Generated chunks & metadata
├── src/
│   ├── api/            # FastAPI app & routers
│   ├── agent/          # LLM orchestration & intent routing
│   ├── retrieval/      # ChromaDB search helpers
│   ├── rules/          # Deterministic eligibility engine
│   ├── ingestion/      # PDF → chunk → embed pipeline
│   └── i18n/           # Language detection & translation
├── tests/              # pytest test suite
├── evals/              # Offline evaluation datasets
└── app/                # Frontend (Phase N)
```

---

## Prerequisites

- **Python 3.11+**
- `pip` package manager
- Git

---

## Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd government-scheme-navigator
```

### 2. Create a virtual environment

```bash
python -m venv .venv

# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -e ".[dev]"
```

### 4. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your values
```

---

## Running the Application

### Development server

```bash
uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000
```

The API will be available at:
- **Health check**: `GET http://localhost:8000/health`
- **Interactive docs**: `http://localhost:8000/docs`
- **OpenAPI schema**: `http://localhost:8000/openapi.json`

---

## Running Tests

```bash
# All fast unit tests
pytest tests/ -v

# Skip slow tests (LLM / ChromaDB dependent)
pytest tests/ -v -m "not slow"

# With coverage
pytest tests/ --cov=src --cov-report=term-missing
```

---

## Linting & Formatting

```bash
# Format check
ruff format --check .

# Lint check
ruff check .

# Lint with auto-fix
ruff check . --fix
```

---

## Critical Safety Principle

> **The LLM never makes final eligibility decisions.**

All eligibility determinations are made exclusively by the deterministic Python rules engine in `src/rules/`. See [AGENTS.md](./AGENTS.md) for the full safety contract.

---

## Development Phases

| Phase | Description | Status |
|---|---|---|
| 0 | Project initialization & setup | ✅ Complete |
| 1 | PDF ingestion pipeline | Planned |
| 2 | Semantic retrieval (ChromaDB) | Planned |
| 3 | Deterministic rules engine | Planned |
| 4 | Agent layer & API | Planned |
| 5 | Multilingual support | Planned |
| 6 | Frontend | Planned |

---

## License

TBD
