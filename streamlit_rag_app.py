"""Government Scheme Navigator - Local RAG & Evidence Retrieval Interface.

Local Streamlit application for grounded question answering across indexed
government scheme documents.

Safety & Integrity Rules (AGENTS.md):
- NEVER determines eligibility.
- Always displays 'Eligibility not assessed — deterministic rules engine
  pending Phase 3.'
- All answers are extractive verbatim passages directly cited from official PDFs.
- No LLM generation or hallucination is permitted.
- Out-of-scope and ambiguous queries trigger explicit, safe abstentions.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import streamlit as st

logger = logging.getLogger("scheme_navigator.streamlit_rag")

# ---------------------------------------------------------------------------
# Configuration & Constants
# ---------------------------------------------------------------------------

PAGE_TITLE = "Government Scheme Navigator — Grounded Retrieval"
PAGE_ICON = "🇮🇳"
CHROMA_DIR = Path("data/chroma")
REGISTRY_PATH = Path("data/scheme_registry.json")

# Date cutoff for labeling documents as historical (older than 3 years)
HISTORICAL_YEAR_CUTOFF = 2023


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    """Load the scheme registry safely.

    Args:
        path: Path to scheme_registry.json.

    Returns:
        Dictionary mapping scheme_id to scheme metadata dict.
    """
    if not path.is_file():
        logger.warning("Scheme registry not found at %s", path)
        return {}

    try:
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
        schemes = data.get("schemes", [])
        return {s["scheme_id"]: s for s in schemes if "scheme_id" in s}
    except Exception as err:
        logger.error("Failed to parse scheme registry: %s", err)
        return {}


def is_historical_document(pub_date: str | None) -> bool:
    """Determine whether a document's effective date is historical.

    Args:
        pub_date: ISO date string (e.g. '2020-03-29') or None.

    Returns:
        True if the publication year is strictly before HISTORICAL_YEAR_CUTOFF.
    """
    if not pub_date:
        return False
    try:
        year = int(pub_date.split("-")[0])
        return year < HISTORICAL_YEAR_CUTOFF
    except (ValueError, IndexError):
        return False


def get_status_badge(status: str) -> tuple[str, str]:
    """Return UI label and color type for an answer response status.

    Args:
        status: One of 'supported', 'insufficient_evidence', 'out_of_scope'.

    Returns:
        Tuple of (badge_label, alert_type) where alert_type is 'success',
        'warning', or 'error'.
    """
    if status == "supported":
        return "🟢 Supported by Official Documents", "success"
    if status == "out_of_scope":
        return "🔴 Question Out of Scope", "error"
    return "🟡 Insufficient Evidence in Indexed Documents", "warning"


# ---------------------------------------------------------------------------
# Cached Resource Initialization
# ---------------------------------------------------------------------------


@st.cache_resource(show_spinner="Initializing embedding model and vector store...")
def get_answer_builder(
    chroma_dir_str: str = "data/chroma",
) -> Any | None:  # noqa: ANN401
    """Initialize and cache the AnswerBuilder with ChromaDB and Embedder.

    Returns:
        Configured AnswerBuilder instance, or None if index is missing.
    """
    chroma_path = Path(chroma_dir_str)
    if not chroma_path.exists() or not (chroma_path / "chroma.sqlite3").exists():
        logger.warning("Local ChromaDB index not found at %s", chroma_path)
        return None

    try:
        from src.retrieval.answer import AnswerBuilder
        from src.retrieval.embedder import SentenceTransformerEmbedder
        from src.retrieval.search import SchemeSearcher
        from src.retrieval.store import ChromaVectorStore

        store = ChromaVectorStore(persist_dir=chroma_path)
        embedder = SentenceTransformerEmbedder()
        searcher = SchemeSearcher(vector_store=store, embedder=embedder)
        return AnswerBuilder(searcher=searcher, top_k=5)
    except Exception as err:
        logger.error("Failed to initialize AnswerBuilder: %s", err)
        return None


# ---------------------------------------------------------------------------
# Main Application UI
# ---------------------------------------------------------------------------


def main() -> None:
    """Render the local Streamlit Grounded Retrieval interface."""
    st.set_page_config(
        page_title=PAGE_TITLE,
        page_icon=PAGE_ICON,
        layout="wide",
    )

    st.title(f"{PAGE_ICON} {PAGE_TITLE}")
    st.caption(
        "Local RAG exploration interface with deterministic evidence validation "
        "and source transparency."
    )

    # Mandatory AGENTS.md safety banner
    st.warning(
        "🛡️ **Eligibility Policy**: Eligibility is **NOT assessed** by this "
        "retrieval layer. Final eligibility self-assessment will be provided in "
        "Phase 3 by a deterministic Python rules engine. Output below contains "
        "verbatim evidence passages only."
    )

    # Check index availability
    builder = get_answer_builder(str(CHROMA_DIR))
    registry = load_registry(REGISTRY_PATH)

    if builder is None:
        st.error(
            f"⚠️ **Local ChromaDB index not found at `{CHROMA_DIR}`.**\n\n"
            "Please run the indexing pipeline before launching this interface:\n"
            "```bash\n"
            "python -m src.retrieval.cli index\n"
            "```"
        )
        st.stop()

    # Sidebar: Scheme Coverage & Source Transparency
    with st.sidebar:
        st.header("Covered Schemes (Phase 2)")
        st.caption("Indexed from verified digital-text government PDFs:")
        for s_id, s_info in registry.items():
            if s_info.get("verification_status") == "verified_digital_text":
                with st.expander(s_info.get("scheme_name", s_id), expanded=False):
                    st.write(f"**Authority**: {s_info.get('issuing_authority')}")
                    pub_date = s_info.get("publication_or_effective_date")
                    if is_historical_document(pub_date):
                        st.caption(f"⏳ Historical PDF: {pub_date}")
                    else:
                        st.caption(f"📅 Effective: {pub_date}")
                    st.markdown(
                        f"[Official Source PDF]({s_info.get('official_source_url')})"
                    )

        st.divider()
        st.info(
            "**Language Support**: English and Kannada (ಕನ್ನಡ).\n"
            "Kannada queries are analyzed and expanded with verified domain intent."
        )

    # Main Input Form
    st.subheader("Ask a Scheme Question")

    # Sample query quick-select buttons
    st.write("Or try a sample question:")
    col1, col2, col3, col4 = st.columns(4)
    sample_query = None

    if col1.button("PM-KISAN Benefits", use_container_width=True):
        sample_query = "What does PM-KISAN provide?"
    if col2.button("ISRO Job (OOS Test)", use_container_width=True):
        sample_query = "How do I apply for an ISRO job?"
    if col3.button("Kannada Farmer Support", use_container_width=True):
        sample_query = "ರೈತರಿಗೆ ಆರ್ಥಿಕ ನೆರವು ನೀಡುವ ಯೋಜನೆ ಯಾವುದು?"
    if col4.button("Kannada License (OOS Test)", use_container_width=True):
        sample_query = "ಡ್ರೈವಿಂಗ್ ಲೈಸೆನ್ಸ್ ಹೇಗೆ ಪಡೆಯುವುದು?"

    query_input = st.text_input(
        "Enter your question in English or Kannada:",
        value=sample_query or "",
        placeholder=(
            "e.g. What does PM-KISAN provide? or ರೈತರಿಗೆ ಆರ್ಥಿಕ ನೆರವು ನೀಡುವ ಯೋಜನೆ ಯಾವುದು?"
        ),
        key="rag_query_input",
    )

    scheme_options = ["Auto-Detect (Search All Schemes)"] + list(registry.keys())
    selected_scheme_label = st.selectbox(
        "Filter by Scheme (Optional):",
        options=scheme_options,
        index=0,
        help="Leave on Auto-Detect for natural bilingual scheme routing.",
    )

    scheme_filter = (
        None
        if selected_scheme_label == "Auto-Detect (Search All Schemes)"
        else selected_scheme_label
    )

    if st.button("Search Official Evidence", type="primary"):
        if not query_input.strip():
            st.error("Please enter a question to search.")
            return

        with st.spinner("Analyzing query and retrieving verified passages..."):
            response = builder.answer(query=query_input, scheme_id=scheme_filter)

        badge_text, alert_type = get_status_badge(response.status)

        # Status Display
        if alert_type == "success":
            st.success(f"### {badge_text}")
        elif alert_type == "warning":
            st.warning(f"### {badge_text}")
        else:
            st.error(f"### {badge_text}")

        if response.detected_scheme_id:
            scheme_title = registry.get(response.detected_scheme_id, {}).get(
                "scheme_name", response.detected_scheme_id
            )
            st.info(
                f"🎯 **Identified Scheme**: {scheme_title} "
                f"(`{response.detected_scheme_id}`)"
            )

        # Handle Abstentions
        if response.status != "supported":
            st.markdown(f"**Abstention Reason**: {response.abstention_reason}")
            if response.status == "out_of_scope":
                st.caption(
                    "This system is specialized exclusively for Indian government "
                    "welfare schemes (PM-KISAN, Ayushman Bharat PM-JAY, "
                    "PM Vishwakarma, and Sukanya Samriddhi Yojana)."
                )
            return

        # Display Extractive Passages
        st.subheader(f"Evidence Passages ({len(response.passages)} retrieved)")
        st.caption(
            "Verbatim extracts from official government documents, ordered by "
            "question-intent relevance."
        )

        for idx, passage in enumerate(response.passages, start=1):
            scheme_meta = registry.get(passage.scheme_id, {})
            scheme_display_name = scheme_meta.get("scheme_name", passage.scheme_id)
            pub_date = scheme_meta.get(
                "publication_or_effective_date", passage.document_version
            )
            is_historical = is_historical_document(pub_date)

            with st.container(border=True):
                col_title, col_meta = st.columns([3, 1])
                with col_title:
                    st.markdown(f"#### [{idx}] {scheme_display_name}")
                with col_meta:
                    if is_historical:
                        st.warning(f"⏳ Historical ({pub_date})", icon="⚠️")
                    elif pub_date:
                        st.info(f"📅 Version: {pub_date}")

                # Verbatim passage
                st.markdown(f"> {passage.passage_text}")

                # Detailed Provenance
                st.divider()
                p_col1, p_col2, p_col3 = st.columns(3)
                with p_col1:
                    st.caption(f"📄 **Document**: `{passage.source_document}`")
                    st.caption(
                        f"📑 **Location**: Page {passage.page_number} "
                        f"(Chunk #{passage.chunk_index})"
                    )
                with p_col2:
                    st.caption(f"🎯 **Vector Distance**: `{passage.distance:.4f}`")
                    if passage.rerank_score is not None:
                        st.caption(f"⚡ **Rerank Score**: `{passage.rerank_score:.4f}`")
                    else:
                        st.caption(
                            f"⚡ **Similarity Score**: `{passage.similarity_score:.4f}`"
                        )
                with p_col3:
                    st.markdown(
                        f"[🔗 Open Official Source PDF]({passage.official_source_url})"
                    )
                    st.caption(f"🆔 `{passage.chunk_id}`")


if __name__ == "__main__":
    main()
