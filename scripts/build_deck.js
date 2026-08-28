const pptxgen = require("pptxgenjs");
const p = new pptxgen();
p.layout = "LAYOUT_WIDE"; const W = 13.3, H = 7.5;

const NAVY = "12213D", NAVY2 = "1E3A5F", TEAL = "1C7293", ICE = "CADCFC";
const CRIT = "B3261E", HIGH = "E0663B", MED = "E0A458", LOW = "4C9A6B";
const INK = "1F2937", MUTE = "6B7280", PAPER = "FFFFFF", CARD = "F4F6FA";
const HEAD = "Cambria", BODY = "Calibri", MONO = "Consolas";
const OUT = "outputs/";

function dot(s, x, y, c, r = 0.06) {
  s.addShape(p.ShapeType.ellipse, { x, y, w: r * 2, h: r * 2, fill: { color: c } });
}
function title(s, t, dark) {
  s.addText(t, { x: 0.6, y: 0.4, w: 12.1, h: 0.7, fontFace: HEAD, bold: true,
    fontSize: 30, color: dark ? PAPER : NAVY });
}
function motif(s) { for (let i = 0; i < 6; i++) dot(s, 11.15 + i * 0.28, 0.55, [TEAL, ICE, HIGH][i % 3], 0.05); }

// =====================================================================
// SLIDE 1 — PROBLEM UNDERSTANDING & OBJECTIVE (dark, two-column compare)
// =====================================================================
let s = p.addSlide();
s.background = { color: NAVY };
motif(s);
s.addText("POC · CUSTOMER OPERATIONS", { x: 0.6, y: 0.55, w: 8, h: 0.3, fontFace: BODY,
  bold: true, fontSize: 12, color: TEAL, charSpacing: 2 });
s.addText("Intelligent Customer Signal Detector", { x: 0.6, y: 0.92, w: 11, h: 0.7,
  fontFace: HEAD, bold: true, fontSize: 32, color: PAPER });
s.addText("Problem Understanding & Objective", { x: 0.6, y: 1.62, w: 11, h: 0.4,
  fontFace: BODY, italic: true, fontSize: 16, color: ICE });

// two-column comparison
const colY = 2.35, colH = 2.75, colW = 5.75;
// Reactive today
s.addShape(p.ShapeType.roundRect, { x: 0.6, y: colY, w: colW, h: colH, rectRadius: 0.1,
  fill: { color: NAVY2 } });
s.addText("REACTIVE TODAY", { x: 0.85, y: colY + 0.15, w: colW - 0.5, h: 0.4,
  fontFace: BODY, bold: true, fontSize: 15, color: HIGH, charSpacing: 1 });
["Signals siloed across chat, billing & usage",
 "Transcripts reviewed manually, one by one",
 "Action only after a complaint escalates",
 "Intervention lands after churn intent forms"].forEach((t, i) => {
  dot(s, 0.95, colY + 0.78 + i * 0.47, HIGH, 0.06);
  s.addText(t, { x: 1.2, y: colY + 0.62 + i * 0.47, w: colW - 0.75, h: 0.42,
    fontFace: BODY, fontSize: 13, color: ICE, valign: "middle" });
});
// Proactive with AI
s.addShape(p.ShapeType.roundRect, { x: 6.95, y: colY, w: colW, h: colH, rectRadius: 0.1,
  fill: { color: TEAL } });
s.addText("PROACTIVE WITH AI", { x: 7.2, y: colY + 0.15, w: colW - 0.5, h: 0.4,
  fontFace: BODY, bold: true, fontSize: 15, color: PAPER, charSpacing: 1 });
["Unified multi-signal scoring engine",
 "LLM correlates chat logs with telemetry",
 "Ranked daily action queue for Ops",
 "Intervene before the customer decides to leave"].forEach((t, i) => {
  dot(s, 7.3, colY + 0.78 + i * 0.47, PAPER, 0.06);
  s.addText(t, { x: 7.55, y: colY + 0.62 + i * 0.47, w: colW - 0.75, h: 0.42,
    fontFace: BODY, fontSize: 13, color: PAPER, valign: "middle" });
});

// bottom strip: objective + target user
s.addShape(p.ShapeType.roundRect, { x: 0.6, y: 5.35, w: 8.0, h: 1.55, rectRadius: 0.1,
  fill: { color: NAVY2 } });
s.addText("OBJECTIVE", { x: 0.85, y: 5.5, w: 7.5, h: 0.3, fontFace: BODY, bold: true,
  fontSize: 12, color: TEAL, charSpacing: 1.5 });
s.addText("Build a unified multi-signal scoring engine that correlates unstructured chat logs with CSAT, billing and usage telemetry to surface early churn/escalation risk.",
  { x: 0.85, y: 5.82, w: 7.5, h: 1.0, fontFace: BODY, fontSize: 14, color: PAPER });
