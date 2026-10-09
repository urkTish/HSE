"use client";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FilePlus2, Loader2, Pencil, Printer, ShieldCheck, TriangleAlert } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ChartRenderer } from "@/components/charts/chart-renderer";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { aiKeys, useAiStatus } from "@/lib/api/ai";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useCurrentProject } from "@/lib/current-project";
import { useArabicDigits, useDisplay } from "@/lib/digits";
import { can, canWrite } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";
import { cn } from "@/lib/utils";
import { useSearchState } from "@/lib/url-state";

type Report = Schemas["MonthlyReportRead"];
const PAGE_SIZE = 25;

function monthLabel(locale: string, iso: string): string {
  const [y, m] = iso.split("-").map(Number);
  return new Intl.DateTimeFormat(locale === "ar" ? "ar-SA-u-ca-gregory-nu-latn" : "en-GB", { month: "long", year: "numeric", timeZone: "UTC" }).format(
    new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, 1)),
  );
}

/** First day of the last complete month (reports cover complete months only). */
function lastCompleteMonth(): string {
  const d = new Date();
  const prev = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() - 1, 1));
  return prev.toISOString().slice(0, 7);
}

export function ReportList({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("reports");
  const te = useTranslations("enums");
  const locale = useLocale();
  const me = useMeData();
  const { date } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const ai = useAiStatus(project.id, can(me, "monthly_report.generate", project.id));
  const query = useQuery({
    queryKey: aiKeys.reports(project.id, page),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/projects/{project_id}/monthly-reports", {
          params: {
            path: { project_id: project.id },
            query: { page, page_size: PAGE_SIZE },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  });
  const canGenerate = canWrite(me, "monthly_report.generate", project.id);
  const aiReady = Boolean(ai.data?.enabled && ai.data.available);
  const generateOpen = s.get("generate") === "1";
  const items = query.data?.items ?? [];

  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          canGenerate ? (
            <Button onClick={() => s.set({ generate: "1" })} disabled={!aiReady} data-testid="generate-report">
              <FilePlus2 aria-hidden />
              {t("generate")}
            </Button>
          ) : null
        }
      />
      {canGenerate && ai.data && !aiReady ? (
        <Alert tone="info" className="mb-4" data-testid="report-ai-off">
          {ai.data.enabled ? t("aiUnavailable") : t("aiDisabled")}
        </Alert>
      ) : null}
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState message={t("empty")} />
      ) : (
        <>
          <Table data-testid="reports-table">
            <THead>
              <TR>
                <TH>{t("month")}</TH>
                <TH>{t("status")}</TH>
                <TH>{t("createdBy")}</TH>
                <TH>{t("publishedAt")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((r) => (
                <TR key={r.id} data-testid="report-row">
                  <TD label={t("month")}>
                    <Link href={`/reports/${r.id}`} className="font-medium text-primary hover:underline">
                      {monthLabel(locale, r.month)}
                    </Link>
                    {r.revised_since_publication ? <span className="inline-flex items-center gap-1 ms-2 text-xs text-warning font-medium"><TriangleAlert aria-hidden className="size-3.5 shrink-0" />{t("revised")}</span> : null}
                  </TD>
                  <TD label={t("status")}>
                    <StatusBadge status={r.status} label={te(`reportStatus.${r.status}`)} />
                  </TD>
                  <TD label={t("createdBy")}>{locale === "ar" ? r.created_by.full_name_ar || r.created_by.full_name_en : r.created_by.full_name_en}</TD>
                  <TD label={t("publishedAt")}>{date(r.published_at)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={query.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      )}
      {generateOpen && canGenerate && aiReady ? <GenerateDialog projectId={project.id} onClose={() => s.set({ generate: null })} quota={ai.data} /> : null}
    </div>
  );
}

function GenerateDialog({ projectId, onClose, quota }: { projectId: string; onClose: () => void; quota?: Schemas["AiStatusRead"] }) {
  const t = useTranslations("reports");
  const tc = useTranslations("common");
  const show = useDisplay(projectId);
  const router = useRouter();
  const qc = useQueryClient();
  const [month, setMonth] = useState(lastCompleteMonth());
  const m = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/ai/monthly-report", {
          body: { project_id: projectId, month: `${month}-01` },
        }),
      ),
    onSuccess: (r) => {
      void qc.invalidateQueries({ queryKey: ["monthly-reports", projectId] });
      void qc.invalidateQueries({ queryKey: aiKeys.status(projectId) });
      router.push(`/reports/${r.id}`);
    },
  });
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent closeLabel={tc("close")} data-testid="generate-dialog">
        <DialogHeader>
          <DialogTitle>{t("generate")}</DialogTitle>
          <DialogDescription>{t("generateHint")}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="rep-month">{t("month")}</Label>
          <Input id="rep-month" type="month" value={month} max={lastCompleteMonth()} onChange={(e) => setMonth(e.target.value)} data-testid="report-month" />
        </div>
        {quota ? (
          <p className="text-xs text-muted-foreground">
            {t("quota", {
              used: show(quota.reports_used_this_month),
              limit: show(quota.reports_limit_per_month),
            })}
          </p>
        ) : null}
        <MutationError error={m.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button onClick={() => m.mutate()} disabled={!month || m.isPending} data-testid="generate-confirm">
            {m.isPending ? <Loader2 aria-hidden className="animate-spin" /> : <FilePlus2 aria-hidden />}
            {t("generate")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function ReportDetail({ id }: { id: string }) {
  const t = useTranslations("reports");
  const te = useTranslations("enums");
  const tn = useTranslations("nav");
  const tc = useTranslations("common");
  const locale = useLocale();
  const me = useMeData();
  const terr = useTranslations("errors");
  const errText = (code: string) => {
    const key = `code.${code}` as Parameters<typeof terr>[0];
    return terr.has(key) ? terr(key) : code;
  };
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: aiKeys.report(id),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/monthly-reports/{report_id}", {
          params: { path: { report_id: id } },
        }),
      ),
    refetchInterval: (query) => (query.state.data?.status === "generating" ? 3000 : false),
  });
  const r = q.data;
  const [lang, setLang] = useState<"en" | "ar">(locale === "ar" ? "ar" : "en");
  const [editing, setEditing] = useState(false);
  const [transition, setTransition] = useState<Schemas["MonthlyReportStatus"] | null>(null);
  const { dateTime } = useFormatters(r?.project_id);

  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!r) return <LoadingState />;

  const pid = r.project_id;
  const editable = (r.status === "draft" || r.status === "reviewed") && (canWrite(me, "monthly_report.generate", pid) || canWrite(me, "monthly_report.review", pid));
  const actions: {
    to: Schemas["MonthlyReportStatus"];
    label: string;
    variant?: "outline";
  }[] = [];
  if (r.status === "draft" && canWrite(me, "monthly_report.review", pid)) actions.push({ to: "reviewed", label: t("markReviewed") });
  if (r.status === "reviewed" && canWrite(me, "monthly_report.publish", pid)) actions.push({ to: "published", label: t("publish") });
  if (r.status === "reviewed" && (canWrite(me, "monthly_report.review", pid) || canWrite(me, "monthly_report.publish", pid)))
    actions.push({
      to: "draft",
      label: t("returnToDraft"),
      variant: "outline",
    });
  const sections = [...r.sections].sort((a, b) => a.order - b.order);

  return (
    <div data-testid="report-detail" data-status={r.status}>
      <div className="print:hidden">
        <Breadcrumbs items={[{ label: tn("reports"), href: "/reports" }, { label: monthLabel(locale, r.month) }]} />
      </div>
      <PrintHeader report={r} />
      <div className="print:hidden">
      <PageHeader
        title={t("reportTitle", {
          project: r.project_code,
          month: monthLabel(lang, r.month),
        })}
        badge={<StatusBadge status={r.status} label={locale === "ar" ? r.status_label_ar : r.status_label_en} />}
        description={
          <span className="flex flex-wrap gap-x-3">
            {r.generated_at ? <span>{t("generatedAt", { time: dateTime(r.generated_at) })}</span> : null}
            {r.published_at ? <span>{t("publishedOn", { time: dateTime(r.published_at) })}</span> : null}
            <span>{locale === "ar" ? r.ai_label_ar : r.ai_label_en}</span>
          </span>
        }
        actions={
          <div className="flex flex-wrap gap-2 print:hidden">
            <div className="flex rounded-md border" role="group" aria-label={t("language")}>
              {(["en", "ar"] as const).map((l) => (
                <Button key={l} size="sm" variant={lang === l ? "default" : "ghost"} aria-pressed={lang === l} onClick={() => setLang(l)} data-testid={`report-lang-${l}`}>
                  {l === "en" ? "English" : "العربية"}
                </Button>
              ))}
            </div>
            {editable && !editing && r.status !== "generating" ? (
              <Button variant="outline" onClick={() => setEditing(true)} data-testid="edit-report">
                <Pencil aria-hidden />
                {tc("edit")}
              </Button>
            ) : null}
            {actions.map((a) => (
              <Button key={a.to} variant={a.variant} onClick={() => setTransition(a.to)} data-testid={`report-transition-${a.to}`}>
                {a.label}
              </Button>
            ))}
            {r.status !== "generating" && r.status !== "failed" ? (
              <Button variant="outline" onClick={() => window.print()} data-testid="print-report">
                <Printer aria-hidden />
                {t("print")}
              </Button>
            ) : null}
          </div>
        }
      />
      </div>
      {r.status === "generating" ? (
        <Alert tone="info" data-testid="report-generating">
          <span className="flex items-center gap-2">
            <Loader2 aria-hidden className="size-4 animate-spin" />
            {t("generating")}
          </span>
        </Alert>
      ) : null}
      {r.status === "failed" ? (
        <Alert tone="danger" data-testid="report-failed">
          {t("failed")} {r.error_code ? errText(r.error_code) : null}
        </Alert>
      ) : null}
      {r.revised_since_publication ? (
        <Alert tone="warning" className="mb-4" data-testid="report-revised">
          {t("revisedBanner")}
        </Alert>
      ) : null}
      {editing ? (
        <NarrativeEditor report={r} onDone={() => setEditing(false)} />
      ) : (
        <div className="flex flex-col gap-4 print:gap-3" lang={lang} dir={lang === "ar" ? "rtl" : "ltr"} data-testid="report-sections">
          {sections.map((s) => (
            <ReportSection key={s.section} s={s} lang={lang} projectId={pid} />
          ))}
        </div>
      )}
      <PrintFooter report={r} />
      {transition ? (
        <TransitionDialog
          report={r}
          to={transition}
          onClose={() => setTransition(null)}
          onDone={(next) => {
            qc.setQueryData(aiKeys.report(id), next);
            void qc.invalidateQueries({ queryKey: ["monthly-reports", pid] });
            toast.success(te(`reportStatus.${next.status}`));
            setTransition(null);
          }}
        />
      ) : null}
    </div>
  );
}

