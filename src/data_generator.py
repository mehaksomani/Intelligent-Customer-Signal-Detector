"""
data_generator.py
=================
Generates 25 realistic, synthetic customer records for the Intelligent Customer
Signal Detector. No real or proprietary data is used.

Schema (exactly as required):
    customer_id            : str   e.g. "CUST-1001"
    customer_name          : str
    subscription_tier      : str   {Enterprise, Pro, Starter}
    csat_score             : int   1-5
    billing_disputes_last_90d : int
    days_inactive          : int
    support_transcript     : str   rich, realistic agent/customer dialogue

Records are drawn from labelled ARCHETYPES so detection quality can be validated
against ground truth. Two audit-only columns are added — `expected_tier` and
`_archetype` — which are NOT consumed by the scoring engine.

Usage:
    python data_generator.py                 # writes data/customers.csv
    from data_generator import generate_customers
    df = generate_customers(seed=7)
"""
from __future__ import annotations
import os
import random
import argparse
import pandas as pd

TIERS = ["Enterprise", "Pro", "Starter"]

FIRST = ["Ava", "Liam", "Noah", "Priya", "Wei", "Sofia", "Marcus", "Aisha", "Diego",
         "Hana", "Omar", "Leah", "Tomas", "Nina", "Raj", "Chloe", "Ben", "Yara",
         "Ivan", "Grace", "Kofi", "Mei", "Luca", "Sara", "Elena"]
LAST = ["Patel", "Chen", "Garcia", "Khan", "Nguyen", "Rossi", "Kim", "Silva",
        "Okafor", "Haddad", "Novak", "Meyer", "Ford", "Adebayo", "Costa", "Bauer"]