s.addShape(p.ShapeType.roundRect, { x: 8.8, y: 5.35, w: 3.9, h: 1.55, rectRadius: 0.1,
  fill: { color: HIGH } });
s.addText("TARGET USER", { x: 9.05, y: 5.5, w: 3.5, h: 0.3, fontFace: BODY, bold: true,
  fontSize: 12, color: PAPER, charSpacing: 1.5 });
s.addText("Customer Operations & Retention teams needing a prioritized daily action queue.",
  { x: 9.05, y: 5.82, w: 3.5, h: 1.0, fontFace: BODY, fontSize: 14, color: PAPER });

// =====================================================================
// SLIDE 2 — SOLUTION ARCHITECTURE & DESIGN FLOW (light, pipeline)
// =====================================================================
s = p.addSlide(); s.background = { color: PAPER };
title(s, "Solution Architecture & Design Flow", false);
s.addText("Structured telemetry and unstructured chat converge into one prioritized triage view.",
  { x: 0.6, y: 1.12, w: 12, h: 0.4, fontFace: BODY, fontSize: 15, color: MUTE });

// input chips feeding the pipeline
const inputs = ["Support chat logs", "CSAT scores", "Billing disputes", "Login inactivity"];
inputs.forEach((t, i) => {
  s.addShape(p.ShapeType.roundRect, { x: 0.7, y: 2.0 + i * 0.78, w: 2.35, h: 0.6,
    rectRadius: 0.08, fill: { color: NAVY } });
  s.addText(t, { x: 0.7, y: 2.0 + i * 0.78, w: 2.35, h: 0.6, fontFace: BODY, bold: true,
    fontSize: 12.5, color: PAPER, align: "center", valign: "middle" });
});
s.addText("INPUTS", { x: 0.7, y: 1.62, w: 2.35, h: 0.3, fontFace: BODY, bold: true,
  fontSize: 11, color: MUTE, align: "center", charSpacing: 1.5 });

// 4 pipeline stages stacked, with down-arrows; fed from inputs
const st2 = [
  ["Ingestion", "Chat logs + structured usage/billing metrics normalized into one record.", TEAL],
  ["Signal Correlation Engine", "Heuristic weighting blended with LLM contextual reasoning over the transcript.", MED],
  ["Risk Scoring Layer", "Multi-factor 0–100 score mapped to Critical / High / Medium / Low SLA tiers.", CRIT],
  ["Triage UI", "Streamlit command center presenting prioritized intervention recommendations.", LOW],
];
const px0 = 4.35, pw = 8.35, ph = 1.06, pgap = 0.28, py0 = 1.78;
st2.forEach((d, i) => {
  const y = py0 + i * (ph + pgap);
  s.addShape(p.ShapeType.roundRect, { x: px0, y, w: pw, h: ph, rectRadius: 0.1, fill: { color: CARD } });
  s.addShape(p.ShapeType.roundRect, { x: px0, y, w: 0.9, h: ph, rectRadius: 0.1, fill: { color: d[2] } });
  s.addText(String(i + 1), { x: px0, y, w: 0.9, h: ph, fontFace: HEAD, bold: true,
    fontSize: 30, color: PAPER, align: "center", valign: "middle" });
  s.addText(d[0], { x: px0 + 1.15, y: y + 0.14, w: pw - 1.35, h: 0.4, fontFace: BODY,
    bold: true, fontSize: 16, color: NAVY });
  s.addText(d[1], { x: px0 + 1.15, y: y + 0.54, w: pw - 1.35, h: 0.45, fontFace: BODY,
    fontSize: 12.5, color: MUTE });
  if (i < 3) {
    const ay = y + ph;
    s.addShape(p.ShapeType.line, { x: px0 + pw / 2, y: ay, w: 0, h: pgap,
      line: { color: NAVY, width: 2, endArrowType: "triangle" } });
  }
});
// connector from inputs block to stage 1
s.addShape(p.ShapeType.line, { x: 3.05, y: 2.85, w: 1.3, h: 0,
  line: { color: NAVY, width: 2, endArrowType: "triangle" } });

// =====================================================================
// SLIDE 3 — IMPLEMENTATION HIGHLIGHTS (JSON schema + UI screenshot)
// =====================================================================
s = p.addSlide(); s.background = { color: PAPER };
title(s, "Implementation Highlights", false);

// left: JSON schema code panel
s.addShape(p.ShapeType.roundRect, { x: 0.6, y: 1.45, w: 5.75, h: 3.35, rectRadius: 0.08,
  fill: { color: NAVY } });
