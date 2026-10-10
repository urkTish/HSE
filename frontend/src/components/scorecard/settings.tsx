"use client";
import { CheckCircle2, Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { StepDialog } from "@/components/access/common";
import { FormField } from "@/components/common/form-field";
import { PageHeader } from "@/components/common/page-header";
import { ProjectGate } from "@/components/common/project-gate";
import { ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Choices } from "@/components/followup/common";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useScProfile, useScProfiles, useScRefresh, useScSettings } from "@/lib/api/scorecard";
import { useFormatters } from "@/lib/use-formatters";
import { ScBadge, ScSubNav, useScCaps, useScRef } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];

export function ScorecardSettingsPage() {
  return <ProjectGate>{(p) => <SettingsPage project={p} />}</ProjectGate>;
}

function SettingsPage({ project }: { project: Project }) {
  const t = useTranslations("sc.settings");
  const tc = useTranslations("common");
  const caps = useScCaps(project.id);
  const q = useScSettings(project.id, { enabled: caps.settings });
  if (!caps.settings) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <ScSubNav />
      <div className="flex flex-col gap-6">
        {q.isLoading ? <LoadingState /> : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.data ? <SettingsForm key={JSON.stringify(q.data)} project={project} s={q.data} /> : null}
        <Profiles project={project} />
      </div>
    </div>
  );
}

/* ───────────── §3.9 settings and SN-5 sources ───────────── */

type NumKey =
  | "scorecard_min_exposure_hours"
  | "scorecard_min_coverage_pct"
  | "scorecard_comment_days"
  | "dispute_resolution_days"
  | "scorecard_trend_points"
  | "scorecard_drop_points"
  | "pip_submit_days"
  | "client_report_due_day";
const NUMS: { k: NumKey; range: string; dec?: boolean }[] = [
  { k: "scorecard_min_exposure_hours", range: "50,000–1,000,000" },
  { k: "scorecard_min_coverage_pct", range: "50.0–90.0", dec: true },
  { k: "scorecard_comment_days", range: "2–10" },
  { k: "dispute_resolution_days", range: "1–10" },
  { k: "scorecard_trend_points", range: "2.0–15.0", dec: true },
  { k: "scorecard_drop_points", range: "5.0–25.0", dec: true },
  { k: "pip_submit_days", range: "3–14" },
  { k: "client_report_due_day", range: "—28" },
];
const MODULES: S["ScModule"][] = ["access", "ptw", "cert", "training", "medical", "heat", "emergency", "field", "toolbox", "env", "followup"];

