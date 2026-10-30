"""Offline evaluation script for semantic retrieval benchmarks."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: S110
        pass  # noqa: S110

from src.retrieval.embedder import SentenceTransformerEmbedder
from src.retrieval.search import SchemeSearcher
from src.retrieval.store import ChromaVectorStore


def run_evaluation(
    eval_path: Path = Path("tests/fixtures/retrieval_eval.json"),
    chroma_dir: Path = Path("data/chroma"),
) -> dict[str, Any]:
    """Execute retrieval benchmark across English and Kannada query sets."""
    eval_data = json.loads(eval_path.read_text(encoding="utf-8"))

    store = ChromaVectorStore(persist_dir=chroma_dir)
    embedder = SentenceTransformerEmbedder()
    searcher = SchemeSearcher(vector_store=store, embedder=embedder)

    en_queries = [
        q
        for q in eval_data["queries"]
        if q["language"] == "en" and q["expected_schemes"]
    ]
    kn_queries = [
        q
        for q in eval_data["queries"]
        if q["language"] == "kn" and q["expected_schemes"]
    ]
    oos_queries = [q for q in eval_data["queries"] if not q["expected_schemes"]]

    def evaluate_set(queries: list[dict[str, Any]]) -> dict[str, Any]:
        hits_at_1 = 0
        hits_at_3 = 0
        reciprocal_ranks: list[float] = []
        failures: list[dict[str, Any]] = []

        for item in queries:
            q_text = item["query"]
            exp = item["expected_schemes"]
            results = searcher.search(q_text, top_k=3, max_distance=None)
            retrieved = [r.scheme_id for r in results]
            distances = [round(r.distance, 4) for r in results]

            hit_1 = bool(retrieved and retrieved[0] in exp)
            hit_3 = any(s in exp for s in retrieved)

            if hit_1:
                hits_at_1 += 1
            if hit_3:
                hits_at_3 += 1

            rr = 0.0
            for rank, s_id in enumerate(retrieved, start=1):
                if s_id in exp:
                    rr = 1.0 / rank
                    break
            reciprocal_ranks.append(rr)

            if not hit_3:
                failures.append(
                    {
                        "id": item["id"],
                        "query": q_text,
                        "expected": exp,
                        "retrieved": retrieved,
                        "distances": distances,
                    }
                )

        n = len(queries)
        hit_distances: list[float] = []
        for item in queries:
            exp = item["expected_schemes"]
            results = searcher.search(item["query"], top_k=3, max_distance=None)
            for r in results:
                if r.scheme_id in exp:
                    hit_distances.append(r.distance)
                    break

        return {
            "total": n,
            "recall_at_1": hits_at_1 / n if n else 0.0,
            "recall_at_3": hits_at_3 / n if n else 0.0,
            "mrr": sum(reciprocal_ranks) / n if n else 0.0,
            "failures": failures,
            "min_hit_distance": min(hit_distances) if hit_distances else None,
            "max_hit_distance": max(hit_distances) if hit_distances else None,
            "avg_hit_distance": sum(hit_distances) / len(hit_distances)
            if hit_distances
            else None,
        }

    en_metrics = evaluate_set(en_queries)
    kn_metrics = evaluate_set(kn_queries)

    # Evaluate out-of-scope queries with default threshold
    oos_results: list[dict[str, Any]] = []
    for item in oos_queries:
        q_text = item["query"]
        raw_res = searcher.search(q_text, top_k=3, max_distance=None)
        filtered_res = searcher.search(q_text, top_k=3, max_distance=0.60)
        oos_results.append(
            {
                "id": item["id"],
                "query": q_text,
                "raw_top_distance": raw_res[0].distance if raw_res else None,
                "raw_top_scheme": raw_res[0].scheme_id if raw_res else None,
                "returned_count_with_threshold": len(filtered_res),
            }
        )

    return {
        "english": en_metrics,
        "kannada": kn_metrics,
        "out_of_scope": oos_results,
    }


def main() -> None:
    results = run_evaluation()
    en = results["english"]
    kn = results["kannada"]

    print("=" * 60)
    print("RETRIEVAL EVALUATION RESULTS")
    print("=" * 60)
    print(f"English (N={en['total']}):")
    print(f"  Recall@1: {en['recall_at_1']:.4f} ({en['recall_at_1'] * 100:.1f}%)")
    print(f"  Recall@3: {en['recall_at_3']:.4f} ({en['recall_at_3'] * 100:.1f}%)")
    print(f"  MRR:      {en['mrr']:.4f}")
    if en["min_hit_distance"] is not None:
        en_dist = (
            f"  Hit Distances: min={en['min_hit_distance']:.4f},"
            f" max={en['max_hit_distance']:.4f},"
            f" avg={en['avg_hit_distance']:.4f}"
        )
        print(en_dist)

    if en["failures"]:
        print("\n  Failed English Queries:")
        for f in en["failures"]:
            print(f"    - [{f['id']}] '{f['query']}'")
            got = f["retrieved"]
            dist = f["distances"]
            print(f"      Expected: {f['expected']} | Got: {got} (Dist: {dist})")

    print(f"\nKannada (N={kn['total']}):")
    print(f"  Recall@1: {kn['recall_at_1']:.4f} ({kn['recall_at_1'] * 100:.1f}%)")
    print(f"  Recall@3: {kn['recall_at_3']:.4f} ({kn['recall_at_3'] * 100:.1f}%)")
    print(f"  MRR:      {kn['mrr']:.4f}")
    if kn["min_hit_distance"] is not None:
        kn_dist = (
            f"  Hit Distances: min={kn['min_hit_distance']:.4f},"
            f" max={kn['max_hit_distance']:.4f},"
            f" avg={kn['avg_hit_distance']:.4f}"
        )
        print(kn_dist)

    if kn["failures"]:
        print("\n  Failed Kannada Queries:")
        for f in kn["failures"]:
            print(f"    - [{f['id']}] '{f['query']}'")
            got = f["retrieved"]
            dist = f["distances"]
            print(f"      Expected: {f['expected']} | Got: {got} (Dist: {dist})")

    print("\nOut-of-Scope Query Distances:")
    for o in results["out_of_scope"]:
        dist_val = f"{o['raw_top_distance']:.4f}"
        scheme = o["raw_top_scheme"]
        print(f"  - [{o['id']}] '{o['query']}' -> Raw min dist: {dist_val} ({scheme})")
    print("=" * 60)


if __name__ == "__main__":
    main()
