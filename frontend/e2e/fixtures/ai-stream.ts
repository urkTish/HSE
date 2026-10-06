/**
 * Recorded /ai/ask Server-Sent Events stream (test fixture only — never imported by app code).
 * Typed against the contract's AiStreamEvent payloads so a contract change breaks the build.
 * There is no ANTHROPIC_API_KEY in e2e, so the UI's streaming path is exercised by replaying this.
 */
import type { components } from "../../src/lib/api/schema";

type S = components["schemas"];

export const ANSWER_ID = "7d0f1c4e-2a55-4b8e-9d6a-0c1f2e3d4a5b";
export const CONVERSATION_ID = "5b2c9e10-8f3a-4c7d-a1e2-3f4a5b6c7d8e";

const citations: S["AiCitation"][] = [
  {
    id: "c1",
    tool: "get_kpis",
    metric: "K-21",
    value_display: "0.92",
    period_label_en: "Sep 2026",
    scope_label_en: "ANIA-EXP, all contractors",
    base_label_en: "per 200,000 h",
    refs: [],
    text_en: "TRIR 0.92 — get_kpis, ANIA-EXP, Sep 2026, all contractors, per 200,000 h",
    text_ar: "معدل الحالات المسجلة 0.92 — get_kpis، ANIA-EXP، سبتمبر 2026، جميع المقاولين، لكل 200,000 ساعة",
  },
  {
    id: "c2",
    tool: "get_kpi_timeseries",
    metric: "K-21",
    value_display: null,
    period_label_en: "Oct 2025 – Sep 2026",
    scope_label_en: "ANIA-EXP, all contractors",
    base_label_en: "per 200,000 h",
    refs: [],
    text_en: "Monthly TRIR — get_kpi_timeseries, ANIA-EXP, Oct 2025 – Sep 2026",
    text_ar: "معدل الحالات المسجلة الشهري — get_kpi_timeseries، ANIA-EXP، أكتوبر 2025 – سبتمبر 2026",
  },
];

const chart: S["ChartSpec"] = {
  chart_id: "ai-1",
  kind: "bar",
  title_en: "Monthly TRIR, ANIA-EXP",
  title_ar: "معدل الحالات المسجلة الشهري، ANIA-EXP",
  x_axis: {
    kind: "period",
    label_en: "Month",
    label_ar: "الشهر",
    categories: [
      { key: "2026-07", label_en: "Jul 2026", label_ar: "يوليو 2026" },
      { key: "2026-08", label_en: "Aug 2026", label_ar: "أغسطس 2026" },
      { key: "2026-09", label_en: "Sep 2026", label_ar: "سبتمبر 2026" },
    ],
  },
  y_axes: [
    {
      id: "rate",
      label_en: "TRIR",
      label_ar: "معدل الحالات المسجلة",
      unit_en: "per 200,000 h",
      unit_ar: "لكل 200,000 ساعة",
    },
  ],
  series: [
    {
      key: "K-21",
      label_en: "TRIR",
      label_ar: "معدل الحالات المسجلة",
      kind: "bar",
      y_axis: "rate",
      stack: null,
      color_role: "lagging",
      points: [
        { x: "2026-07", value: "0.51", display: "0.51" },
        { x: "2026-08", value: "0.99", display: "0.99" },
        { x: "2026-09", value: "0.92", display: "0.92" },
      ],
    },
  ],
  bands: [],
  reference_lines: [],
  table: null,
  notes: [],
  citation: {
    tool: "get_kpi_timeseries",
    metric: "K-21",
    period_label_en: "Jul – Sep 2026",
    scope_label_en: "ANIA-EXP",
    base_label_en: "per 200,000 h",
  },
};

const recommendations: S["AiRecommendation"][] = [
  {
    id: "r2",
    control_level: "administrative",
    title: "Re-brief scaffold inspection tagging",
    text: "Weekly scaffold tag audits on Pier B; brief all NAJD supervisors (cites c1).",
    citation_ids: ["c1"],
  },
  {
    id: "r1",
    control_level: "engineering",
    title: "Install double guardrails and toe-boards",
    text: "Fit double guardrails and toe-boards on all working platforms above 2 m at Pier B (cites c1, c2).",
    citation_ids: ["c1", "c2"],
  },
];

