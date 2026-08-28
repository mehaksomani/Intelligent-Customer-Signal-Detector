"""
app.py — Intelligent Customer Signal Detector (Streamlit command center)
========================================================================
Run:
    pip install -r requirements.txt
    streamlit run app.py

Flow:  customers.csv  ->  detector.analyze_dataframe()  ->  KPIs, risk matrix,
priority triage table, per-customer inspector, and filtered CSV export.

Set ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY to enable LLM analysis.
With no key the app runs in deterministic mock mode (clearly labelled).
"""
import os
import pandas as pd
import streamlit as st
import plotly.express as px
from dotenv import load_dotenv

# MUST be called before importing detector!
load_dotenv()
from src import detector
from src import data_generator
from src import db

db.init_db()

st.set_page_config(page_title="Customer Signal Detector",
                   page_icon="📡", layout="wide")

TIER_COLOR = {"Critical": "#B3261E", "High": "#E0663B",
              "Medium": "#E0A458", "Low": "#4C9A6B"}
TIER_ORDER = ["Critical", "High", "Medium", "Low"]
DATA_PATH = "data/customers.csv"


# --------------------------------------------------------------------------
# Data + analysis (cached so re-filtering doesn't re-run the engine)
# --------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_and_analyze(csv_bytes: bytes | None, regen_token: int):
    if csv_bytes is not None:
        from io import BytesIO
        df = pd.read_csv(BytesIO(csv_bytes))
    else:
        if not os.path.exists(DATA_PATH):
            os.makedirs("data", exist_ok=True)
            data_generator.generate_customers().to_csv(DATA_PATH, index=False)
        df = pd.read_csv(DATA_PATH)
    required = {"customer_id", "customer_name", "subscription_tier", "csat_score",
                "billing_disputes_last_90d", "days_inactive", "support_transcript"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Input CSV is missing columns: {', '.join(sorted(missing))}")
    result, mode = detector.analyze_dataframe(df)
    return result, mode


def tier_badge(tier: str) -> str:
    return f"<span style='background:{TIER_COLOR[tier]};color:white;padding:2px 10px;" \
           f"border-radius:10px;font-size:0.8rem;font-weight:600'>{tier}</span>"


# --------------------------------------------------------------------------
# Sidebar — data source, provider status, filters
# --------------------------------------------------------------------------
st.sidebar.title("📡 Signal Detector")

st.sidebar.header("Data source")
src = st.sidebar.radio("Source", ["Sample (25 synthetic)", "Upload CSV"],
                       label_visibility="collapsed")
csv_bytes, regen = None, 0
if src == "Upload CSV":
    up = st.sidebar.file_uploader("Customer CSV", type="csv")
    if up is None:
        st.sidebar.info("Upload a CSV with the required schema, or use the sample.")
        st.stop()
    csv_bytes = up.getvalue()
else:
    if "regen" not in st.session_state:
        st.session_state.regen = 0
    if st.sidebar.button("🔄 Regenerate sample"):
        os.makedirs("data", exist_ok=True)
        data_generator.generate_customers(
            seed=st.session_state.regen + 1).to_csv(DATA_PATH, index=False)
        st.session_state.regen += 1
        st.cache_data.clear()
    regen = st.session_state.regen

try:
    with st.spinner("Analyzing customer signals…"):
        data, mode = load_and_analyze(csv_bytes, regen)
except Exception as e:
    st.error(f"Could not analyze data: {e}")
    st.stop()

# --------------------------------------------------------------------------
# Header + mode banner
# --------------------------------------------------------------------------
st.title("Intelligent Customer Signal Detector")
st.caption("Correlates support transcripts with CSAT, billing and inactivity "
           "telemetry to surface churn/escalation risk — with a prioritized action queue.")

if mode == "mock":
    st.info("⚙️ **Mock mode** — no LLM API key detected, using deterministic keyword "
            "analysis. Set `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or `GEMINI_API_KEY` "
            "for full LLM reasoning.")
else:
    st.success(f"🧠 **LLM mode** — transcript analysis via **{mode}**.")

# --------------------------------------------------------------------------
# Filters
# --------------------------------------------------------------------------
st.sidebar.header("Filters")
tiers = st.sidebar.multiselect("Risk tier", TIER_ORDER,
                               default=["Critical", "High", "Medium"])
subs = st.sidebar.multiselect("Subscription tier",
                              sorted(data["subscription_tier"].unique()),
                              default=sorted(data["subscription_tier"].unique()))
min_score = st.sidebar.slider("Minimum risk score", 0, 100, 0)

with st.sidebar.expander("ℹ️ How scoring works"):
    st.caption("Transparent weighted blend of transcript (LLM) + telemetry signals, "
               "with hard-rule overrides. Tiers: Critical ≥ 75, High ≥ 50, "
               "Medium ≥ 25, Low < 25. Reads below 60% confidence are flagged "
               "for manual review.")
    st.dataframe(pd.DataFrame({"weight": detector.WEIGHTS}).style.format("{:.0%}"),
                 use_container_width=True)

view = data[data["risk_tier"].isin(tiers)
            & data["subscription_tier"].isin(subs)
            & (data["risk_score"] >= min_score)].copy()
view = view.sort_values("risk_score", ascending=False)

# --------------------------------------------------------------------------
# KPI cards
# --------------------------------------------------------------------------
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total monitored", len(data))
c2.metric("🔴 Critical risk", int((data["risk_tier"] == "Critical").sum()))
c3.metric("🟠 High risk", int((data["risk_tier"] == "High").sum()))
c4.metric("Average risk score", f"{data['risk_score'].mean():.0f}")
c5.metric("⚠️ Needs review", int(data["needs_review"].sum()),
          help="Transcripts the model read with low confidence — route to a human.")

st.divider()

# --------------------------------------------------------------------------
# Risk matrix (bubble) + triage table
# --------------------------------------------------------------------------
left, right = st.columns([1.05, 1])

with left:
    st.subheader("Risk matrix")
    st.caption("Days inactive × CSAT · bubble size = billing disputes · color = risk tier")
    plot_df = view.copy()
    plot_df["disputes_size"] = plot_df["billing_disputes_last_90d"] + 0.6  # keep 0 visible
    fig = px.scatter(
        plot_df, x="days_inactive", y="csat_score",
        size="disputes_size", color="risk_tier",
        color_discrete_map=TIER_COLOR, category_orders={"risk_tier": TIER_ORDER},
        hover_name="customer_name",
        hover_data={"customer_id": True, "risk_score": True, "risk_tier": True,
                    "subscription_tier": True, "billing_disputes_last_90d": True,
                    "disputes_size": False, "csat_score": False, "days_inactive": False},
        size_max=34, labels={"days_inactive": "Days inactive", "csat_score": "CSAT (1–5)",
                             "risk_tier": "Risk tier"})
    fig.update_yaxes(range=[0.5, 5.5], dtick=1)
    fig.update_layout(height=460, legend_title_text="", margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("Priority action triage")
    st.caption("Sorted by risk score. Highest-urgency accounts first.")
    decided = db.latest_decisions()
    table = view[["customer_id", "customer_name", "subscription_tier", "risk_score",
                  "risk_tier", "confidence", "suggested_retention_action"]].copy()
    table.insert(5, "status", table["customer_id"].map(decided).fillna("— open —"))
    table = table.rename(columns={
        "customer_id": "ID", "customer_name": "Customer", "subscription_tier": "Plan",
        "risk_score": "Risk", "risk_tier": "Tier", "confidence": "Conf",
        "status": "Status", "suggested_retention_action": "Recommended action"})

    def _hl(row):
        return [f"background-color: {TIER_COLOR[row['Tier']]}22"] * len(row)

    st.dataframe(
        table.style.apply(_hl, axis=1).format({"Risk": "{:.0f}", "Conf": "{:.0%}"}),
        use_container_width=True, height=420, hide_index=True)

    st.download_button(
        "⬇️ Export filtered signals (CSV)",
        view.drop(columns=["contributions", "qualitative_signals"], errors="ignore")
            .to_csv(index=False),
        file_name="priority_signals.csv", mime="text/csv")

st.divider()

# --------------------------------------------------------------------------
# Inspector panel
# --------------------------------------------------------------------------
st.subheader("🔎 Customer inspector")
if not len(view):
    st.info("No customers match the current filters.")
else:
    pick = st.selectbox("Select a customer",
                        (view["customer_id"] + " · " + view["customer_name"]).tolist())
    row = view[view["customer_id"] == pick.split(" · ")[0]].iloc[0]

    a, b = st.columns([1.1, 1])
    with a:
        st.markdown(f"### {row['customer_name']}")
        st.markdown(f"`{row['customer_id']}` · **{row['subscription_tier']}**  "
                    f"{tier_badge(row['risk_tier'])}  ·  Risk **{row['risk_score']:.0f}/100**  "
                    f"·  Confidence **{row['confidence']:.0%}**",
                    unsafe_allow_html=True)
        if row["needs_review"]:
            st.warning("⚠️ Low extraction confidence — route to a human for manual review "
                       "before acting.")
        m1, m2, m3 = st.columns(3)
        m1.metric("CSAT", f"{row['csat_score']}/5")
        m2.metric("Billing disputes", int(row["billing_disputes_last_90d"]))
        m3.metric("Days inactive", int(row["days_inactive"]))

        st.markdown("**🧠 AI rationale**")
        st.info(row["rationale"])
        st.markdown("**✅ Recommended retention action**")
        st.success(row["suggested_retention_action"])

        if row.get("evidence"):
            st.markdown("**🔍 Evidence from transcript**")
            st.markdown("".join(
                f"<span style='display:inline-block;background:#FFF3CD;border-radius:8px;"
                f"padding:3px 10px;margin:3px 4px 0 0;font-size:0.85rem'>“{e}”</span>"
                for e in row["evidence"]), unsafe_allow_html=True)

        st.markdown("**Key signals**")
        st.markdown("".join(
            f"<span style='display:inline-block;background:#EEF2F7;border-radius:8px;"
            f"padding:3px 10px;margin:3px 4px 0 0;font-size:0.85rem'>{s}</span>"
            for s in row["key_signals"]), unsafe_allow_html=True)

    with b:
        st.markdown("**📄 Support transcript**")
        st.text_area("transcript", row["support_transcript"], height=200,
                     label_visibility="collapsed")

        # quantitative "why": per-signal points that build the risk score
        contrib = {k: v for k, v in row["contributions"].items() if v > 0}
        if contrib:
            cdf = (pd.DataFrame({"signal": list(contrib.keys()),
                                 "points": list(contrib.values())})
                   .sort_values("points"))
            cdf["signal"] = cdf["signal"].str.replace("_", " ")
            cfig = px.bar(cdf, x="points", y="signal", orientation="h",
                          title="Risk score contribution (points)",
                          color_discrete_sequence=[TIER_COLOR[row["risk_tier"]]])
            cfig.update_layout(height=230, margin=dict(l=0, r=0, t=34, b=0),
                               xaxis_title=None, yaxis_title=None, showlegend=False)
            st.plotly_chart(cfig, use_container_width=True)

        q = row["qualitative_signals"]
        st.caption(
            f"Transcript signals · sentiment {q['sentiment']:+.2f} · "
            f"churn intent {q['churn_intent']:.2f} · frustration {q['frustration']:.2f} · "
            f"competitor: {'yes' if q['competitor_mention'] else 'no'} · "
            f"feature gap: {'yes' if q['feature_gap'] else 'no'} · "
            f"billing issue: {'yes' if q['billing_issue'] else 'no'}")

    # ---- close the loop: log the action an agent took on this customer -------
    st.markdown("**📝 Log a triage action** (closes the loop — persisted for audit)")
    with st.form("action_form", clear_on_submit=True):
        f1, f2 = st.columns([1, 2])
        decision = f1.selectbox("Decision", db.DECISIONS)
        note = f2.text_input("Note (optional)", placeholder="e.g. Left voicemail, "
                             "offered 10% renewal credit")
        if st.form_submit_button("Save action"):
            db.record_action(row["customer_id"], row["customer_name"],
                             row["risk_tier"], float(row["risk_score"]), decision, note)
            st.success(f"Logged “{decision}” for {row['customer_name']}.")
            st.rerun()

st.divider()

# --------------------------------------------------------------------------
# Triage action log (persisted history)
# --------------------------------------------------------------------------
st.subheader("📋 Triage action log")
log = db.read_actions()
if log.empty:
    st.caption("No actions logged yet — record one from the inspector above.")
else:
    show_log = log[["logged_at", "customer_id", "customer_name", "risk_tier",
                    "risk_score", "decision", "note"]].rename(columns={
        "logged_at": "When (UTC)", "customer_id": "ID", "customer_name": "Customer",
        "risk_tier": "Tier", "risk_score": "Risk", "decision": "Decision", "note": "Note"})
    st.dataframe(show_log.style.format({"Risk": "{:.0f}"}),
                 use_container_width=True, height=240, hide_index=True)
    st.download_button("⬇️ Export action log (CSV)", log.to_csv(index=False),
                       "triage_action_log.csv", "text/csv")
