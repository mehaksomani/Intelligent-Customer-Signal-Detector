"""
detector.py
===========
Core Signal Detection Engine for the Intelligent Customer Signal Detector.

Design (hybrid, explainable):

    1. QUALITATIVE layer  — an LLM reads the support transcript and returns a
       STRICT JSON object of semantic signals (churn intent, frustration,
       competitor mention, feature gap, billing issue, passive dissatisfaction).
       Provider-agnostic: Anthropic, OpenAI, or Gemini, chosen from whichever
       API key is present. Falls back to a deterministic MOCK if no key / on error.

    2. QUANTITATIVE layer — hard thresholds & normalised metrics from CSAT,
       billing disputes and inactivity.

    3. FUSION layer       — the two are blended with transparent weights into a
       risk_score (0-100), mapped to a risk_tier, with hard-rule overrides
       (e.g. CSAT<=2 AND disputes>=2). Every fired signal is surfaced in
       `key_signals`, so Ops can see *why* — not just a black-box number.

Public API:
    analyze_customer(record: dict) -> dict     # single record
    analyze_customers(records: list[dict]) -> tuple[list[dict], str]   # batch, + mode
    analyze_dataframe(df) -> tuple[pd.DataFrame, str]

Returned analysis fields (per the brief):
    risk_score, risk_tier, key_signals, rationale, suggested_retention_action
    (plus the qualitative sub-signals for the Inspector panel).
"""
from __future__ import annotations
import os
import re
import json
import logging

from typing import Optional

from src.models import TranscriptSignals

logger = logging.getLogger("detector")

# ---------------------------------------------------------------------------
# Configuration — weights, thresholds, models (all tunable & documented)
# ---------------------------------------------------------------------------
WEIGHTS = {
    # qualitative (from transcript)
    "churn_intent": 0.24,
    "frustration": 0.10,
    "competitor_mention": 0.08,
    "feature_gap": 0.04,
    "passive_dissatisfaction": 0.06,
    "billing_sentiment": 0.06,
    # quantitative (from metrics)
    "csat_risk": 0.16,
    "disputes_risk": 0.14,
    "inactivity_risk": 0.12,
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9

# risk_score -> tier thresholds
TIER_BANDS = [("Critical", 75), ("High", 50), ("Medium", 25), ("Low", 0)]

# below this transcript-read confidence, flag the record for manual review
REVIEW_CONFIDENCE = float(os.getenv("REVIEW_CONFIDENCE", "0.6"))

# normalisation ceilings for quantitative signals
DISPUTE_CEIL = 3      # >=3 disputes = max risk on that axis
INACTIVE_CEIL = 60    # >=60 days inactive = max risk on that axis

DEFAULT_MODELS = {
    "anthropic": os.getenv("CLAUDE_MODEL", "claude-sonnet-5"),
    "openai": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    "gemini": os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
}

# ---------------------------------------------------------------------------
# Strict-JSON prompt (zero-shot structured extraction)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are a senior customer-retention analyst. Read one support transcript and "
    "return ONLY a strict JSON object of semantic signals. Do not over-flag: venting "
    "or a minor complaint from an otherwise happy customer is NOT churn intent. "
    "Return JSON only — no markdown, no prose."
)

JSON_SCHEMA = """Return a JSON object with EXACTLY these keys:
{
  "churn_intent": float 0.0-1.0,           // explicit "cancel/leave/not renewing" = high; "reviewing options" ~0.5; happy = 0.0
  "frustration": float 0.0-1.0,            // emotional intensity of dissatisfaction
  "competitor_mention": boolean,           // references a competitor / alternative / migrating away
  "feature_gap": boolean,                  // a missing/broken capability is blocking them
  "billing_issue": boolean,                // a billing/charge/invoice problem is raised
  "passive_dissatisfaction": boolean,      // disengaging quietly, "reviewing tools", low energy
  "sentiment": float -1.0..1.0,            // overall tone
  "confidence": float 0.0-1.0,             // how confident you are in this read (low if the transcript is ambiguous)
  "key_phrases": [string]                  // up to 3 short quotes from the transcript that justify the signals
}"""


