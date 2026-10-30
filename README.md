# Government Scheme Navigator

A multilingual English/Kannada application for discovering Indian government
welfare schemes and exploring evidence from verified official documents. The
citizen-facing Streamlit app calls the FastAPI backend. Retrieval returns
extractive passages and provenance; eligibility decisions are reserved for a
deterministic, validated rules engine.

## Current capabilities and limits

- The registry API lists all registered schemes and their verification status.
  Registry membership does not mean a scheme is present in the retrieval index.
- The informational query API delegates to the Phase 2E `AnswerBuilder` and
  preserves its abstention status, evidence, and source metadata. Retrieved
  information is not an official eligibility decision.
- The citizen app supports English and Kannada interface labels, scheme
  discovery, and evidence-based questions.
- The eligibility API delegates to the Phase 3 deterministic engine and accepts
  its `CitizenProfile` schema. No production rule sets are checked in yet, so
  registered schemes currently return `unsupported_scheme` without a decision.
  Configured rules must resolve through the Phase 3 evidence sidecar to a
  matching exact-source catalogue record; invalid provenance fails closed.
- This checkout does not contain a ChromaDB index. Retrieval reports its
  unavailable/missing/empty state until a verified index is provisioned.

## Architecture

```text
Citizen browser
    │
    ▼
Streamlit UI (app/citizen_app.py)
    │ HTTP
    ▼
FastAPI (src/api/)
    │
    ├── Query orchestration → Phase 2E AnswerBuilder → ChromaDB
    ├── Scheme listing → data/scheme_registry.json
    └── Eligibility → Phase 3 deterministic engine → data/rules/<scheme_id>.json
```

`streamlit_app.py` is the Phase 1 registry demo. `streamlit_rag_app.py` is the
Phase 2E local retrieval demo. The citizen-facing app is `app/citizen_app.py`;
it consumes the API rather than implementing retrieval or eligibility.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for endpoint contracts and
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for setup and deployment preparation.

## Requirements and setup

- Python 3.11 or newer.
- Git and pip.
- The embedding model and a compatible indexed ChromaDB database are needed for
  informational answers. Health checks do not download or load the model.

From the repository root:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]" -r requirements.txt
cp .env.example .env
```

On Windows PowerShell, activate with:

```powershell
.venv\Scripts\Activate.ps1
```

`streamlit` is listed in `requirements.txt`; `pip install -e ".[dev]" -r
requirements.txt` installs it alongside the project and development extras.
Use an absolute `CHROMA_PERSIST_DIR` to select an external index location. A
relative Chroma path resolves from the repository root, independent of the
launch working directory. The default is `./data/chroma`.
Set `CORS_ORIGINS` to a JSON list of explicit browser origins if a browser
client calls FastAPI directly. The default empty allowlist is sufficient for
the Streamlit app, which calls the API server-to-server.

## Start the services

Start FastAPI from the repository root:

```bash
uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal with the same virtual environment:

```bash
streamlit run app/citizen_app.py
```

The UI reads `API_BASE_URL` from the repository `.env` file or environment;
the default is `http://127.0.0.1:8000`.

Other demos remain available:

```bash
streamlit run streamlit_app.py       # Phase 1 registry demo
streamlit run streamlit_rag_app.py   # Phase 2E local RAG demo
```

## API endpoints

Interactive OpenAPI documentation is at `http://127.0.0.1:8000/docs`.

| Method and path | Purpose |
|---|---|
| `GET /health` | Existing liveness response; preserved for compatibility |
| `GET /api/health` | Retrieval, registry, and eligibility component status |
| `GET /api/schemes` | Registry listing; optional `q`, `jurisdiction`, and `verification_status` filters |
| `POST /api/query` | Informational retrieval with official evidence and provenance |
| `POST /api/eligibility/check` | Deterministic eligibility check using a configured Phase 3 rule set |

Example informational request:

```bash
curl -X POST http://127.0.0.1:8000/api/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"What does PM-KISAN provide?","scheme_id":"central_pm_kisan"}'
```

Supported responses contain verbatim evidence passages with scheme ID, source
document, official URL, page number, document version, chunk identifiers, and
retrieval scores. Unsupported or insufficient-evidence queries return a typed
abstention. A retrieval service that is not configured returns HTTP 503.

## Ingestion and indexing

Original government documents are stored under `data/raw/` and treated as
read-only. The Phase 1 ingestion CLI creates processed document JSON; the
Phase 2 retrieval CLI indexes eligible processed documents into ChromaDB.
Consult the CLI `--help` output for available options:

```bash
python -m src.ingestion.cli --help
python -m src.retrieval.cli --help
```

Only documents that meet the retrieval indexer's verification requirements are
indexed. Scanned, legacy-font, unresolved, or otherwise unindexed sources must
not be presented as searchable. The index should be generated from verified
source artifacts and stored on a persistent volume for deployment.

## Tests and quality checks

```bash
python -m pytest tests/api -q
python -m pytest -q
ruff format --check .
ruff check .
```

Automated tests use temporary data and mocks for external services. Two PDF
tests skip when the host has no suitable Indic system font; see
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for current limitations.

## Privacy and important notice

The eligibility form sends only the fields entered by the citizen when they
submit; the application does not persist that profile. Do not enter Aadhaar
numbers, phone numbers, bank details, or other sensitive personal information.
An outcome applies only to the configured rules and is not an official
government decision or a guarantee of benefit approval. Always check the cited
source document and relevant government authority.

## Project phases

Phase 1 ingestion, Phase 2 retrieval, Phase 3 rule engine and catalogue code,
Phase 4 API, and the bilingual Phase 5 citizen UI are present in this checkout.
Phase 3 data includes no executable rule sets; the evidence catalogue and
candidate-link sidecar are empty. Real scheme eligibility outcomes therefore
remain unavailable until reviewed rule data and source evidence are supplied.
Production Phase 6 deployment and hosting are not configured.
