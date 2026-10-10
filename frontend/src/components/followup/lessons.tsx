"use client";
import { BookOpen, CheckCircle2, Link2, Plus, Search, Trash2, TriangleAlert, Users } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Code, StepDialog } from "@/components/access/common";
import { ApiWarnings, PossibleIdHint } from "@/components/common/api-warnings";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { UserSelect } from "@/components/common/pickers";
import { ProjectGate } from "@/components/common/project-gate";
import { RecordActions } from "@/components/common/record-actions";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { StackedDate } from "@/components/medical/common";
import { StatusBadge } from "@/components/common/status-badge";
import { useCurrentProject } from "@/lib/current-project";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useEffectivenessChecks, useFuRefresh, useLesson, useLessonDistribution, useLessons, useProjectDistribution } from "@/lib/api/followup";
import { useProjects } from "@/lib/api/queries";
import { useDisplay } from "@/lib/digits";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { useRefLists } from "@/lib/reference";
import { useDebounced } from "@/lib/use-debounced";
import { useSearchState } from "@/lib/url-state";
import { Choices, DayDue, DeadlineRule, FuBadge, LessonSubNav, ResultBadge, dayPassed, useBi, useFuCaps } from "./common";
import { RegistryExport } from "@/components/scorecard/exports";

type S = Schemas;
type Lesson = S["FuLessonRead"];

const STATUSES: S["FuLessonStatus"][] = ["published", "archived", "in_review", "draft"];

/* ═════════════ library (LL-5): search with Arabic normalisation on the server ═════════════ */

export function LessonLibraryPage() {
  const t = useTranslations("fu.lessons");
  const tc = useTranslations("common");
  const te = useTranslations("enums");
  const ref = useRefLists();
  const caps = useFuCaps(null);
  const s = useSearchState();
  const [text, setText] = useState(s.get("q") ?? "");
  const q = useDebounced(text.trim(), 350);
  const status = (s.get("status") as S["FuLessonStatus"] | null) ?? "";
  const activity = (s.get("activity") as S["Activity"] | null) ?? "";
  const mechanism = (s.get("mechanism") as S["Mechanism"] | null) ?? "";
  const year = s.get("year") ?? "";
  const list = useLessons(
    { q: q || null, status: status ? [status] : null, activity: activity || null, mechanism: mechanism || null, year: year ? Number(year) : null, page_size: 50 },
    { enabled: caps.library },
  );
  const [creating, setCreating] = useState(false);
  if (!caps.library) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = list.data?.items ?? [];
  const years = Array.from({ length: 4 }, (_, i) => String(new Date().getFullYear() - i));
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.draft ? (
            <Button onClick={() => setCreating(true)} className="min-h-12 sm:min-h-control" data-testid="lesson-new">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <LessonSubNav />
      <ListToolbar actions={<RegistryExport dataset="lessons" projectId={null} />}>
        <div className="flex flex-col gap-1.5 lg:w-72">
          <label htmlFor="ll-q" className="text-sm font-medium">
            {tc("search")}
          </label>
          <div className="relative">
            <Search aria-hidden className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="ll-q"
              type="search"
              value={text}
              placeholder={t("searchHint")}
              className="ps-9"
              onChange={(e) => {
                setText(e.target.value);
                s.set({ q: e.target.value || null });
              }}
              data-testid="ll-search"
            />
          </div>
        </div>
        <SelectFilter
          id="ll-status"
          label={t("status")}
          value={status}
          onChange={(v) => s.set({ status: v || null })}
          options={STATUSES.filter((x) => caps.draft || x === "published" || x === "archived").map((x) => ({ value: x, label: te(`fuLessonStatus.${x}`) }))}
          allLabel={t("libraryAll")}
        />
        <SelectFilter id="ll-activity" label={t("activity")} value={activity} onChange={(v) => s.set({ activity: v || null })} options={ref.options("activity").map((o) => ({ value: o.value as S["Activity"], label: o.label }))} />
        <SelectFilter id="ll-mechanism" label={t("mechanism")} value={mechanism} onChange={(v) => s.set({ mechanism: v || null })} options={ref.options("mechanism").map((o) => ({ value: o.value as S["Mechanism"], label: o.label }))} />
        <SelectFilter id="ll-year" label={t("year")} value={year} onChange={(v) => s.set({ year: v || null })} options={years.map((y) => ({ value: y, label: y }))} />
      </ListToolbar>
      {list.isLoading ? (
        <LoadingState />
      ) : list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : items.length ? (
        <ul className="grid gap-3 lg:grid-cols-2" data-testid="ll-results">
          {items.map((l) => (
            <LessonCard key={l.id} l={l} />
          ))}
        </ul>
      ) : (
        <EmptyState message={t("empty")} />
      )}
      {creating ? <NewLessonDialog onClose={() => setCreating(false)} /> : null}
    </div>
  );
}

function LessonCard({ l }: { l: S["FuLessonListItem"] }) {
  const t = useTranslations("fu.lessons");
  const bi = useBi();
  const ref = useRefLists();
  return (
    <li className="flex flex-col gap-2 rounded-md border p-4" data-testid="ll-card" data-no={l.lesson_no} data-status={l.status}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link href={`/lessons/${l.id}`} className="inline-flex min-h-touch items-center gap-2 font-medium text-primary hover:underline">
          <BookOpen aria-hidden className="size-4 shrink-0" />
          <Code>{l.lesson_no}</Code>
        </Link>
        <FuBadge group="fuLessonStatus" status={l.status} testId="ll-status" />
      </div>
      <p className="font-medium">{bi(l.title_en, l.title_ar) || "—"}</p>
      {l.key_lessons[0] ? <p className="text-sm text-muted-foreground">{bi(l.key_lessons[0].text_en, l.key_lessons[0].text_ar)}</p> : null}
      <p className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
        {l.source_project_code ? <Code>{l.source_project_code}</Code> : null}
        {l.month ? <Code>{l.month}</Code> : null}
        {(l.applicability.activities ?? []).map((a) => (
          <span key={a}>{ref.label("activity", a)}</span>
        ))}
        {l.root_cause_codes.length ? <Code>{l.root_cause_codes.join(", ")}</Code> : null}
        {l.archived ? <span className="font-medium">{t("archivedNote")}</span> : null}
      </p>
    </li>
  );
}