# ---------------------------------------------------------------------------
# Archetype library: (behavioural ranges) + a bank of rich transcripts.
# ---------------------------------------------------------------------------
ARCHETYPES = {
    "critical_churn": {
        "expected_tier": "Critical",
        "tier_weights": {"Enterprise": 0.6, "Pro": 0.4, "Starter": 0.0},
        "csat": (1, 2), "disputes": (2, 4), "inactive": (25, 75),
        "transcripts": [
            ("Customer: This is the third outage this month and support went dark for "
             "two days. We've already started migrating to a competitor.\n"
             "Agent: I'm very sorry to hear that — can we set up a call?\n"
             "Customer: No. Please send offboarding steps and how to export our data "
             "before the next invoice. We are not renewing."),
            ("Customer: I've raised this ticket four times and nothing is fixed. "
             "Leadership has asked me to cancel the contract.\n"
             "Agent: I understand your frustration, let me escalate.\n"
             "Customer: It's too late. Cancel our renewal and stop billing us."),
            ("Customer: We were double-charged again and the platform was down during "
             "our launch. That's the final straw.\n"
             "Agent: I can look into the charges right away.\n"
             "Customer: Don't bother. We're moving to another vendor next month."),
        ],
    },
    "high_frustration": {
        "expected_tier": "High",
        "tier_weights": {"Enterprise": 0.4, "Pro": 0.5, "Starter": 0.1},
        "csat": (2, 3), "disputes": (0, 1), "inactive": (10, 35),
        "transcripts": [
            ("Customer: The CSV export we were promised in Q1 still isn't here and it's "
             "blocking our reporting. Honestly I'm evaluating alternatives that have it.\n"
             "Agent: It's on the roadmap for next quarter.\n"
             "Customer: That's what you said last time. This is getting hard to justify "
             "internally."),
            ("Customer: The API keeps timing out and it's affecting our workflows daily. "
             "My team is losing patience.\n"
             "Agent: Have you tried increasing the retry window?\n"
             "Customer: We shouldn't have to. If this continues we'll have to look "
             "elsewhere."),
            ("Customer: Every release seems to break something. The dashboard is slower "
             "than it was six months ago and two features we rely on were removed.\n"
             "Agent: I'll pass the feedback along.\n"
             "Customer: I keep hearing that. We need to see actual improvement soon."),
            ("Customer: Onboarding my new team took way longer than it should — the docs "
             "are out of date and the SSO setup failed twice.\n"
             "Agent: Apologies for the trouble.\n"
             "Customer: It's shaken my confidence in rolling this out more widely."),
        ],
    },
    "billing_dispute": {
        "expected_tier": "High",
        "tier_weights": {"Enterprise": 0.3, "Pro": 0.5, "Starter": 0.2},
        "csat": (2, 3), "disputes": (2, 4), "inactive": (1, 12),
        "transcripts": [
            ("Customer: I was charged twice this month and the amount is wrong — this is "
             "really frustrating. The product is fine, but the billing keeps failing.\n"
             "Agent: I'll open a billing investigation.\n"
             "Customer: Please refund the duplicate today. This is the second month in a row."),
            ("Customer: My invoice jumped 40% with no notice and now there's a "
             "failed-payment flag even though my card is valid.\n"
             "Agent: Let me check the account.\n"
             "Customer: Fix this before you suspend us — we use the service every day."),
            ("Customer: You've applied a discount incorrectly for three billing cycles and "
             "I keep having to chase refunds. It's exhausting.\n"
             "Agent: I'm sorry, I'll correct it.\n"
             "Customer: I like the tool, but the billing errors are wearing me down."),
            ("Customer: There's a duplicate charge and a mystery 'overage' fee I don't "
             "understand. Can someone actually explain my bill?\n"
             "Agent: Of course, let me walk you through it.\n"
             "Customer: Thanks — I just need this sorted, it's happened too often."),
        ],
    },
    "passive_disengage": {
        "expected_tier": "Medium",
        "tier_weights": {"Enterprise": 0.3, "Pro": 0.4, "Starter": 0.3},
        "csat": (3, 4), "disputes": (0, 1), "inactive": (30, 80),
        "transcripts": [
            ("Customer: No urgent issue. We've scaled back usage this quarter while we "
             "review our tooling. Wanted to flag it in case it affects our plan.\n"
             "Agent: Thanks for letting us know — anything we can help with?\n"
             "Customer: Not right now, just evaluating options before renewal."),
            ("Customer: Quick one — is there a way to pause the subscription? Our usage "
             "has dropped and I'm reviewing all tools.\n"
             "Agent: I can share pause options.\n"
             "Customer: Great, we're deciding what to keep for next year."),
            ("Customer: We haven't logged in much lately. The team got busy and the tool "
             "slipped down our priority list.\n"
             "Agent: Would a refresher session help?\n"
             "Customer: Maybe later — we'll see how the quarter goes."),
            ("Customer: Just confirming our renewal date. We're doing a cost review and "
             "trimming subscriptions we don't fully use.\n"
             "Agent: It renews next month.\n"
             "Customer: Okay, noted. Still deciding on this one."),
        ],
    },
    "happy_advocate": {
        "expected_tier": "Low",
        "tier_weights": {"Enterprise": 0.4, "Pro": 0.4, "Starter": 0.2},
        "csat": (5, 5), "disputes": (0, 0), "inactive": (0, 10),
        "transcripts": [
            ("Customer: The team loves it — adoption is way up. We want to add 15 seats "
             "and look at the Enterprise tier. Who handles pricing?\n"
             "Agent: I'll connect you with your account manager!\n"
             "Customer: Perfect, we're expanding to a second department next month."),
            ("Customer: Fantastic support last week — resolved in minutes. Reliability has "
             "been great lately.\n"
             "Agent: So glad to hear it.\n"
             "Customer: We're rolling this out company-wide, honestly a pleasure to use."),
            ("Customer: Just wanted to say the new analytics view is excellent. It's "
             "saving us hours every week.\n"
             "Agent: Thank you, that means a lot!\n"
             "Customer: Keep it up — we're recommending you to a partner org."),
            ("Customer: Renewal's coming up and it's an easy yes. Might upgrade for the "
             "advanced permissions.\n"
             "Agent: Happy to help with that.\n"
             "Customer: Great product, great team."),
            ("Customer: Loving the reliability improvements this quarter. No complaints.\n"
             "Agent: Wonderful!\n"
             "Customer: We're increasing usage and adding a new project next sprint."),
        ],
    },
    "stable_neutral": {
        "expected_tier": "Low",
        "tier_weights": {"Enterprise": 0.2, "Pro": 0.4, "Starter": 0.4},
        "csat": (3, 4), "disputes": (0, 1), "inactive": (3, 25),
        "transcripts": [
            ("Customer: How do I reset a team member's password?\n"
             "Agent: I can walk you through it.\n"
             "Customer: Thanks, that worked."),
            ("Customer: Is there a guide for setting up a recurring report?\n"
             "Agent: Yes, I'll send the link.\n"
             "Customer: Appreciate it."),
            ("Customer: What's the API rate limit on the Pro plan? Planning a small "
             "integration.\n"
             "Agent: It's 600 requests/min.\n"
             "Customer: Perfect, that works for us."),
            ("Customer: Can you confirm which region our data is stored in?\n"
             "Agent: EU-West, as configured.\n"
             "Customer: Great, just doing some housekeeping."),
            ("Customer: How do I add a webhook for new events?\n"
             "Agent: Here are the steps.\n"
             "Customer: Got it, thanks for the quick help."),
        ],
    },
    "ambiguous": {
        "expected_tier": "Low",
        "tier_weights": {"Enterprise": 0.3, "Pro": 0.4, "Starter": 0.3},
        "csat": (3, 3), "disputes": (0, 0), "inactive": (5, 20),
        "transcripts": [
            ("Customer: Hi. Not sure yet.\n"
             "Agent: Happy to help — what's on your mind?\n"
             "Customer: Will let you know. Thanks."),
        ],
    },
}