const text =
  "TRIR for ANIA-EXP in **Sep 2026** was **0.92 per 200,000 h** (4 recordable cases, 870,000 man-hours).\n\n" +
  "Sources: [1] get_kpis, ANIA-EXP, Sep 2026, all contractors, per 200,000 h";

const answer: S["AiAnswer"] = {
  id: ANSWER_ID,
  conversation_id: CONVERSATION_ID,
  project_id: "00000000-0000-0000-0000-000000000000",
  language: "en",
  question_masked: "What was our TRIR in September 2026? Call me on [MOBILE]",
  prompt_warnings: ["MOBILE_MASKED"],
  text,
  citations,
  recommendations,
  chart,
  grounding: "passed",
  fallback_table: null,
  ai_label_en: "AI-generated — check before use",
  ai_label_ar: "مُنشأ بالذكاء الاصطناعي — تحقق قبل الاستخدام",
  model: "claude-sonnet",
  created_at: "2026-10-06T08:00:00Z",
};

type Frame = [string, unknown];

function encode(frames: Frame[]): string {
  return frames.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join(": keep-alive\n\n");
}

/** Full happy-path stream: meta → status* → delta* → citations → chart → recommendations → done. */
export function trirStream(projectId: string): string {
  const meta: S["AiStreamMeta"] = {
    answer_id: ANSWER_ID,
    conversation_id: CONVERSATION_ID,
    model: "claude-sonnet",
    prompt_warnings: ["MOBILE_MASKED"],
    question_masked: answer.question_masked,
  };
  const status: S["AiStreamStatus"][] = [
    {
      stage: "tool",
      tool: "get_kpis",
      message_en: "Reading KPIs…",
      message_ar: "قراءة المؤشرات…",
    },
    {
      stage: "grounding",
      tool: null,
      message_en: "Checking every number…",
      message_ar: "التحقق من كل رقم…",
    },
  ];
  const chunks = [text.slice(0, 40), text.slice(40, 100), text.slice(100)];
  return encode([
    ["meta", meta],
    ...status.map((s): Frame => ["status", s]),
    ...chunks.map((c): Frame => ["delta", { text: c } satisfies S["AiStreamDelta"]]),
    ["citations", citations],
    ["chart", chart],
    ["recommendations", recommendations],
    ["done", { ...answer, project_id: projectId }],
  ]);
}

/** Insufficient data: no figures in scope, nothing cited, no chart. */
export function insufficientStream(projectId: string): string {
  const t = "No man-hours are recorded for ANIA-EXP in Oct 2026, so rates cannot be calculated.";
  return encode([
    [
      "meta",
      {
        answer_id: ANSWER_ID,
        conversation_id: CONVERSATION_ID,
        model: "claude-sonnet",
        prompt_warnings: [],
        question_masked: "TRIR this month?",
      },
    ],
    ["delta", { text: t }],
    ["citations", []],
    [
      "done",
      {
        ...answer,
        project_id: projectId,
        text: t,
        citations: [],
        recommendations: [],
        chart: null,
        prompt_warnings: [],
        grounding: "not_applicable",
        question_masked: "TRIR this month?",
      },
    ],
  ]);
}

/** Provider times out after the stream started (AI-18). */
export function midStreamErrorStream(): string {
  return encode([
    [
      "meta",
      {
        answer_id: ANSWER_ID,
        conversation_id: CONVERSATION_ID,
        model: "claude-sonnet",
        prompt_warnings: [],
        question_masked: "x",
      },
    ],
    [
      "status",
      {
        stage: "thinking",
        tool: null,
        message_en: "Thinking…",
        message_ar: "جارٍ التفكير…",
      },
    ],
    [
      "error",
      {
        code: "AI_UNAVAILABLE",
        message: "AI unavailable",
        message_ar: "الذكاء الاصطناعي غير متاح",
      } satisfies S["AiStreamError"],
    ],
  ]);
}
