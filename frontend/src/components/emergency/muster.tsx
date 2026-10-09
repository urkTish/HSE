"use client";
import { useQuery } from "@tanstack/react-query";
import { Camera, Check, Plus, Printer, ScanLine, Trash2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FormField } from "@/components/common/form-field";
import { PageHeader } from "@/components/common/page-header";
import { ProjectById } from "@/components/common/project-gate";
import { useProjectOptions } from "@/components/common/pickers";
import { ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Code, StepDialog, WorkerLabel } from "@/components/access/common";
import { CameraScanner } from "@/components/gate/gate-check";
import { Link } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { ek, useAssemblyPoints, useEmergencyRefresh, useMuster } from "@/lib/api/emergency";
import { useFormatters } from "@/lib/use-formatters";
import { cn } from "@/lib/utils";
import { AnswerButtons, EmReasonDialog, EntryStateBadge, Minutes, MusterStatusBadge, PrivacyNote, useEmCaps, useEmRef } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];
type Muster = S["MusterRead"];
type Entry = S["MusterEntryRead"];
type Reason = S["ResolutionReason"];

const LIVE: readonly S["MusterStatus"][] = ["open", "reconciled"];

/* ═════════════ muster / headcount (§3.6, MU-1…MU-9): phone first ═════════════ */

export function MusterPage({ id }: { id: string }) {
  const q = useMuster(id, { live: true });
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return null;
  const m = q.data;
  return <ProjectById id={m.project_id}>{(p) => <MusterView project={p} m={m} />}</ProjectById>;
}

function MusterView({ project, m }: { project: Project; m: Muster }) {
  const t = useTranslations("emergency.muster");
  const te = useTranslations("enums");
  const caps = useEmCaps(project.id);
  const opts = useProjectOptions(project.id);
  const { label } = useEmRef();
  const [voiding, setVoiding] = useState(false);
  const live = LIVE.includes(m.status);
  const canRun = caps.run && live;
  const source = m.source_type === "drill" ? `/drills/${m.source_id}` : `/emergency-events/${m.source_id}`;
  const site = opts.sites.find((s) => s.value === m.site_id)?.code ?? "";
  const outstanding = m.mode === "roll" ? m.unaccounted : m.count_rows.reduce((n, r) => n + r.outstanding, 0);
  return (
    <div className="mx-auto max-w-3xl">
      <Breadcrumbs items={[{ href: m.source_type === "drill" ? "/drills" : "/emergency-events", label: t(m.source_type === "drill" ? "drills" : "events") }, { label: m.muster_no }]} />
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            <Code>{m.muster_no}</Code>
            <MusterStatusBadge status={m.status} />
          </span>
        }
        description={
          <span className="flex flex-wrap items-center gap-x-2">
            <Code>{site}</Code>
            <span>· {te(`emMusterMode.${m.mode}`)}</span>
            <Link href={source} className="text-primary hover:underline" data-testid="muster-source">
              {t(m.source_type === "drill" ? "openDrill" : "openEvent")}
            </Link>
          </span>
        }
        actions={
          <div className="flex flex-wrap gap-2">
            {canRun && m.status === "open" && m.mode === "roll" ? (
              <Button variant="outline" asChild>
                <Link href={`/musters/${m.id}/sheet`} data-testid="muster-sheet">
                  <Printer aria-hidden />
                  {t("sheet")}
                </Link>
              </Button>
            ) : null}
            {caps.void && m.status !== "voided" ? (
              <Button variant="destructive-outline" onClick={() => setVoiding(true)} data-testid="muster-void">
                {t("void")}
              </Button>
            ) : null}
          </div>
        }
      />
      <Counters m={m} outstanding={outstanding} />
      {m.status === "reconciled" || m.status === "closed" ? (
        <Alert tone={outstanding ? "warning" : "success"} className="mb-3" data-testid="muster-done">
          {outstanding ? t("closedOutstanding", { n: outstanding }) : t("reconciled")}
        </Alert>
      ) : null}
      {Object.keys(m.by_reason).length ? (
        <p className="mb-3 flex flex-wrap gap-2 text-sm" data-testid="muster-reasons">
          {Object.entries(m.by_reason).map(([k, n]) => (
            <Badge key={k} tone={k === "found_on_site" ? "danger" : "neutral"}>
              {label("resolution_reasons", k)}: <bdi className="ltr tabular-nums">{n}</bdi>
            </Badge>
          ))}
        </p>
      ) : null}
      {m.mode === "roll" ? (
        <>
          {canRun ? <ScanPanel project={project} m={m} /> : null}
          {m.entries ? <RollList project={project} m={m} canRun={canRun} /> : <PrivacyNote testId="muster-privacy">{t("namesHidden")}</PrivacyNote>}
        </>
      ) : (
        <CountRows project={project} m={m} canRun={canRun} />
      )}
      {voiding ? (
        <EmReasonDialog
          title={t("voidTitle", { no: m.muster_no })}
          confirmLabel={t("void")}
          onConfirm={(reason) => unwrap(api.POST("/api/v1/musters/{muster_id}/void", { params: { path: { muster_id: m.id } }, body: { reason } }))}
          onClose={() => setVoiding(false)}
        />
      ) : null}
    </div>
  );
}

