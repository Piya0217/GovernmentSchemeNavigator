# Local run, demo, and deployment preparation

## Local demo

1. Create and activate a Python 3.11+ virtual environment. Install from the
   repository root:

   ```bash
   python -m pip install -e ".[dev]" -r requirements.txt
   cp .env.example .env
   ```

2. Prepare the processed documents and ChromaDB index using the Phase 1 and
   Phase 2 CLIs. Set `CHROMA_PERSIST_DIR` to the index directory. Relative paths
   resolve from the repository root; absolute paths are preserved.

3. Start the API in one terminal:

   ```bash
   uvicorn src.api.main:app --host 127.0.0.1 --port 8000
   ```

4. Start the citizen UI in another terminal:

   ```bash
   streamlit run app/citizen_app.py
   ```

5. Open the Streamlit URL printed by the command. Visit `GET /health`,
   `GET /api/health`, and `/docs` on the API to inspect readiness and contracts.
   Try an English question and a Kannada question. Supported answers display
   verbatim passages and source/page links; unsupported questions should show
   the retrieval abstention.

The first actual retrieval query may load the configured Sentence Transformers
model into memory (and may require that model to already be cached or obtainable
by the runtime). Health checks do not load it.

## Environment configuration

- `API_BASE_URL`: FastAPI URL consumed by the Streamlit server; default is
  `http://127.0.0.1:8000`.
- `API_HOST`, `API_PORT`: FastAPI bind configuration documented in `.env.example`.
- `CHROMA_PERSIST_DIR`: persistent ChromaDB directory. It must contain the
  `scheme_chunks` collection with usable indexed content.
- `EMBEDDING_MODEL`: must match the model used to create the index.
- `APP_ENV`, `LOG_LEVEL`: runtime environment and logging level.

Do not commit `.env`, credentials, citizen information, Chroma databases,
processed personal data, model files, or virtual environments.

## Deployment topology

Deploy FastAPI and Streamlit as separate services. Set `API_BASE_URL` in the
Streamlit service to the backend's HTTPS URL. Mount a persistent volume for the
Chroma index on the backend and set `CHROMA_PERSIST_DIR` to that mount. Ensure
the index was built with the configured embedding model and verified source
documents. Keep the index private to the backend; do not place it in the UI
artifact or source repository.

Streamlit makes server-side HTTP requests to FastAPI, so browser CORS is not
needed for this topology. If a browser client calls FastAPI directly, set
`CORS_ORIGINS` to a JSON array of explicit allowed origins. The default is an
empty allowlist. Terminate TLS at the hosting platform or trusted reverse
proxy. Set service health checks to `/api/health`; a degraded retrieval status
means query support is not ready.

## Current deployment blockers

- There is no indexed ChromaDB artifact or configured persistent-volume
  deployment in this checkout.
- No production rule sets are available in `data/rules/`; the eligibility API
  correctly reports registered schemes as unsupported until reviewed rules are
  supplied. The evidence catalogue and candidate-link sidecar are empty.
- At runtime, each configured rule must resolve through the Phase 3 evidence
  sidecar to an exact-source catalogue record and a matching reviewed registry
  document. Invalid or missing references make eligibility unavailable; they
  never produce an ineligible result. Approval and source-review metadata are
  curation assertions, not authenticated identity or currentness checks.
- No hosting provider or production domain has been selected. This document
  describes the service topology and required settings, not a completed or
  deployed production service.