s.addText("Structured JSON output (zero-shot schema)", { x: 0.8, y: 1.58, w: 5.4, h: 0.35,
  fontFace: BODY, bold: true, fontSize: 13, color: TEAL });
const code = [
  '{',
  '  "churn_intent": 0.0-1.0,',
  '  "frustration": 0.0-1.0,',
  '  "competitor_mention": bool,',
  '  "feature_gap": bool,',
  '  "billing_issue": bool,',
  '  "passive_dissatisfaction": bool,',
  '  "sentiment": -1.0..1.0,',
  '  "confidence": 0.0-1.0,',
  '  "key_phrases": [string]',
  '}',
].join("\n");
s.addText(code, { x: 0.8, y: 2.0, w: 5.4, h: 2.55, fontFace: MONO, fontSize: 12,
  color: ICE, align: "left", valign: "top", lineSpacingMultiple: 1.1 });

// left-bottom caption
s.addText("Enforced JSON → reliable parsing into operational tables.",
  { x: 0.6, y: 4.9, w: 5.75, h: 0.4, fontFace: BODY, italic: true, fontSize: 12, color: MUTE });

// right: UI screenshot (risk matrix)
let rw = 6.35, rh = rw / (1476 / 826);   // risk_matrix aspect
s.addImage({ path: OUT + "risk_matrix.png", x: 6.6, y: 1.45, w: rw, h: rw / 1.786 });
s.addText("Live risk matrix from the Streamlit command center.",
  { x: 6.6, y: 1.45 + rw / 1.786 + 0.03, w: rw, h: 0.35, fontFace: BODY, italic: true,
    fontSize: 11.5, color: MUTE });

// bottom: three highlight bullets
const hi = [
  ["Hybrid signal analysis", "Hard thresholds (CSAT ≤ 2, high disputes) + soft semantic signals (passive dissatisfaction, competitor mentions).", TEAL],
  ["Pydantic-validated output", "Zero-shot JSON is schema-validated before scoring — malformed reads are caught and safely handled.", MED],
  ["Confidence + human-in-loop", "Low-confidence transcript reads are auto-flagged for manual review; every flag cites transcript evidence.", LOW],
];
const bw = 3.9, by = 5.55;
hi.forEach((d, i) => {
  const x = 0.6 + i * (bw + 0.2);
  s.addShape(p.ShapeType.roundRect, { x, y: by, w: bw, h: 1.5, rectRadius: 0.08, fill: { color: CARD } });
  dot(s, x + 0.24, by + 0.3, d[2], 0.08);
  s.addText(d[0], { x: x + 0.46, y: by + 0.12, w: bw - 0.6, h: 0.4, fontFace: BODY,
    bold: true, fontSize: 13.5, color: NAVY, valign: "middle" });
  s.addText(d[1], { x: x + 0.24, y: by + 0.6, w: bw - 0.45, h: 0.85, fontFace: BODY,
    fontSize: 11, color: INK });
});

// =====================================================================
// SLIDE 4 — CHALLENGES & LEARNINGS (2x2: challenge vs solution)
// =====================================================================
s = p.addSlide(); s.background = { color: PAPER };
title(s, "Challenges & Learnings", false);
s.addText("Every challenge resolved by anchoring AI judgment to hard evidence.",
  { x: 0.6, y: 1.12, w: 12, h: 0.4, fontFace: BODY, fontSize: 15, color: MUTE });

const items = [
  ["Signal noise & false positives", "A venting-but-happy customer must not top the queue.",
   "Anchor qualitative sentiment with hard billing/usage metrics; positive-language guard caps churn intent."],
  ["LLM latency & cost", "Scoring 100s of transcripts in real time is a bottleneck.",
   "Batch transcript analysis asynchronously; deterministic scoring runs instantly on cached signals."],
  ["Operational trust", "Ops teams reject a raw sentiment score they can't defend.",
   "Every flag shows its key_signals + transcript evidence — explainable, not black-box."],
  ["Reliable structured output", "Free-form LLM text breaks downstream tables.",
   "Zero-shot JSON schema + robust parsing + mock fallback keep the pipeline unbreakable."],
];
const cW = 6.05, cH = 2.35, gx = 0.6, gyy = 1.6, gpx = 0.6, gpy = 0.2;
items.forEach((it, i) => {
  const x = gx + (i % 2) * (cW + gpx);
  const y = gyy + Math.floor(i / 2) * (cH + gpy);
  s.addShape(p.ShapeType.roundRect, { x, y, w: cW, h: cH, rectRadius: 0.09, fill: { color: CARD } });
  dot(s, x + 0.3, y + 0.36, MED, 0.09);
  s.addText(it[0], { x: x + 0.55, y: y + 0.15, w: cW - 0.7, h: 0.45, fontFace: BODY,
    bold: true, fontSize: 15.5, color: NAVY });
  s.addText([{ text: "Challenge  ", options: { bold: true, color: CRIT, fontSize: 11.5 } },
             { text: it[1], options: { color: INK, fontSize: 12.5 } }],
    { x: x + 0.3, y: y + 0.72, w: cW - 0.55, h: 0.66 });
  s.addText([{ text: "Solution  ", options: { bold: true, color: LOW, fontSize: 11.5 } },
             { text: it[2], options: { color: INK, fontSize: 12.5 } }],
    { x: x + 0.3, y: y + 1.42, w: cW - 0.55, h: 0.85 });
});

