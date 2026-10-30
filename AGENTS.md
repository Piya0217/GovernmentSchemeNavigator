# Government Scheme Navigator — AGENTS.md

> Architecture reference, coding rules, and directory conventions for all
> human and AI contributors.

---

## 1. Project Purpose

An AI-powered multilingual assistant that helps Indian citizens:

1. **Discover** government welfare schemes relevant to their situation.
2. **Understand** scheme eligibility criteria in simple language.
3. **Self-assess** eligibility via a deterministic rules engine — _not_ an LLM.

---

## 2. Core Architecture

```
User Query (any language)
        │
        ▼
┌───────────────────┐
│   FastAPI Layer   │  src/api/
│  (REST endpoints) │
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│   Agent Layer     │  src/agent/
│  (orchestration,  │
│   intent routing) │
└────────┬──────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌──────────────────┐
│ i18n   │ │  Retrieval Layer │  src/retrieval/
│ Layer  │ │  (ChromaDB RAG,  │
│src/i18n│ │  embeddings)     │
└────────┘ └────────┬─────────┘
                    │
                    ▼
           ┌──────────────────┐
           │  Rules Engine    │  src/rules/
           │  (deterministic  │
           │  eligibility)    │
           └──────────────────┘
```

### 2.1 Ingestion Pipeline (offline)

```
Official PDF / Document
        │
        ▼
┌─────────────────────┐
│  Ingestion Layer    │  src/ingestion/
│  (PyMuPDF -> chunks │
│   -> embeddings ->  │
│   ChromaDB)         │
└─────────────────────┘
```

---

## 3. Critical Safety Rules (NON-NEGOTIABLE)

### 3.1 LLM Boundaries -- What the LLM MUST NEVER Do

| Action | LLM Allowed? | Reason |
|---|---|---|
| Make final eligibility decisions | NEVER | Must be deterministic & auditable |
| Activate rules without validation | NEVER | Rules require human review against official docs |
| Produce a positive result from missing data | NEVER | Uncertainty -> NOT eligible |
| Access external URLs or services | NEVER | Scope creep / data integrity |

### 3.2 LLM Permitted Actions

| Action | Allowed? | Notes |
|---|---|---|
| Extract _candidate_ rules from documents | Yes | Stored as `pending`, not `active` |
| Translate or rephrase scheme descriptions | Yes | Output is informational only |
| Identify relevant schemes from user query | Yes | Retrieval shortlisting only |
| Explain eligibility criteria in natural language | Yes | Must cite source document |

### 3.3 Rules Engine Contract

- All eligibility decisions are made **exclusively** by the deterministic Python
  rules engine in `src/rules/`.
- A rule must be in `status: active` (validated by a human or validation
  script against the official document) before it is applied.
- When any required field is `None` / missing -> the rule **fails** (not eligible).
- Rules are versioned. Any change increments the schema version.

### 3.4 Uncertainty Policy

> **Missing or uncertain information MUST NOT produce a positive eligibility
> result.**

If the user has not provided a required field, the engine returns:
`{"eligible": false, "reason": "insufficient_information", "missing_fields": [...]}`

---

## 4. Directory Conventions

```
government-scheme-navigator/
├── AGENTS.md           <- You are here
├── README.md           <- Setup & run instructions
├── pyproject.toml      <- Project metadata, deps, tool config
├── .env.example        <- Template for environment variables
├── .gitignore
│
├── data/
│   ├── raw/            <- Original PDF/HTML scheme documents (never modified)
│   └── processed/      <- Chunked text, metadata JSON after ingestion
│
├── src/
│   ├── ingestion/      <- PDF parsing, chunking, embedding upload
│   ├── retrieval/      <- ChromaDB client, semantic search helpers
│   ├── rules/          <- Deterministic eligibility rules engine
│   ├── agent/          <- LLM orchestration, intent routing, prompt templates
│   ├── api/            <- FastAPI app, routers, request/response schemas
│   └── i18n/           <- Translation helpers, language detection
│
├── tests/              <- pytest unit & integration tests (mirrors src/)
├── evals/              <- Offline evaluation datasets & scripts
└── app/                <- Frontend (added in a later phase)
```

### 4.1 Module Rules

- Each `src/` subdirectory **must** contain an `__init__.py`.
- Public functions must have **type hints** on all parameters and return types.
- Functions should be **small** (<= 30 lines of logic). Extract helpers freely.
- No circular imports between `src/` modules. Dependency direction:
  `api -> agent -> retrieval -> rules -> (no further deps)`
- `src/rules/` has **zero** LLM dependencies.

---

## 5. Coding Standards

| Concern | Standard |
|---|---|
| Formatter / Linter | **Ruff** (`ruff format` + `ruff check`) |
| Type checking | **mypy** (strict mode recommended) |
| Testing | **pytest** with `tests/` mirroring `src/` |
| Docstrings | Google-style |
| Python version | **3.11+** |
| Imports | Absolute only (`from src.rules.engine import ...`) |
| Secrets | **Never** hardcode. Use `.env` + `pydantic-settings` |

### 5.1 Naming Conventions

| Element | Convention | Example |
|---|---|---|
| Files & modules | `snake_case` | `rules_engine.py` |
| Classes | `PascalCase` | `EligibilityRule` |
| Functions & vars | `snake_case` | `check_eligibility()` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_RETRIES` |
| Type aliases | `PascalCase` | `SchemeId = str` |

---

## 6. Environment Variables

All configuration lives in `.env` (gitignored). See `.env.example` for the
complete reference. Load via `pydantic-settings` `BaseSettings`.

Key variables:

| Variable | Description |
|---|---|
| `APP_ENV` | `development` or `staging` or `production` |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` |
| `CHROMA_PERSIST_DIR` | Path to ChromaDB persistence directory |
| `EMBEDDING_MODEL` | HuggingFace model ID for sentence-transformers |
| `LLM_PROVIDER` | LLM provider identifier (future use) |
| `LLM_MODEL` | Model name/ID (future use) |

---

## 7. Data Governance

- `data/raw/` -- **read-only** at runtime. Only ingestion scripts write here.
- `data/processed/` -- generated artifacts, safe to delete and regenerate.
- No PII (personally identifiable information) is stored in any data directory.
- ChromaDB stores embeddings of _scheme documents_, never user data.

---

## 8. Testing Requirements

- Every public function in `src/` must have at least one test.
- Tests that require the LLM or ChromaDB must be marked `@pytest.mark.slow`
  and skipped in CI by default.
- Fast unit tests (< 2 s total) must pass before every commit.

---

## 9. Contribution Workflow

1. Create a feature branch: `feature/<short-description>`.
2. Run `ruff format . && ruff check .` -- fix all issues.
3. Run `pytest tests/ -x` -- all tests pass.
4. Open a pull request with a clear description.
5. PR must reference the relevant AGENTS.md section if adding a new component.

---

_Last updated: Phase 0 -- Project Initialization_
