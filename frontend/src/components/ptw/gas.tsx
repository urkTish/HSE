"use client";
import { CircleCheck, OctagonAlert, OctagonX, Plus, Trash2, TriangleAlert } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { TpiLabel, TpiSelect } from "@/components/cert/common";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { SignaturePad, StepDialog } from "@/components/access/common";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { CheckboxGroup } from "@/components/common/checkbox-group";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SearchFilter, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useAppointments, useBumpTests, useDetector, useDetectors, useGasTest, useGasTests, usePermit, usePermits, usePtwRefresh } from "@/lib/api/ptw";
import { can, canWrite } from "@/lib/permissions";
import { DETECTOR_STATUSES, GAS_READING_POINTS, GAS_SENSORS, GAS_TEST_TYPES, LEL_REFERENCE_GASES } from "@/lib/ptw-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { Countdown, DateTimeInput, DecimalInput, GasSubNav, nowIso, PermitNo, TypeChips, useNow, useProjectId, userLabel } from "./common";
import { RecordActions } from "@/components/common/record-actions";

type S = Schemas;
type Reading = { point: S["GasReadingPoint"]; o2_pct: string; lel_pct: string; h2s_ppm: string; co_ppm: string; other: Record<string, string> };
type Limits = S["AppliedLimits"];
const PAGE_SIZE = 50;
const STD = ["o2_pct", "lel_pct", "h2s_ppm", "co_ppm"] as const;
type Std = (typeof STD)[number];

/* ───────────── shared ───────────── */


/** Which reading field a server fail code points at (the server evaluates; the UI only marks the cell). */
const FAIL_FIELD: Record<S["GasFailCode"], Std | "other"> = { O2_OUT_OF_RANGE: "o2_pct", LEL_ABOVE_LIMIT: "lel_pct", H2S_ABOVE_LIMIT: "h2s_ppm", CO_ABOVE_LIMIT: "co_ppm", OTHER_ABOVE_LIMIT: "other" };

function LimitsText({ l }: { l: Limits }) {
  const t = useTranslations("gas");
  const te = useTranslations("enums");
  return (
    <div className="flex flex-col gap-1 text-sm" data-testid="gas-limits">
      <p className="text-xs text-muted-foreground">{t("limitsFrom", { list: l.profiles.map((p) => te(`gasProfile.${p}`)).join(" + ") })}</p>
      <p className="flex flex-wrap gap-x-4 gap-y-1">
        <span>
          O₂ <bdi className="ltr tabular-nums">{l.limits.o2_min_pct}–{l.limits.o2_max_pct} %</bdi>
        </span>
        <span>
          LEL <bdi className="ltr tabular-nums">&lt; {l.limits.lel_below_pct} %</bdi>
        </span>
        <span>
          H₂S <bdi className="ltr tabular-nums">&lt; {l.limits.h2s_below_ppm} ppm</bdi>
        </span>
        <span>
          CO <bdi className="ltr tabular-nums">&lt; {l.limits.co_below_ppm} ppm</bdi>
        </span>
        {l.other_toxics.map((o) => (
          <span key={o.gas}>
            {o.gas} <bdi className="ltr tabular-nums">&lt; {o.below} {o.unit}</bdi>
          </span>
        ))}
      </p>
    </div>
  );
}