function NewLessonDialog({ onClose }: { onClose: () => void }) {
  const t = useTranslations("fu.lessons");
  const refresh = useFuRefresh();
  const router = useRouter();
  const [extRef, setExtRef] = useState("");
  const [en, setEn] = useState("");
  const [arText, setAr] = useState("");
  return (
    <StepDialog
      title={t("newTitle")}
      description={t("newBody")}
      confirmLabel={t("create")}
      testId="lesson-create"
      disabled={!extRef.trim()}
      onConfirm={async () => {
        const l = await unwrap(api.POST("/api/v1/lessons", { body: { source: "external", external_ref: extRef.trim(), title_en: en.trim() || null, title_ar: arText.trim() || null } }));
        await refresh();
        router.push(`/lessons/${l.id}`);
      }}
      onClose={onClose}
    >
      <FormField id="nl-ref" label={t("externalRef")} required hint={t("externalRefHint")}>
        <Input value={extRef} onChange={(e) => setExtRef(e.target.value)} maxLength={120} data-testid="nl-ref" />
      </FormField>
      <FormField id="nl-en" label={t("titleEn")}>
        <Input dir="ltr" value={en} onChange={(e) => setEn(e.target.value)} maxLength={150} />
      </FormField>
      <FormField id="nl-ar" label={t("titleAr")}>
        <Input dir="rtl" value={arText} onChange={(e) => setAr(e.target.value)} maxLength={150} />
      </FormField>
    </StepDialog>
  );
}

/* ═════════════ lesson page: draft → review → publish → distribution, links, effectiveness ═════════════ */

export function LessonPage({ id }: { id: string }) {
  const t = useTranslations("fu.lessons");
  const tn = useTranslations("fu.nav");
  const q = useLesson(id);
  const l = q.data;
  const { projectId } = useCurrentProject();
  const caps = useFuCaps(l?.source_project_id ?? projectId);
  const name = useLocalizedName();
  const bi = useBi();
  const [dialog, setDialog] = useState<"return" | "archive" | "delete" | "submit" | null>(null);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!l) return <LoadingState />;
  const mine = caps.me?.id === l.author?.id;
  const editable = caps.draft && l.status === "draft";
  return (
    <div className="flex flex-col gap-6">
      <Breadcrumbs items={[{ label: tn("library"), href: "/lessons" }, { label: l.lesson_no }]} />
      <div className="flex flex-col gap-2">
        <p className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <Code data-testid="lesson-no">{l.lesson_no}</Code>
          {l.incident_ref ? (
            <>
              ·
              {l.incident_id ? (
                <Link href={`/incidents/${l.incident_id}`} className="text-primary hover:underline">
                  <Code>{l.incident_ref}</Code>
                </Link>
              ) : (
                <Code>{l.incident_ref}</Code>
              )}
            </>
          ) : l.external_ref ? (
            <>· {l.external_ref}</>
          ) : null}
          {l.required ? <Badge tone="info">{t("required")}</Badge> : null}
        </p>
        <h1 className="flex flex-wrap items-center gap-2 text-xl font-semibold">
          <span data-testid="lesson-title">{bi(l.title_en, l.title_ar) || t("untitled")}</span>
          <FuBadge group="fuLessonStatus" status={l.status} testId="lesson-status" />
        </h1>
        <dl className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
          {l.publish_due_on && (l.status === "draft" || l.status === "in_review") ? (
            <div className="flex flex-col">
              <dt className="text-xs text-muted-foreground">{t("publishDue")}</dt>
              <dd>
                <DayDue date={l.publish_due_on} projectId={l.source_project_id} />
              </dd>
            </div>
          ) : null}
          <div className="flex flex-col">
            <dt className="text-xs text-muted-foreground">{t("author")}</dt>
            <dd>{l.author ? name(l.author.full_name_en, l.author.full_name_ar) : "—"}</dd>
          </div>
          {l.published_at ? (
            <div className="flex flex-col">
              <dt className="text-xs text-muted-foreground">{t("published")}</dt>
              <dd>
                <StackedDate v={l.published_at} projectId={l.source_project_id} />
              </dd>
            </div>
          ) : null}
          {l.approved_by ? (
            <div className="flex flex-col">
              <dt className="text-xs text-muted-foreground">{t("approvedBy")}</dt>
              <dd>{name(l.approved_by.full_name_en, l.approved_by.full_name_ar)}</dd>
            </div>
          ) : null}
        </dl>
      </div>
      {l.return_comment && l.status === "draft" ? (
        <Alert tone="warning" data-testid="lesson-returned">
          {t("returned")}: {l.return_comment}
        </Alert>
      ) : null}
      {l.status === "archived" ? (
        <Alert tone="info">
          {t("archivedNote")}
          {l.superseded_by_lesson_no ? ` · ${t("supersededBy")} ${l.superseded_by_lesson_no}` : ""}
          {l.status_reason ? ` · ${l.status_reason}` : ""}
        </Alert>
      ) : null}
      <ApiWarnings warnings={l.warnings} />

      {editable ? <LessonEditor key={l.id + l.status} l={l} /> : <LessonView l={l} />}

      <div className="flex flex-wrap gap-2">
        {editable && (mine || caps.publish) ? (
          <Button className="min-h-12 sm:min-h-control" onClick={() => setDialog("submit")} data-testid="lesson-submit">
            {t("submit")}
          </Button>
        ) : null}
        {caps.publish && l.status === "in_review" ? (
          <Button variant="outline" className="min-h-12 sm:min-h-control" onClick={() => setDialog("return")} data-testid="lesson-return">
            {t("return")}
          </Button>
        ) : null}
      </div>

      {l.status === "in_review" && caps.publish ? mine ? <Alert tone="info" data-testid="lesson-self">{t("selfApproval")}</Alert> : <PublishPanel l={l} /> : null}
      {l.status === "published" || l.status === "archived" ? <Distribution l={l} /> : null}
      {l.status !== "draft" || l.links.length ? <Links l={l} /> : null}
      {l.check ? <CheckCard check={l.check} /> : null}

      {(caps.publish && l.status === "published") || (l.status === "draft" && mine && !l.system_created) ? (
        <RecordActions testId="lesson-end">
          {caps.publish && l.status === "published" ? (
            <Button variant="destructive-outline" onClick={() => setDialog("archive")} data-testid="lesson-archive">
              {t("archive")}
            </Button>
          ) : null}
          {l.status === "draft" && mine && !l.system_created ? (
            <Button variant="destructive-outline" onClick={() => setDialog("delete")} data-testid="lesson-delete">
              <Trash2 aria-hidden />
              {t("delete")}
            </Button>
          ) : null}
        </RecordActions>
      ) : null}
      {dialog ? <LessonStepDialog l={l} kind={dialog} onClose={() => setDialog(null)} /> : null}
    </div>
  );
}

