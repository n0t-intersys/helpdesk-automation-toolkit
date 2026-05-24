#!/usr/bin/env python3
"""
Knowledge Base Search — TF-IDF powered search over a structured KB JSON file.

Usage:
    python kb_search.py --query "cannot connect to VPN"
    python kb_search.py --query "reset password" --top 5
    python kb_search.py --list-categories
    python kb_search.py --category "Network" --query "slow internet"
"""

import argparse
import json
import logging
import math
import re
import sys
from collections import Counter
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

KB_PATH = Path(__file__).parent / "sample_data" / "knowledge_base.json"

# ---------------------------------------------------------------------------
# Lightweight TF-IDF implementation (no external deps)
# ---------------------------------------------------------------------------

STOP_WORDS = {
    "a", "an", "the", "is", "it", "in", "on", "at", "to", "for", "of", "and",
    "or", "but", "not", "with", "from", "by", "be", "this", "that", "are",
    "was", "were", "have", "has", "had", "do", "does", "did", "will", "would",
    "can", "could", "should", "may", "might", "must", "shall", "i", "you",
    "he", "she", "we", "they", "my", "your", "our", "their", "its",
}


def tokenize(text: str) -> list[str]:
    """Lowercase, remove punctuation, remove stop words."""
    words = re.findall(r"\b[a-z]{2,}\b", text.lower())
    return [w for w in words if w not in STOP_WORDS]


def build_tfidf_index(articles: list[dict]) -> tuple[list[dict], dict[str, float]]:
    """
    Build TF-IDF vectors for all KB articles.

    Returns (enriched articles list, IDF lookup dict).
    """
    N = len(articles)
    df: dict[str, int] = Counter()

    for art in articles:
        full_text = f"{art['title']} {art['title']} {art['content']} {' '.join(art.get('tags', []))}"
        tokens = set(tokenize(full_text))
        for tok in tokens:
            df[tok] += 1

    idf: dict[str, float] = {
        term: math.log((N + 1) / (count + 1)) + 1
        for term, count in df.items()
    }

    for art in articles:
        full_text = f"{art['title']} {art['title']} {art['content']} {' '.join(art.get('tags', []))}"
        tokens = tokenize(full_text)
        tf = Counter(tokens)
        total = len(tokens) or 1
        art["_tfidf"] = {
            term: (count / total) * idf.get(term, 1.0)
            for term, count in tf.items()
        }

    return articles, idf


def cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """Compute cosine similarity between two TF-IDF sparse vectors."""
    common = set(vec_a) & set(vec_b)
    if not common:
        return 0.0
    dot = sum(vec_a[t] * vec_b[t] for t in common)
    mag_a = math.sqrt(sum(v ** 2 for v in vec_a.values()))
    mag_b = math.sqrt(sum(v ** 2 for v in vec_b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def search(
    query: str,
    articles: list[dict],
    idf: dict[str, float],
    top_k: int = 3,
    category_filter: str | None = None,
) -> list[tuple[float, dict]]:
    """Return top-k articles ranked by TF-IDF cosine similarity."""
    tokens = tokenize(query)
    tf = Counter(tokens)
    total = len(tokens) or 1
    query_vec = {
        term: (count / total) * idf.get(term, 1.0)
        for term, count in tf.items()
    }

    scored = []
    for art in articles:
        if category_filter and art.get("category", "").lower() != category_filter.lower():
            continue
        score = cosine_similarity(query_vec, art.get("_tfidf", {}))
        scored.append((score, art))

    scored.sort(key=lambda x: -x[0])
    return scored[:top_k]


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def display_results(results: list[tuple[float, dict]], query: str) -> None:
    print(f"\n{'═'*70}")
    print(f"  Search results for: \"{query}\"")
    print(f"{'═'*70}")

    if not results or results[0][0] == 0.0:
        print("  No matching articles found.\n")
        return

    for rank, (score, art) in enumerate(results, 1):
        if score < 0.01:
            continue
        bar_len = int(score * 30)
        bar = "█" * bar_len + "░" * (30 - bar_len)
        print(f"\n  [{rank}] {art['title']}")
        print(f"      Category : {art.get('category', 'General')}  |  ID: {art.get('id', '?')}")
        print(f"      Relevance: {bar} {score:.2%}")
        print(f"      Tags     : {', '.join(art.get('tags', []))}")
        print(f"\n      {art['content'][:300]}{'…' if len(art['content']) > 300 else ''}")
        if art.get("steps"):
            print(f"\n      Resolution Steps:")
            for i, step in enumerate(art["steps"][:4], 1):
                print(f"        {i}. {step}")
            if len(art["steps"]) > 4:
                print(f"        … ({len(art['steps']) - 4} more steps in full article)")
    print(f"\n{'═'*70}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="TF-IDF knowledge base search for IT helpdesk articles.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--query", "-q", type=str, help="Search query string")
    parser.add_argument("--kb", type=Path, default=KB_PATH, help="Path to KB JSON file")
    parser.add_argument("--top", type=int, default=3, help="Number of results to return")
    parser.add_argument("--category", type=str, help="Filter results by category")
    parser.add_argument("--list-categories", action="store_true", help="List all available categories")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.kb.exists():
        logger.error("Knowledge base file not found: %s", args.kb)
        logger.error("Run: python kb_search.py --kb sample_data/knowledge_base.json")
        return 1

    with args.kb.open() as fh:
        kb_data = json.load(fh)

    articles = kb_data.get("articles", kb_data) if isinstance(kb_data, dict) else kb_data
    articles, idf = build_tfidf_index(articles)
    logger.info("Indexed %d KB articles.", len(articles))

    if args.list_categories:
        cats = sorted({a.get("category", "General") for a in articles})
        print("\nAvailable categories:")
        for c in cats:
            count = sum(1 for a in articles if a.get("category") == c)
            print(f"  {c:<20} ({count} articles)")
        print()
        return 0

    if not args.query:
        logger.error("Provide --query or --list-categories")
        return 1

    results = search(args.query, articles, idf, top_k=args.top, category_filter=args.category)
    display_results(results, args.query)
    return 0


if __name__ == "__main__":
    sys.exit(main())