function SettingsForm({ project, s }: { project: Project; s: S["ScSettingsRead"] }) {
  const t = useTranslations("sc.settings");
  const te = useTranslations("enums");
  const { dateTime } = useFormatters(project.id);
  const refresh = useScRefresh();
  const [from, setFrom] = useState(s.scorecard_from_month ?? "");
  const [nums, setNums] = useState<Record<NumKey, string>>(Object.fromEntries(NUMS.map((n) => [n.k, String(s[n.k])])) as Record<NumKey, string>);
  const [ext, setExt] = useState(s.external_distribution_enabled);
  const [domains, setDomains] = useState(s.external_domains.join(", "));
  const [langs, setLangs] = useState<S["RpLanguages"]>(s.report_languages);
  const [live, setLive] = useState<Record<string, string>>(Object.fromEntries(MODULES.map((m) => [m, s.source_live_from[m] ?? ""])));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function run(fn: () => Promise<unknown>, done: string) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await refresh();
      toast.success(done);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  function save() {
    const body: S["ScSettingsUpdate"] = {};
    if ((s.scorecard_from_month ?? "") !== from) body.scorecard_from_month = from || null;
    for (const n of NUMS) if (String(s[n.k]) !== nums[n.k]) (body as Record<string, unknown>)[n.k] = n.dec ? nums[n.k] : Number(nums[n.k]);
    if (ext !== s.external_distribution_enabled) body.external_distribution_enabled = ext;
    const d = domains
      .split(/[,\s]+/)
      .map((x) => x.trim())
      .filter(Boolean);
    if (d.join() !== s.external_domains.join()) body.external_domains = d;
    if (langs !== s.report_languages) body.report_languages = langs;
    const map = Object.fromEntries(MODULES.map((m) => [m, live[m] || null]));
    if (MODULES.some((m) => (s.source_live_from[m] ?? "") !== live[m])) body.source_live_from = map;
    return run(() => unwrap(api.PATCH("/api/v1/projects/{project_id}/scorecard-settings", { params: { path: { project_id: project.id } }, body })), t("saved"));
  }

  return (
    <div className="flex flex-col gap-4" data-testid="sc-settings">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("groupCycle")}</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <FormField id="ss-from" label={t("f.scorecard_from_month")} hint={t("fromHint")}>
            <Input type="month" className="ltr" value={from} onChange={(e) => setFrom(e.target.value)} data-testid="ss-scorecard_from_month" />
          </FormField>
          {NUMS.map((n) => (
            <FormField key={n.k} id={`ss-${n.k}`} label={t(`f.${n.k}`)} hint={t("allowed", { range: n.range })}>
              <Input type={n.dec ? "text" : "number"} inputMode={n.dec ? "decimal" : undefined} className="ltr" value={nums[n.k]} onChange={(e) => setNums({ ...nums, [n.k]: e.target.value })} data-testid={`ss-${n.k}`} />
            </FormField>
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("groupReports")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <fieldset className="flex flex-col gap-1">
            <legend className="mb-1 text-sm font-medium">{t("f.report_languages")}</legend>
            <Choices label={t("f.report_languages")} testId="ss-langs" value={langs} options={(["en_ar_separate", "bilingual_single"] as const).map((x) => ({ value: x, label: te(`rpLanguages.${x}`) }))} onChange={setLangs} />
          </fieldset>
          <label className="flex min-h-touch items-center gap-3 text-sm">
            <Checkbox checked={ext} onChange={(e) => setExt(e.target.checked)} data-testid="ss-external" />
            {t("f.external_distribution_enabled")}
          </label>
          <FormField id="ss-domains" label={t("f.external_domains")} hint={t("domainsHint")}>
            <Input className="ltr" value={domains} onChange={(e) => setDomains(e.target.value)} data-testid="ss-domains" />
          </FormField>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("groupSources")}</CardTitle>
          <p className="text-xs text-muted-foreground">{t("sourcesHint")}</p>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {MODULES.map((m) => (
              <FormField key={m} id={`ss-live-${m}`} label={te(`scModule.${m}`)}>
                <Input type="date" className="ltr" value={live[m]} onChange={(e) => setLive({ ...live, [m]: e.target.value })} data-testid={`ss-live-${m}`} />
              </FormField>
            ))}
          </div>
          <p className="flex flex-wrap items-center gap-2 text-sm" data-testid="ss-sources-confirmed">
            {s.sources_confirmed_at ? (
              <>
                <CheckCircle2 aria-hidden className="size-4 text-success" />
                {t("confirmedAt", { at: dateTime(s.sources_confirmed_at) })}
              </>
            ) : (
              <span className="text-warning">{t("notConfirmed")}</span>
            )}
          </p>
          <Button
            variant="outline"
            className="w-fit"
            disabled={busy}
            onClick={() => void run(() => unwrap(api.POST("/api/v1/projects/{project_id}/scorecard-settings/confirm-sources", { params: { path: { project_id: project.id } } })), t("sourcesConfirmed"))}
            data-testid="ss-confirm-sources"
          >
            {t("confirmSources")}
          </Button>
        </CardContent>
      </Card>
      <MutationError error={error} />
      <div className="flex justify-end">
        <Button onClick={() => void save()} disabled={busy} data-testid="ss-save">
          {t("save")}
        </Button>
      </div>
    </div>
  );
}

/* ───────────── profiles (§3.1, SP-1…SP-5) ───────────── */

function Profiles({ project }: { project: Project }) {
  const t = useTranslations("sc.profile");
  const q = useScProfiles({ project_id: project.id, page_size: 100 });
  const refresh = useScRefresh();
  const [selected, setSelected] = useState<string>("");
  const [create, setCreate] = useState(false);
  const [scope, setScope] = useState<"org" | "project">("org");
  const items = q.data?.items ?? [];
  const current = selected || items.find((p) => p.status === "draft")?.id || items.find((p) => p.status === "active")?.id || "";
  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
        <div>
          <CardTitle className="text-base">{t("title")}</CardTitle>
          <p className="text-xs text-muted-foreground">{t("subtitle")}</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => setCreate(true)} data-testid="sp-new">
          <Plus aria-hidden />
          {t("newDraft")}
        </Button>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {q.isLoading ? (
          <LoadingState rows={2} />
        ) : (
          <ul className="flex flex-wrap gap-2" data-testid="sp-list">
            {items.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  onClick={() => setSelected(p.id)}
                  aria-pressed={current === p.id}
                  className={`flex min-h-touch items-center gap-2 rounded-md border px-3 text-sm ${current === p.id ? "border-2 border-primary" : ""}`}
                  data-testid="sp-item"
                  data-status={p.status}
                >
                  <bdi className="ltr font-mono">
                    {p.profile_code} v{p.version}
                  </bdi>
                  <ScBadge group="scProfileStatus" status={p.status} />
                  <span className="text-xs text-muted-foreground">{t("from", { m: p.effective_from_month })}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {current ? <ProfileEditor key={current} id={current} /> : null}
      </CardContent>
      {create ? (
        <StepDialog
          title={t("newDraft")}
          description={t("newBody")}
          confirmLabel={t("create")}
          testId="sp-create-confirm"
          onConfirm={async () => {
            const p = await unwrap(api.POST("/api/v1/scorecard-profiles", { body: { project_id: scope === "project" ? project.id : null } }));
            await refresh();
            setSelected(p.id);
          }}
          onClose={() => setCreate(false)}
        >
          <Choices
            label={t("scope")}
            testId="sp-scope"
            value={scope}
            options={[
              { value: "org", label: t("scopeOrg") },
              { value: "project", label: t("scopeProject") },
            ]}
            onChange={setScope}
          />
        </StepDialog>
      ) : null}
    </Card>
  );
}

function ProfileEditor({ id }: { id: string }) {
  const t = useTranslations("sc.profile");
  const te = useTranslations("enums");
  const ref = useScRef();
  const refresh = useScRefresh();
  const q = useScProfile(id);
  const p = q.data;
  const [draft, setDraft] = useState<S["ScProfileRead"] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!p) return <LoadingState rows={3} />;
  const d = draft ?? p;
  const editable = p.status === "draft";
  const sum = d.pillars.reduce((a, x) => a + Number(x.weight || 0), 0);

  async function run(fn: () => Promise<unknown>, done: string) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await refresh();
      setDraft(null);
      toast.success(done);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const save = () =>
    run(
      () =>
        unwrap(
          api.PATCH("/api/v1/scorecard-profiles/{profile_id}", {
            params: { path: { profile_id: id } },
            body: {
              effective_from_month: d.effective_from_month,
              pillars: d.pillars,
              metrics: d.metrics.map((m) => ({ metric_code: m.metric_code, weight: m.weight, good: m.good, bad: m.bad, min_volume: m.min_volume, enabled: m.enabled })),
              caps: d.caps,
              bands: d.bands,
            },
          }),
        ),
      t("saved"),
    );
  const activate = () => run(() => unwrap(api.POST("/api/v1/scorecard-profiles/{profile_id}/activate", { params: { path: { profile_id: id } } })), t("activated"));
  const setPillar = (code: string, weight: string) => setDraft({ ...d, pillars: d.pillars.map((x) => (x.pillar_code === code ? { ...x, weight } : x)) });
  const setMetric = (code: string, patch: Partial<S["ScMetricConfig"]>) => setDraft({ ...d, metrics: d.metrics.map((x) => (x.metric_code === code ? { ...x, ...patch } : x)) });

  return (
    <div className="flex flex-col gap-4" data-testid="sp-editor" data-status={p.status}>
      {!editable ? <p className="text-sm text-muted-foreground">{t("readOnly")}</p> : null}
      <FormField id="sp-from" label={t("effectiveFrom")} hint={t("effectiveHint")}>
        <Input id="sp-from" type="month" className="ltr sm:w-48" value={d.effective_from_month} disabled={!editable} onChange={(e) => setDraft({ ...d, effective_from_month: e.target.value })} data-testid="sp-from" />
      </FormField>
      <div>
        <h3 className="mb-2 text-sm font-semibold">
          {t("pillars")} <span className={`ms-2 text-xs font-normal ${Math.abs(sum - 100) > 1e-9 ? "text-danger" : "text-muted-foreground"}`} data-testid="sp-sum">{t("sum", { v: sum.toFixed(1) })}</span>
        </h3>
        <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-5">
          {d.pillars.map((x) => (
            <FormField key={x.pillar_code} id={`sp-p-${x.pillar_code}`} label={`${x.pillar_code} · ${ref.label("pillars", x.pillar_code)}`}>
              <Input id={`sp-p-${x.pillar_code}`} inputMode="decimal" className="ltr" value={x.weight} disabled={!editable} onChange={(e) => setPillar(x.pillar_code, e.target.value)} data-testid={`sp-pillar-${x.pillar_code}`} />
            </FormField>
          ))}
        </div>
      </div>
      <div>
        <h3 className="mb-2 text-sm font-semibold">{t("metrics")}</h3>
        <Table data-testid="sp-metrics">
          <THead>
            <TR>
              <TH>{t("metric")}</TH>
              <TH>{t("weight")}</TH>
              <TH>{t("good")}</TH>
              <TH>{t("bad")}</TH>
              <TH>{t("minVolume")}</TH>
              <TH>{t("enabled")}</TH>
            </TR>
          </THead>
          <TBody>
            {d.metrics.map((m) => (
              <TR key={m.metric_code} data-testid="sp-metric" data-metric={m.metric_code}>
                <TD label={t("metric")}>
                  <span className="font-mono text-xs">{m.metric_code}</span> · {ref.label("metrics", m.metric_code)}
                  <span className="block text-xs text-muted-foreground">
                    {m.pillar_code} · {m.kpi_ref} · {te(`scWindow.${m.window}`)}
                  </span>
                </TD>
                <TD label={t("weight")}>
                  <Input aria-label={t("weight")} inputMode="decimal" className="ltr w-20" value={m.weight} disabled={!editable} onChange={(e) => setMetric(m.metric_code, { weight: e.target.value })} />
                </TD>
                <TD label={t("good")}>
                  <Input aria-label={t("good")} inputMode="decimal" className="ltr w-20" value={m.good} disabled={!editable} onChange={(e) => setMetric(m.metric_code, { good: e.target.value })} />
                </TD>
                <TD label={t("bad")}>
                  <Input aria-label={t("bad")} inputMode="decimal" className="ltr w-20" value={m.bad} disabled={!editable} onChange={(e) => setMetric(m.metric_code, { bad: e.target.value })} />
                </TD>
                <TD label={t("minVolume")}>
                  <Input aria-label={t("minVolume")} type="number" className="ltr w-20" value={m.min_volume} disabled={!editable} onChange={(e) => setMetric(m.metric_code, { min_volume: Number(e.target.value) })} />
                </TD>
                <TD label={t("enabled")}>
                  <Checkbox aria-label={t("enabled")} checked={m.enabled} disabled={!editable} onChange={(e) => setMetric(m.metric_code, { enabled: e.target.checked })} />
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <h3 className="mb-2 text-sm font-semibold">{t("caps")}</h3>
          <ul className="flex flex-col gap-2">
            {d.caps.map((c) => (
              <li key={c.cap_code} className="flex flex-wrap items-center gap-3 text-sm" data-testid="sp-cap" data-cap={c.cap_code}>
                <label className="flex min-h-touch items-center gap-2">
                  <Checkbox checked={c.enabled} disabled={!editable} onChange={(e) => setDraft({ ...d, caps: d.caps.map((x) => (x.cap_code === c.cap_code ? { ...x, enabled: e.target.checked } : x)) })} data-testid={`sp-cap-${c.cap_code}`} />
                  <span className="font-mono">{c.cap_code}</span>
                </label>
                <span className="text-muted-foreground">{ref.label("caps", c.cap_code)}</span>
                <Select aria-label={t("maxGrade")} className="w-20" value={c.max_grade} disabled={!editable} onChange={(e) => setDraft({ ...d, caps: d.caps.map((x) => (x.cap_code === c.cap_code ? { ...x, max_grade: e.target.value as S["ScGrade"] } : x)) })}>
                  {(["A", "B", "C", "D"] as const).map((g) => (
                    <option key={g} value={g}>
                      {g}
                    </option>
                  ))}
                </Select>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="mb-2 text-sm font-semibold">{t("bands")}</h3>
          <div className="flex flex-wrap gap-2">
            {d.bands.map((b) => (
              <FormField key={b.grade} id={`sp-band-${b.grade}`} label={t("bandMin", { g: b.grade })}>
                <Input id={`sp-band-${b.grade}`} inputMode="decimal" className="ltr w-24" value={b.min_score} disabled={!editable} onChange={(e) => setDraft({ ...d, bands: d.bands.map((x) => (x.grade === b.grade ? { ...x, min_score: e.target.value } : x)) })} />
              </FormField>
            ))}
          </div>
        </div>
      </div>
      <MutationError error={error} />
      {editable ? (
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="outline" disabled={busy || !draft} onClick={() => void save()} data-testid="sp-save">
            {t("save")}
          </Button>
          <Button disabled={busy || Boolean(draft)} onClick={() => void activate()} data-testid="sp-activate">
            {t("activate")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
