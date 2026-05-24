#!/usr/bin/env python3
"""
Ticket Classifier — Auto-categorizes IT support tickets using keyword matching
and a Naive Bayes ML classifier trained on sample data.

Usage:
    python ticket_classifier.py --input sample_data/tickets.json
    python ticket_classifier.py --text "Cannot connect to VPN after password reset"
    python ticket_classifier.py --train --input sample_data/tickets.json
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Category definitions with weighted keyword lists
# ---------------------------------------------------------------------------
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "security_incident": [
        "ransomware", "malware", "virus", "phishing", "breach", "hack",
        "compromised", "suspicious", "unauthorized", "intrusion", "cryptolocker",
        "credential theft", "data leak", "crowdstrike alert", "incident",
        "infected", "trojan", "spyware", "rootkit", "exploit",
    ],
    "access_management": [
        "access", "permission", "login", "password", "reset", "unlock",
        "vpn", "mfa", "two-factor", "account", "active directory", "ad account",
        "sharepoint", "privilege", "admin rights", "role", "group policy",
        "authentication", "sso", "oauth", "ldap", "rbac",
    ],
    "hardware": [
        "screen", "monitor", "keyboard", "mouse", "laptop", "desktop",
        "printer", "scanner", "dock", "docking station", "battery",
        "hard drive", "ssd", "ram", "memory", "cpu", "overheating",
        "black screen", "flickering", "pixel", "display", "port",
    ],
    "software": [
        "software", "application", "app", "crash", "error", "install",
        "update", "upgrade", "license", "office", "windows", "macos",
        "outlook", "excel", "word", "teams", "zoom", "browser",
        "dll", "corrupt", "unresponsive", "freeze", "blue screen", "bsod",
    ],
    "network": [
        "network", "internet", "wifi", "ethernet", "bandwidth", "slow",
        "connectivity", "ip address", "dns", "dhcp", "firewall", "proxy",
        "drive mapping", "shared drive", "file server", "nas", "switch",
        "router", "vlan", "ping", "latency", "packet loss",
    ],
}

PRIORITY_SCORES: dict[str, int] = {
    "security_incident": 10,
    "access_management": 6,
    "network": 5,
    "hardware": 4,
    "software": 3,
}


# ---------------------------------------------------------------------------
# Keyword-based classifier
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Lowercase and strip punctuation for matching."""
    return re.sub(r"[^\w\s]", " ", text.lower())


def classify_by_keywords(text: str) -> tuple[str, dict[str, int]]:
    """
    Score a ticket text against each category's keyword list.

    Returns the winning category and the full score breakdown.
    """
    normalized = _normalize(text)
    scores: dict[str, int] = {cat: 0 for cat in CATEGORY_KEYWORDS}

    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in normalized:
                # Multi-word matches weighted higher
                scores[category] += 2 if " " in kw else 1

    best = max(scores, key=lambda c: scores[c])
    if scores[best] == 0:
        best = "software"  # default fallback
    return best, scores


# ---------------------------------------------------------------------------
# Optional sklearn ML classifier
# ---------------------------------------------------------------------------