function LessonStepDialog({ l, kind, onClose }: { l: Lesson; kind: "return" | "archive" | "delete" | "submit"; onClose: () => void }) {
  const t = useTranslations("fu.lessons");
  const tc = useTranslations("fu.common");
  const refresh = useFuRefresh();
  const router = useRouter();
  const [text, setText] = useState("");
  const min = kind === "archive" ? 20 : kind === "return" ? 1 : 0;
  return (
    <StepDialog
      title={t(`${kind}Title`, { no: l.lesson_no })}
      description={t(`${kind}Body`)}
      confirmLabel={t(kind)}
      destructive={kind === "archive" || kind === "delete"}
      dismissLabel={tc("back")}
      testId={`lesson-${kind}-confirm`}
      disabled={text.trim().length < min}
      onConfirm={async () => {
        if (kind === "delete") {
          await unwrap(api.DELETE("/api/v1/lessons/{lesson_id}", { params: { path: { lesson_id: l.id } } }));
          await refresh();
          router.push("/lessons");
          return;
        }
        const action: S["FuLessonAction"] = kind === "return" ? "return_to_draft" : kind;
        await unwrap(api.POST("/api/v1/lessons/{lesson_id}/transitions", { params: { path: { lesson_id: l.id } }, body: { action, comment: text.trim() || null } }));
        await refresh();
        toast.success(t("done"));
      }}
      onClose={onClose}
    >
      {kind === "archive" || kind === "return" ? (
        <FormField id="ls-text" label={kind === "archive" ? tc("reason") : t("comment")} required hint={kind === "archive" ? tc("reasonMin", { min: 20, n: text.trim().length }) : undefined}>
          <Textarea value={text} onChange={(e) => setText(e.target.value)} maxLength={500} data-testid="ls-text" />
        </FormField>
      ) : null}
    </StepDialog>
  );
}

/** Two-language block: English LTR, Arabic RTL, side by side on wide screens. */
function BiBlock({ label, en, ar, testId }: { label: string; en: string | null | undefined; ar: string | null | undefined; testId?: string }) {
  return (
    <section className="flex flex-col gap-1" data-testid={testId}>
      <h3 className="text-sm font-semibold">{label}</h3>
      <div className="grid gap-3 md:grid-cols-2">
        <p dir="ltr" lang="en" className="whitespace-pre-wrap text-sm">
          {en || "—"}
        </p>
        <p dir="rtl" lang="ar" className="whitespace-pre-wrap text-sm">
          {ar || "—"}
        </p>
      </div>
    </section>
  );
}

function Applicability({ a }: { a: S["FuApplicability"] }) {
  const t = useTranslations("fu.lessons");
  const te = useTranslations("enums");
  const ref = useRefLists();
  return (
    <FieldList>
      <FieldItem label={t("activities")}>{(a.activities ?? []).map((x) => ref.label("activity", x)).join(" · ") || "—"}</FieldItem>
      <FieldItem label={t("mechanisms")}>{(a.mechanisms ?? []).map((x) => ref.label("mechanism", x)).join(" · ") || "—"}</FieldItem>
      <FieldItem label={t("trades")}>{(a.trades ?? []).map((x) => ref.label("trade", x)).join(" · ") || "—"}</FieldItem>
      <FieldItem label={t("zoneTypes")}>{(a.zone_types ?? []).map((x) => te(`zoneType.${x}` as "zoneType.airside")).join(" · ") || "—"}</FieldItem>
    </FieldList>
  );
}

function LessonView({ l }: { l: Lesson }) {
  const t = useTranslations("fu.lessons");
  const te = useTranslations("enums");
  return (
    <Card>
      <CardContent className="flex flex-col gap-4 p-4">
        <BiBlock label={t("titleField")} en={l.title_en} ar={l.title_ar} />
        <BiBlock label={t("whatHappened")} en={l.what_happened_en} ar={l.what_happened_ar} testId="lesson-what" />
        <BiBlock label={t("why")} en={l.why_en} ar={l.why_ar} />
        <section className="flex flex-col gap-1">
          <h3 className="text-sm font-semibold">{t("keyLessons")}</h3>
          <ol className="flex list-decimal flex-col gap-2 ps-5" data-testid="lesson-key">
            {l.key_lessons.map((k, i) => (
              <li key={i} className="grid gap-1 text-sm md:grid-cols-2">
                <span dir="ltr" lang="en">
                  {k.text_en || "—"}
                </span>
                <span dir="rtl" lang="ar">
                  {k.text_ar || "—"}
                </span>
              </li>
            ))}
          </ol>
        </section>
        <FieldList>
          <FieldItem label={t("rootCauses")}>{l.root_cause_codes.length ? <Code>{l.root_cause_codes.join(", ")}</Code> : "—"}</FieldItem>
          <FieldItem label={t("severity")}>{l.severity_potential ?? "—"}</FieldItem>
          <FieldItem label={t("actionsTaken")}>
            {l.actions_taken.length
              ? l.actions_taken.map((a) => (
                  <span key={a.ca_ref} className="me-2 inline-flex gap-1">
                    <Code>{a.ca_ref}</Code>
                    {a.control_level ? <span className="text-muted-foreground">({te(`controlLevel.${a.control_level}`)})</span> : null}
                  </span>
                ))
              : "—"}
          </FieldItem>
          {l.distribution_project_codes.length ? (
            <FieldItem label={t("projects")}>
              <Code>{l.distribution_project_codes.join(", ")}</Code>
            </FieldItem>
          ) : null}
        </FieldList>
        <Applicability a={l.applicability} />
      </CardContent>
    </Card>
  );
}