function Counters({ m, outstanding }: { m: Muster; outstanding: number }) {
  const t = useTranslations("emergency.muster");
  const cell = (key: "expected" | "accounted" | "missing" | "resolved", n: number | string, tone?: "danger" | "success") => (
    <div className={cn("rounded-lg border bg-surface p-3", tone === "danger" && "border-danger/60", tone === "success" && "border-success/60")} data-testid={`mc-${key}`} data-n={n}>
      <p className="text-xs text-muted-foreground">{t(`c_${key}`)}</p>
      <p className={cn("text-3xl font-semibold tabular-nums", tone === "danger" && "text-danger")}>
        <bdi className="ltr">{n}</bdi>
      </p>
    </div>
  );
  const expected = m.mode === "roll" ? m.expected : m.count_rows.reduce((n, r) => n + r.expected, 0);
  const accounted = m.mode === "roll" ? m.accounted : m.count_rows.reduce((n, r) => n + r.accounted, 0);
  const resolved = m.mode === "roll" ? m.resolved : m.count_rows.reduce((n, r) => n + r.resolved.reduce((s, x) => s + Number(x.count ?? 0), 0), 0);
  return (
    <div className="mb-3 flex flex-col gap-2" data-testid="muster-counters">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {cell("expected", expected)}
        {cell("accounted", accounted, "success")}
        {cell("missing", outstanding, outstanding ? "danger" : undefined)}
        {cell("resolved", resolved)}
      </div>
      <p className="flex flex-wrap gap-x-4 text-sm text-muted-foreground">
        {m.mode === "roll" ? (
          <span data-testid="mc-extras">
            {t("extras")}: <bdi className="ltr tabular-nums">{m.extras}</bdi>
          </span>
        ) : null}
        {m.visitors_expected !== null ? (
          <span data-testid="mc-visitors">
            {t("visitors")}: <bdi className="ltr tabular-nums">{`${m.visitors_accounted ?? 0}/${m.visitors_expected}`}</bdi>
          </span>
        ) : null}
        <span>
          {t("headcountTime")}: <Minutes v={m.headcount_min} testId="mc-headcount-min" />
        </span>
      </p>
    </div>
  );
}