# ===========================================================================
# 1. LLM PROVIDER ADAPTERS  (Anthropic / OpenAI / Gemini) + mock
# ===========================================================================
def _detect_provider() -> Optional[str]:
    """Pick a provider from whichever API key is present. None -> mock mode."""
    forced = os.getenv("LLM_PROVIDER")
    if forced in ("anthropic", "openai", "gemini"):
        return forced
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        return "gemini"
    return None


def _extract_json(text: str) -> dict:
    """Robustly pull a JSON object out of a model response."""
    text = re.sub(r"```(?:json)?", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    return json.loads(text)


def _call_anthropic(transcript: str, model: str) -> dict:
    import anthropic
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=model, max_tokens=400, system=SYSTEM_PROMPT,
        messages=[{"role": "user",
                   "content": f"{JSON_SCHEMA}\n\nTRANSCRIPT:\n\"\"\"{transcript}\"\"\""}],
    )
    return _extract_json("".join(
        b.text for b in msg.content if getattr(b, "type", "") == "text"))


def _call_openai(transcript: str, model: str) -> dict:
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(
        model=model, temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user",
                   "content": f"{JSON_SCHEMA}\n\nTRANSCRIPT:\n\"\"\"{transcript}\"\"\""}],
    )
    return _extract_json(resp.choices[0].message.content)


def _call_gemini(transcript: str, model: str) -> dict:
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    gm = genai.GenerativeModel(model, system_instruction=SYSTEM_PROMPT)
    resp = gm.generate_content(
        f"{JSON_SCHEMA}\n\nTRANSCRIPT:\n\"\"\"{transcript}\"\"\"",
        generation_config={"temperature": 0, "response_mime_type": "application/json"})
    return _extract_json(resp.text)


_PROVIDER_FN = {"anthropic": _call_anthropic, "openai": _call_openai, "gemini": _call_gemini}


# ---------------------------------------------------------------------------
# Deterministic MOCK (keyword heuristics) — used when no API key / on failure.
# Mirrors the LLM's JSON schema so the pipeline is identical downstream.
# ---------------------------------------------------------------------------
_CANCEL = ["cancel", "not renewing", "offboard", "stop billing", "export our data",
           "final straw", "moving to another vendor", "migrating to a competitor",
           "not renew"]
_REVIEW = ["evaluating alternatives", "look elsewhere", "reviewing", "review our tooling",
           "evaluating options", "pause the subscription", "deciding what to keep",
           "cost review", "before renewal", "hard to justify", "justify internally",
           "improvement soon", "shaken my confidence", "confidence in rolling"]
_NEG = ["frustrat", "outage", "down", "wrong", "broke", "breaks", "break something",
        "slow", "slower", "failed", "timing out", "times out", "exhausting",
        "wearing me down", "losing patience", "too late", "double-charged",
        "double charge", "duplicate", "shaken", "hard to justify", "not acceptable",
        "blocking", "still isn't", "last time", "third", "four times", "second month",
        "second time", "every release", "removed", "out of date", "chase", "keep hearing",
        "mystery", "don't understand", "keeps"]
_POS = ["love", "loves", "fantastic", "excellent", "great", "pleasure", "easy yes",
        "recommending", "keep it up", "no complaints", "wonderful", "saving us hours",
        "means a lot"]
_COMP = ["competitor", "another vendor", "alternatives", "look elsewhere", "elsewhere",
         "migrating"]
_FEATURE = ["csv export", "feature", "api", "dashboard", "sso", "removed", "roadmap",
            "reporting", "docs are out of date", "docs", "permissions", "analytics view"]
