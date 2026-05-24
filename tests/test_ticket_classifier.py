"""Unit tests for ticket_classifier.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ticket_classifier import classify_by_keywords, classify_ticket, _normalize


def test_normalize_strips_punctuation():
    assert _normalize("Can't connect!") == "can t connect "


def test_normalize_lowercases():
    assert _normalize("VPN FAILURE") == "vpn failure"


class TestKeywordClassifier:
    def test_security_incident_ransomware(self):
        cat, scores = classify_by_keywords("ransomware detected crowdstrike alert")
        assert cat == "security_incident"
        assert scores["security_incident"] > 0

    def test_security_incident_phishing(self):
        cat, _ = classify_by_keywords("suspicious phishing email credential harvest")
        assert cat == "security_incident"

    def test_access_management_vpn(self):
        cat, _ = classify_by_keywords("cannot login vpn password reset active directory")
        assert cat == "access_management"

    def test_hardware_screen(self):
        cat, _ = classify_by_keywords("laptop screen flickering black display")
        assert cat == "hardware"

    def test_software_office_crash(self):
        cat, _ = classify_by_keywords("microsoft office crashes error dll corrupt")
        assert cat == "software"

    def test_network_drive_mapping(self):
        cat, _ = classify_by_keywords("network drive not mapping file server dns")
        assert cat == "network"

    def test_default_fallback(self):
        cat, scores = classify_by_keywords("the quick brown fox")
        # All scores zero → defaults to software
        assert cat == "software"

    def test_scores_are_non_negative(self):
        _, scores = classify_by_keywords("test input")
        for v in scores.values():
            assert v >= 0

    def test_returns_all_categories(self):
        _, scores = classify_by_keywords("some text")
        expected = {"security_incident", "access_management", "hardware", "software", "network"}
        assert set(scores.keys()) == expected


class TestClassifyTicket:
    def _make_ticket(self, subject: str, body: str = "", priority: str = "P3") -> dict:
        return {"id": "T-TEST", "subject": subject, "body": body, "priority": priority}

    def test_returns_category_field(self):
        ticket = self._make_ticket("vpn login failure")
        result = classify_ticket(ticket)
        assert "category" in result

    def test_preserves_original_fields(self):
        ticket = self._make_ticket("test", priority="P1")
        result = classify_ticket(ticket)
        assert result["id"] == "T-TEST"
        assert result["priority"] == "P1"

    def test_confidence_between_0_and_100(self):
        ticket = self._make_ticket("ransomware attack detected")
        result = classify_ticket(ticket)
        assert 0 <= result["confidence_pct"] <= 100

    def test_priority_score_present(self):
        ticket = self._make_ticket("ransomware breach critical")
        result = classify_ticket(ticket)
        assert "priority_score" in result
        assert result["priority_score"] == 10  # security_incident has highest score

    def test_keyword_scores_in_result(self):
        ticket = self._make_ticket("software crash error")
        result = classify_ticket(ticket)
        assert "keyword_scores" in result
        assert isinstance(result["keyword_scores"], dict)

    def test_classification_method_keyword(self):
        ticket = self._make_ticket("ransomware malware breach infected endpoint exploit")
        result = classify_ticket(ticket, ml_clf=None)
        assert result["classification_method"] == "keyword"