// =====================================================================
// SLIDE 5 — DEMO SUMMARY & NEXT STEPS (dark, roadmap + links)
// =====================================================================
s = p.addSlide(); s.background = { color: NAVY };
title(s, "Demo Summary & Next Steps", true); motif(s);

s.addText("Demo recap", { x: 0.6, y: 1.25, w: 6, h: 0.4, fontFace: BODY, bold: true,
  fontSize: 15, color: TEAL });
["End-to-end: synthetic chat logs → AI analysis → real-time risk triage queue",
 "KPI cards, risk matrix, triage table, inspector & a persisted action log",
 "Each flag ships a risk score, evidence, rationale, and a retention action",
 "Runs with any LLM (Anthropic/OpenAI/Gemini) or a no-key deterministic fallback"]
  .forEach((t, i) => {
    dot(s, 0.72, 1.86 + i * 0.52, LOW, 0.07);
    s.addText(t, { x: 0.97, y: 1.69 + i * 0.52, w: 6.0, h: 0.47, fontFace: BODY,
      fontSize: 13, color: ICE, valign: "middle" });
  });

let tw = 6.1, th = tw / (1335 / 484 > 0 ? 2.9 : 2.9);
s.addImage({ path: OUT + "triage_table.png", x: 0.6, y: 4.05, w: tw, h: tw / 2.9 });
s.addText("Priority action triage (sample output)", { x: 0.6, y: 4.05 + tw / 2.9 + 0.03,
  w: tw, h: 0.3, fontFace: BODY, italic: true, fontSize: 11, color: MUTE });

// right: roadmap pillars
s.addShape(p.ShapeType.roundRect, { x: 7.0, y: 1.25, w: 5.7, h: 3.75, rectRadius: 0.12,
  fill: { color: NAVY2 } });
s.addText("Production next steps", { x: 7.25, y: 1.42, w: 5.2, h: 0.4, fontFace: BODY,
  bold: true, fontSize: 15, color: HIGH });
[["1 · Live integrations", "Webhooks into Zendesk, Intercom & Stripe for real-time signals."],
 ["2 · Automated alerting", "Push Critical-tier flags to Slack / PagerDuty instantly."],
 ["3 · Closed-loop learning", "Action log ships today; next, correlate outcomes to refine scoring."]]
  .forEach((t, i) => {
    const y = 2.0 + i * 0.98;
    dot(s, 7.45, y + 0.14, TEAL, 0.08);
    s.addText(t[0], { x: 7.7, y: y - 0.02, w: 4.85, h: 0.38, fontFace: BODY, bold: true,
      fontSize: 14, color: PAPER });
    s.addText(t[1], { x: 7.7, y: y + 0.34, w: 4.85, h: 0.55, fontFace: BODY,
      fontSize: 12, color: ICE });
  });

// links badges
s.addShape(p.ShapeType.roundRect, { x: 7.0, y: 5.2, w: 5.7, h: 1.65, rectRadius: 0.12,
  fill: { color: TEAL } });
s.addText("Links", { x: 7.25, y: 5.33, w: 5, h: 0.32, fontFace: BODY, bold: true,
  fontSize: 14, color: NAVY, charSpacing: 1.5 });
s.addText([
  { text: "GitHub:  ", options: { bold: true, color: NAVY, fontSize: 13 } },
  { text: "<add repo link>", options: { color: PAPER, fontSize: 13, breakLine: true } },
  { text: "Demo (Loom):  ", options: { bold: true, color: NAVY, fontSize: 13 } },
  { text: "<add video link>", options: { color: PAPER, fontSize: 13, breakLine: true } },
  { text: "Run:  ", options: { bold: true, color: NAVY, fontSize: 13 } },
  { text: "streamlit run app.py", options: { color: PAPER, fontSize: 13, fontFace: MONO } },
], { x: 7.25, y: 5.68, w: 5.3, h: 1.1, lineSpacingMultiple: 1.3 });

p.writeFile({ fileName: "outputs/ICSD_Summary_Deck.pptx" }).then(f => console.log("Wrote", f));