_BILL = ["charged", "charge", "invoice", "billing", "refund", "failed-payment",
         "failed payment", "overage", "discount", "double-charged", "duplicate", "bill"]
_PASSIVE = ["scaled back", "reviewing", "pause the subscription", "haven't logged in",
            "slipped down", "cost review", "evaluating options", "deciding what to keep",
            "usage has dropped", "review our tooling", "trimming subscriptions",
            "see how the quarter goes"]


def _mock_analyze(transcript: str) -> dict:
    t = transcript.lower()
    neg = sum(w in t for w in _NEG)
    pos = sum(w in t for w in _POS)

    comp = any(w in t for w in _COMP)
    if any(w in t for w in _CANCEL):
        churn = 0.95
    elif comp:                                   # naming an alternative = strong soft signal
        churn = 0.6
    elif any(w in t for w in _REVIEW):
        churn = 0.45
    else:
        churn = 0.0
    if pos >= 2 and neg <= 1:                    # clearly happy => not leaving
        churn = min(churn, 0.05)

    sentiment = max(-1.0, min(1.0, (pos - neg) / 3.0))
    phrases = []
    for w in ("not renewing", "final straw", "evaluating alternatives",
              "double-charged", "csv export", "timing out", "scaled back"):
        if w in t:
            phrases.append(w)

    # confidence: high when the signal is unambiguous, lower when signals conflict
    conf = 0.7
    if any(w in t for w in _CANCEL) or pos >= 2:
        conf = 0.9                                  # explicit intent or clearly happy
    if pos >= 1 and neg >= 2:
        conf = 0.55                                 # mixed / conflicting signals
    # a very short, contentless message is genuinely hard to read -> flag for review
    customer_words = sum(
        len(ln.split(":", 1)[1].split()) for ln in transcript.splitlines()
        if ln.lower().startswith("customer") and ":" in ln)
    if customer_words <= 10 and churn == 0 and neg == 0 and pos == 0:
        conf = 0.5

    return {
        "churn_intent": churn,
        "frustration": min(1.0, neg / 3.0),
        "competitor_mention": any(w in t for w in _COMP),
        "feature_gap": any(w in t for w in _FEATURE) and neg >= 1,
        "billing_issue": any(w in t for w in _BILL),
        "passive_dissatisfaction": any(w in t for w in _PASSIVE) and churn < 0.9,
        "sentiment": sentiment,
        "confidence": conf,
        "key_phrases": phrases[:3],
    }


def _get_qual_signals(transcript: str, provider: Optional[str]) -> tuple[TranscriptSignals, str]:
    """Return (signals, mode). Tries the LLM provider; validates via Pydantic;
    falls back to the deterministic mock on any error (network/auth/parse/schema)."""
    if provider:
        try:
            raw = _PROVIDER_FN[provider](transcript, DEFAULT_MODELS[provider])
            return TranscriptSignals(**raw), provider           # schema-validated
        except Exception as e:                    # network, auth, parse, ValidationError...
            logger.warning("LLM call failed (%s: %s) — using mock for this record",
                           provider, e)
    return TranscriptSignals(**_mock_analyze(transcript)), "mock"


# ===========================================================================
# 2 + 3. QUANTITATIVE SCORING + FUSION
# ===========================================================================
def _clamp01(x):
    return max(0.0, min(1.0, x))


