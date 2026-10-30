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

## Document Ingestion (Phase 1)

Official PDF documents stored in `data/raw/` are parsed, cleaned, chunked, and written to `data/processed/` as structured JSON artifacts. The original source PDFs are preserved strictly read-only.

### CLI Usage

Ingest a scheme document with explicit metadata (example using the synthetic test fixture):

```bash
python -m src.ingestion.cli \
  --pdf-path tests/fixtures/synthetic_sample_pm_kisan.pdf \
  --scheme-id pm-kisan-sample \
  --official-url "https://pmkisan.gov.in" \
  --document-version "2024-v1" \
  --chunk-size 500 \
  --chunk-overlap 100 \
  --output-dir data/processed
```

> For production ingestion, place verified official government PDFs in `data/raw/` and point `--pdf-path` to the target file.

### Python API Usage

```python
from pathlib import Path
from src.ingestion import (
    run_ingestion_pipeline,
    DocumentMetadata,
    ChunkingConfig,
)

metadata = DocumentMetadata(
    scheme_id="pm-kisan-sample",
    source_document="synthetic_sample_pm_kisan.pdf",
    official_source_url="https://pmkisan.gov.in",
    document_version="2024-v1",
)

config = ChunkingConfig(chunk_size=500, chunk_overlap=100)

doc = run_ingestion_pipeline(
    pdf_path=Path("tests/fixtures/synthetic_sample_pm_kisan.pdf"),
    metadata=metadata,
    chunk_config=config,
    output_dir=Path("data/processed"),
)

print(f"Ingested {doc.total_chunks} chunks across {doc.total_pages} pages.")
```

### Processed Output Structure

The output is saved as `data/processed/<scheme_id>.json`. Each chunk preserves full provenance:

- `scheme_id`: Identifier of the scheme.
- `source_document`: File name of the source PDF.
- `official_source_url`: Government portal URL.
- `page_number`: 1-indexed source page.
- `chunk_index`: 0-indexed sequential position across the entire document.
- `text`: Cleaned and normalized text content.
- `extraction_timestamp`: ISO 8601 UTC timestamp.
- `document_version`: Version string if provided.

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
| 1 | PDF ingestion pipeline | ✅ Complete |
| 2 | Semantic retrieval (ChromaDB) | Planned |
| 3 | Deterministic rules engine | Planned |
| 4 | Agent layer & API | Planned |
| 5 | Multilingual support | Planned |
| 6 | Frontend | Planned |

---

## License

TBD
