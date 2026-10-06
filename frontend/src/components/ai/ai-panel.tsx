"use client";
import { Dialog as D } from "radix-ui";
import { Bot, FileText, Loader2, Plus, Send, Sparkles, Square, X } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { ChartRenderer } from "@/components/charts/chart-renderer";
import { Link } from "@/i18n/navigation";
import { askAi, useAiStatus, type AiStreamEvent } from "@/lib/api/ai";
import { ApiError, type Schemas } from "@/lib/api/client";
import { useArabicDigits, useDisplay } from "@/lib/digits";
import { useErrorMessage } from "@/lib/i18n-helpers";
import { toQueryString } from "@/lib/url-state";

interface Turn {
  id: number;
  question: string;
  stage: Schemas["AiStreamStatus"] | null;
  text: string;
  citations: Schemas["AiCitation"][];
  chart: Schemas["ChartSpec"] | null;
  recommendations: Schemas["AiRecommendation"][];
  answer: Schemas["AiAnswer"] | null;
  meta: Schemas["AiStreamMeta"] | null;
  error: { code: string; message: string } | null;
  streaming: boolean;
}

const CONTROL_ORDER: Schemas["ControlLevel"][] = ["elimination", "substitution", "engineering", "administrative", "ppe"];

/**
 * "Ask about your HSE data" (§8.1 item 7). Hidden when the assistant is disabled for the project
 * (AC73) or the user lacks capability 40; shows "AI unavailable" when no provider is reachable (AC75).
 */
export function AiAssistant({ projectId, filters }: { projectId: string; filters: Schemas["DashboardFilters"] }) {
  const t = useTranslations("ai");
  const status = useAiStatus(projectId);
  const [open, setOpen] = useState(false);
  const s = status.data;
  if (!s || !s.enabled || !s.can_ask) return null;
  return (
    <>
      <Button type="button" onClick={() => setOpen(true)} data-testid="ai-open">
        <Sparkles aria-hidden />
        {t("open")}
      </Button>
      {s.can_generate_report && s.available ? (
        <Button asChild variant="outline">
          <Link href={`/reports?generate=1&project=${projectId}`} data-testid="ai-draft-report">
            <FileText aria-hidden />
            {t("draftReport")}
          </Link>
        </Button>
      ) : null}
      <D.Root open={open} onOpenChange={setOpen}>
        <D.Portal>
          <D.Overlay className="fixed inset-0 z-50 bg-overlay sm:bg-transparent" />
          <D.Content
            className="fixed inset-y-0 end-0 z-50 flex w-full flex-col border-s bg-surface shadow-xl outline-none sm:max-w-lg"
            data-testid="ai-panel"
            aria-describedby={undefined}
          >
            <AiConversation status={s} projectId={projectId} filters={filters} onClose={() => setOpen(false)} />
          </D.Content>
        </D.Portal>
      </D.Root>
    </>
  );
}