function ReportSection({ s, lang, projectId }: { s: Schemas["ReportSectionRead"]; lang: "en" | "ar"; projectId: string }) {
  const show = useDisplay(projectId);
  const digits = useArabicDigits(projectId);
  const t = useTranslations("reports");
  const narrative = lang === "ar" ? s.narrative_ar : s.narrative_en;
  return (
    <Card className="report-section print:rounded-none print:border-0 print:bg-transparent print:shadow-none" data-testid="report-section" data-section={s.section}>
      <CardHeader className="pb-2 print:border-b print:px-0 print:pt-0">
        <CardTitle className="text-base break-after-avoid print:text-[12pt]">
          {s.order}. {lang === "ar" ? s.title_ar : s.title_en}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 print:px-0 print:pt-2">
        {narrative ? (
          <div className="text-sm leading-relaxed [&_li]:ms-4 [&_ol]:list-decimal [&_p]:mb-2 [&_ul]:list-disc" data-testid="report-narrative">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{digits ? show(narrative) : narrative}</ReactMarkdown>
          </div>
        ) : null}
        {s.tables.map((tb, i) => (
          <div key={i} className="overflow-x-auto" data-testid="report-table">
            <table className="w-full border-collapse text-xs">
              <thead>
                <tr>
                  {tb.columns.map((c) => (
                    <th key={c.key} className={cn("border-b border-input bg-muted p-1.5 font-semibold", c.numeric ? "text-end" : "text-start")}>
                      {lang === "ar" ? c.label_ar : c.label_en}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tb.rows.map((row, j) => (
                  <tr key={j} className="border-b">
                    {tb.columns.map((c) => (
                      <td key={c.key} className={cn("p-1.5 tabular-nums", c.numeric ? "text-end" : "text-start")}>
                        {show(String((row as Record<string, unknown>)[c.key] ?? ""))}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
        {s.charts.map((c) => (
          <ChartRenderer key={c.chart_id} spec={c} height={220} arabicDigits={digits} />
        ))}
        {s.citations.length > 0 ? (
          <div className="text-[11px] text-muted-foreground">
            <span className="font-semibold">{t("sources")}: </span>
            {s.citations.map((c) => show(lang === "ar" ? c.text_ar : c.text_en)).join(" · ")}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function NarrativeEditor({ report, onDone }: { report: Report; onDone: () => void }) {
  const t = useTranslations("reports");
  const tc = useTranslations("common");
  const locale = useLocale();
  const qc = useQueryClient();
  const narrativeSections = report.sections.filter((s) => s.narrative_en !== null || s.narrative_ar !== null).sort((a, b) => a.order - b.order);
  const [v, setV] = useState<Record<string, { en: string; ar: string }>>(() =>
    Object.fromEntries(narrativeSections.map((s) => [s.section, { en: s.narrative_en ?? "", ar: s.narrative_ar ?? "" }])),
  );
  const m = useMutation({
    mutationFn: () =>
      unwrap(
        api.PATCH("/api/v1/monthly-reports/{report_id}", {
          params: { path: { report_id: report.id } },
          body: {
            sections: narrativeSections
              .filter((s) => v[s.section]?.en !== (s.narrative_en ?? "") || v[s.section]?.ar !== (s.narrative_ar ?? ""))
              .map((s) => ({
                section: s.section,
                narrative_en: v[s.section]?.en ?? null,
                narrative_ar: v[s.section]?.ar ?? null,
              })),
          },
        }),
      ),
    onSuccess: (next) => {
      qc.setQueryData(aiKeys.report(report.id), next);
      toast.success(tc("saved"));
      onDone();
    },
  });
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        m.mutate();
      }}
      data-testid="report-editor"
    >
      <Alert tone="info">{t("editHint")}</Alert>
      {narrativeSections.map((s) => (
        <Card key={s.section}>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">
              {s.order}. {locale === "ar" ? s.title_ar : s.title_en}
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor={`n-${s.section}-en`}>English</Label>
              <Textarea
                id={`n-${s.section}-en`}
                dir="ltr"
                rows={6}
                value={v[s.section]?.en ?? ""}
                onChange={(e) =>
                  setV((x) => ({
                    ...x,
                    [s.section]: {
                      en: e.target.value,
                      ar: x[s.section]?.ar ?? "",
                    },
                  }))
                }
                data-testid={`narrative-${s.section}-en`}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor={`n-${s.section}-ar`}>العربية</Label>
              <Textarea
                id={`n-${s.section}-ar`}
                dir="rtl"
                lang="ar"
                rows={6}
                value={v[s.section]?.ar ?? ""}
                onChange={(e) =>
                  setV((x) => ({
                    ...x,
                    [s.section]: {
                      en: x[s.section]?.en ?? "",
                      ar: e.target.value,
                    },
                  }))
                }
                data-testid={`narrative-${s.section}-ar`}
              />
            </div>
          </CardContent>
        </Card>
      ))}
      <MutationError error={m.error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={m.isPending} data-testid="save-report">
          {m.isPending ? tc("saving") : tc("save")}
        </Button>
        <Button type="button" variant="outline" onClick={onDone}>
          {tc("cancel")}
        </Button>
      </div>
    </form>
  );
}

function TransitionDialog({ report, to, onClose, onDone }: { report: Report; to: Schemas["MonthlyReportStatus"]; onClose: () => void; onDone: (r: Report) => void }) {
  const t = useTranslations("reports");
  const tc = useTranslations("common");
  const [comment, setComment] = useState("");
  const needsComment = to === "draft";
  const m = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/monthly-reports/{report_id}/transitions", {
          params: { path: { report_id: report.id } },
          body: { to_status: to, comment: comment.trim() || null },
        }),
      ),
    onSuccess: onDone,
  });
  const title = to === "reviewed" ? t("markReviewed") : to === "published" ? t("publish") : t("returnToDraft");
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent closeLabel={tc("close")}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{to === "published" ? t("publishHint") : to === "draft" ? t("returnHint") : t("reviewHint")}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="rep-comment">{needsComment ? t("comment") : t("commentOptional")}</Label>
          <Textarea id="rep-comment" rows={3} value={comment} onChange={(e) => setComment(e.target.value)} data-testid="report-comment" />
        </div>
        <MutationError error={m.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button onClick={() => m.mutate()} disabled={m.isPending || (needsComment && comment.trim().length === 0)} data-testid="report-transition-confirm">
            {title}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** "EN|AR" message → both halves (the print view shows both languages side by side). */
function useBilingual() {
  const t = useTranslations("reports.printDoc");
  return (key: Parameters<typeof t>[0]) => {
    const [en = "", ar = ""] = t(key).split("|");
    return { en, ar };
  };
}

/** Print-only cover block: bilingual (EN | AR) whatever the on-screen language, for client and authority submission. */
function PrintHeader({ report: r }: { report: Report }) {
  const bi = useBilingual();
  const { projects } = useCurrentProject();
  const p = projects.find((x) => x.id === r.project_id);
  const { dateTime } = useFormatters(r.project_id);
  const title = bi("title");
  const rows: { k: ReturnType<typeof bi>; en: string; ar: string; ltr?: boolean }[] = [
    { k: bi("project"), en: p ? `${r.project_code} — ${p.name_en}` : r.project_code, ar: p ? `${r.project_code} — ${p.name_ar || p.name_en}` : r.project_code },
    { k: bi("month"), en: monthLabel("en", r.month), ar: monthLabel("ar", r.month) },
    { k: bi("status"), en: r.status_label_en, ar: r.status_label_ar },
  ];
  // One date cell spanning both language columns (formatted in the UI language and project date settings).
  if (r.published_at) rows.push({ k: bi("published"), en: dateTime(r.published_at), ar: "", ltr: true });
  else if (r.generated_at) rows.push({ k: bi("generated"), en: dateTime(r.generated_at), ar: "", ltr: true });
  return (
    <header dir="ltr" className="mb-4 hidden border-b-2 border-foreground pb-3 print:block" data-testid="report-print-header">
      <div className="flex items-center justify-between gap-4">
        <div dir="ltr" lang="en" className="flex items-center gap-2">
          <span aria-hidden className="flex size-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <ShieldCheck className="size-5" />
          </span>
          <div>
            <p className="text-[9pt] tracking-wide text-muted-foreground uppercase">{r.project_code}</p>
            <p className="text-[15pt] leading-tight font-semibold">{title.en}</p>
          </div>
        </div>
        <p dir="rtl" lang="ar" className="text-[15pt] leading-tight font-semibold">
          {title.ar}
        </p>
      </div>
      <table dir="ltr" className="mt-3 w-full text-[9.5pt]">
        <tbody>
          {rows.map((row) => (
            <tr key={row.k.en} className="border-t">
              <th scope="row" className="w-[17%] py-1 pe-2 text-start font-medium text-muted-foreground">
                {row.k.en}
              </th>
              {row.ltr ? (
                <td colSpan={2} className="py-1 text-center">
                  <bdi>{row.en}</bdi>
                </td>
              ) : (
                <>
                  <td className="w-[33%] py-1 pe-3">{row.en}</td>
                  <td dir="rtl" lang="ar" className="w-[33%] py-1 ps-3 text-start">
                    {row.ar}
                  </td>
                </>
              )}
              <th scope="row" dir="rtl" lang="ar" className="w-[17%] py-1 ps-2 text-start font-medium text-muted-foreground">
                {row.k.ar}
              </th>
            </tr>
          ))}
        </tbody>
      </table>
    </header>
  );
}

/**
 * Footer on every printed page: confidentiality line (EN | AR) and the frozen figures hash. Chrome has no
 * running elements, so the text is handed to the `@page` margin boxes through custom properties on <html>
 * (see globals.css); nothing renders on screen.
 */
function PrintFooter({ report: r }: { report: Report }) {
  const bi = useBilingual();
  const conf = bi("confidential");
  const hash = bi("hash");
  const start = r.data_hash ? `${conf.en} · ${hash.en} ${r.data_hash.slice(0, 12)}` : conf.en;
  const end = conf.ar;
  useEffect(() => {
    const root = document.documentElement.style;
    root.setProperty("--print-footer-start", JSON.stringify(start));
    root.setProperty("--print-footer-end", JSON.stringify(end));
    return () => {
      root.removeProperty("--print-footer-start");
      root.removeProperty("--print-footer-end");
    };
  }, [start, end]);
  return null;
}