/** Draft editor (219): EN / AR texts, key lessons 1–5, root causes and applicability. The server rejects identities (P6f-3). */
function LessonEditor({ l }: { l: Lesson }) {
  const t = useTranslations("fu.lessons");
  const te = useTranslations("enums");
  const ref = useRefLists();
  const refresh = useFuRefresh();
  const [v, setV] = useState({
    title_en: l.title_en ?? "",
    title_ar: l.title_ar ?? "",
    what_happened_en: l.what_happened_en ?? "",
    what_happened_ar: l.what_happened_ar ?? "",
    why_en: l.why_en ?? "",
    why_ar: l.why_ar ?? "",
    root: l.root_cause_codes.join(", "),
  });
  const [keys, setKeys] = useState<S["FuKeyLesson"][]>(l.key_lessons.length ? l.key_lessons : [{ text_en: "", text_ar: "" }]);
  const [app, setApp] = useState<S["FuApplicability"]>(l.applicability);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  async function save() {
    setBusy(true);
    setError(null);
    try {
      await unwrap(
        api.PATCH("/api/v1/lessons/{lesson_id}", {
          params: { path: { lesson_id: l.id } },
          body: {
            title_en: v.title_en.trim() || null,
            title_ar: v.title_ar.trim() || null,
            what_happened_en: v.what_happened_en.trim() || null,
            what_happened_ar: v.what_happened_ar.trim() || null,
            why_en: v.why_en.trim() || null,
            why_ar: v.why_ar.trim() || null,
            root_cause_codes: v.root.split(/[,\s،]+/).filter(Boolean),
            key_lessons: keys.filter((k) => k.text_en?.trim() || k.text_ar?.trim()),
            applicability: app,
          },
        }),
      );
      await refresh();
      toast.success(t("saved"));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const pair = (k: "title" | "what_happened" | "why", rows?: number) => (
    <div className="grid gap-3 md:grid-cols-2">
      {(["en", "ar"] as const).map((lang) => {
        const key = `${k}_${lang}` as keyof typeof v;
        return (
          <FormField key={lang} id={`le-${key}`} label={`${t(k === "title" ? "titleField" : k === "what_happened" ? "whatHappened" : "why")} (${t(`lang.${lang}`)})`}>
            {rows ? (
              <Textarea dir={lang === "ar" ? "rtl" : "ltr"} lang={lang} rows={rows} value={v[key]} onChange={(e) => setV({ ...v, [key]: e.target.value })} maxLength={1500} data-testid={`le-${key}`} />
            ) : (
              <Input dir={lang === "ar" ? "rtl" : "ltr"} lang={lang} value={v[key]} onChange={(e) => setV({ ...v, [key]: e.target.value })} maxLength={150} data-testid={`le-${key}`} />
            )}
          </FormField>
        );
      })}
    </div>
  );
  return (
    <Card data-testid="lesson-editor">
      <CardHeader>
        <CardTitle className="text-base">{t("edit")}</CardTitle>
        <p className="text-xs text-muted-foreground">{t("deidentify")}</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {pair("title")}
        {pair("what_happened", 4)}
        {pair("why", 3)}
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-sm font-medium">{t("keyLessons")}</legend>
          {keys.map((k, i) => (
            <div key={i} className="grid gap-2 md:grid-cols-[1fr_1fr_auto]" data-testid="le-key">
              <Input aria-label={`${t("keyLessons")} ${i + 1} (${t("lang.en")})`} dir="ltr" value={k.text_en ?? ""} onChange={(e) => setKeys(keys.map((x, j) => (j === i ? { ...x, text_en: e.target.value } : x)))} data-testid={`le-key-en-${i}`} />
              <Input aria-label={`${t("keyLessons")} ${i + 1} (${t("lang.ar")})`} dir="rtl" value={k.text_ar ?? ""} onChange={(e) => setKeys(keys.map((x, j) => (j === i ? { ...x, text_ar: e.target.value } : x)))} data-testid={`le-key-ar-${i}`} />
              <Button variant="ghost" aria-label={t("removeKey")} disabled={keys.length === 1} onClick={() => setKeys(keys.filter((_, j) => j !== i))}>
                <Trash2 aria-hidden />
              </Button>
            </div>
          ))}
          {keys.length < 5 ? (
            <Button variant="outline" size="sm" className="w-fit" onClick={() => setKeys([...keys, { text_en: "", text_ar: "" }])}>
              <Plus aria-hidden />
              {t("addKey")}
            </Button>
          ) : null}
        </fieldset>
        <div className="grid gap-3 md:grid-cols-2">
          <FormField id="le-root" label={t("rootCauses")} hint={t("rootHint")}>
            <Input dir="ltr" value={v.root} onChange={(e) => setV({ ...v, root: e.target.value })} data-testid="le-root" />
          </FormField>
          <MultiSelect id="le-activities" label={t("activities")} options={ref.options("activity")} value={(app.activities ?? []) as string[]} onChange={(x) => setApp({ ...app, activities: x as S["Activity"][] })} testId="le-activities" />
          <MultiSelect id="le-mechanisms" label={t("mechanisms")} options={ref.options("mechanism")} value={(app.mechanisms ?? []) as string[]} onChange={(x) => setApp({ ...app, mechanisms: x as S["Mechanism"][] })} />
          <MultiSelect id="le-trades" label={t("trades")} options={ref.options("trade")} value={(app.trades ?? []) as string[]} onChange={(x) => setApp({ ...app, trades: x as S["Trade"][] })} />
          <MultiSelect
            id="le-zones"
            label={t("zoneTypes")}
            options={(["airside", "landside"] as const).map((z) => ({ value: z, label: te(`zoneType.${z}`) }))}
            value={app.zone_types ?? []}
            onChange={(x) => setApp({ ...app, zone_types: x })}
          />
        </div>
        <PossibleIdHint text={`${v.what_happened_en} ${v.why_en}`} />
        <MutationError error={error} />
        <Button className="w-fit" disabled={busy} onClick={() => void save()} data-testid="le-save">
          {t("save")}
        </Button>
      </CardContent>
    </Card>
  );
}

/** Publication (220, not the author): choose projects; DS-1 fixes the (project, contractor) pairs. */
function PublishPanel({ l }: { l: Lesson }) {
  const t = useTranslations("fu.lessons");
  const projects = useProjects({ page_size: 100 });
  const refresh = useFuRefresh();
  const [ids, setIds] = useState<string[]>(l.distribution_project_ids.length ? l.distribution_project_ids : l.source_project_id ? [l.source_project_id] : []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  async function publish() {
    setBusy(true);
    setError(null);
    try {
      await unwrap(api.PATCH("/api/v1/lessons/{lesson_id}", { params: { path: { lesson_id: l.id } }, body: { distribution_project_ids: ids } }));
      await unwrap(api.POST("/api/v1/lessons/{lesson_id}/transitions", { params: { path: { lesson_id: l.id } }, body: { action: "publish" } }));
      await refresh();
      toast.success(t("publishedToast"));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card data-testid="lesson-publish-panel">
      <CardHeader>
        <CardTitle className="text-base">{t("publishTitle")}</CardTitle>
        <p className="text-xs text-muted-foreground">{t("publishHint")}</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <MultiSelect
          id="lp-projects"
          label={t("projects")}
          options={(projects.data?.items ?? []).map((p) => ({ value: p.id, label: p.code }))}
          value={ids}
          onChange={setIds}
          testId="lp-projects"
        />
        <MutationError error={error} />
        <Button className="min-h-12 w-fit sm:min-h-control" disabled={busy} onClick={() => void publish()} data-testid="lesson-publish">
          {t("publish")}
        </Button>
      </CardContent>
    </Card>
  );
}

/* ───────────── distribution and acknowledgement (DS-1…DS-4) ───────────── */

function Distribution({ l }: { l: Lesson }) {
  const t = useTranslations("fu.dist");
  const q = useLessonDistribution(l.id);
  const items = q.data?.items ?? [];
  const show = useDisplay(l.source_project_id);
  return (
    <Card data-testid="lesson-distribution">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          <Users aria-hidden className="size-4" />
          {t("title")}
          <span className="text-sm font-normal text-muted-foreground" data-testid="dist-count">
            {t("count", { done: show(String(l.acknowledged)), total: show(String(l.distribution_items)) })}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent>{q.isLoading ? <LoadingState rows={2} /> : <AckList items={items} />}</CardContent>
    </Card>
  );
}

/** Distribution items as cards; a pending item the user may acknowledge has its form inline (phone-first). */
function AckList({ items, titles }: { items: S["FuDistributionRead"][]; titles?: Map<string, string> }) {
  const t = useTranslations("fu.dist");
  const td = useTranslations("fuDesign");
  const te = useTranslations("enums");
  const name = useLocalizedName();
  if (!items.length) return <EmptyState message={t("empty")} />;
  return (
    <ul className="flex flex-col gap-3" data-testid="dist-items">
      {items.map((d) => (
        <li key={d.id} className="flex flex-col gap-2 rounded-md border p-3" data-testid="dist-item" data-lesson={d.lesson_no} data-engagement={d.engagement_code ?? ""} data-status={d.status}>
          <div className="flex flex-wrap items-start justify-between gap-2">
            <span className="flex flex-col gap-0.5">
              {titles ? (
                <Link href={`/lessons/${d.lesson_id}`} className="font-medium text-primary hover:underline">
                  <Code>{d.lesson_no}</Code>
                </Link>
              ) : null}
              {titles?.get(d.lesson_id) ? <span className="font-medium">{titles.get(d.lesson_id)}</span> : null}
              <span className="text-sm">
                <Code>{d.project_code}</Code> · <Code>{d.engagement_code ?? "—"}</Code>
              </span>
            </span>
            <span className="flex flex-wrap items-center gap-1.5">
              {d.status === "pending" && dayPassed(d.ack_due_on) ? <StatusBadge status="overdue" label={td("overdue")} /> : null}
              <FuBadge group="fuDistributionStatus" status={d.status} testId="dist-status" />
            </span>
          </div>
          <div className="flex flex-wrap items-end gap-x-6 gap-y-1 text-sm">
            <span className="flex flex-col">
              <span className="text-xs text-muted-foreground">{t("due")}</span>
              <DayDue date={d.ack_due_on} open={d.status === "pending"} projectId={d.project_id} />
            </span>
            {d.acknowledged_at ? (
              <span className="inline-flex items-center gap-1 text-success">
                <CheckCircle2 aria-hidden className="size-4" />
                {d.response ? te(`fuAckResponse.${d.response}`) : null}
                {d.acknowledged_by ? ` · ${name(d.acknowledged_by.full_name_en, d.acknowledged_by.full_name_ar)}` : ""}
              </span>
            ) : null}
          </div>
          {d.reason ? <p className="text-xs text-muted-foreground">{d.reason}</p> : null}
          {d.on_behalf_note ? <p className="text-xs text-muted-foreground">{t("onBehalf")}: {d.on_behalf_note}</p> : null}
          {d.status === "pending" ? <AckForm d={d} /> : null}
        </li>
      ))}
    </ul>
  );
}

function AckForm({ d }: { d: S["FuDistributionRead"] }) {
  const t = useTranslations("fu.dist");
  const te = useTranslations("enums");
  const caps = useFuCaps(d.project_id);
  const refresh = useFuRefresh();
  const [resp, setResp] = useState<S["FuAckResponse"] | "">("");
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  if (!caps.acknowledge) return null;
  const rep = caps.me?.employer_type === "contractor";
  async function go() {
    setBusy(true);
    setError(null);
    try {
      await unwrap(
        api.POST("/api/v1/lesson-distribution/{item_id}/acknowledge", {
          params: { path: { item_id: d.id } },
          body: { response: resp as S["FuAckResponse"], reason: reason.trim() || null, on_behalf_note: note.trim() || null },
        }),
      );
      await refresh();
      toast.success(t("done"));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex flex-col gap-2 border-t pt-2" data-testid="ack-form">
      <Choices label={t("response")} testId="ack-response" value={resp} options={(["will_brief", "not_applicable"] as const).map((x) => ({ value: x, label: te(`fuAckResponse.${x}`) }))} onChange={setResp} />
      {resp === "not_applicable" ? (
        <FormField id={`ack-reason-${d.id}`} label={t("reason")} required hint={t("min20", { n: reason.trim().length })}>
          <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} data-testid="ack-reason" />
        </FormField>
      ) : null}
      {!rep ? (
        <FormField id={`ack-note-${d.id}`} label={t("onBehalf")} hint={t("onBehalfHint")}>
          <Textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} data-testid="ack-note" />
        </FormField>
      ) : null}
      <MutationError error={error} />
      <Button className="min-h-12 w-full sm:w-fit" disabled={busy || !resp || (resp === "not_applicable" && reason.trim().length < 20)} onClick={() => void go()} data-testid="ack-submit">
        {t("acknowledge")}
      </Button>
    </div>
  );
}

/* ───────────── 6d links: topics, campaigns, checklist change requests (LK-1…LK-3) ───────────── */

function Links({ l }: { l: Lesson }) {
  const t = useTranslations("fu.links");
  const te = useTranslations("enums");
  const caps = useFuCaps(l.source_project_id);
  const bi = useBi();
  const [adding, setAdding] = useState(false);
  const [reject, setReject] = useState<S["FuLinkRead"] | null>(null);
  return (
    <Card data-testid="lesson-links">
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Link2 aria-hidden className="size-4" />
          {t("title")}
        </CardTitle>
        {caps.draft && l.status !== "archived" ? (
          <Button size="sm" variant="outline" onClick={() => setAdding(true)} data-testid="link-add">
            <Plus aria-hidden />
            {t("add")}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent>
        {l.links.length === 0 ? (
          <EmptyState message={t("empty")} />
        ) : (
          <ul className="flex flex-col divide-y">
            {l.links.map((k) => (
              <li key={k.id} className="flex flex-col gap-1 py-2 text-sm" data-testid="link-row" data-kind={k.kind}>
                <span className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{te(`fuLinkKind.${k.kind}`)}</span>
                  <Code>{k.ref}</Code>
                  {k.item_code ? <Code>{k.item_code}</Code> : null}
                  {k.status ? <FuBadge group="fuChangeStatus" status={k.status} testId="link-status" /> : null}
                  {k.adopted_version ? <span className="text-muted-foreground">{t("version", { v: k.adopted_version })}</span> : null}
                </span>
                {k.proposed_text_en || k.proposed_text_ar ? <span className="text-muted-foreground">{bi(k.proposed_text_en, k.proposed_text_ar)}</span> : null}
                {k.reject_reason ? <span className="text-muted-foreground">{k.reject_reason}</span> : null}
                {k.kind === "template_change" && k.status === "open" && caps.rejectChange ? (
                  <Button size="sm" variant="destructive-outline" className="w-fit" onClick={() => setReject(k)} data-testid="link-reject">
                    {t("reject")}
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
      {adding ? <AddLinkDialog l={l} onClose={() => setAdding(false)} /> : null}
      {reject ? <RejectDialog link={reject} onClose={() => setReject(null)} /> : null}
    </Card>
  );
}

function AddLinkDialog({ l, onClose }: { l: Lesson; onClose: () => void }) {
  const t = useTranslations("fu.links");
  const te = useTranslations("enums");
  const refresh = useFuRefresh();
  const { projectId } = useCurrentProject();
  const published = l.status === "published";
  const [kind, setKind] = useState<S["FuLinkKind"]>("topic");
  const [refText, setRef] = useState("");
  const [item, setItem] = useState("");
  const [en, setEn] = useState("");
  const [arText, setAr] = useState("");
  const kinds: S["FuLinkKind"][] = published ? ["topic", "campaign", "template_change"] : ["topic", "template_change"];
  return (
    <StepDialog
      title={t("addTitle")}
      description={kind === "topic" ? t("topicHint") : kind === "campaign" ? t("campaignHint") : t("changeHint")}
      confirmLabel={t("save")}
      testId="link-save"
      wide
      disabled={kind === "template_change" && (!refText.trim() || (!en.trim() && !arText.trim()))}
      onConfirm={async () => {
        await unwrap(
          api.POST("/api/v1/lessons/{lesson_id}/links", {
            params: { path: { lesson_id: l.id } },
            body: {
              kind,
              ref: refText.trim() || null,
              project_id: kind === "campaign" || (kind === "topic" && !refText.trim()) ? projectId : null,
              item_code: item.trim() || null,
              proposed_text_en: en.trim() || null,
              proposed_text_ar: arText.trim() || null,
            },
          }),
        );
        await refresh();
        toast.success(t("saved"));
      }}
      onClose={onClose}
    >
      <Choices label={t("kind")} testId="link-kind" value={kind} options={kinds.map((k) => ({ value: k, label: te(`fuLinkKind.${k}`) }))} onChange={setKind} />
      {kind !== "campaign" ? (
        <FormField id="link-ref" label={kind === "topic" ? t("topicCode") : t("templateCode")} required={kind === "template_change"} hint={kind === "topic" ? t("topicCodeHint") : undefined}>
          <Input className="ltr" value={refText} onChange={(e) => setRef(e.target.value)} maxLength={40} data-testid="link-ref" />
        </FormField>
      ) : null}
      {kind === "template_change" ? (
        <>
          <FormField id="link-item" label={t("itemCode")} hint={t("itemCodeHint")}>
            <Input className="ltr" value={item} onChange={(e) => setItem(e.target.value)} maxLength={40} data-testid="link-item" />
          </FormField>
          <FormField id="link-en" label={t("proposedEn")}>
            <Textarea dir="ltr" value={en} onChange={(e) => setEn(e.target.value)} maxLength={500} data-testid="link-en" />
          </FormField>
          <FormField id="link-ar" label={t("proposedAr")}>
            <Textarea dir="rtl" value={arText} onChange={(e) => setAr(e.target.value)} maxLength={500} data-testid="link-ar" />
          </FormField>
        </>
      ) : null}
    </StepDialog>
  );
}

function RejectDialog({ link, onClose }: { link: S["FuLinkRead"]; onClose: () => void }) {
  const t = useTranslations("fu.links");
  const tc = useTranslations("fu.common");
  const refresh = useFuRefresh();
  const [reason, setReason] = useState("");
  return (
    <StepDialog
      title={t("rejectTitle", { ref: link.ref })}
      confirmLabel={t("reject")}
      destructive
      dismissLabel={tc("back")}
      testId="link-reject-confirm"
      disabled={reason.trim().length < 20}
      onConfirm={async () => {
        await unwrap(api.POST("/api/v1/lesson-links/{link_id}/reject", { params: { path: { link_id: link.id } }, body: { reason: reason.trim() } }));
        await refresh();
      }}
      onClose={onClose}
    >
      <FormField id="lr-reason" label={tc("reason")} required hint={tc("reasonMin", { min: 20, n: reason.trim().length })}>
        <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} />
      </FormField>
    </StepDialog>
  );
}

/* ───────────── 90-day effectiveness check (EF-1…EF-5) ───────────── */

function Facts({ facts, projectId }: { facts: Record<string, unknown>; projectId: string | null }) {
  const t = useTranslations("fu.check");
  const show = useDisplay(projectId);
  const n = (k: string) => show(String(facts[k] ?? "—"));
  const rec = (facts.recurrences as (string | { ref?: string })[] | undefined) ?? [];
  return (
    <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2" data-testid="check-facts">
      <div className="flex flex-col">
        <dt className="text-xs text-muted-foreground">{t("recurrences")}</dt>
        <dd className="flex flex-wrap items-center gap-2">
          {rec.length ? (
            <>
              <TriangleAlert aria-hidden className="size-4 text-danger" />
              {rec.map((r, i) => (
                <Code key={i}>{typeof r === "string" ? r : (r.ref ?? "")}</Code>
              ))}
            </>
          ) : (
            <>
              <CheckCircle2 aria-hidden className="size-4 text-success" />
              {t("none")}
            </>
          )}
        </dd>
      </div>
      <div className="flex flex-col">
        <dt className="text-xs text-muted-foreground">{t("acks")}</dt>
        <dd className="tabular-nums">
          <bdi className="ltr">
            {n("ack_done")} / {n("ack_total")}
          </bdi>{" "}
          ({n("ack_rate_pct")} %)
        </dd>
      </div>
      <div className="flex flex-col">
        <dt className="text-xs text-muted-foreground">{t("campaigns")}</dt>
        <dd className="tabular-nums">
          <bdi className="ltr">
            {n("campaign_pairs_met")} / {n("campaign_pairs_total")}
          </bdi>
        </dd>
      </div>
      <div className="flex flex-col">
        <dt className="text-xs text-muted-foreground">{t("cas")}</dt>
        <dd className="tabular-nums">
          <bdi className="ltr">
            {n("cas_closed")} / {n("cas_total")}
          </bdi>
        </dd>
      </div>
    </dl>
  );
}

function CheckCard({ check }: { check: S["FuCheckRead"] }) {
  const t = useTranslations("fu.check");
  const caps = useFuCaps(check.project_id);
  const name = useLocalizedName();
  const [open, setOpen] = useState(false);
  return (
    <Card data-testid="lesson-check" data-status={check.status}>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          {t("title")}
          <FuBadge group="fuCheckStatus" status={check.status} testId="check-status" />
          {check.overdue ? <StatusBadge status="overdue" label={t("overdue")} /> : null}
        </CardTitle>
        {caps.effectiveness && check.status === "scheduled" ? (
          <Button size="sm" onClick={() => setOpen(true)} data-testid="check-complete">
            {t("complete")}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
          <span className="flex flex-col">
            <span className="text-xs text-muted-foreground">{t("due")}</span>
            <DayDue date={check.due_on} open={check.status === "scheduled"} projectId={check.project_id} />
          </span>
          <span className="flex flex-col">
            <span className="text-xs text-muted-foreground">{t("suggested")}</span>
            <ResultBadge result={check.suggested_result} />
          </span>
          {check.result ? (
            <span className="flex flex-col">
              <span className="text-xs text-muted-foreground">{t("result")}</span>
              <ResultBadge result={check.result} />
              {check.completed_by ? <span className="text-xs text-muted-foreground">{name(check.completed_by.full_name_en, check.completed_by.full_name_ar)}</span> : null}
            </span>
          ) : null}
        </div>
        <Facts facts={check.facts} projectId={check.project_id} />
        {check.rationale ? <p className="text-sm text-muted-foreground">{check.rationale}</p> : null}
        {check.follow_up_ca_ref || check.follow_up_lesson_no ? (
          <p className="text-sm">
            {t("followUp")}: <Code>{check.follow_up_ca_ref ?? check.follow_up_lesson_no}</Code>
          </p>
        ) : null}
      </CardContent>
      {open ? <CompleteCheckDialog check={check} onClose={() => setOpen(false)} /> : null}
    </Card>
  );
}

export function CompleteCheckDialog({ check, onClose }: { check: S["FuCheckRead"]; onClose: () => void }) {
  const t = useTranslations("fu.check");
  const te = useTranslations("enums");
  const tc = useTranslations("fu.common");
  const refresh = useFuRefresh();
  const { projectId } = useCurrentProject();
  const pid = check.project_id ?? projectId ?? "";
  const [result, setResult] = useState<S["FuEffectResult"] | "">(check.suggested_result ?? "");
  const [rationale, setRationale] = useState("");
  const [owner, setOwner] = useState("");
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const differs = Boolean(result) && result !== check.suggested_result;
  const needCa = result === "not_effective";
  const dialogTitle: string = t("completeTitle", { no: check.lesson_no });
  return (
    <StepDialog
      title={dialogTitle}
      description={t("completeBody")}
      confirmLabel={t("complete")}
      testId="check-confirm"
      wide
      disabled={!result || (differs && rationale.trim().length < 20) || (needCa && !owner)}
      onConfirm={async () => {
        await unwrap(
          api.POST("/api/v1/effectiveness-checks/{check_id}/complete", {
            params: { path: { check_id: check.id } },
            body: {
              result: result as S["FuEffectResult"],
              rationale: rationale.trim() || null,
              follow_up_ca: needCa ? { owner_id: owner, title: title.trim() || null, due_date: due || null } : null,
            },
          }),
        );
        await refresh();
        toast.success(t("done"));
      }}
      onClose={onClose}
    >
      <Facts facts={check.facts} projectId={check.project_id} />
      <p className="text-sm">
        {t("suggested")}: <ResultBadge result={check.suggested_result} />
      </p>
      <Choices
        label={t("result")}
        testId="check-result"
        value={result}
        options={(["effective", "partly_effective", "not_effective"] as const).map((r) => ({ value: r, label: te(`fuEffectResult.${r}`) }))}
        onChange={setResult}
      />
      {differs ? (
        <FormField id="ck-rationale" label={t("rationale")} required hint={tc("reasonMin", { min: 20, n: rationale.trim().length })}>
          <Textarea value={rationale} onChange={(e) => setRationale(e.target.value)} maxLength={1000} data-testid="check-rationale" />
        </FormField>
      ) : null}
      {needCa ? (
        <div className="flex flex-col gap-3 rounded-md border p-3">
          <p className="text-sm font-medium">{t("caTitle")}</p>
          <FormField id="ck-owner" label={t("caOwner")} required>
            <UserSelect projectId={pid} value={owner} onChange={(e) => setOwner(e.target.value)} data-testid="check-owner" />
          </FormField>
          <FormField id="ck-title" label={t("caText")}>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
          </FormField>
          <FormField id="ck-due" label={t("caDue")}>
            <Input type="date" value={due} onChange={(e) => setDue(e.target.value)} />
          </FormField>
        </div>
      ) : null}
    </StepDialog>
  );
}

/* ═════════════ acknowledgements of the current project (221; phone-first) ═════════════ */

export function LessonAcksPage() {
  return <ProjectGate>{(p) => <Acks project={p} />}</ProjectGate>;
}

function Acks({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("fu.dist");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useFuCaps(project.id);
  const bi = useBi();
  const s = useSearchState();
  const status = (s.get("status") as S["FuDistributionStatus"] | null) ?? "pending";
  const q = useProjectDistribution(project.id, { status: status ? [status] : null }, { enabled: caps.view || caps.acknowledge });
  const lessons = useLessons({ page_size: 100 }, { enabled: caps.library });
  if (!caps.view && !caps.acknowledge) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const titles = new Map((lessons.data?.items ?? []).map((l) => [l.id, bi(l.title_en, l.title_ar)]));
  return (
    <div>
      <PageHeader title={t("pageTitle")} description={t("pageSubtitle")} />
      <LessonSubNav />
      <DeadlineRule className="mb-3" />
      <ListToolbar>
        <Select aria-label={t("status")} className="lg:w-56" value={status} onChange={(e) => s.set({ status: e.target.value })} data-testid="acks-status">
          {(["pending", "acknowledged", "not_applicable", "withdrawn"] as const).map((x) => (
            <option key={x} value={x}>
              {te(`fuDistributionStatus.${x}`)}
            </option>
          ))}
        </Select>
      </ListToolbar>
      {q.isLoading ? <LoadingState /> : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : <AckList items={q.data?.items ?? []} titles={titles} />}
    </div>
  );
}

/* ═════════════ effectiveness register (215) ═════════════ */

export function EffectivenessChecksPage() {
  return <ProjectGate>{(p) => <Checks project={p} />}</ProjectGate>;
}

function Checks({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("fu.check");
  const tc = useTranslations("common");
  const caps = useFuCaps(project.id);
  const q = useEffectivenessChecks(project.id, { page_size: 100 }, { enabled: caps.view });
  const [done, setDone] = useState<S["FuCheckRead"] | null>(null);
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = [...(q.data?.items ?? [])].sort((a, b) => Number(b.overdue) - Number(a.overdue) || (a.status === b.status ? a.due_on.localeCompare(b.due_on) : a.status === "scheduled" ? -1 : 1));
  return (
    <div>
      <PageHeader title={t("pageTitle")} description={t("pageSubtitle")} />
      <LessonSubNav />
      <DeadlineRule className="mb-3" />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <Table data-testid="checks-table">
          <THead>
            <TR>
              <TH>{t("lesson")}</TH>
              <TH>{t("due")}</TH>
              <TH>{t("status")}</TH>
              <TH>{t("suggested")}</TH>
              <TH>{t("result")}</TH>
              <TH>{tc("actions")}</TH>
            </TR>
          </THead>
          <TBody>
            {items.map((c) => (
              <TR key={c.id} data-testid="check-row" data-no={c.lesson_no}>
                <TD label={t("lesson")}>
                  <Link href={`/lessons/${c.lesson_id}`} className="text-primary hover:underline">
                    <Code>{c.lesson_no}</Code>
                  </Link>
                </TD>
                <TD label={t("due")}>
                  <DayDue date={c.due_on} open={c.status === "scheduled"} projectId={project.id} />
                </TD>
                <TD label={t("status")}>
                  <FuBadge group="fuCheckStatus" status={c.status} testId="check-status" />
                </TD>
                <TD label={t("suggested")}>
                  <ResultBadge result={c.suggested_result} />
                </TD>
                <TD label={t("result")}>
                  <ResultBadge result={c.result} />
                </TD>
                <TD label={tc("actions")}>
                  {caps.effectiveness && c.status === "scheduled" ? (
                    <Button size="sm" variant="outline" onClick={() => setDone(c)} data-testid="check-row-complete">
                      {t("complete")}
                    </Button>
                  ) : null}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : (
        <EmptyState message={t("empty")} />
      )}
      {done ? <CompleteCheckDialog check={done} onClose={() => setDone(null)} /> : null}
    </div>
  );
}
