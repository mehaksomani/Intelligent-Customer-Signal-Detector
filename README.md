# Intelligent Customer Signal Detector

Analyzes siloed customer interaction data — **support transcripts, CSAT, billing
disputes, login inactivity** — and surfaces early **churn / escalation** signals with
a prioritized, explainable action queue for Customer Operations & Retention teams.

Built with **Python · Streamlit · Pandas · Plotly** and a provider-agnostic **LLM**
layer (Anthropic / OpenAI / Gemini) with a deterministic **mock fallback** so it runs
with no API key.

---

## Problem Overview

Customer-risk signals are fragmented — chat logs sit in the helpdesk, CSAT in surveys,
disputes in billing, engagement in product telemetry — and are reviewed manually and
reactively. By the time a complaint escalates or a cancellation arrives, churn intent
has already formed. This tool **unifies those signals into a single 0–100 risk score
per customer**, explains *why* each account is flagged, and recommends a concrete
retention action — turning a reactive process into a proactive daily triage queue.

## Architecture Flow

```
            ┌─ Support chat logs ─┐
 INPUTS  ───┤  CSAT · Billing     ├──► 1. Ingestion  ─►  2. Signal Correlation Engine
            └─ Login inactivity ──┘        (normalize)        (heuristics + LLM reasoning)
                                                                        │
   4. Triage UI  ◄─────────────────────  3. Risk Scoring Layer  ◄───────┘
   (Streamlit: KPIs, risk matrix,          (weighted 0–100 + hard-rule
    triage table, inspector, export)        overrides → Critical/High/Medium/Low)
```

- **`src/data_generator.py`** — 25 synthetic, archetype-seeded customers (schema below).
- **`src/detector.py`** — the engine. An LLM extracts qualitative signals from the
  transcript into a **Pydantic-validated** JSON schema (out-of-range values are
  clamped, malformed responses caught); these are fused with quantitative metrics
  via **transparent weights + hard-rule overrides**; a grounded LLM (or template)
  writes the rationale and retention action. Provider-agnostic, with per-record
  mock fallback on any error. Low-confidence reads are flagged for **manual review**.
- **`app.py`** — Streamlit dashboard: KPI cards, interactive Plotly risk matrix,
  sortable color-coded triage table, per-customer inspector, and CSV export.
- **`src/db.py`** — SQLite persistence for the **closed loop**: ops log what they did
  about a flagged customer (contacted / save-offer / dismissed / snoozed); decisions
  persist, drive a live **Status** column on the queue, and form an auditable log.

**Hybrid, explainable scoring.** Hard thresholds (e.g. `CSAT ≤ 2` with `≥ 2` disputes,
explicit churn intent) set a minimum tier, while soft semantic signals (frustration,
competitor mentions, passive disengagement) drive the weighted score. Every flag lists
its `key_signals` and cites transcript `evidence`, and each analysis carries a
**confidence** score — reads below 60% are auto-flagged for human review. So Ops sees
the evidence and the uncertainty, not a black box.

## Setup Instructions

```bash
pip install -r requirements.txt

# (optional) enable LLM analysis — pick ONE provider:
export ANTHROPIC_API_KEY=sk-ant-...      # or OPENAI_API_KEY / GEMINI_API_KEY
# with no key set, the app runs in deterministic MOCK mode

python -m src.data_generator            # writes data/customers.csv (25 records)
streamlit run app.py                     # launch the dashboard
```

CLI scoring (no UI): `python -m src.detector` ·
regenerate deck assets: `python scripts/make_assets.py` (run from the project root).

**Run the tests:**

```bash
pytest -q            # unit tests for the scoring logic, hard rules & archetypes
```

**Performance:** transcript analysis is fanned out across a thread pool
(`MAX_WORKERS`, default 8), so latency stays flat as the customer count grows —
LLM calls are I/O-bound and independent per customer.

**Validation:** on the 25 seeded customers the engine reproduces the ground-truth risk
tier **100%** of the time in mock mode — including correctly holding "venting-but-happy"
accounts at **Low**.

## Assumptions

- No real/proprietary data — a synthetic dataset is generated; two audit-only columns
  (`expected_tier`, `_archetype`) validate accuracy and are ignored by the engine.
- Signal **weights, tier bands, and hard rules** live in `src/detector.py` and are meant to
  be re-calibrated on labelled churn outcomes in production.
- One recent transcript per customer (the schema/pipeline extends to full history).
- `days_inactive` is a proxy for product-usage telemetry.

## Sample Input / Output JSON

**Input (one customer record):**

```json
{
  "customer_id": "CUST-1002",
  "customer_name": "Wei Adebayo",
  "subscription_tier": "Enterprise",
  "csat_score": 1,
  "billing_disputes_last_90d": 3,
  "days_inactive": 51,
  "support_transcript": "Customer: This is the third outage this month and support went dark for two days. We've already started migrating to a competitor. Agent: I'm very sorry — can we set up a call? Customer: No. Please send offboarding steps and how to export our data before the next invoice. We are not renewing."
}
```

**Output (signal object):**

```json
{
  "customer_id": "CUST-1002",
  "risk_score": 84,
  "risk_tier": "Critical",
  "confidence": 0.9,
  "needs_review": false,
  "key_signals": [
    "Explicit churn/cancellation intent",
    "Low CSAT (1/5)",
    "3 billing disputes in 90 days",
    "Low engagement (51 days inactive)",
    "Competitor / alternative mentioned",
    "Hard rule: explicit churn intent detected"
  ],
  "evidence": ["not renewing", "final straw"],
  "rationale": "Wei Adebayo shows explicit churn intent alongside hard risk signals (CSAT 1/5, 3 disputes, 51 days inactive). This is an imminent, high-urgency loss.",
  "suggested_retention_action": "Escalate to a senior CSM for a same-day retention call; prepare a tailored save-offer and data-continuity plan."
}
```

## Project structure

```
intelligent-customer-signal-detector/
├── app.py                    # Streamlit entry point (run: streamlit run app.py)
├── src/                      # core package
│   ├── data_generator.py     #   25-record synthetic dataset (required schema)
│   ├── detector.py           #   signal engine: LLM + heuristics + mock fallback
│   ├── models.py             #   Pydantic schemas validating LLM output
│   └── db.py                 #   SQLite triage action log (closed-loop persistence)
├── scripts/                  # dev tooling (not imported by the app)
│   ├── make_assets.py        #   generates the deck's charts
│   └── build_deck.js         #   generates the 5-slide PPTX (pptxgenjs)
├── tests/test_detector.py    # 15 unit tests (pytest -q)
├── data/customers.csv        # sample input
├── requirements.txt · .gitignore
├── Input_Output_Design/
    ├── pipeline.png
    ├── risk_matrix.png
    ├── scored_customers.csv
    ├── triage_table.png
├── ICSD_Summary_Deck.pptx
├── README.md · DEMO_SCRIPT.md
```