function ScanPanel({ project, m }: { project: Project; m: Muster }) {
  const t = useTranslations("emergency.muster");
  const refresh = useEmergencyRefresh();
  const aps = useAssemblyPoints(project.id, { site_id: m.site_id });
  const apOptions = (aps.data?.items ?? []).filter((a) => m.ap_ids.length === 0 || m.ap_ids.includes(a.id));
  const [ap, setAp] = useState("");
  const [camera, setCamera] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [last, setLast] = useState<Entry | null>(null);
  const scan = async (payload: string) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const e = await unwrap(api.POST("/api/v1/musters/{muster_id}/scan", { params: { path: { muster_id: m.id } }, body: { payload: payload.trim(), ap_id: ap || null } }));
      setLast(e);
      setTyped("");
      toast.success(e.extra ? t("scannedExtra") : t("scanned"));
      await refresh();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card className="mb-3" data-testid="muster-scan">
      <CardContent className="flex flex-col gap-3 p-4">
        <FormField id="ms-ap" label={t("ap")}>
          <Select id="ms-ap" value={ap} onChange={(e) => setAp(e.target.value)} data-testid="ms-ap" className="min-h-11">
            <option value="">{t("apAny")}</option>
            {apOptions.map((a) => (
              <option key={a.id} value={a.id}>
                {a.ap_code}
              </option>
            ))}
          </Select>
        </FormField>
        <Button size="lg" className="min-h-14 text-base" onClick={() => setCamera((v) => !v)} data-testid="ms-camera">
          <Camera aria-hidden />
          {t("scanCard")}
        </Button>
        {camera ? <CameraScanner onResult={(p) => void scan(p)} onClose={() => setCamera(false)} paused={busy} /> : null}
        <div className="flex gap-2">
          <Input className="ltr min-h-11" placeholder="HSE2:AC:…" value={typed} onChange={(e) => setTyped(e.target.value)} onKeyDown={(e) => e.key === "Enter" && typed.trim() && void scan(typed)} aria-label={t("payload")} data-testid="ms-payload" />
          <Button variant="outline" className="min-h-11" disabled={!typed.trim() || busy} onClick={() => void scan(typed)} data-testid="ms-payload-go">
            <ScanLine aria-hidden />
            {t("record")}
          </Button>
        </div>
        <MutationError error={error} />
        {last ? (
          <p className="flex flex-wrap items-center gap-2 text-sm" data-testid="ms-last" data-extra={last.extra ? "yes" : "no"}>
            <Check aria-hidden className="size-4 text-success" />
            {last.worker ? <WorkerLabel w={last.worker} /> : null}
            {last.engagement_code ? <Code className="text-xs">{last.engagement_code}</Code> : null}
            {last.extra ? <Badge tone="warning">{t("extra")}</Badge> : null}
          </p>
        ) : null}
        <p className="text-xs text-muted-foreground">{t("scanHint")}</p>
      </CardContent>
    </Card>
  );
}

type RollFilter = "missing" | "accounted" | "resolved" | "all";