def _score(record: dict, q: TranscriptSignals) -> dict:
    csat = int(record["csat_score"])
    disputes = int(record["billing_disputes_last_90d"])
    inactive = int(record["days_inactive"])

    norm = {
        "churn_intent": q.churn_intent,
        "frustration": q.frustration,
        "competitor_mention": 1.0 if q.competitor_mention else 0.0,
        "feature_gap": 1.0 if q.feature_gap else 0.0,
        "passive_dissatisfaction": 1.0 if q.passive_dissatisfaction else 0.0,
        "billing_sentiment": 1.0 if (q.billing_issue and disputes > 0) else
                             (0.5 if q.billing_issue else 0.0),
        "csat_risk": _clamp01((5 - csat) / 4.0),
        "disputes_risk": _clamp01(disputes / DISPUTE_CEIL),
        "inactivity_risk": _clamp01(inactive / INACTIVE_CEIL),
    }
    contributions = {k: round(norm[k] * WEIGHTS[k] * 100, 1) for k in WEIGHTS}
    risk_score = round(sum(contributions.values()), 1)

    # ---- transparent hard-rule overrides -------------------------------
    # Encodes the "hard thresholds + soft semantic signals" policy: certain
    # signal combinations set a minimum tier regardless of the weighted sum.
    hard_rules = []
    if q.churn_intent >= 0.85:
        risk_score = max(risk_score, 78)          # explicit intent to leave => Critical
        hard_rules.append("Hard rule: explicit churn intent detected")
    if csat <= 2 and disputes >= 2:
        risk_score = max(risk_score, 66)          # unhappy + repeated billing failures
        hard_rules.append("Hard rule: CSAT ≤ 2 with ≥ 2 billing disputes")
    if disputes >= 3 or (disputes >= 2 and csat <= 3):
        risk_score = max(risk_score, 52)          # billing-escalation risk
        hard_rules.append("Hard rule: repeated billing disputes")
    if q.frustration >= 0.55 and (q.feature_gap or q.competitor_mention) and csat <= 3:
        risk_score = max(risk_score, 52)          # actively frustrated + blocking gap
        hard_rules.append("Hard rule: high frustration with a blocking issue")
    risk_score = round(min(risk_score, 100.0), 1)

    tier = next(t for t, lo in TIER_BANDS if risk_score >= lo)
    return {"risk_score": risk_score, "risk_tier": tier,
            "contributions": contributions, "hard_rules": hard_rules}


# human-readable labels for fired signals
def _build_key_signals(record, q: TranscriptSignals, scored: dict) -> list[str]:
    sig = []
    csat = int(record["csat_score"])
    disputes = int(record["billing_disputes_last_90d"])
    inactive = int(record["days_inactive"])
    if q.churn_intent >= 0.85:
        sig.append("Explicit churn/cancellation intent")
    elif q.churn_intent >= 0.4:
        sig.append("Considering leaving / reviewing options")
    if csat <= 2:
        sig.append(f"Low CSAT ({csat}/5)")
    elif csat == 3:
        sig.append(f"Mediocre CSAT ({csat}/5)")
    if disputes >= 2:
        sig.append(f"{disputes} billing disputes in 90 days")
    elif disputes == 1:
        sig.append("1 billing dispute in 90 days")
    if inactive >= INACTIVE_CEIL:
        sig.append(f"Inactive {inactive} days")
    elif inactive >= 30:
        sig.append(f"Low engagement ({inactive} days inactive)")
    if q.competitor_mention:
        sig.append("Competitor / alternative mentioned")
    if q.feature_gap:
        sig.append("Blocking feature gap raised")
    if q.billing_issue:
        sig.append("Billing error in transcript")
    if q.passive_dissatisfaction:
        sig.append("Passive disengagement")
    sig.extend(scored["hard_rules"])
    return sig or ["No material risk signals"]


# ===========================================================================
# 4. RATIONALE + RETENTION ACTION  (LLM-grounded, deterministic fallback)
# ===========================================================================
RATIONALE_SYSTEM = (
    "You are a retention analyst writing for a busy Customer Operations team. Given a "
    "customer's computed signals, write a 2-3 sentence rationale (grounded ONLY in the "
    "signals) and ONE concrete, operational retention action. If anger is a recoverable "
    "billing error, recommend fixing billing rather than a discount. Return strict JSON: "
    '{"rationale": str, "suggested_retention_action": str}. No preamble.')


