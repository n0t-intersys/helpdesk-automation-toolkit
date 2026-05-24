# helpdesk-automation-toolkit

```
┌─────────────────────────────────────────────────────────────────────┐
│  IT Service Desk Automation Suite                                    │
│  Ticket Classification · SLA Monitoring · Onboarding · KB Search    │
└─────────────────────────────────────────────────────────────────────┘
```

[![CI](https://github.com/n0t-intersys/helpdesk-automation-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/n0t-intersys/helpdesk-automation-toolkit/actions)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Code Style: flake8](https://img.shields.io/badge/code%20style-flake8-blueviolet)](https://flake8.pycqa.org/)

A Python toolkit simulating core IT service desk workflows — designed to demonstrate
automation, ML-assisted classification, and SLA governance in a realistic helpdesk context.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Ticket Ingestion Layer                                │
│            (JSON file / API / ServiceNow webhook)                       │
└───────────────────────────┬─────────────────────────────────────────────┘
                            │
              ┌─────────────▼──────────────┐
              │    ticket_classifier.py     │
              │  Keyword + Naive Bayes ML   │
              │  → category + confidence    │
              └─────────────┬──────────────┘
                            │
         ┌──────────────────┼────────────────────┐
         │                  │                    │
┌────────▼──────┐  ┌────────▼──────┐  ┌─────────▼──────┐
│ sla_monitor   │  │  kb_search    │  │  onboarding     │
│ .py           │  │  .py          │  │  _checklist.py  │
│               │  │               │  │                 │
│ P1/P2/P3/P4   │  │ TF-IDF search │  │ Role-based      │
│ SLA tracking  │  │ KB articles   │  │ AD provisioning │
│ CSV export    │  │ Ranked results│  │ Markdown output │
└───────┬───────┘  └───────────────┘  └─────────────────┘
        │
┌───────▼──────────────────┐
│   CSV / JSON Reports      │
│   Console dashboards      │
└───────────────────────────┘
```

---

## Tools

| Script | Description | Key Libraries |
|--------|-------------|---------------|
| `ticket_classifier.py` | Auto-categorizes tickets via keyword + Naive Bayes | `sklearn`, stdlib |
| `sla_monitor.py` | SLA tier tracking, breach detection, CSV report | stdlib only |
| `onboarding_checklist.py` | Role-based onboarding with AD PowerShell stubs | stdlib only |
| `kb_search.py` | TF-IDF knowledge base search (no external deps) | stdlib only |

---

## Quick Start

```bash
# Clone and install
git clone https://github.com/n0t-intersys/helpdesk-automation-toolkit.git
cd helpdesk-automation-toolkit
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Classify tickets from JSON
python ticket_classifier.py --input sample_data/tickets.json

# Check SLA status against 4pm on 2025-01-15
python sla_monitor.py \
    --input sample_data/tickets.json \
    --as-of "2025-01-15T16:00:00Z" \
    --output sla_report.csv

# Generate onboarding checklist
python onboarding_checklist.py \
    --role new_hire \
    --name "Jane Doe" \
    --dept Engineering \
    --start-date 2025-02-03 \
    --output onboarding_jane_doe.md

# Search the knowledge base
python kb_search.py --query "vpn connection fails after password reset" --top 3
```

---

## Sample Output

### ticket_classifier.py

```
2025-01-15 10:00:01 [INFO] [TKT-003] Ransomware alert on workstation ... → SECURITY_INCIDENT (80% confidence, keyword)
2025-01-15 10:00:01 [INFO] [TKT-001] Cannot log into VPN after password → ACCESS_MANAGEMENT (70% confidence, keyword)

════════════════════════════════════════════════════════════
  CLASSIFICATION SUMMARY  (10 tickets)
════════════════════════════════════════════════════════════
  security_incident      ██ (2)
  access_management      ████ (4)
  network                █ (1)
  hardware               █ (1)
  software               ██ (2)
════════════════════════════════════════════════════════════
```

### sla_monitor.py

```
════════════════════════════════════════════════════════════════════════════════
  SLA MONITORING REPORT  |  As of: 2025-01-15 16:00 UTC
  Total: 10 tickets  |  Breached: 3  |  At Risk: 2
════════════════════════════════════════════════════════════════════════════════
  ID           P    Age(h)    SLA%  Status                         Subject
  ──────────── ─── ──────── ─────── ─────────────────────────────── ──────────────
  TKT-003      P1      6.0   150%  🔴 ⚠  BREACH — OVERDUE          Ransomware alert...
  TKT-005      P2      5.0    62%  🟡 ⚡ AT RISK                    Network drive Z:...
  TKT-001      P2      7.5    93%  🔴 ⚠  BREACH — OVERDUE          Cannot log into VPN...
```

---

## Running Tests

```bash
pytest tests/ -v --cov=. --cov-report=term-missing
```

---

## Lessons Learned

Building this toolkit surfaced several real-world helpdesk automation insights:

1. **Keyword matching is surprisingly effective** for structured IT vocabularies — but fails on ambiguous tickets like "it's not working." A hybrid keyword + ML approach achieves better precision without requiring a large labelled dataset.

2. **SLA tier design is a business, not technical, decision.** The P1-P4 thresholds in this tool should be configured per-organization in a config file, not hardcoded. A 4-hour P1 resolution SLA that works for a 50-person company is inadequate for a 24/7 production environment.

3. **Onboarding automation catches access creep early.** The checklist generator enforces least-privilege defaults (contractor OU restrictions, JIT admin access) that are easy to skip manually. Automating the checklist creates an audit trail.

4. **TF-IDF without stop-word tuning underperforms on IT text.** Common IT terms like "user", "error", and "issue" act as noise if not treated as domain-specific stop words.

---

## Project Structure

```
helpdesk-automation-toolkit/
├── ticket_classifier.py
├── sla_monitor.py
├── onboarding_checklist.py
├── kb_search.py
├── requirements.txt
├── .env.example
├── sample_data/
│   ├── tickets.json
│   └── knowledge_base.json
├── tests/
│   ├── test_ticket_classifier.py
│   └── test_sla_monitor.py
└── .github/
    └── workflows/
        └── ci.yml
```

---

## License

MIT — see [LICENSE](LICENSE).
