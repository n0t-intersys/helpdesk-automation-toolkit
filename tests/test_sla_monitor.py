"""Unit tests for sla_monitor.py"""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sla_monitor import SLATier, SLARecord, SLA_TIERS, parse_iso


class TestSLATier:
    def test_p1_response_minutes(self):
        assert SLA_TIERS["P1"].response_minutes == 15

    def test_p1_resolution_hours(self):
        assert SLA_TIERS["P1"].resolution_hours == 4

    def test_p4_resolution_hours(self):
        assert SLA_TIERS["P4"].resolution_hours == 72

    def test_response_delta_is_timedelta(self):
        tier = SLA_TIERS["P2"]
        assert tier.response_delta == timedelta(minutes=60)

    def test_resolution_delta_is_timedelta(self):
        tier = SLA_TIERS["P3"]
        assert tier.resolution_delta == timedelta(hours=24)


class TestParseIso:
    def test_parses_z_suffix(self):
        dt = parse_iso("2025-01-15T10:00:00Z")
        assert dt.tzinfo is not None
        assert dt.hour == 10

    def test_parses_offset(self):
        dt = parse_iso("2025-01-15T10:00:00+00:00")
        assert dt.hour == 10


class TestSLARecord:
    def _make_record(self, priority: str, age_hours: float, resolved: bool = False) -> SLARecord:
        created = datetime(2025, 1, 15, 8, 0, tzinfo=timezone.utc)
        resolved_at = (created + timedelta(hours=age_hours)) if resolved else None
        return SLARecord(
            ticket_id="T-001",
            subject="Test ticket",
            priority=priority,
            created_at=created,
            resolved_at=resolved_at,
            requester="test@company.com",
            department="IT",
        )

    def test_p1_breach_after_4_hours(self):
        rec = self._make_record("P1", age_hours=5)
        as_of = datetime(2025, 1, 15, 13, 0, tzinfo=timezone.utc)
        rec.evaluate(as_of)
        assert rec.resolution_breach is True

    def test_p1_ok_within_4_hours(self):
        rec = self._make_record("P1", age_hours=0)
        as_of = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
        rec.evaluate(as_of)
        assert rec.resolution_breach is False

    def test_p3_breach_after_24_hours(self):
        rec = self._make_record("P3", age_hours=0)
        as_of = datetime(2025, 1, 16, 10, 0, tzinfo=timezone.utc)
        rec.evaluate(as_of)
        assert rec.resolution_breach is True

    def test_resolution_pct_capped_at_999(self):
        rec = self._make_record("P1", age_hours=0)
        as_of = datetime(2025, 1, 16, 8, 0, tzinfo=timezone.utc)  # 24 hrs later
        rec.evaluate(as_of)
        assert rec.resolution_pct <= 999.0

    def test_status_ok_for_new_ticket(self):
        rec = self._make_record("P2", age_hours=0)
        as_of = datetime(2025, 1, 15, 9, 0, tzinfo=timezone.utc)  # 1 hr later
        rec.evaluate(as_of)
        assert rec.status == "OK"

    def test_to_dict_has_required_keys(self):
        rec = self._make_record("P2", age_hours=0)
        rec.evaluate(datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc))
        d = rec.to_dict()
        for key in ["ticket_id", "priority", "age_hours", "resolution_breach", "status"]:
            assert key in d

    def test_at_risk_between_75_and_100_pct(self):
        # P2 = 8hr resolution; 7 hours consumed = 87.5%
        rec = self._make_record("P2", age_hours=0)
        as_of = datetime(2025, 1, 15, 15, 0, tzinfo=timezone.utc)  # 7 hrs later
        rec.evaluate(as_of)
        assert rec.resolution_pct >= 75
        assert rec.resolution_breach is False
        assert "AT RISK" in rec.status or "BREACH" in rec.status
