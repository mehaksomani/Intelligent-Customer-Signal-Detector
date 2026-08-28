"""Generate static assets for the summary deck + README sample output.
Run from the project root:  python scripts/make_assets.py
"""
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import plotly.express as px
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

logging.disable(logging.WARNING)
from src.detector import analyze_dataframe

os.makedirs("outputs", exist_ok=True)
TIER_COLOR = {"Critical": "#B3261E", "High": "#E0663B", "Medium": "#E0A458", "Low": "#4C9A6B"}
TIER_ORDER = ["Critical", "High", "Medium", "Low"]

df = pd.read_csv("data/customers.csv")
res, mode = analyze_dataframe(df)
res.sort_values("risk_score", ascending=False).drop(
    columns=["contributions", "qualitative_signals"]).to_csv(
    "outputs/scored_customers.csv", index=False)

# ---------- 1. Risk matrix (real Plotly bubble chart) ----------
pl = res.copy()
pl["disputes_size"] = pl["billing_disputes_last_90d"] + 0.6
fig = px.scatter(
    pl, x="days_inactive", y="csat_score", size="disputes_size", color="risk_tier",
    color_discrete_map=TIER_COLOR, category_orders={"risk_tier": TIER_ORDER},
    hover_name="customer_name", size_max=40,
    labels={"days_inactive": "Days inactive", "csat_score": "CSAT (1–5)", "risk_tier": "Risk tier"},
    title="Risk Matrix — Days Inactive × CSAT (size = disputes, color = tier)")
fig.update_yaxes(range=[0.5, 5.5], dtick=1)
fig.update_layout(width=1100, height=620, template="plotly_white",
                  legend_title_text="", font=dict(size=15),
                  margin=dict(l=60, r=20, t=60, b=55))
try:
    fig.write_image("outputs/risk_matrix.png", scale=2)
    print("risk_matrix.png via kaleido")
except Exception as e:                              # matplotlib fallback
    print("kaleido failed, matplotlib fallback:", e)
    plt.figure(figsize=(11, 6.2))
    for t in TIER_ORDER:
        d = pl[pl["risk_tier"] == t]
        plt.scatter(d["days_inactive"], d["csat_score"],
                    s=(d["billing_disputes_last_90d"] + 0.6) * 220,
                    c=TIER_COLOR[t], alpha=0.75, edgecolors="white", label=t)
    plt.xlabel("Days inactive"); plt.ylabel("CSAT (1–5)"); plt.ylim(0.5, 5.5)
    plt.title("Risk Matrix — Days Inactive × CSAT (size = disputes, color = tier)")
    plt.legend(title="Risk tier"); plt.tight_layout()
    plt.savefig("outputs/risk_matrix.png", dpi=150); plt.close()

# ---------- 2. Priority triage table (top 10) ----------
q = res.sort_values("risk_score", ascending=False).head(10)[
    ["customer_id", "customer_name", "subscription_tier", "csat_score",
     "billing_disputes_last_90d", "days_inactive", "risk_score", "confidence",
     "risk_tier"]].copy()
q.columns = ["ID", "Customer", "Plan", "CSAT", "Disputes", "Inactive", "Risk",
             "Conf", "Tier"]
q["Risk"] = q["Risk"].round(0).astype(int)
q["Conf"] = (q["Conf"] * 100).round(0).astype(int).astype(str) + "%"
fig2, ax = plt.subplots(figsize=(12, 4.4)); ax.axis("off")
tbl = ax.table(cellText=q.values, colLabels=q.columns, cellLoc="center", loc="center")
tbl.auto_set_font_size(False); tbl.set_fontsize(10); tbl.scale(1, 1.7)
for j in range(len(q.columns)):
    tbl[0, j].set_facecolor("#12213D"); tbl[0, j].set_text_props(color="w", weight="bold")
for i in range(len(q)):
    tbl[i + 1, 8].set_facecolor(TIER_COLOR[q.iloc[i]["Tier"]] + "66")
ax.set_title("Priority Action Triage — top 10 by risk score", fontsize=13,
             weight="bold", pad=14)
plt.savefig("outputs/triage_table.png", bbox_inches="tight", dpi=150); plt.close()

# ---------- 3. 4-stage pipeline diagram ----------
fig3, ax = plt.subplots(figsize=(12, 3.6)); ax.set_xlim(0, 12); ax.set_ylim(0, 3.6); ax.axis("off")
stages = [
    ("Ingestion", "Unstructured chat logs\n+ CSAT · billing · inactivity", "#DBE4F0"),
    ("Signal Correlation\nEngine", "Heuristic weighting\nblended with LLM reasoning", "#F0E2D0"),
    ("Risk Scoring Layer", "Multi-factor score 0–100\nmapped to SLA tiers", "#F7D9D9"),
    ("Triage UI", "Streamlit command center\n+ retention actions", "#DBEEE0"),
]
w, h, gap, y = 2.6, 1.8, 0.55, 1.0
for i, (t, d, c) in enumerate(stages):
    x = 0.3 + i * (w + gap)
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.06,rounding_size=0.12",
                                fc=c, ec="#12213D", lw=1.5))
    ax.text(x + w / 2, y + h - 0.42, f"{i+1}. {t}", ha="center", va="center",
            fontsize=11.5, weight="bold", color="#12213D")
    ax.text(x + w / 2, y + 0.5, d, ha="center", va="center", fontsize=9.5, color="#333")
    if i < 3:
        ax.add_patch(FancyArrowPatch((x + w, y + h / 2), (x + w + gap, y + h / 2),
                     arrowstyle="-|>", mutation_scale=18, lw=1.8, color="#12213D"))
ax.set_title("Solution Architecture — 4-stage pipeline", fontsize=13, weight="bold")
plt.tight_layout(); plt.savefig("outputs/pipeline.png", bbox_inches="tight", dpi=150); plt.close()

print("Assets written to outputs/ · mode:", mode,
      "· tier agreement:", f"{(res['risk_tier']==res['expected_tier']).mean()*100:.0f}%"
      if "expected_tier" in res else "n/a")