function RollList({ project, m, canRun }: { project: Project; m: Muster; canRun: boolean }) {
  const t = useTranslations("emergency.muster");
  const te = useTranslations("enums");
  const { dateTime } = useFormatters(project.id);
  const refresh = useEmergencyRefresh();
  const [filter, setFilter] = useState<RollFilter>("missing");
  const [search, setSearch] = useState("");
  const [resolve, setResolve] = useState<Entry | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const entries = useMemo(() => m.entries ?? [], [m.entries]);
  const counts = useMemo(
    () => ({
      missing: entries.filter((e) => e.state === "expected" || e.state === "unaccounted").length,
      accounted: entries.filter((e) => e.state === "accounted").length,
      resolved: entries.filter((e) => e.state === "resolved").length,
      all: entries.length,
    }),
    [entries],
  );
  const needle = search.trim().toLowerCase();
  const shown = entries
    .filter((e) => (filter === "all" ? true : filter === "missing" ? e.state === "expected" || e.state === "unaccounted" : e.state === filter))
    .filter((e) => !needle || [e.worker?.worker_no, e.worker?.full_name_en, e.worker?.full_name_ar, e.engagement_code].some((x) => x?.toLowerCase().includes(needle)))
    .slice(0, 300);
  const tick = async (e: Entry) => {
    setBusy(e.id);
    try {
      await unwrap(api.POST("/api/v1/musters/{muster_id}/entries/{entry_id}/tick", { params: { path: { muster_id: m.id, entry_id: e.id } } }));
      await refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };
  return (
    <Card data-testid="muster-roll">
      <CardHeader className="gap-3">
        <CardTitle>{t("roll")}</CardTitle>
        <div role="tablist" className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {(["missing", "accounted", "resolved", "all"] as const).map((f) => (
            <Button key={f} role="tab" aria-selected={filter === f} variant={filter === f ? "default" : "outline"} className="min-h-11" onClick={() => setFilter(f)} data-testid={`roll-${f}`}>
              {t(`f_${f}`)} <bdi className="ltr tabular-nums">({counts[f]})</bdi>
            </Button>
          ))}
        </div>
        <Input className="min-h-11" placeholder={t("search")} aria-label={t("search")} value={search} onChange={(e) => setSearch(e.target.value)} data-testid="roll-search" />
      </CardHeader>
      <CardContent className="p-0">
        {shown.length ? (
          <ul className="divide-y">
            {shown.map((e) => (
              <li key={e.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2" data-testid="roll-entry" data-state={e.state} data-worker={e.worker?.worker_no ?? ""}>
                <span className="flex min-w-0 flex-col gap-0.5">
                  <span className="flex flex-wrap items-center gap-2">
                    {e.worker ? <WorkerLabel w={e.worker} /> : "—"}
                    {e.extra ? <Badge tone="warning">{t("extra")}</Badge> : null}
                  </span>
                  <span className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    {e.engagement_code ? <Code>{e.engagement_code}</Code> : null}
                    <EntryStateBadge state={e.state} />
                    {e.at ? <span>{dateTime(e.at)}</span> : null}
                    {e.method ? <span>{te(`emEntryMethod.${e.method}`)}</span> : null}
                    {e.resolution_reason ? <ReasonLabel r={e.resolution_reason} /> : null}
                  </span>
                </span>
                {canRun && (e.state === "expected" || e.state === "unaccounted") ? (
                  <span className="flex gap-2">
                    <Button className="min-h-11" onClick={() => void tick(e)} disabled={busy === e.id} data-testid="roll-tick">
                      <Check aria-hidden />
                      {t("tick")}
                    </Button>
                    <Button className="min-h-11" variant="outline" onClick={() => setResolve(e)} data-testid="roll-resolve">
                      {t("resolve")}
                    </Button>
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="px-4 py-6 text-center text-sm text-muted-foreground" data-testid="roll-empty">
            {filter === "missing" ? t("noneMissing") : t("noEntries")}
          </p>
        )}
      </CardContent>
      {resolve ? <ResolveDialog m={m} e={resolve} onClose={() => setResolve(null)} /> : null}
    </Card>
  );
}

function ReasonLabel({ r }: { r: string }) {
  const { label } = useEmRef();
  return <span data-testid="entry-reason">{label("resolution_reasons", r)}</span>;
}

function useReasonOptions() {
  const { items, label } = useEmRef();
  return items("resolution_reasons").map((x) => ({ value: x.code as Reason, label: label("resolution_reasons", x.code) }));
}

function ResolveDialog({ m, e, onClose }: { m: Muster; e: Entry; onClose: () => void }) {
  const t = useTranslations("emergency.muster");
  const refresh = useEmergencyRefresh();
  const options = useReasonOptions();
  const [reason, setReason] = useState<Reason | null>(null);
  const [note, setNote] = useState("");
  const noteNeeded = reason === "record_error" ? 10 : 0;
  return (
    <StepDialog
      title={t("resolveTitle", { no: e.worker?.worker_no ?? "" })}
      description={t("resolveHint")}
      confirmLabel={t("resolve")}
      testId="resolve-confirm"
      disabled={!reason || note.trim().length < noteNeeded}
      warning={reason === "found_on_site" ? (m.source_type === "drill" ? t("foundDrill") : t("foundEvent")) : undefined}
      onConfirm={async () => {
        await unwrap(api.POST("/api/v1/musters/{muster_id}/entries/{entry_id}/resolve", { params: { path: { muster_id: m.id, entry_id: e.id } }, body: { reason: reason as Reason, note: note.trim() || null } }));
        await refresh();
      }}
      onClose={onClose}
    >
      <div className="[&_[role=radiogroup]]:grid-cols-1 sm:[&_[role=radiogroup]]:grid-cols-2">
        <AnswerButtons value={reason} options={options} onChange={setReason} testId="rs-reason" danger={["found_on_site"]} />
      </div>
      <FormField id="rs-note" label={t("note")} required={noteNeeded > 0} hint={noteNeeded ? t("noteMin", { n: note.trim().length }) : t("noNames")} className="mt-3">
        <Textarea id="rs-note" value={note} onChange={(x) => setNote(x.target.value)} maxLength={500} data-testid="rs-note" />
      </FormField>
    </StepDialog>
  );
}

/* ── count mode (MU-3) ── */

type Res = { engagement_id: string; reason: Reason; count: string; note: string };

function CountRows({ project, m, canRun }: { project: Project; m: Muster; canRun: boolean }) {
  const t = useTranslations("emergency.muster");
  const opts = useProjectOptions(project.id);
  const { label } = useEmRef();
  const reasons = useReasonOptions();
  const refresh = useEmergencyRefresh();
  const engs = opts.engagements.filter((e) => e.siteIds.includes(m.site_id) || m.count_rows.some((r) => r.engagement_id === e.value));
  const rowOf = (id: string) => m.count_rows.find((r) => r.engagement_id === id);
  const [rows, setRows] = useState<Record<string, { expected: string; accounted: string }>>(() =>
    Object.fromEntries(m.count_rows.map((r) => [r.engagement_id, { expected: String(r.expected), accounted: String(r.accounted) }])),
  );
  const [res, setRes] = useState<Res[]>([]);
  const [visE, setVisE] = useState(m.visitors_expected !== null ? String(m.visitors_expected) : "");
  const [visA, setVisA] = useState(m.visitors_accounted !== null ? String(m.visitors_accounted) : "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const val = (id: string, k: "expected" | "accounted") => rows[id]?.[k] ?? "";
  const set = (id: string, k: "expected" | "accounted", v: string) => setRows({ ...rows, [id]: { expected: val(id, "expected"), accounted: val(id, "accounted"), [k]: v } });
  const changed = Object.entries(rows).filter(([id, r]) => {
    const o = rowOf(id);
    return r.expected !== "" && r.accounted !== "" && (!o || String(o.expected) !== r.expected || String(o.accounted) !== r.accounted);
  });
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await unwrap(
        api.PUT("/api/v1/musters/{muster_id}/counts", {
          params: { path: { muster_id: m.id } },
          body: {
            rows: changed.map(([id, r]) => ({ engagement_id: id, expected: Number(r.expected), accounted: Number(r.accounted) })),
            resolutions: res.map((x) => ({ engagement_id: x.engagement_id, reason: x.reason, count: Number(x.count), note: x.note.trim() || null })),
            visitors_expected: visE === "" ? null : Number(visE),
            visitors_accounted: visA === "" ? null : Number(visA),
          },
        }),
      );
      setRes([]);
      await refresh();
      toast.success(t("countsSaved"));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  const outstandingEngs = m.count_rows.filter((r) => r.outstanding > 0);
  return (
    <Card data-testid="muster-counts">
      <CardHeader>
        <CardTitle>{t("counts")}</CardTitle>
        <p className="text-sm text-muted-foreground">{t("countsHint")}</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 p-4 pt-0">
        <ul className="flex flex-col gap-2">
          {engs.map((e) => {
            const r = rowOf(e.value);
            return (
              <li key={e.value} className="grid grid-cols-[1fr_5rem_5rem] items-end gap-2 rounded-md border p-2" data-testid="count-row" data-eng={e.code} data-outstanding={r?.outstanding ?? ""}>
                <span className="flex flex-col">
                  <Code className="font-medium">{e.code}</Code>
                  {r ? (
                    <span className="text-xs text-muted-foreground">
                      {r.outstanding ? <span className="font-semibold text-danger">{t("outstanding", { n: r.outstanding })}</span> : t("allAccounted")}
                      {r.resolved.map((x, i) => (
                        <span key={i} className="block">
                          {label("resolution_reasons", String(x.reason ?? ""))}: <bdi className="ltr">{String(x.count ?? "")}</bdi>
                        </span>
                      ))}
                    </span>
                  ) : null}
                </span>
                <FormField id={`cr-e-${e.code}`} label={t("expected")}>
                  <Input id={`cr-e-${e.code}`} className="min-h-11 tabular-nums" type="number" inputMode="numeric" min={0} value={val(e.value, "expected")} disabled={!canRun} onChange={(x) => set(e.value, "expected", x.target.value)} data-testid="cr-expected" />
                </FormField>
                <FormField id={`cr-a-${e.code}`} label={t("accounted")}>
                  <Input id={`cr-a-${e.code}`} className="min-h-11 tabular-nums" type="number" inputMode="numeric" min={0} value={val(e.value, "accounted")} disabled={!canRun} onChange={(x) => set(e.value, "accounted", x.target.value)} data-testid="cr-accounted" />
                </FormField>
              </li>
            );
          })}
        </ul>
        {canRun ? (
          <>
            {res.map((x, i) => (
              <div key={i} className="flex flex-col gap-2 rounded-md border p-2" data-testid="count-resolution">
                <div className="grid grid-cols-[1fr_5rem_auto] items-end gap-2">
                  <FormField id={`rz-e-${i}`} label={t("engagement")}>
                    <Select id={`rz-e-${i}`} className="min-h-11" value={x.engagement_id} onChange={(e) => setRes(res.map((y, j) => (j === i ? { ...y, engagement_id: e.target.value } : y)))} data-testid="rz-engagement">
                      {outstandingEngs.map((r) => (
                        <option key={r.engagement_id} value={r.engagement_id}>
                          {r.engagement_code}
                        </option>
                      ))}
                    </Select>
                  </FormField>
                  <FormField id={`rz-n-${i}`} label={t("count")}>
                    <Input id={`rz-n-${i}`} className="min-h-11" type="number" inputMode="numeric" min={1} value={x.count} onChange={(e) => setRes(res.map((y, j) => (j === i ? { ...y, count: e.target.value } : y)))} data-testid="rz-count" />
                  </FormField>
                  <Button variant="ghost" className="min-h-11" aria-label={t("remove")} onClick={() => setRes(res.filter((_, j) => j !== i))}>
                    <Trash2 aria-hidden />
                  </Button>
                </div>
                <div className="[&_[role=radiogroup]]:grid-cols-1 sm:[&_[role=radiogroup]]:grid-cols-2">
                  <AnswerButtons value={x.reason} options={reasons} onChange={(v) => setRes(res.map((y, j) => (j === i ? { ...y, reason: v } : y)))} testId={`rz-reason-${i}`} danger={["found_on_site"]} />
                </div>
                <Input placeholder={t("note")} aria-label={t("note")} value={x.note} onChange={(e) => setRes(res.map((y, j) => (j === i ? { ...y, note: e.target.value } : y)))} maxLength={500} data-testid="rz-note" />
              </div>
            ))}
            {outstandingEngs.length ? (
              <Button variant="outline" className="min-h-11 w-fit" onClick={() => setRes([...res, { engagement_id: outstandingEngs[0]?.engagement_id ?? "", reason: "off_site_confirmed", count: "1", note: "" }])} data-testid="rz-add">
                <Plus aria-hidden />
                {t("addResolution")}
              </Button>
            ) : null}
            <div className="grid grid-cols-2 gap-2">
              <FormField id="cv-ve" label={t("visitorsExpected")}>
                <Input id="cv-ve" className="min-h-11" type="number" inputMode="numeric" min={0} value={visE} onChange={(e) => setVisE(e.target.value)} />
              </FormField>
              <FormField id="cv-va" label={t("visitorsAccounted")}>
                <Input id="cv-va" className="min-h-11" type="number" inputMode="numeric" min={0} value={visA} onChange={(e) => setVisA(e.target.value)} />
              </FormField>
            </div>
            <MutationError error={error} />
            <Button size="lg" className="min-h-12" onClick={() => void save()} disabled={busy || (!changed.length && !res.length && visE === String(m.visitors_expected ?? "") && visA === String(m.visitors_accounted ?? ""))} data-testid="counts-save">
              {t("saveCounts")}
            </Button>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}

/* ═════════════ printable muster sheet (MU-9, audited export) ═════════════ */

type SheetWorker = { worker_no: string; name_en?: string | null; name_ar?: string | null };

export function MusterSheetPage({ id }: { id: string }) {
  const ar = useLocale() === "ar";
  const m = useMuster(id);
  // Each fetch is an audited export: fetch once, never refetch in the background.
  const q = useQuery({
    queryKey: [...ek.muster(id), "sheet"],
    queryFn: () => unwrap(api.GET("/api/v1/musters/{muster_id}/sheet", { params: { path: { muster_id: id } } })),
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    retry: false,
  });
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} />;
  if (!q.data) return null;
  const s = q.data;
  return (
    <ProjectById id={m.data?.project_id ?? ""}>
      {(p) => (
        <SheetBody projectId={p.id} muster={s.muster_no} at={s.generated_at} groups={s.engagements as { engagement_code: string; workers: SheetWorker[] }[]} ar={ar} back={`/musters/${id}`} />
      )}
    </ProjectById>
  );
}

function SheetBody({
  projectId,
  muster,
  at,
  groups,
  ar,
  back,
}: {
  projectId: string;
  muster: string;
  at: string;
  groups: { engagement_code: string; workers: SheetWorker[] }[];
  ar: boolean;
  back: string;
}) {
  const t = useTranslations("emergency.muster");
  const tc = useTranslations("common");
  const { dateTime } = useFormatters(projectId);
  return (
    <div className="mx-auto max-w-3xl" data-testid="muster-sheet-page">
      <div className="mb-4 flex gap-2 print:hidden">
        <Button onClick={() => window.print()} data-testid="do-print">
          <Printer aria-hidden />
          {tc("print")}
        </Button>
        <Button variant="outline" asChild>
          <Link href={back}>{tc("back")}</Link>
        </Button>
      </div>
      <h1 className="text-xl font-semibold">{t("sheetTitle", { no: muster })}</h1>
      <p className="mb-1 text-sm text-muted-foreground">{t("sheetGenerated", { at: dateTime(at) })}</p>
      <p className="mb-4 text-xs text-muted-foreground">{t("sheetConfidential")}</p>
      {groups.map((g) => (
        <section key={g.engagement_code} className="mb-6 break-inside-avoid" data-testid="sheet-group" data-eng={g.engagement_code}>
          <h2 className="mb-2 font-semibold">
            <Code>{g.engagement_code}</Code> · <bdi className="ltr">{g.workers.length}</bdi>
          </h2>
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr>
                <th className="w-10 border px-2 py-1 text-start">#</th>
                <th className="border px-2 py-1 text-start">{t("workerNo")}</th>
                <th className="border px-2 py-1 text-start">{t("name")}</th>
                <th className="w-20 border px-2 py-1 text-center">{t("present")}</th>
              </tr>
            </thead>
            <tbody>
              {g.workers.map((w, i) => (
                <tr key={w.worker_no} data-testid="sheet-row">
                  <td className="border px-2 py-1 tabular-nums">{i + 1}</td>
                  <td className="border px-2 py-1">
                    <Code>{w.worker_no}</Code>
                  </td>
                  <td className="border px-2 py-1" dir="auto">
                    {(ar ? w.name_ar || w.name_en : w.name_en || w.name_ar) ?? ""}
                  </td>
                  <td className="border px-2 py-1 text-center">☐</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </div>
  );
}