# how many of each archetype -> 25 total
MIX = {
    "critical_churn": 3,
    "high_frustration": 4,
    "billing_dispute": 4,
    "passive_disengage": 4,
    "happy_advocate": 5,
    "stable_neutral": 4,
    "ambiguous": 1,
}


def _ri(rng, lo, hi):
    return rng.randint(lo, hi)


def _pick_tier(rng, weights):
    tiers, w = zip(*weights.items())
    return rng.choices(tiers, weights=w, k=1)[0]


def generate_customers(seed: int = 7) -> pd.DataFrame:
    rng = random.Random(seed)
    names = rng.sample(
        [f"{f} {l}" for f in FIRST for l in LAST], k=sum(MIX.values()))
    rows, cid, n = [], 1001, 0
    for arche, count in MIX.items():
        spec = ARCHETYPES[arche]
        transcripts = list(spec["transcripts"])
        rng.shuffle(transcripts)
        for i in range(count):
            rows.append({
                "customer_id": f"CUST-{cid}",
                "customer_name": names[n],
                "subscription_tier": _pick_tier(rng, spec["tier_weights"]),
                "csat_score": _ri(rng, *spec["csat"]),
                "billing_disputes_last_90d": _ri(rng, *spec["disputes"]),
                "days_inactive": _ri(rng, *spec["inactive"]),
                "support_transcript": transcripts[i % len(transcripts)],
                "expected_tier": spec["expected_tier"],   # audit only
                "_archetype": arche,                       # audit only
            })
            cid += 1
            n += 1
    df = pd.DataFrame(rows).sample(frac=1, random_state=seed).reset_index(drop=True)
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="data/customers.csv")
    args = ap.parse_args()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    df = generate_customers(args.seed)
    df.to_csv(args.out, index=False)
    print(f"Wrote {len(df)} customers -> {args.out}")
    print(df.groupby("_archetype").size().to_string())