function ResultBadge({ result }: { result: S["GasTestResult"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="gas-result" data-result={result}>
      <StatusBadge status={result === "pass" ? "ok" : "failed"} label={te(`gasResult.${result}`)} />
    </span>
  );
}

/** Large live result of the server's evaluation: icon + word + sentence, readable in the sun. */
function GasVerdict({ result, compact }: { result: S["GasTestResult"]; compact?: boolean }) {
  const te = useTranslations("enums");
  const td = useTranslations("ptwDesign");
  const pass = result === "pass";
  const Icon = pass ? CircleCheck : OctagonX;
  return (
    <div className={cn("flex items-center gap-3 rounded-lg border-2 p-3", pass ? "border-success/50 bg-success-bg text-success" : "border-danger/60 bg-danger-bg text-danger")} data-verdict={result}>
      <Icon aria-hidden className={cn("shrink-0", compact ? "size-7" : "size-9")} strokeWidth={2.25} />
      <span className="min-w-0">
        <span className={cn("block leading-tight font-bold uppercase", compact ? "text-xl" : "text-2xl")}>{te(`gasResult.${result}`)}</span>
        <span className="block text-sm font-medium text-foreground">{pass ? td("gasPassLine") : td("gasFailLine")}</span>
      </span>
    </div>
  );
}

/** Column label and the applied limit for each standard reading (both from the server's applied limits). */
function useStdColumns(limits: Limits) {
  const l = limits.limits;
  return [
    { k: "o2_pct" as const, label: "O₂ %", limit: `${l.o2_min_pct}–${l.o2_max_pct}` },
    { k: "lel_pct" as const, label: "LEL %", limit: `< ${l.lel_below_pct}` },
    { k: "h2s_ppm" as const, label: "H₂S ppm", limit: `< ${l.h2s_below_ppm}` },
    { k: "co_ppm" as const, label: "CO ppm", limit: `< ${l.co_below_ppm}` },
  ];
}

/** A reading the server marked as outside its limit: bold, red, a warning icon and the words, never colour alone. */
function ReadingValue({ value, fail }: { value: string | null | undefined; fail: boolean }) {
  const t = useTranslations("ptwDesign");
  if (!fail) return <bdi className="ltr tabular-nums">{value ?? "—"}</bdi>;
  return (
    <span className="inline-flex items-center gap-1 rounded bg-danger-bg px-1.5 font-bold text-danger" data-fail="true">
      <TriangleAlert aria-hidden className="size-4 shrink-0" />
      <bdi className="ltr tabular-nums">{value ?? "—"}</bdi>
      <span className="text-xs font-semibold">{t("outOfLimit")}</span>
    </span>
  );
}

/** The governing reading in the narrow preview column: one line per gas with its limit (no sideways scroll). */
function WorstReading({ r, limits }: { r: S["GasReadingRead"]; limits: Limits }) {
  const te = useTranslations("enums");
  const td = useTranslations("ptwDesign");
  const cols = useStdColumns(limits);
  return (
    <div className="rounded-md border text-sm" data-testid="gas-readings">
      <p className="border-b px-2 py-1 text-xs text-muted-foreground">{te(`gasPoint.${r.point}`)}</p>
      <dl className="divide-y">
        {cols.map((c) => (
          <div key={c.k} className="flex items-center justify-between gap-2 px-2 py-1.5">
            <dt className="flex flex-col leading-tight">
              <bdi className="ltr font-medium">{c.label}</bdi>
              <span className="text-[11px] text-muted-foreground">
                {td("limit")} <bdi className="ltr tabular-nums">{c.limit}</bdi>
              </span>
            </dt>
            <dd>
              <ReadingValue value={r[c.k]} fail={r.fail_codes.some((x) => FAIL_FIELD[x] === c.k)} />
            </dd>
          </div>
        ))}
        {limits.other_toxics.map((o) => (
          <div key={o.gas} className="flex items-center justify-between gap-2 px-2 py-1.5">
            <dt className="flex flex-col leading-tight">
              <bdi className="ltr font-medium">
                {o.gas} {o.unit}
              </bdi>
              <span className="text-[11px] text-muted-foreground">
                {td("limit")} <bdi className="ltr tabular-nums">{`< ${o.below}`}</bdi>
              </span>
            </dt>
            <dd>
              <ReadingValue value={r.other.find((x) => x.gas === o.gas)?.value} fail={r.fail_codes.includes("OTHER_ABOVE_LIMIT")} />
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function ReadingsTable({ readings, limits }: { readings: S["GasReadingRead"][]; limits: Limits }) {
  const t = useTranslations("gas");
  const td = useTranslations("ptwDesign");
  const te = useTranslations("enums");
  const others = limits.other_toxics;
  const cols = useStdColumns(limits);
  const head = (label: string, limit: string) => (
    <span className="flex flex-col leading-tight">
      <bdi className="ltr">{label}</bdi>
      <span className="text-[11px] font-normal text-muted-foreground">
        {td("limit")} <bdi className="ltr tabular-nums">{limit}</bdi>
      </span>
    </span>
  );
  return (
    <div className="overflow-x-auto">
      <Table data-testid="gas-readings">
        <THead>
          <TR>
            <TH>{t("point")}</TH>
            {cols.map((c) => (
              <TH key={c.k}>{head(c.label, c.limit)}</TH>
            ))}
            {others.map((o) => (
              <TH key={o.gas}>{head(`${o.gas} ${o.unit}`, `< ${o.below}`)}</TH>
            ))}
          </TR>
        </THead>
        <TBody>
          {readings.map((r, i) => (
            <TR key={i} data-fail={r.fail_codes.length ? "true" : "false"}>
              <TD label={t("point")}>{te(`gasPoint.${r.point}`)}</TD>
              {cols.map((c) => (
                <TD key={c.k} label={`${c.label} (${c.limit})`}>
                  <ReadingValue value={r[c.k]} fail={r.fail_codes.some((x) => FAIL_FIELD[x] === c.k)} />
                </TD>
              ))}
              {others.map((o) => (
                <TD key={o.gas} label={`${o.gas} ${o.unit} (< ${o.below})`}>
                  <ReadingValue value={r.other.find((x) => x.gas === o.gas)?.value} fail={r.fail_codes.includes("OTHER_ABOVE_LIMIT")} />
                </TD>
              ))}
            </TR>
          ))}
        </TBody>
      </Table>
    </div>
  );
}

/* ───────────── gas test log ───────────── */

export function GasTestListPage() {
  return <ProjectGate>{(p) => <GasTestList project={p} />}</ProjectGate>;
}

function GasTestList({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("gas");
  const te = useTranslations("enums");
  const me = useMeData();
  const locale = useLocale();
  const { dateTime } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const types = s.getAll("test_type") as S["GasTestType"][];
  const q = useGasTests(project.id, {
    permit_id: s.get("permit_id") || null,
    detector_id: s.get("detector_id") || null,
    test_type: types.length ? types : null,
    result: (s.get("result") as S["GasTestResult"] | null) || null,
    date_from: s.get("date_from") || null,
    date_to: s.get("date_to") || null,
    page,
    page_size: PAGE_SIZE,
  });
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          canWrite(me, "gas_test.record", project.id) ? (
            <Button asChild>
              <Link href="/gas-tests/new" data-testid="new-gas-test">
                <Plus aria-hidden />
                {t("record")}
              </Link>
            </Button>
          ) : null
        }
      />
      <GasSubNav />
      <ListToolbar>
        <MultiSelect id="gt-type" label={t("testType")} options={GAS_TEST_TYPES.map((x) => ({ value: x, label: te(`gasTestType.${x}`) }))} value={types} onChange={(v) => s.set({ test_type: v })} />
        <SelectFilter id="gt-result" label={t("result")} value={(s.get("result") ?? "") as S["GasTestResult"] | ""} onChange={(v) => s.set({ result: v })} options={(["pass", "fail"] as const).map((x) => ({ value: x, label: te(`gasResult.${x}`) }))} />
        <FormField id="gt-from" label={t("from")}>
          <Input id="gt-from" type="date" className="ltr" value={s.get("date_from") ?? ""} onChange={(e) => s.set({ date_from: e.target.value })} />
        </FormField>
        <FormField id="gt-to" label={t("to")}>
          <Input id="gt-to" type="date" className="ltr" value={s.get("date_to") ?? ""} onChange={(e) => s.set({ date_to: e.target.value })} />
        </FormField>
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="gas-tests-table">
            <THead>
              <TR>
                <TH>{t("test")}</TH>
                <TH>{t("permit")}</TH>
                <TH>{t("testType")}</TH>
                <TH>{t("tester")}</TH>
                <TH>{t("detector")}</TH>
                <TH>{t("result")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((g) => (
                <TR key={g.id} data-testid="gas-test-row" className={g.superseded ? "opacity-60" : undefined}>
                  <TD label={t("test")}>
                    <Link href={`/gas-tests/${g.id}`} className="ltr font-medium text-primary hover:underline">
                      {g.test_no}
                    </Link>
                    <span className="[unicode-bidi:isolate] block text-xs text-muted-foreground">{dateTime(g.tested_at)}</span>
                  </TD>
                  <TD label={t("permit")}>
                    <PermitNo p={g.permit} />
                  </TD>
                  <TD label={t("testType")}>{te(`gasTestType.${g.test_type}`)}</TD>
                  <TD label={t("tester")}>{g.tester.holder_name_en ? (locale === "ar" && g.tester.holder_name_ar ? g.tester.holder_name_ar : g.tester.holder_name_en) : <bdi className="ltr">{g.tester.appointment_no}</bdi>}</TD>
                  <TD label={t("detector")}>
                    <bdi className="ltr">{g.detector.detector_no}</bdi>
                  </TD>
                  <TD label={t("result")}>
                    <ResultBadge result={g.result} />
                    {g.fail_codes.length ? <span className="block text-xs text-danger">{g.fail_codes.map((c) => te(`gasFailCode.${c}`)).join(", ")}</span> : null}
                    {g.superseded ? <span className="block text-xs text-muted-foreground">{t("superseded")}</span> : null}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={q.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState />
      )}
    </div>
  );
}

/* ───────────── gas test entry with live preview ───────────── */

export function GasTestEntryPage() {
  return <ProjectGate>{(p) => <GasTestEntry project={p} />}</ProjectGate>;
}

function defaultPoints(types: S["PermitType"][]): S["GasReadingPoint"][] {
  return types.includes("confined_space") ? ["top", "middle", "bottom"] : ["at_work_point"];
}

function defaultType(p: S["PermitRead"]): S["GasTestType"] {
  if (p.status === "approved") return "pre_issue";
  if (p.status === "suspended") return p.status_reason === "gas_test_failed" || p.status_reason === "gas_alarm" ? "post_alarm" : "revalidation";
  if (p.gas.post_break_test_required) return "post_break";
  return "periodic";
}

function GasTestEntry({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("gas");
  const s = useSearchState();
  const permitId = s.get("permit_id") ?? "";
  const live = usePermits(project.id, { status: ["approved", "issued", "active", "suspended"], page_size: 200 });
  const choices = (live.data?.items ?? []).filter((p) => p.gas_status !== "not_required");
  return (
    <div className="flex flex-col gap-5">
      <div>
        <Breadcrumbs items={[{ label: t("title"), href: "/gas-tests" }, { label: t("record") }]} />
        <PageHeader title={t("record")} description={t("recordHint")} />
      </div>
      <FormField id="ge-permit" label={t("permit")} required>
        <Select id="ge-permit" value={permitId} onChange={(e) => s.set({ permit_id: e.target.value })} data-testid="gas-permit">
          <option value="">—</option>
          {choices.map((p) => (
            <option key={p.id} value={p.id}>
              {p.display_no} · {p.title}
            </option>
          ))}
        </Select>
      </FormField>
      {permitId ? <GasTestForm key={permitId} permitId={permitId} /> : null}
    </div>
  );
}

function limitText(l: Limits, k: Std): string {
  const x = l.limits;
  return k === "o2_pct" ? `${x.o2_min_pct}–${x.o2_max_pct} %` : k === "lel_pct" ? `< ${x.lel_below_pct} %` : k === "h2s_ppm" ? `< ${x.h2s_below_ppm} ppm` : `< ${x.co_below_ppm} ppm`;
}

function GasTestForm({ permitId }: { permitId: string }) {
  const t = useTranslations("gas");
  const td = useTranslations("ptwDesign");
  const te = useTranslations("enums");
  const terr = useTranslations("errors");
  const tc = useTranslations("common");
  const me = useMeData();
  const router = useRouter();
  const refresh = usePtwRefresh();
  const pq = usePermit(permitId);
  const p = pq.data;
  const pid = p?.project_id ?? "";
  const testers = useAppointments(pid, { function: ["gas_tester"], status: ["active"], page_size: 200 }, { enabled: Boolean(p) });
  const detectors = useDetectors(pid, { status: ["in_service"], page_size: 200 }, { enabled: Boolean(p) });
  const [type, setType] = useState<S["GasTestType"] | "">("");
  const [at, setAt] = useState(nowIso());
  const [tester, setTester] = useState("");
  const [detector, setDetector] = useState("");
  const [readings, setReadings] = useState<Reading[] | null>(null);
  const [temp, setTemp] = useState("");
  const [sig, setSig] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [preview, setPreview] = useState<S["GasEvaluation"] | null>(null);
  const [previewError, setPreviewError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const testType = type || (p ? defaultType(p) : "periodic");
  const rows = useMemo<Reading[]>(() => readings ?? (p ? defaultPoints(p.work_types).map((pt) => ({ point: pt, o2_pct: "", lel_pct: "", h2s_ppm: "", co_ppm: "", other: {} })) : []), [readings, p]);
  const body = useMemo(
    () =>
      rows.map((r) => ({
        point: r.point,
        o2_pct: r.o2_pct || null,
        lel_pct: r.lel_pct || null,
        h2s_ppm: r.h2s_ppm || null,
        co_ppm: r.co_ppm || null,
        other: Object.entries(r.other)
          .filter(([, v]) => v.trim() !== "")
          .map(([gas, value]) => ({ gas, value, unit: preview?.applicable_limits.other_toxics.find((o) => o.gas === gas)?.unit ?? "ppm" })),
      })),
    [rows, preview?.applicable_limits.other_toxics],
  );
  const bodyKey = JSON.stringify([testType, at, detector, body]);
  useEffect(() => {
    if (!p) return;
    const h = setTimeout(() => {
      unwrap(api.POST("/api/v1/permits/{permit_id}/gas-tests/preview", { params: { path: { permit_id: p.id } }, body: { test_type: testType, tested_at: at || null, detector_id: detector || null, readings: body } }))
        .then((r) => {
          setPreview(r);
          setPreviewError(null);
        })
        .catch((e) => setPreviewError(e));
    }, 400);
    return () => clearTimeout(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bodyKey, p?.id]);
  if (pq.isError) return <ErrorState error={pq.error} onRetry={() => pq.refetch()} />;
  if (!p) return <LoadingState />;
  const appt = testers.data?.items.find((a) => a.id === tester);
  const testerIsMe = appt?.holder_user?.id === me.id;
  const needsTemp = p.work_types.includes("confined_space");
  const others = preview?.applicable_limits.other_toxics ?? [];
  const setRow = (i: number, patch: Partial<Reading>) => setReadings(rows.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  async function save() {
    setBusy(true);
    setError(null);
    try {
      const g = await unwrap(
        api.POST("/api/v1/permits/{permit_id}/gas-tests", {
          params: { path: { permit_id: permitId } },
          body: { test_type: testType, tested_at: at, tester_appointment_id: tester, detector_id: detector, readings: body, internal_temp_c: temp || null, tester_signature_png_base64: sig, note: note.trim() || null },
        }),
      );
      await refresh();
      toast.success(t("savedToast", { no: g.test_no }));
      router.push(`/gas-tests/${g.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_22rem]">
      <div className="flex flex-col gap-4">
        <Card>
          <CardContent className="grid gap-3 pt-5 sm:grid-cols-2">
            <p className="flex flex-wrap items-center gap-2 text-sm sm:col-span-2">
              <PermitNo p={p} /> <TypeChips types={p.work_types} short />
            </p>
            <FormField id="ge-type" label={t("testType")} required>
              <Select id="ge-type" value={testType} onChange={(e) => setType(e.target.value as S["GasTestType"])} data-testid="gas-type">
                {GAS_TEST_TYPES.map((x) => (
                  <option key={x} value={x}>
                    {te(`gasTestType.${x}`)}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField id="ge-at" label={t("testedAt")} required hint={t("backdateHint")}>
              <DateTimeInput id="ge-at" value={at} onChange={setAt} />
            </FormField>
            <FormField id="ge-tester" label={t("tester")} required hint={t("testerHint")}>
              <Select id="ge-tester" value={tester} onChange={(e) => setTester(e.target.value)} data-testid="gas-tester">
                <option value="">—</option>
                {(testers.data?.items ?? []).map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.appointment_no} · {a.holder_user ? userLabel(a.holder_user, "en") : (a.holder_worker?.full_name_en ?? a.holder_worker?.worker_no ?? "")}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField id="ge-det" label={t("detector")} required hint={t("detectorHint")}>
              <Select id="ge-det" value={detector} onChange={(e) => setDetector(e.target.value)} data-testid="gas-detector">
                <option value="">—</option>
                {(detectors.data?.items ?? []).map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.detector_no} · {d.make_model}
                    {d.bump_tested_today ? "" : ` · ${t("noBumpToday")}`}
                  </option>
                ))}
              </Select>
            </FormField>
            {needsTemp ? (
              <FormField id="ge-temp" label={t("internalTemp")} required>
                <DecimalInput id="ge-temp" value={temp} onChange={setTemp} />
              </FormField>
            ) : null}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("readings")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {needsTemp ? <p className="text-xs text-muted-foreground">{t("cseThreePoints")}</p> : null}
            {rows.map((r, i) => (
              <div key={i} className="flex flex-col gap-2 rounded-md border p-2" data-testid="gas-reading-row">
                <div className="flex items-center gap-2">
                  <Select aria-label={t("point")} className="w-44" value={r.point} onChange={(e) => setRow(i, { point: e.target.value as S["GasReadingPoint"] })}>
                    {GAS_READING_POINTS.map((x) => (
                      <option key={x} value={x}>
                        {te(`gasPoint.${x}`)}
                      </option>
                    ))}
                  </Select>
                  {rows.length > 1 ? (
                    <Button size="sm" variant="ghost" aria-label={t("removePoint")} onClick={() => setReadings(rows.filter((_, k) => k !== i))}>
                      <Trash2 aria-hidden />
                    </Button>
                  ) : null}
                </div>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  {STD.map((k) => {
                    const lim = preview ? limitText(preview.applicable_limits, k) : null;
                    return (
                      <FormField key={k} id={`gr-${i}-${k}`} label={t(`unit.${k}`)} hint={lim ? (
                          <>
                            {td("limit")} <bdi className="ltr tabular-nums">{lim}</bdi>
                          </>
                        ) : undefined}>
                        <DecimalInput
                          id={`gr-${i}-${k}`}
                          value={r[k]}
                          onChange={(v) => setRow(i, { [k]: v } as Partial<Reading>)}
                          data-testid={`reading-${k}`}
                        />
                      </FormField>
                    );
                  })}
                  {others.map((o) => (
                    <FormField key={o.gas} id={`gr-${i}-${o.gas}`} label={`${o.gas} (${o.unit})`}>
                      <DecimalInput id={`gr-${i}-${o.gas}`} value={r.other[o.gas] ?? ""} onChange={(v) => setRow(i, { other: { ...r.other, [o.gas]: v } })} />
                    </FormField>
                  ))}
                </div>
              </div>
            ))}
            <div>
              <Button size="sm" variant="outline" onClick={() => setReadings([...rows, { point: "at_work_point", o2_pct: "", lel_pct: "", h2s_ppm: "", co_ppm: "", other: {} }])} data-testid="add-point">
                <Plus aria-hidden />
                {t("addPoint")}
              </Button>
            </div>
            {preview ? (
              // Phones: the live result right under the readings (the full preview panel is further down).
              <div className="flex flex-col gap-1 lg:hidden" aria-live="polite">
                <GasVerdict result={preview.result} compact />
                {preview.fail_codes.length ? (
                  <ul className="flex flex-col gap-1 text-sm font-semibold text-danger">
                    {preview.fail_codes.map((c) => (
                      <li key={c} className="flex items-start gap-1.5">
                        <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
                        {te(`gasFailCode.${c}`)}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex flex-col gap-3 pt-5">
            {testerIsMe ? <p className="text-sm text-muted-foreground">{t("selfSign")}</p> : <SignaturePad id="ge-sig" label={t("testerSignature")} onChange={setSig} />}
            <FormField id="ge-note" label={t("note")}>
              <Textarea id="ge-note" value={note} onChange={(e) => setNote(e.target.value)} />
            </FormField>
          </CardContent>
        </Card>
        <MutationError error={error} />
        <div className="flex justify-end">
          <Button onClick={() => void save()} disabled={busy || !tester || !detector || (!testerIsMe && !sig) || (needsTemp && !temp)} data-testid="save-gas-test">
            {busy ? tc("saving") : t("save")}
          </Button>
        </div>
      </div>
      <aside className="flex flex-col gap-3 lg:sticky lg:top-4 lg:self-start" data-testid="gas-preview">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("preview")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {preview ? (
              <>
                <span data-testid="gas-result" data-result={preview.result}>
                  <GasVerdict result={preview.result} />
                </span>
                {preview.fail_codes.length ? (
                  <ul className="flex flex-col gap-1 text-sm font-semibold text-danger" data-testid="preview-fails">
                    {preview.fail_codes.map((c) => (
                      <li key={c} data-code={c} className="flex items-start gap-1.5">
                        <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
                        {te(`gasFailCode.${c}`)}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {preview.errors.length ? (
                  <ul className="text-sm text-warning" data-testid="preview-errors">
                    {preview.errors.map((c) => (
                      <li key={c} data-code={c}>
                        {terr.has(`code.${c}` as "code.UNKNOWN") ? terr(`code.${c}` as "code.UNKNOWN") : c}
                      </li>
                    ))}
                  </ul>
                ) : null}
                <LimitsText l={preview.applicable_limits} />
                <p className="text-xs font-medium">{t("worst")}</p>
                <WorstReading r={preview.worst} limits={preview.applicable_limits} />
                <p className="text-xs text-muted-foreground">{t("previewHint")}</p>
              </>
            ) : previewError ? (
              <MutationError error={previewError} />
            ) : (
              <LoadingState />
            )}
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}

/* ───────────── gas test detail ───────────── */

export function GasTestDetail({ id }: { id: string }) {
  const t = useTranslations("gas");
  const te = useTranslations("enums");
  const locale = useLocale();
  const me = useMeData();
  const q = useGasTest(id);
  const refresh = usePtwRefresh();
  const [supersede, setSupersede] = useState(false);
  const [reason, setReason] = useState("");
  const pid = useProjectId();
  const now = useNow(30_000);
  const { dateTime } = useFormatters(pid);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const g = q.data;
  const canRecord = can(me, "gas_test.record", pid);
  return (
    <div className="flex flex-col gap-5" data-testid="gas-test-detail">
      <div>
        <Breadcrumbs items={[{ label: t("title"), href: "/gas-tests" }, { label: g.test_no }]} />
        <PageHeader
          title={<bdi className="ltr">{g.test_no}</bdi>}
          description={te(`gasTestType.${g.test_type}`)}
          actions={
            <>
              <ResultBadge result={g.result} />
              {!g.superseded && canRecord ? (
                <Button variant="outline" onClick={() => setSupersede(true)} data-testid="supersede">
                  {t("supersede")}
                </Button>
              ) : null}
            </>
          }
        />
      </div>
      {g.superseded ? <Alert tone="warning">{t("supersededBecause", { reason: g.superseded_reason ?? "" })}</Alert> : null}
      {g.fail_codes.length ? <Alert tone="danger">{g.fail_codes.map((c) => te(`gasFailCode.${c}`)).join(", ")}</Alert> : null}
      {!g.superseded && g.result === "pass" ? (
        <div className="flex flex-wrap gap-3">
          {new Date(g.valid_for_start_until).getTime() > now ? <Countdown to={g.valid_for_start_until} label={t("validForStart")} testId="timer-gas-start" /> : null}
          {g.next_due_at ? <Countdown to={g.next_due_at} label={t("nextDue")} testId="timer-gas-retest" warnMinutes={15} /> : null}
        </div>
      ) : null}
      <Card>
        <CardContent className="pt-5">
          <FieldList>
            <FieldItem label={t("permit")}>
              <PermitNo p={g.permit} />
            </FieldItem>
            <FieldItem label={t("testedAt")}>
              <span className="[unicode-bidi:isolate]">{dateTime(g.tested_at)}</span>
            </FieldItem>
            <FieldItem label={t("shift")}>{g.shift_no ?? "—"}</FieldItem>
            <FieldItem label={t("tester")}>
              {g.tester.holder_name_en ? (locale === "ar" && g.tester.holder_name_ar ? g.tester.holder_name_ar : g.tester.holder_name_en) : "—"} · <bdi className="ltr">{g.tester.appointment_no}</bdi>
            </FieldItem>
            <FieldItem label={t("recordedBy")}>{userLabel(g.recorded_by, locale)}</FieldItem>
            <FieldItem label={t("detector")}>
              <Link href={`/gas-detectors/${g.detector.id}`} className="ltr text-primary hover:underline">
                {g.detector.detector_no}
              </Link>
            </FieldItem>
            <FieldItem label={t("validForStart")}>
              <span className="[unicode-bidi:isolate]">{dateTime(g.valid_for_start_until)}</span>
            </FieldItem>
            <FieldItem label={t("nextDue")}>
              <span className="ltr">{g.next_due_at ? dateTime(g.next_due_at) : "—"}</span>
            </FieldItem>
            {g.internal_temp_c ? (
              <FieldItem label={t("internalTemp")}>
                <bdi className="ltr">{g.internal_temp_c} °C</bdi>
              </FieldItem>
            ) : null}
            {g.note ? <FieldItem label={t("note")}>{g.note}</FieldItem> : null}
            <FieldItem label={t("signature")}>{g.tester_signature_attachment_id ? t("signed") : t("selfSigned")}</FieldItem>
          </FieldList>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("readings")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <LimitsText l={g.applicable_limits} />
          <ReadingsTable readings={g.readings} limits={g.applicable_limits} />
        </CardContent>
      </Card>
      <HistoryPanel entityType="gas_test" entityId={g.id} />
      {supersede ? (
        <StepDialog
          title={t("supersedeTitle")}
          description={t("supersedeHint")}
          confirmLabel={t("supersede")}
          disabled={reason.trim().length < 10}
          onClose={() => setSupersede(false)}
          onConfirm={async () => {
            await unwrap(api.POST("/api/v1/gas-tests/{gas_test_id}/supersede", { params: { path: { gas_test_id: g.id } }, body: { reason: reason.trim() } }));
            await refresh();
            toast.success(t("supersededToast"));
          }}
        >
          <FormField id="gs-reason" label={t("reason")} required hint={t("min10")}>
            <Textarea id="gs-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
          </FormField>
        </StepDialog>
      ) : null}
    </div>
  );
}

/* ───────────── detector register ───────────── */

export function DetectorListPage() {
  return <ProjectGate>{(p) => <DetectorList project={p} />}</ProjectGate>;
}

function DetectorList({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("gas");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const { date } = useFormatters(project.id);
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as S["DetectorStatus"][];
  const [creating, setCreating] = useState(false);
  const q = useDetectors(project.id, {
    status: status.length ? status : null,
    engagement_id: s.get("engagement_id") || null,
    calibration_due_within_days: s.getInt("due_within", 0) || null,
    q: s.get("q") || null,
    page,
    page_size: PAGE_SIZE,
  });
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("detectors")}
        description={t("detectorsHint")}
        actions={
          canWrite(me, "gas_detector.manage", project.id) ? (
            <Button onClick={() => setCreating(true)} data-testid="new-detector">
              <Plus aria-hidden />
              {t("newDetector")}
            </Button>
          ) : null
        }
      />
      <GasSubNav />
      <ListToolbar>
        <SearchFilter id="gd-q" value={s.get("q") ?? ""} onChange={(v) => s.set({ q: v })} placeholder={t("detectorSearch")} />
        <MultiSelect id="gd-status" label={tc("status")} options={DETECTOR_STATUSES.map((x) => ({ value: x, label: te(`detectorStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
        <SelectFilter id="gd-eng" label={tc("contractor")} value={s.get("engagement_id") ?? ""} onChange={(v) => s.set({ engagement_id: v })} options={opts.engagements.map((e) => ({ value: e.value, label: e.label }))} />
        <SelectFilter id="gd-due" label={t("calDue")} value={s.get("due_within") ?? ""} onChange={(v) => s.set({ due_within: v })} options={["7", "30"].map((d) => ({ value: d, label: t("withinDays", { n: Number(d) }) }))} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="detectors-table">
            <THead>
              <TR>
                <TH>{t("detector")}</TH>
                <TH>{tc("contractor")}</TH>
                <TH>{t("sensors")}</TH>
                <TH>{t("calDue")}</TH>
                <TH>{t("bumpToday")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((d) => (
                <TR key={d.id} data-testid="detector-row">
                  <TD label={t("detector")}>
                    <Link href={`/gas-detectors/${d.id}`} className="ltr font-medium text-primary hover:underline">
                      {d.detector_no}
                    </Link>
                    <span className="block text-xs text-muted-foreground">{d.make_model}</span>
                  </TD>
                  <TD label={tc("contractor")}>{d.engagement.short_code}</TD>
                  <TD label={t("sensors")}>{d.sensors.map((x) => te(`gasSensor.${x}`)).join(", ")}</TD>
                  <TD label={t("calDue")}>
                    <span className={cn("ltr", d.calibration_days_left < 0 ? "text-danger" : d.calibration_days_left <= 30 ? "text-warning" : undefined)}>{date(d.calibration_due_on)}</span>
                  </TD>
                  <TD label={t("bumpToday")}>{d.bump_tested_today ? tc("yes") : tc("no")}</TD>
                  <TD label={tc("status")}>
                    <StatusBadge status={d.status} label={te(`detectorStatus.${d.status}`)} />
                    {d.quarantine_reason ? <span className="flex items-center gap-1 text-xs text-danger font-medium"><OctagonAlert aria-hidden className="size-3.5 shrink-0" />{te(`quarantineReason.${d.quarantine_reason}`)}</span> : null}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={q.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState />
      )}
      {creating ? <DetectorCreateDialog project={project} onClose={() => setCreating(false)} /> : null}
    </div>
  );
}

function DetectorCreateDialog({ project, onClose }: { project: S["ProjectRead"]; onClose: () => void }) {
  const t = useTranslations("gas");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const router = useRouter();
  const opts = useProjectOptions(project.id);
  const [eng, setEng] = useState("");
  const [model, setModel] = useState("");
  const [serial, setSerial] = useState("");
  const [sensors, setSensors] = useState<S["GasSensor"][]>(["o2", "lel", "h2s", "co"]);
  const [lel, setLel] = useState<S["LelReferenceGas"] | "">("methane");
  const [calOn, setCalOn] = useState("");
  const [cert, setCert] = useState("");
  const [certDue, setCertDue] = useState("");
  const [calBody, setCalBody] = useState("");
  return (
    <StepDialog
      title={t("newDetector")}
      confirmLabel={tc("create")}
      wide
      disabled={!eng || !model.trim() || !serial.trim() || !sensors.length || !calOn || !cert.trim()}
      onClose={onClose}
      testId="save-detector"
      onConfirm={async () => {
        const d = await unwrap(
          api.POST("/api/v1/projects/{project_id}/gas-detectors", {
            params: { path: { project_id: project.id } },
            body: { engagement_id: eng, make_model: model.trim(), serial: serial.trim(), sensors, lel_reference_gas: lel || null, calibrated_on: calOn, calibration_cert_ref: cert.trim(), certificate_due_on: certDue || null, calibration_body_id: calBody || null },
          }),
        );
        toast.success(t("detectorCreated", { no: d.detector_no }));
        router.push(`/gas-detectors/${d.id}`);
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="dc-eng" label={tc("contractor")} required>
          <Select id="dc-eng" value={eng} onChange={(e) => setEng(e.target.value)}>
            <option value="">—</option>
            {opts.engagements.map((e) => (
              <option key={e.value} value={e.value}>
                {e.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="dc-model" label={t("makeModel")} required>
          <Input id="dc-model" value={model} onChange={(e) => setModel(e.target.value)} />
        </FormField>
        <FormField id="dc-serial" label={t("serial")} required>
          <Input id="dc-serial" className="ltr" value={serial} onChange={(e) => setSerial(e.target.value)} />
        </FormField>
        <FormField id="dc-lel" label={t("lelGas")}>
          <Select id="dc-lel" value={lel} onChange={(e) => setLel(e.target.value as S["LelReferenceGas"] | "")}>
            <option value="">—</option>
            {LEL_REFERENCE_GASES.map((x) => (
              <option key={x} value={x}>
                {te(`lelGas.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <CheckboxGroup id="dc-sensors" legend={t("sensors")} options={GAS_SENSORS.map((x) => ({ value: x, label: te(`gasSensor.${x}`) }))} value={sensors} onChange={(v) => setSensors(v as S["GasSensor"][])} className="sm:col-span-2" />
        <FormField id="dc-cal" label={t("calibratedOn")} required>
          <Input id="dc-cal" type="date" className="ltr" value={calOn} onChange={(e) => setCalOn(e.target.value)} />
        </FormField>
        <FormField id="dc-cert" label={t("certRef")} required>
          <Input id="dc-cert" className="ltr" value={cert} onChange={(e) => setCert(e.target.value)} />
        </FormField>
        <FormField id="dc-certdue" label={t("certDue")} hint={t("certDueHint")}>
          <Input id="dc-certdue" type="date" className="ltr" value={certDue} onChange={(e) => setCertDue(e.target.value)} />
        </FormField>
        <TpiSelect id="dc-calbody" label={t("calibrationBody")} value={calBody} onChange={setCalBody} kind="calibration_lab" projectId={project.id} />
      </div>
    </StepDialog>
  );
}

type DStep = "calibrate" | "bump" | "retire";

export function DetectorDetail({ id }: { id: string }) {
  const t = useTranslations("gas");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const me = useMeData();
  const q = useDetector(id);
  const bumps = useBumpTests(id);
  const [step, setStep] = useState<DStep | null>(null);
  const { date, dateTime } = useFormatters(q.data?.project_id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const d = q.data;
  const manage = canWrite(me, "gas_detector.manage", d.project_id);
  const record = canWrite(me, "gas_test.record", d.project_id) || manage;
  return (
    <div className="flex flex-col gap-5" data-testid="detector-detail" data-status={d.status}>
      <div>
        <Breadcrumbs items={[{ label: t("detectors"), href: "/gas-detectors" }, { label: d.detector_no }]} />
        <PageHeader
          title={<bdi className="ltr">{d.detector_no}</bdi>}
          description={d.make_model}
          actions={
            <span data-testid="detector-status" data-status={d.status}>
              <StatusBadge status={d.status} label={te(`detectorStatus.${d.status}`)} />
            </span>
          }
        />
      </div>
      {d.status !== "retired" ? (
        <div className="flex flex-wrap gap-2">
          {record ? (
            <Button onClick={() => setStep("bump")} data-testid="record-bump">
              {t("recordBump")}
            </Button>
          ) : null}
          {manage ? (
            <Button variant="outline" onClick={() => setStep("calibrate")} data-testid="record-calibration">
              {t("recordCalibration")}
            </Button>
          ) : null}
        </div>
      ) : null}
      {d.quarantine_reason ? (
        <Alert tone="danger">
          {t("quarantinedBecause", { reason: te(`quarantineReason.${d.quarantine_reason}`) })}
          {d.quarantined_at ? <span className="[unicode-bidi:isolate] ms-1">{dateTime(d.quarantined_at)}</span> : null}
        </Alert>
      ) : null}
      <Card>
        <CardContent className="pt-5">
          <FieldList>
            <FieldItem label={tc("contractor")}>{d.engagement.short_code}</FieldItem>
            <FieldItem label={t("serial")} ltr>
              {d.serial}
            </FieldItem>
            <FieldItem label={t("sensors")}>{d.sensors.map((x) => te(`gasSensor.${x}`)).join(", ")}</FieldItem>
            <FieldItem label={t("lelGas")}>{d.lel_reference_gas ? te(`lelGas.${d.lel_reference_gas}`) : "—"}</FieldItem>
            <FieldItem label={t("calibratedOn")}>
              <span className="[unicode-bidi:isolate]">{date(d.calibrated_on)}</span> · <bdi className="ltr">{d.calibration_cert_ref}</bdi>
            </FieldItem>
            <FieldItem label={t("calibrationBody")}>{d.calibration_body ? <TpiLabel tpi={d.calibration_body} /> : "—"}</FieldItem>
            <FieldItem label={t("calDue")}>
              <span className={cn("ltr", d.calibration_days_left < 0 ? "text-danger" : d.calibration_days_left <= 30 ? "text-warning" : undefined)}>{date(d.calibration_due_on)}</span>{" "}
              <span className="text-xs text-muted-foreground">{t("daysLeft", { n: d.calibration_days_left })}</span>
            </FieldItem>
            <FieldItem label={t("bumpToday")}>{d.bump_tested_today ? tc("yes") : tc("no")}</FieldItem>
            <FieldItem label={t("livePermits")}>
              {d.live_permits.length
                ? d.live_permits.map((p) => (
                    <span key={p.id} className="me-2">
                      <PermitNo p={p} />
                    </span>
                  ))
                : "—"}
            </FieldItem>
          </FieldList>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("bumpTests")}</CardTitle>
        </CardHeader>
        <CardContent>
          {bumps.data?.items.length ? (
            <ul className="flex flex-col divide-y rounded-md border text-sm" data-testid="bump-tests">
              {bumps.data.items.map((b) => (
                <li key={b.id} className="flex flex-wrap items-center gap-2 p-2">
                  <StatusBadge status={b.result === "pass" ? "ok" : "failed"} label={te(`gasResult.${b.result}`)} />
                  <span className="[unicode-bidi:isolate]">{dateTime(b.tested_at)}</span>
                  <span className="text-xs text-muted-foreground">
                    {b.sensors_responded.map((x) => te(`gasSensor.${x}`)).join(", ")} · {b.tested_by_user ? userLabel(b.tested_by_user, locale) : (b.tested_by_worker?.worker_no ?? "")} · {t("lot")} <bdi className="ltr">{b.gas_cylinder_lot}</bdi>
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">{t("noBumps")}</p>
          )}
        </CardContent>
      </Card>
      <HistoryPanel entityType="gas_detector" entityId={d.id} projectId={d.project_id} />
      {step ? <DetectorStepDialog d={d} step={step} onClose={() => setStep(null)} /> : null}
      {manage && d.status !== "retired" ? (
        <RecordActions className="mt-0">
          <Button variant="destructive-outline" onClick={() => setStep("retire")} data-testid="retire-detector">
            {t("retire")}
          </Button>
        </RecordActions>
      ) : null}
    </div>
  );
}

function DetectorStepDialog({ d, step, onClose }: { d: S["DetectorRead"]; step: DStep; onClose: () => void }) {
  const t = useTranslations("gas");
  const te = useTranslations("enums");
  const refresh = usePtwRefresh();
  const path = { params: { path: { detector_id: d.id } } };
  const [calOn, setCalOn] = useState("");
  const [cert, setCert] = useState("");
  const [certDue, setCertDue] = useState("");
  const [at, setAt] = useState(nowIso());
  const [result, setResult] = useState<S["BumpTestResult"]>("pass");
  const [sensors, setSensors] = useState<S["GasSensor"][]>(d.sensors);
  const [lot, setLot] = useState("");
  const [lotExp, setLotExp] = useState("");
  const [reason, setReason] = useState("");
  let disabled = false;
  let body: React.ReactNode;
  let run: () => Promise<unknown>;
  if (step === "calibrate") {
    disabled = !calOn || !cert.trim();
    run = async () => {
      await unwrap(api.POST("/api/v1/gas-detectors/{detector_id}/calibrations", { ...path, body: { calibrated_on: calOn, calibration_cert_ref: cert.trim(), certificate_due_on: certDue || null } }));
      await refresh();
    };
    body = (
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="cal-on" label={t("calibratedOn")} required>
          <Input id="cal-on" type="date" className="ltr" value={calOn} onChange={(e) => setCalOn(e.target.value)} />
        </FormField>
        <FormField id="cal-cert" label={t("certRef")} required>
          <Input id="cal-cert" className="ltr" value={cert} onChange={(e) => setCert(e.target.value)} />
        </FormField>
        <FormField id="cal-due" label={t("certDue")} hint={t("certDueHint")}>
          <Input id="cal-due" type="date" className="ltr" value={certDue} onChange={(e) => setCertDue(e.target.value)} />
        </FormField>
      </div>
    );
  } else if (step === "bump") {
    disabled = !lot.trim() || !lotExp;
    run = async () => {
      await unwrap(api.POST("/api/v1/gas-detectors/{detector_id}/bump-tests", { ...path, body: { tested_at: at, result, sensors_responded: sensors, gas_cylinder_lot: lot.trim(), gas_cylinder_expiry: lotExp } }));
      await refresh();
    };
    body = (
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="bt-at" label={t("testedAt")} required>
          <DateTimeInput id="bt-at" value={at} onChange={setAt} />
        </FormField>
        <FormField id="bt-result" label={t("result")} required>
          <Select id="bt-result" value={result} onChange={(e) => setResult(e.target.value as S["BumpTestResult"])} data-testid="bump-result">
            {(["pass", "fail"] as const).map((x) => (
              <option key={x} value={x}>
                {te(`gasResult.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <CheckboxGroup id="bt-sensors" legend={t("sensorsResponded")} options={d.sensors.map((x) => ({ value: x, label: te(`gasSensor.${x}`) }))} value={sensors} onChange={(v) => setSensors(v as S["GasSensor"][])} className="sm:col-span-2" />
        <FormField id="bt-lot" label={t("lot")} required>
          <Input id="bt-lot" className="ltr" value={lot} onChange={(e) => setLot(e.target.value)} />
        </FormField>
        <FormField id="bt-exp" label={t("lotExpiry")} required>
          <Input id="bt-exp" type="date" className="ltr" value={lotExp} onChange={(e) => setLotExp(e.target.value)} />
        </FormField>
        {result === "fail" ? <Alert tone="warning" className="sm:col-span-2">{t("bumpFailHint")}</Alert> : null}
      </div>
    );
  } else {
    disabled = reason.trim().length < 10;
    run = async () => {
      await unwrap(api.POST("/api/v1/gas-detectors/{detector_id}/retire", { ...path, body: { reason: reason.trim() } }));
      await refresh();
    };
    body = (
      <FormField id="rt-reason" label={t("reason")} required hint={t("min10")}>
        <Textarea id="rt-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
      </FormField>
    );
  }
  const titles: Record<DStep, string> = { calibrate: t("recordCalibration"), bump: t("recordBump"), retire: t("retire") };
  return (
    <StepDialog title={titles[step]} confirmLabel={titles[step]} destructive={step === "retire"} disabled={disabled} onConfirm={run} onClose={onClose} wide testId="detector-step-confirm">
      {body}
    </StepDialog>
  );
}