def build_ml_classifier() -> Optional[object]:
    """
    Build a Naive Bayes classifier using sklearn if available.
    Returns None if sklearn is not installed.
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.naive_bayes import ComplementNB
        from sklearn.pipeline import Pipeline
    except ImportError:
        logger.warning("sklearn not installed — ML classifier unavailable. "
                       "Falling back to keyword matching only.")
        return None

    # Minimal training corpus; production systems would use a labelled dataset
    training_data = [
        ("ransomware detected on workstation files encrypted crowdstrike alert", "security_incident"),
        ("phishing email suspicious sender credential harvest link", "security_incident"),
        ("malware trojan virus infected endpoint breach unauthorized access", "security_incident"),
        ("cannot login vpn password expired active directory account locked", "access_management"),
        ("need access sharepoint permission group policy admin rights mfa reset", "access_management"),
        ("new hire account setup active directory email license provisioning", "access_management"),
        ("laptop screen flickering black display monitor external", "hardware"),
        ("printer offline hp laserjet not responding paper jam toner", "hardware"),
        ("keyboard mouse dock battery hard drive ssd overheating ram", "hardware"),
        ("microsoft office crashes error dll corrupt word excel outlook", "software"),
        ("application cannot start windows update blue screen bsod install", "software"),
        ("zoom teams license software upgrade unresponsive freeze browser", "software"),
        ("network drive not mapping file server shared dns dhcp connectivity", "network"),
        ("vpn slow wifi ethernet bandwidth latency packet loss internet", "network"),
        ("switch router vlan firewall proxy ip address ping connectivity", "network"),
    ]

    texts, labels = zip(*training_data)
    clf = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1)),
        ("nb", ComplementNB()),
    ])
    clf.fit(texts, labels)
    logger.info("ML classifier trained successfully.")
    return clf


def classify_ticket(ticket: dict, ml_clf=None) -> dict:
    """
    Classify a single ticket dict, combining keyword + ML signals.

    Returns enriched ticket with 'category', 'confidence', 'scores'.
    """
    text = f"{ticket.get('subject', '')} {ticket.get('body', '')}"

    kw_category, kw_scores = classify_by_keywords(text)

    if ml_clf is not None:
        ml_category = ml_clf.predict([text])[0]
        # Merge: ML result overrides keyword if scores are tied
        kw_top_score = kw_scores[kw_category]
        if kw_top_score <= 1:
            final_category = ml_category
            method = "ml"
        else:
            final_category = kw_category
            method = "keyword"
    else:
        final_category = kw_category
        method = "keyword"

    priority_boost = PRIORITY_SCORES.get(final_category, 3)
    confidence = min(100, kw_scores[kw_category] * 10) if kw_scores[kw_category] > 0 else 30

    return {
        **ticket,
        "category": final_category,
        "confidence_pct": confidence,
        "classification_method": method,
        "priority_score": priority_boost,
        "keyword_scores": kw_scores,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Auto-classify IT support tickets by category.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", type=Path, help="JSON file with ticket array")
    group.add_argument("--text", type=str, help="Classify a single text string")
    parser.add_argument("--output", type=Path, help="Write results to JSON file")
    parser.add_argument("--no-ml", action="store_true", help="Disable sklearn ML classifier")
    parser.add_argument("--verbose", action="store_true", help="Show keyword score breakdown")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    ml_clf = None
    if not args.no_ml:
        ml_clf = build_ml_classifier()

    if args.text:
        fake_ticket = {"id": "ADHOC", "subject": args.text, "body": ""}
        result = classify_ticket(fake_ticket, ml_clf)
        print(f"\n{'─'*50}")
        print(f"  Category : {result['category'].upper()}")
        print(f"  Confidence: {result['confidence_pct']}%")
        print(f"  Method   : {result['classification_method']}")
        if args.verbose:
            print(f"  Scores   : {result['keyword_scores']}")
        print(f"{'─'*50}\n")
        return 0

    if not args.input.exists():
        logger.error("Input file not found: %s", args.input)
        return 1

    with args.input.open() as fh:
        tickets: list[dict] = json.load(fh)

    results = []
    category_counts: dict[str, int] = {}

    for ticket in tickets:
        classified = classify_ticket(ticket, ml_clf)
        results.append(classified)
        category_counts[classified["category"]] = (
            category_counts.get(classified["category"], 0) + 1
        )
        logger.info(
            "[%s] %s → %s (%.0f%% confidence, %s)",
            classified["id"],
            classified.get("subject", "")[:50],
            classified["category"].upper(),
            classified["confidence_pct"],
            classified["classification_method"],
        )

    print(f"\n{'═'*60}")
    print(f"  CLASSIFICATION SUMMARY  ({len(results)} tickets)")
    print(f"{'═'*60}")
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        bar = "█" * count
        print(f"  {cat:<22} {bar} ({count})")
    print(f"{'═'*60}\n")

    if args.output:
        with args.output.open("w") as fh:
            json.dump(results, fh, indent=2)
        logger.info("Results written to %s", args.output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
