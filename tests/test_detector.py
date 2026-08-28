"""
tests/test_detector.py
======================
Unit tests for the signal detection engine. Run with:  pytest -q

These lock in the behaviour that matters for an ops team: the scoring is a valid
0-100, the weights are a proper distribution, hard rules fire, and the labelled
archetypes classify into the expected tiers in deterministic mock mode.
"""
import os
import sys
import math

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import detector
from src import data_generator


# ---- ensure tests never accidentally hit a real API (force mock) ----------
@pytest.fixture(autouse=True)
def _force_mock(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY",
              "GOOGLE_API_KEY", "LLM_PROVIDER"):
        monkeypatch.delenv(k, raising=False)


def _rec(**over):
    base = dict(customer_id="CUST-9001", customer_name="Test User",
                subscription_tier="Pro", csat_score=3,
                billing_disputes_last_90d=0, days_inactive=5,
                support_transcript="How do I reset a password? Thanks.")
    base.update(over)
    return base


# --------------------------------------------------------------------------
def test_weights_form_a_distribution():
    assert math.isclose(sum(detector.WEIGHTS.values()), 1.0, abs_tol=1e-9)


def test_output_has_required_fields():
    res = analyze = detector.analyze_customer(_rec())
    for f in ("risk_score", "risk_tier", "key_signals", "rationale",
              "suggested_retention_action"):
        assert f in res
    assert 0 <= res["risk_score"] <= 100
    assert res["risk_tier"] in ("Critical", "High", "Medium", "Low")
    assert isinstance(res["key_signals"], list) and res["key_signals"]


def test_mock_is_deterministic():
    r1 = detector.analyze_customer(_rec())
    r2 = detector.analyze_customer(_rec())
    assert r1["risk_score"] == r2["risk_score"]
    assert r1["risk_tier"] == r2["risk_tier"]


def test_explicit_churn_is_critical():
    res = detector.analyze_customer(_rec(
        csat_score=1, billing_disputes_last_90d=3, days_inactive=50,
        support_transcript=("Customer: We are not renewing. Please send offboarding "
                            "steps and how to export our data. We've moved to a competitor.")))
    assert res["risk_tier"] == "Critical"
    assert res["risk_score"] >= 75


def test_happy_customer_is_low():
    res = detector.analyze_customer(_rec(
        csat_score=5, billing_disputes_last_90d=0, days_inactive=3,
        support_transcript=("Customer: The team loves it, adoption is up. We want to "
                            "add 15 seats. Fantastic support, a pleasure to use.")))
    assert res["risk_tier"] == "Low"
    assert res["qualitative_signals"]["churn_intent"] < 0.2


def test_hard_rule_low_csat_plus_disputes():
    # even a neutral transcript must escalate when CSAT<=2 and disputes>=2
    res = detector.analyze_customer(_rec(
        csat_score=2, billing_disputes_last_90d=2, days_inactive=5,
        support_transcript="Customer: Can you confirm my renewal date? Thanks."))
    assert res["risk_tier"] in ("High", "Critical")
    assert any("Hard rule" in s for s in res["key_signals"])


def test_venting_but_happy_not_flagged():
    # negative words but clearly positive + healthy metrics -> stays Low
    res = detector.analyze_customer(_rec(
        csat_score=5, billing_disputes_last_90d=0, days_inactive=4,
        support_transcript=("Customer: Ugh the new layout drove me crazy at first! "
                            "But honestly we love it and use it every day. Keep it up.")))
    assert res["risk_tier"] == "Low"


def test_batch_preserves_order_and_mode():
    recs = [_rec(customer_id=f"CUST-{i}") for i in range(6)]
    out, mode = detector.analyze_customers(recs, max_workers=4)
    assert mode == "mock"
    assert [r["customer_id"] for r in out] == [r["customer_id"] for r in recs]


def test_pydantic_clamps_out_of_range_values():
    from src.models import TranscriptSignals
    s = TranscriptSignals(churn_intent=1.9, frustration=-3, sentiment=8,
                          confidence="bad", competitor_mention=1,
                          key_phrases=["a", "b", "c", "d", "e"])
    assert s.churn_intent == 1.0 and s.frustration == 0.0
    assert s.sentiment == 1.0 and s.confidence == 0.0
    assert s.competitor_mention is True and len(s.key_phrases) == 3


def test_output_exposes_confidence_and_review_flag():
    res = detector.analyze_customer(_rec())
    assert 0.0 <= res["confidence"] <= 1.0
    assert isinstance(res["needs_review"], bool)
    assert isinstance(res["evidence"], list)


def test_low_confidence_triggers_manual_review():
    # a terse, contentless transcript should be low-confidence -> needs_review
    res = detector.analyze_customer(_rec(
        support_transcript=("Customer: Hi. Not sure yet.\nAgent: How can I help?\n"
                            "Customer: Will let you know. Thanks.")))
    assert res["confidence"] < 0.6
    assert res["needs_review"] is True


# --------------------------------------------------------------------------
# Persistence layer (closed-loop triage action log)
# --------------------------------------------------------------------------
def test_db_records_and_reads_actions(tmp_path):
    from src import db
    p = tmp_path / "triage.db"
    db.init_db(p)
    assert db.read_actions(p).empty
    rid = db.record_action("CUST-1", "Ada Lovelace", "Critical", 88.0,
                           "Contacted", "left voicemail", path=p)
    assert rid == 1
    log = db.read_actions(p)
    assert len(log) == 1 and log.iloc[0]["customer_id"] == "CUST-1"


def test_db_latest_decision_wins(tmp_path):
    from src import db
    p = tmp_path / "triage.db"
    db.record_action("CUST-9", "Test", "High", 60, "Snoozed", path=p)
    db.record_action("CUST-9", "Test", "High", 60, "Contacted", path=p)
    assert db.latest_decisions(p)["CUST-9"] == "Contacted"


def test_db_rejects_unknown_decision(tmp_path):
    from src import db
    with pytest.raises(ValueError):
        db.record_action("CUST-1", "X", "Low", 10, "Teleported", path=tmp_path / "t.db")


def test_seeded_archetypes_classify_well():
    df = data_generator.generate_customers(seed=7)
    out, _ = detector.analyze_dataframe(df, max_workers=1)
    agreement = (out["risk_tier"] == out["expected_tier"]).mean()
    # deterministic mock should reproduce the ground-truth tier for the vast majority
    assert agreement >= 0.9, f"tier agreement too low: {agreement:.0%}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
