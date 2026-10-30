# Architecture and API contracts

## Data flow

```text
Official PDFs → Phase 1 extraction/cleaning/chunking → processed JSON
       → Phase 2 embedding/indexing → persistent ChromaDB

Streamlit citizen UI → FastAPI → (scheme registry | AnswerBuilder)

FastAPI eligibility endpoint → Phase 3 EligibilityService adapter → deterministic rules engine
```

The FastAPI query route delegates to the existing `AnswerBuilder`. Evidence
filtering, reranking, abstention, and passage provenance stay in `src/retrieval`.
The API does not create factual claims or citations. The UI displays the
retrieval response's passage text, scheme ID, source document, official URL,
page, version, chunk ID/index, distance, similarity, and rerank score.

## API

### `GET /health`

Legacy liveness response with `status`, `version`, and `service`. This contract
is preserved.

### `GET /api/health`

Returns `status` (`ok` or `degraded`), `version`, `service`, and component
fields `retrieval`, `eligibility`, and `scheme_registry`. Retrieval reports
`ready`, `collection_missing`, `collection_empty`, or `unavailable`. Health
inspects the existing `scheme_chunks` collection and one stored text/metadata
record. It does not create a collection or load the embedding model.

### `GET /api/schemes`

Returns registry `version`, `last_updated`, `total`, and `schemes`. Optional
filters are `q`, `jurisdiction` (`central` or `state`), and the registry's
`verification_status`. Nullable source/document fields and registry statuses
are preserved. The endpoint reports registry entries; it does not guarantee
that each scheme is in the live index.

### `POST /api/query`

Request:

```json
{"query":"What does PM-KISAN provide?","scheme_id":"central_pm_kisan"}
```

`scheme_id` is optional. The response uses the existing Phase 2E
`AnswerResponse`: query, status (`supported`, `insufficient_evidence`, or
`out_of_scope`), passages, abstention reason, `eligibility_assessed`, and
detected scheme ID. Passage fields are defined by
`src/retrieval/answer.py::EvidencePassage`. A retrieval service that is not
configured returns HTTP 503; retrieval's own abstentions are returned without
reconstruction.

### `POST /api/eligibility/check`

Accepts `scheme_id` and the Phase 3 `CitizenProfile` fields (`age`,
`annual_income`, `occupation`, `state`, `district`, `gender`, and
`household_size`). The API loads a Phase 3 `EligibilityRuleSet` from
`data/rules/<scheme_id>.json` and delegates evaluation to
`src.rules.engine.evaluate_eligibility`. Missing rule files return
`unsupported_scheme` with `eligible: false`; the API does not infer criteria.
The JSON file must match the Phase 3 `EligibilityRuleSet` model and use
`RULE_SCHEMA_VERSION` (`1.0.0`). `evaluate_eligibility` runs structural
`validate_rule_set` checks, then the rule evaluator enforces activation
validation. Production rules must be reviewed, `ACTIVE`, and carry matching
approval metadata and source provenance (document ID, URL, version, and page).
Before invoking the engine, the eligibility adapter loads the Phase 3
`SchemeRegistry`, `EvidenceCatalogue`, and `RuleEvidenceSidecar` schemas and
runs the Phase 3 `validate_catalogue` cross-reference validator. Because
`EligibilityRule` has no `evidence_id` field, each rule must have a sidecar
link; the adapter resolves that link to exactly one `EvidenceRecord` matching
the rule's scheme, document, version, page, optional section, and excerpt hash.
The record must be non-synthetic exact source text. Its registry document must
match the provenance URL/version and have source identity confirmed and content
reviewed. The catalogue model verifies the excerpt hash against the stored
excerpt. Rule citations are returned only after these checks pass.
Missing or inconsistent evidence returns HTTP 503 and the engine is not called.
The sidecar's `PENDING` label describes its candidate-link schema; it does not
make a rule executable. Only the rules engine's `ACTIVE` status and approval
validation control execution.
Configured results retain the engine outcome, per-rule outcomes, missing
fields, explanations, and provenance citations (document ID, source URL,
document version, page, section, excerpt hash). `PENDING`, `REVIEWED`, and
`RETIRED` rules remain non-executable under the engine; they cannot yield a
positive result.

## Safety and data handling

- Retrieval is informational and does not make eligibility decisions.
- Only the actual Phase 3 deterministic engine may decide eligibility; only
  executable, validated rules may be used.
- Missing or uncertain profile data must not lead to a positive result.
- Answers must retain source evidence. If evidence is insufficient, present the
  API abstention rather than filling gaps.
- The UI collects only the optional Phase 3 profile fields and sends them when
  the user submits the eligibility form. The app does not persist these fields;
  users must not enter personal identifiers.

## Current limitations

- No production rule sets are present under `data/rules/`. The Phase 3 evidence
  catalogue and candidate evidence sidecar currently contain empty arrays, so
  registered schemes remain `unsupported_scheme`.
- Rule files are discovered by the exact `<scheme_id>.json` filename under
  `data/rules/`; Pydantic schema validation happens on load and Phase 3
  structural validation runs in the engine. Readiness checks also reject
  structurally invalid sets, filename/scheme mismatches, and `ACTIVE` rules
  with invalid approval metadata or invalid catalogue provenance. Invalid JSON,
  model data, or evidence references return a service error. Structurally
  invalid rule instances that reach the engine fail closed as
  `NEEDS_MORE_INFORMATION`.
- Runtime provenance checks establish catalogue consistency, not independent
  source truth. Review/identity statuses and approval metadata are trusted
  curation fields; they do not authenticate reviewer identity or prove that a
  source is current. Production rule data still needs human review and genuine
  official-source evidence.
- Registry records do not contain scheme-domain categories or per-scheme index
  membership. The UI filters registry search by name and jurisdiction and
  preserves verification status; it does not invent categories.
- A real ChromaDB index is not checked into this repository. Provision one
  before expecting supported retrieval responses.
