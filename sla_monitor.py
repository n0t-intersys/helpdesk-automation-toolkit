#!/usr/bin/env python3
"""
SLA Monitor — Tracks ticket age against SLA tiers and flags breaches.

SLA Tiers:
    P1 — Critical:  Response 15 min | Resolution 4 hrs
    P2 — High:      Response 1 hr   | Resolution 8 hrs
    P3 — Medium:    Response 4 hrs  | Resolution 24 hrs
    P4 — Low:       Response 8 hrs  | Resolution 72 hrs

Usage:
    python sla_monitor.py --input sample_data/tickets.json
    python sla_monitor.py --input sample_data/tickets.json --output report.csv
    python sla_monitor.py --input sample_data/tickets.json --as-of "2025-01-15T16:00:00Z"
"""

import argparse
import csv
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SLA definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SLATier:
    name: str
    response_minutes: int
    resolution_hours: int

    @property
    def response_delta(self) -> timedelta:
        return timedelta(minutes=self.response_minutes)

    @property
    def resolution_delta(self) -> timedelta:
        return timedelta(hours=self.resolution_hours)


SLA_TIERS: dict[str, SLATier] = {
    "P1": SLATier("Critical",  response_minutes=15,  resolution_hours=4),
    "P2": SLATier("High",      response_minutes=60,  resolution_hours=8),
    "P3": SLATier("Medium",    response_minutes=240, resolution_hours=24),
    "P4": SLATier("Low",       response_minutes=480, resolution_hours=72),
}

# ---------------------------------------------------------------------------
# SLA record
# ---------------------------------------------------------------------------

@dataclass
class SLARecord:
    ticket_id: str
    subject: str
    priority: str
    created_at: datetime
    resolved_at: Optional[datetime]
    requester: str
    department: str

    age_hours: float = field(init=False)
    tier: SLATier = field(init=False)
    response_breach: bool = field(init=False)
    resolution_breach: bool = field(init=False)
    resolution_pct: float = field(init=False)
    status: str = field(init=False)

    def __post_init__(self) -> None:
        self.tier = SLA_TIERS.get(self.priority, SLA_TIERS["P4"])

    def evaluate(self, as_of: datetime) -> None:
        """Compute SLA compliance metrics against a reference timestamp."""
        end_time = self.resolved_at if self.resolved_at else as_of
        age = end_time - self.created_at
        self.age_hours = age.total_seconds() / 3600

        # Response breach: approximated — if ticket is older than response SLA
        self.response_breach = age > self.tier.response_delta

        # Resolution breach
        self.resolution_breach = age > self.tier.resolution_delta

        # Percentage of resolution SLA consumed
        self.resolution_pct = min(
            999.0,
            (age.total_seconds() / self.tier.resolution_delta.total_seconds()) * 100,
        )

        if self.resolved_at:
            self.status = "RESOLVED" if not self.resolution_breach else "BREACHED (resolved late)"
        elif self.resolution_breach:
            self.status = "⚠  BREACH — OVERDUE"
        elif self.resolution_pct >= 75:
            self.status = "⚡ AT RISK"
        else:
            self.status = "OK"

    def to_dict(self) -> dict:
        return {
            "ticket_id": self.ticket_id,
            "subject": self.subject[:60],
            "priority": self.priority,
            "tier_name": self.tier.name,
            "requester": self.requester,
            "department": self.department,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else "",
            "age_hours": round(self.age_hours, 2),
            "response_sla_minutes": self.tier.response_minutes,
            "resolution_sla_hours": self.tier.resolution_hours,
            "response_breach": self.response_breach,
            "resolution_breach": self.resolution_breach,
            "resolution_pct_consumed": round(self.resolution_pct, 1),
            "status": self.status,
        }


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def parse_iso(ts: str) -> datetime:
    """Parse ISO 8601 timestamp to timezone-aware datetime."""
    ts = ts.replace("Z", "+00:00")
    return datetime.fromisoformat(ts)


def load_tickets(path: Path, as_of: datetime) -> list[SLARecord]:
    """Load tickets from JSON and return evaluated SLA records."""
    with path.open() as fh:
        raw: list[dict] = json.load(fh)

    records = []
    for t in raw:
        rec = SLARecord(
            ticket_id=t.get("id", "UNKNOWN"),
            subject=t.get("subject", ""),
            priority=t.get("priority", "P4"),
            created_at=parse_iso(t["created_at"]),
            resolved_at=parse_iso(t["resolved_at"]) if t.get("resolved_at") else None,
            requester=t.get("requester", ""),
            department=t.get("department", ""),
        )
        rec.evaluate(as_of)
        records.append(rec)

    return records


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_console_report(records: list[SLARecord], as_of: datetime) -> None:
    breach_count = sum(1 for r in records if r.resolution_breach)
    at_risk_count = sum(1 for r in records if not r.resolution_breach and r.resolution_pct >= 75)

    print(f"\n{'═'*80}")
    print(f"  SLA MONITORING REPORT  |  As of: {as_of.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Total: {len(records)} tickets  |  Breached: {breach_count}  |  At Risk: {at_risk_count}")
    print(f"{'═'*80}")
    print(f"  {'ID':<12} {'P':<3} {'Age(h)':>7} {'SLA%':>7} {'Status':<30} Subject")
    print(f"  {'─'*12} {'─'*3} {'─'*7} {'─'*7} {'─'*30} {'─'*30}")

    for r in sorted(records, key=lambda x: (-x.resolution_pct, x.priority)):
        subj = (r.subject[:32] + "…") if len(r.subject) > 33 else r.subject
        breach_marker = "🔴" if r.resolution_breach else ("🟡" if r.resolution_pct >= 75 else "🟢")
        print(
            f"  {r.ticket_id:<12} {r.priority:<3} {r.age_hours:>7.1f} "
            f"{r.resolution_pct:>6.0f}% {breach_marker} {r.status:<28} {subj}"
        )

    print(f"{'═'*80}")

    # Priority breakdown
    print("\n  BREACH SUMMARY BY PRIORITY:")
    for pri in ["P1", "P2", "P3", "P4"]:
        tier_records = [r for r in records if r.priority == pri]
        breached = [r for r in tier_records if r.resolution_breach]
        if tier_records:
            print(f"    {pri} ({SLA_TIERS[pri].name:8}): {len(breached)}/{len(tier_records)} breached")
    print()


def write_csv_report(records: list[SLARecord], output_path: Path) -> None:
    fieldnames = list(records[0].to_dict().keys()) if records else []
    with output_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(r.to_dict() for r in records)
    logger.info("CSV report written to %s", output_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor ticket SLA compliance and flag breaches.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--input", type=Path, required=True, help="Tickets JSON file")
    parser.add_argument("--output", type=Path, help="Write CSV report to this path")
    parser.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="Evaluate SLA as of this ISO timestamp (default: now)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.input.exists():
        logger.error("Input file not found: %s", args.input)
        return 1

    as_of = (
        parse_iso(args.as_of)
        if args.as_of
        else datetime.now(tz=timezone.utc)
    )
    logger.info("Evaluating SLA as of %s", as_of.isoformat())

    records = load_tickets(args.input, as_of)
    print_console_report(records, as_of)

    if args.output:
        write_csv_report(records, args.output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