def _narrative_llm(record, q, scored, provider) -> Optional[dict]:
    payload = {
        "subscription_tier": record["subscription_tier"],
        "csat_score": record["csat_score"],
        "billing_disputes_last_90d": record["billing_disputes_last_90d"],
        "days_inactive": record["days_inactive"],
        "risk_score": scored["risk_score"], "risk_tier": scored["risk_tier"],
        "qualitative_signals": q.model_dump(),
    }
    prompt = json.dumps(payload)
    try:
        if provider == "anthropic":
            import anthropic
            m = anthropic.Anthropic().messages.create(
                model=DEFAULT_MODELS["anthropic"], max_tokens=300,
                system=RATIONALE_SYSTEM, messages=[{"role": "user", "content": prompt}])
            return _extract_json("".join(b.text for b in m.content
                                         if getattr(b, "type", "") == "text"))
        if provider == "openai":
            from openai import OpenAI
            r = OpenAI().chat.completions.create(
                model=DEFAULT_MODELS["openai"], temperature=0,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": RATIONALE_SYSTEM},
                          {"role": "user", "content": prompt}])
            return _extract_json(r.choices[0].message.content)
        if provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
            gm = genai.GenerativeModel(DEFAULT_MODELS["gemini"],
                                       system_instruction=RATIONALE_SYSTEM)
            r = gm.generate_content(prompt, generation_config={
                "temperature": 0, "response_mime_type": "application/json"})
            return _extract_json(r.text)
    except Exception as e:
        logger.warning("Rationale LLM call failed — using template (%s)", e)
    return None


def _narrative_fallback(record, q, scored) -> dict:
    tier = scored["risk_tier"]
    name = record["customer_name"]
    csat = record["csat_score"]
    disputes = record["billing_disputes_last_90d"]
    inactive = record["days_inactive"]
    recoverable_billing = q.billing_issue and q.churn_intent < 0.85

    if tier == "Low":
        rationale = (f"{name} shows healthy signals (CSAT {csat}/5, {disputes} disputes, "
                     f"{inactive} days inactive) with positive or routine sentiment. "
                     f"No churn indicators in the transcript.")
        action = ("No intervention needed — flag as a candidate for upsell or "
                  "advocacy/reference outreach.")
    elif recoverable_billing and tier in ("Medium", "High"):
        rationale = (f"Frustration is driven by a recoverable billing problem "
                     f"({disputes} disputes in 90 days) while product engagement is "
                     f"largely intact — a fixable, not-yet-lost account.")
        action = ("Route to billing to correct the charge within 24h, then send a "
                  "proactive apology + confirmation from the CSM.")
    elif tier == "Critical":
        rationale = (f"{name} shows explicit churn intent alongside hard risk signals "
                     f"(CSAT {csat}/5, {disputes} disputes, {inactive} days inactive). "
                     f"This is an imminent, high-urgency loss.")
        action = ("Escalate to a senior CSM for a same-day retention call; prepare a "
                  "tailored save-offer and data-continuity plan.")
    else:  # High / Medium
        rationale = (f"{name} shows building risk from a mix of signals "
                     f"(CSAT {csat}/5, {inactive} days inactive). Sentiment is "
                     f"deteriorating but the relationship is recoverable.")
        action = ("Assign a CSM to a proactive check-in this week; address the specific "
                  "issue raised and reconfirm value before renewal.")
    return {"rationale": rationale, "suggested_retention_action": action}