function AiConversation({
  status,
  projectId,
  filters,
  onClose,
}: {
  status: Schemas["AiStatusRead"];
  projectId: string;
  filters: Schemas["DashboardFilters"];
  onClose: () => void;
}) {
  const t = useTranslations("ai");
  const tc = useTranslations("common");
  const locale = useLocale();
  const ar = locale === "ar";
  const show = useDisplay(projectId);
  const msg = useErrorMessage();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [q, setQ] = useState("");
  const [deep, setDeep] = useState(false);
  const [used, setUsed] = useState(status.questions_used_today);
  const conversation = useRef<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const busy = turns.some((x) => x.streaming);
  const remaining = Math.max(0, status.questions_limit_per_day - used);
  const suggestions = ar ? status.suggested_questions_ar : status.suggested_questions_en;

  function patch(id: number, f: (x: Turn) => Turn) {
    setTurns((all) => all.map((x) => (x.id === id ? f(x) : x)));
  }

  async function ask(question: string) {
    const text = question.trim();
    if (!text || busy) return;
    const id = Date.now();
    setTurns((all) => [
      ...all,
      {
        id,
        question: text,
        stage: null,
        text: "",
        citations: [],
        chart: null,
        recommendations: [],
        answer: null,
        meta: null,
        error: null,
        streaming: true,
      },
    ]);
    setQ("");
    const ctrl = new AbortController();
    abort.current = ctrl;
    const onEvent = (e: AiStreamEvent) => {
      switch (e.event) {
        case "meta":
          conversation.current = e.data.conversation_id;
          patch(id, (x) => ({ ...x, meta: e.data }));
          break;
        case "status":
          patch(id, (x) => ({ ...x, stage: e.data }));
          break;
        case "delta":
          patch(id, (x) => ({ ...x, text: x.text + e.data.text }));
          break;
        case "citations":
          patch(id, (x) => ({ ...x, citations: e.data }));
          break;
        case "chart":
          patch(id, (x) => ({ ...x, chart: e.data }));
          break;
        case "recommendations":
          patch(id, (x) => ({ ...x, recommendations: e.data }));
          break;
        case "done":
          conversation.current = e.data.conversation_id;
          patch(id, (x) => ({
            ...x,
            answer: e.data,
            text: e.data.text,
            citations: e.data.citations,
            chart: e.data.chart,
            recommendations: e.data.recommendations,
            stage: null,
            streaming: false,
          }));
          break;
        case "error":
          patch(id, (x) => ({
            ...x,
            error: {
              code: e.data.code,
              message: (ar ? e.data.message_ar : null) ?? e.data.message,
            },
            stage: null,
            streaming: false,
          }));
          break;
      }
    };
    try {
      await askAi(
        {
          project_id: projectId,
          question: text,
          language: ar ? "ar" : "en",
          conversation_id: conversation.current,
          filters,
          deep_analysis: deep,
        },
        onEvent,
        ctrl.signal,
      );
      setUsed((u) => u + 1);
      patch(id, (x) => (x.streaming ? { ...x, streaming: false, stage: null } : x));
    } catch (err) {
      if (ctrl.signal.aborted) {
        patch(id, (x) => ({
          ...x,
          streaming: false,
          stage: null,
          error: { code: "ABORTED", message: t("stopped") },
        }));
        return;
      }
      const code = err instanceof ApiError ? err.code : "UNKNOWN";
      patch(id, (x) => ({
        ...x,
        streaming: false,
        stage: null,
        error: { code, message: msg(err) },
      }));
    }
  }

  return (
    <>
      <header className="flex items-center justify-between gap-2 border-b p-3">
        <D.Title className="flex items-center gap-2 text-base font-semibold">
          <Bot aria-hidden className="size-5" />
          {t("title")}
        </D.Title>
        <div className="flex items-center gap-1">
          {turns.length > 0 ? (
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() => {
                setTurns([]);
                conversation.current = null;
              }}
              data-testid="ai-new"
            >
              <Plus aria-hidden />
              {t("newConversation")}
            </Button>
          ) : null}
          <Button size="icon" variant="ghost" onClick={onClose} aria-label={tc("close")}>
            <X aria-hidden />
          </Button>
        </div>
      </header>
      <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-3" data-testid="ai-turns">
        {!status.available ? (
          <Alert tone="warning" data-testid="ai-unavailable">
            {t("unavailable")}
          </Alert>
        ) : null}
        <p className="text-xs text-muted-foreground">{t("scopeNote")}</p>
        {turns.length === 0 && status.available ? (
          <div className="flex flex-col gap-2">
            <p className="text-sm font-medium">{t("suggested")}</p>
            <ul className="flex flex-col gap-2">
              {suggestions.map((s) => (
                <li key={s}>
                  <button
                    type="button"
                    className="min-h-11 w-full rounded-md border px-3 py-2 text-start text-sm hover:bg-accent"
                    onClick={() => void ask(s)}
                    data-testid="ai-suggestion"
                  >
                    {s}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {turns.map((turn) => (
          <TurnView key={turn.id} turn={turn} projectId={projectId} show={show} />
        ))}
      </div>
      <form
        className="flex flex-col gap-2 border-t p-3"
        onSubmit={(e) => {
          e.preventDefault();
          void ask(q);
        }}
      >
        <label htmlFor="ai-q" className="sr-only">
          {t("placeholder")}
        </label>
        <Textarea
          id="ai-q"
          value={q}
          rows={2}
          maxLength={2000}
          placeholder={t("placeholder")}
          disabled={!status.available || remaining === 0}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void ask(q);
            }
          }}
          data-testid="ai-question"
        />
        <div className="flex flex-wrap items-center justify-between gap-2">
          <label className="flex min-h-11 items-center gap-2 text-xs">
            <Checkbox checked={deep} onChange={(e) => setDeep(e.target.checked)} disabled={!status.available} />
            {t("deep")}
          </label>
          <span className="text-xs text-muted-foreground" data-testid="ai-quota">
            {t("quota", {
              used: show(used),
              limit: show(status.questions_limit_per_day),
            })}
          </span>
          {busy ? (
            <Button type="button" variant="outline" onClick={() => abort.current?.abort()} data-testid="ai-stop">
              <Square aria-hidden />
              {t("stop")}
            </Button>
          ) : (
            <Button type="submit" disabled={!q.trim() || !status.available || remaining === 0} data-testid="ai-send">
              <Send aria-hidden className="rtl:-scale-x-100" />
              {t("send")}
            </Button>
          )}
        </div>
      </form>
    </>
  );
}

function TurnView({ turn, projectId, show }: { turn: Turn; projectId: string; show: (v: string) => string }) {
  const t = useTranslations("ai");
  const te = useTranslations("enums");
  const ar = useLocale() === "ar";
  const digits = useArabicDigits(projectId);
  const a = turn.answer;
  const warnings = a?.prompt_warnings ?? turn.meta?.prompt_warnings ?? [];
  const recs = [...turn.recommendations].sort((x, y) => CONTROL_ORDER.indexOf(x.control_level) - CONTROL_ORDER.indexOf(y.control_level));
  const answerId = a?.id ?? turn.meta?.answer_id ?? null;
  const insufficient = Boolean(a && a.citations.length === 0 && !a.chart && !a.fallback_table && a.grounding === "not_applicable");

  return (
    <article className="flex flex-col gap-2" data-testid="ai-turn">
      <p className="self-end rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground" data-testid="ai-turn-question">
        {turn.question}
      </p>
      {warnings.length > 0 ? (
        <Alert tone="warning" data-testid="ai-prompt-warning">
          {warnings.map((w) => te(`promptWarning.${w}`)).join(" ")}
        </Alert>
      ) : null}
      {turn.stage ? (
        <p className="flex items-center gap-2 text-xs text-muted-foreground" role="status" aria-live="polite" data-testid="ai-stage" data-stage={turn.stage.stage}>
          <Loader2 aria-hidden className="size-3.5 animate-spin" />
          {ar ? turn.stage.message_ar : turn.stage.message_en}
        </p>
      ) : turn.streaming && !turn.text ? (
        <p className="flex items-center gap-2 text-xs text-muted-foreground" role="status">
          <Loader2 aria-hidden className="size-3.5 animate-spin" />
          {t("thinking")}
        </p>
      ) : null}
      {a ? (
        <p className="inline-flex items-center gap-1.5 self-start rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground" data-testid="ai-label" data-grounding={a.grounding}>
          <Sparkles aria-hidden className="size-3" />
          {ar ? a.ai_label_ar : a.ai_label_en} · <span className="ltr">{a.model}</span>
        </p>
      ) : null}
      {turn.text ? (
        <div
          className="prose-sm max-w-none rounded-lg border bg-background p-3 text-sm [&_li]:ms-4 [&_ol]:list-decimal [&_p]:mb-2 [&_table]:w-full [&_td]:border [&_td]:px-1 [&_th]:border [&_th]:px-1 [&_ul]:list-disc"
          data-testid="ai-answer"
          aria-busy={turn.streaming}
        >
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{digits ? show(turn.text) : turn.text}</ReactMarkdown>
        </div>
      ) : null}
      {insufficient ? (
        <Alert tone="info" data-testid="ai-insufficient">
          {t("insufficient")}
        </Alert>
      ) : null}
      {a?.fallback_table ? (
        <div className="overflow-x-auto rounded-md border" data-testid="ai-fallback-table">
          <table className="w-full text-xs">
            <thead>
              <tr>
                {a.fallback_table.columns.map((c) => (
                  <th key={c.key} className="border-b p-1.5 text-start">
                    {ar ? c.label_ar : c.label_en}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {a.fallback_table.rows.map((r, i) => (
                <tr key={i}>
                  {a.fallback_table?.columns.map((c) => (
                    <td key={c.key} className="border-b p-1.5">
                      {show(String((r as Record<string, unknown>)[c.key] ?? ""))}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {turn.chart ? (
        <div className="rounded-lg border p-2" data-testid="ai-chart">
          <ChartRenderer spec={turn.chart} height={200} arabicDigits={digits} />
        </div>
      ) : null}
      {turn.citations.length > 0 ? (
        <div data-testid="ai-citations">
          <p className="text-xs font-semibold">{t("sources")}</p>
          <ol className="list-decimal ps-5 text-xs text-muted-foreground">
            {turn.citations.map((c) => (
              <li key={c.id} data-testid="ai-citation">
                {show(ar ? c.text_ar : c.text_en)}
              </li>
            ))}
          </ol>
        </div>
      ) : null}
      {recs.length > 0 ? (
        <div className="flex flex-col gap-2" data-testid="ai-recommendations">
          <p className="text-xs font-semibold">{t("recommendations")}</p>
          {recs.map((r) => (
            <div key={r.id} className="rounded-md border p-2" data-testid="ai-recommendation" data-control={r.control_level}>
              <p className="text-sm font-medium">
                <span className="me-2 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">{te(`controlLevel.${r.control_level}`)}</span>
                {r.title}
              </p>
              <p className="mt-1 text-xs whitespace-pre-wrap">{show(r.text)}</p>
              {answerId ? (
                <Button asChild size="sm" variant="outline" className="mt-2">
                  <Link
                    href={`/actions/new${toQueryString({
                      project: projectId,
                      source_type: "ai_recommendation",
                      source_id: answerId,
                      ai_recommendation_id: r.id,
                      title: r.title.slice(0, 200),
                      description: r.text,
                      control_level: r.control_level,
                    })}`}
                    data-testid="ai-create-ca"
                  >
                    <Plus aria-hidden />
                    {t("createCa")}
                  </Link>
                </Button>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
      {turn.error ? (
        <Alert tone={turn.error.code === "AI_RATE_LIMITED" || turn.error.code === "ABORTED" ? "warning" : "danger"} data-testid="ai-error" data-code={turn.error.code}>
          {turn.error.message}
        </Alert>
      ) : null}
    </article>
  );
}