# ===========================================================================
# PUBLIC API
# ===========================================================================
def analyze_customer(record: dict, provider: Optional[str] = "auto") -> dict:
    """Analyze a single customer record and return the full signal object."""
    if provider == "auto":
        provider = _detect_provider()
    q, mode = _get_qual_signals(record["support_transcript"], provider)
    scored = _score(record, q)
    key_signals = _build_key_signals(record, q, scored)

    narrative = _narrative_llm(record, q, scored, provider) if mode != "mock" else None
    if not narrative or "rationale" not in narrative:
        narrative = _narrative_fallback(record, q, scored)

    # human-in-the-loop: low model confidence on the transcript read -> flag for review
    needs_review = q.confidence < REVIEW_CONFIDENCE
    if needs_review:
        key_signals = key_signals + [f"⚠ Low extraction confidence ({q.confidence:.0%}) — verify"]

    return {
        "customer_id": record["customer_id"],
        "customer_name": record["customer_name"],
        "subscription_tier": record["subscription_tier"],
        "csat_score": record["csat_score"],
        "billing_disputes_last_90d": record["billing_disputes_last_90d"],
        "days_inactive": record["days_inactive"],
        "support_transcript": record["support_transcript"],
        "risk_score": scored["risk_score"],
        "risk_tier": scored["risk_tier"],
        "confidence": round(q.confidence, 2),
        "needs_review": needs_review,
        "key_signals": key_signals,
        "evidence": q.key_phrases,
        "rationale": narrative["rationale"],
        "suggested_retention_action": narrative["suggested_retention_action"],
        "contributions": scored["contributions"],
        "qualitative_signals": q.model_dump(),
        "analysis_mode": mode,
        # keep audit columns if present (ignored by the app UI)
        **({"expected_tier": record["expected_tier"]} if "expected_tier" in record else {}),
    }


def analyze_customers(records: list[dict], provider: Optional[str] = "auto",
                      progress=None, max_workers: Optional[int] = None
                      ) -> tuple[list[dict], str]:
    """Batch-analyze records concurrently.

    Transcripts are independent, so analysis is embarrassingly parallel. We fan
    the per-customer LLM calls out across a thread pool (I/O-bound → threads are
    ideal) to keep latency flat as the customer count grows, while preserving
    input order in the returned list. Returns (results, overall_mode).
    """
    from concurrent.futures import ThreadPoolExecutor
    import threading

    if provider == "auto":
        provider = _detect_provider()
    workers = max_workers or int(os.getenv("MAX_WORKERS", "8"))
    workers = max(1, min(workers, len(records) or 1))

    results: list[Optional[dict]] = [None] * len(records)
    modes: set[str] = set()
    done = {"n": 0}
    lock = threading.Lock()

    def _worker(idx_rec):
        idx, rec = idx_rec
        res = analyze_customer(rec, provider=provider)
        with lock:
            results[idx] = res
            modes.add(res["analysis_mode"])
            done["n"] += 1
            if progress:
                progress(done["n"] / len(records))
        return idx

    if workers == 1:                                   # deterministic path / tests
        for pair in enumerate(records):
            _worker(pair)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(_worker, enumerate(records)))

    mode = "mock" if modes == {"mock"} else (provider or "mock")
    return [r for r in results if r is not None], mode


def analyze_dataframe(df, provider: Optional[str] = "auto", progress=None,
                      max_workers: Optional[int] = None):
    import pandas as pd
    results, mode = analyze_customers(df.to_dict("records"), provider, progress,
                                      max_workers=max_workers)
    return pd.DataFrame(results), mode


if __name__ == "__main__":
    import pandas as pd
    logging.basicConfig(level=logging.INFO)
    df = pd.read_csv("data/customers.csv")
    out, mode = analyze_dataframe(df)
    out = out.sort_values("risk_score", ascending=False)
    print(f"\nMODE: {mode}\n")
    cols = ["customer_id", "customer_name", "subscription_tier", "risk_score",
            "risk_tier", "expected_tier"]
    print(out[cols].to_string(index=False))
    if "expected_tier" in out:
        acc = (out["risk_tier"] == out["expected_tier"]).mean()
        print(f"\nTier agreement vs ground truth: {acc*100:.0f}%")
    print("\nExample full record:")
    ex = out.iloc[0]
    print(json.dumps({k: ex[k] for k in
                      ["customer_id", "risk_score", "risk_tier", "key_signals",
                       "rationale", "suggested_retention_action"]},
                     indent=2, default=str))
