"use client";
import { CheckCircle2, ChevronDown, ChevronUp, ClipboardCheck, FileImage, OctagonAlert, Plus, Wrench, XCircle } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Code, DeploymentPicker } from "@/components/access/common";
import { ApiWarnings, useWarningToasts } from "@/components/common/api-warnings";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { StackedDate } from "@/components/medical/common";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { CriticalMark, PhotoPicker, useBi } from "@/components/field/common";
import { DateFilter } from "@/components/training/common";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useMissingChecks, usePreUseCheck, usePreUseChecks, usePreUseForm, useSiteVehicles, useSvRefresh } from "@/lib/api/site-vehicles";
import { todayInZone } from "@/lib/datetime";
import { useDisplay } from "@/lib/digits";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { ChoiceMark } from "@/components/heat/common";
import { CheckResultBadge, DriverText, PrototypeBadge, ReadinessBadge, SvGate, SvSubNav, VehicleRefText, useSvCaps, useSvLabels } from "./common";

type S = Schemas;
type Item = S["TemplateItem-Output"];
type Ans = { answer: "" | "compliant" | "non_compliant" | "na"; note: string };
const PAGE_SIZE = 50;
/** Today's missing checks: the first six, then "Show all" (a full site is 20+ cards). */
const MISSING_FOLD = 6;

/* ═════════════ register + today's missing list (§8, PU-1) ═════════════ */

export function PreUseChecksPage() {
  return <SvGate>{(p) => <Register project={p} />}</SvGate>;
}

function Register({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("sv.check");
  const tc = useTranslations("common");
  const l = useSvLabels();
  const caps = useSvCaps(project.id);
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const from = s.get("date_from") ?? "";
  const to = s.get("date_to") ?? "";
  const passed = s.get("passed") ?? "";
  const source = (s.get("source") ?? "") as S["SiteVehCheckSource"] | "";
  const authorised = s.get("driver_authorised") ?? "";
  const eng = s.get("engagement_id") ?? "";
  const vehicle = s.get("vehicle_id") ?? "";
  const q = usePreUseChecks(
    project.id,
    {
      date_from: from || null,
      date_to: to || null,
      passed: passed ? passed === "true" : null,
      source: source || null,
      driver_authorised: authorised ? authorised === "true" : null,
      engagement_id: eng ? [eng] : null,
      vehicle_id: vehicle || null,
      page,
      page_size: PAGE_SIZE,
    },
    { enabled: !caps.aggregatesOnly },
  );
  if (caps.aggregatesOnly) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        badge={<PrototypeBadge />}
        description={t("subtitle")}
        actions={
          caps.record ? (
            <Button asChild>
              <Link href="/site-vehicles/checks/new" data-testid="sv-new-check">
                <Plus aria-hidden />
                {t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <SvSubNav projectId={project.id} />
      <Missing project={project} />
      <h2 className="mt-6 mb-2 text-sm font-semibold">{t("recorded")}</h2>
      <ListToolbar>
        <DateFilter id="pu-from" label={t("dateFrom")} value={from} onChange={(v) => s.set({ date_from: v })} />
        <DateFilter id="pu-to" label={t("dateTo")} value={to} onChange={(v) => s.set({ date_to: v })} />
        <SelectFilter
          id="pu-passed"
          label={t("result")}
          value={passed}
          onChange={(v) => s.set({ passed: v })}
          options={[
            { value: "true", label: t("pass") },
            { value: "false", label: t("fail") },
          ]}
        />
        <SelectFilter id="pu-source" label={t("source")} value={source} onChange={(v) => s.set({ source: v })} options={(["app", "paper"] as const).map((x) => ({ value: x, label: l.source(x) }))} />
        <SelectFilter
          id="pu-auth"
          label={t("driverAuthorised")}
          value={authorised}
          onChange={(v) => s.set({ driver_authorised: v })}
          options={[
            { value: "true", label: t("authorisedYes") },
            { value: "false", label: t("authorisedNo") },
          ]}
        />
        <SelectFilter id="pu-eng" label={tc("contractor")} value={eng} onChange={(v) => s.set({ engagement_id: v })} options={opts.engagements} allLabel={tc("anyContractor")} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table compact data-testid="sv-checks">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("date")}</TH>
                <TH>{t("vehicle")}</TH>
                <TH>{t("driver")}</TH>
                <TH>{t("result")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((c) => (
                <TR key={c.id} data-testid="sv-check-row" data-no={c.check_no} data-passed={c.passed} data-source={c.source}>
                  <TD label={t("no")}>
                    <Link href={`/site-vehicles/checks/${c.id}`} className="ltr font-medium text-primary hover:underline [overflow-wrap:anywhere]">
                      {c.check_no}
                    </Link>
                    {c.source === "paper" ? (
                      <Badge tone="neutral" className="ms-1.5" data-testid="sv-paper">
                        <FileImage aria-hidden />
                        {l.source("paper")}
                      </Badge>
                    ) : null}
                  </TD>
                  <TD label={t("date")} className="max-md:order-2 max-md:text-xs">
                    <StackedDate v={c.check_date} projectId={project.id} />
                  </TD>
                  <TD label={t("vehicle")} className="max-md:order-2">
                    <VehicleRefText v={c.vehicle} />
                  </TD>
                  <TD label={t("driver")} data-full="" className="max-md:order-3">
                    <DriverText w={c.driver} />
                    <AuthorisedMark ok={c.driver_authorised} />
                  </TD>
                  <TD label={t("result")} className="max-md:order-1 max-md:ms-auto">
                    <CheckResultBadge passed={c.passed} critical={c.critical_fail_count} />
                    {c.hold_set ? (
                      <span className="mt-0.5 flex items-center gap-1 text-xs font-medium text-danger">
                        <Wrench aria-hidden className="size-3.5 shrink-0" />
                        {t("holdSet")}
                      </span>
                    ) : null}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={q.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState message={t("empty")} />
      )}
    </div>
  );
}

function AuthorisedMark({ ok }: { ok: boolean }) {
  const t = useTranslations("sv.check");
  return (
    <span className={cn("mt-0.5 flex items-center gap-1 text-xs", ok ? "text-muted-foreground" : "font-medium text-warning")} data-testid="sv-authorised" data-ok={ok}>
      {ok ? <CheckCircle2 aria-hidden className="size-3.5" /> : <XCircle aria-hidden className="size-3.5" />}
      {ok ? t("authorisedYes") : t("authorisedNo")}
    </span>
  );
}

/** Today's missing checks per contractor (PU-1): vehicles required today without a Completed check. */
function Missing({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("sv.check");
  const show = useDisplay(project.id);
  const caps = useSvCaps(project.id);
  const { date } = useFormatters(project.id);
  const s = useSearchState();
  const day = s.get("day") ?? "";
  const q = useMissingChecks(project.id, day);
  const td = useTranslations("svDesign.missing");
  const [allMissing, setAllMissing] = useState(false);
  const d = q.data;
  return (
    <Card data-testid="sv-missing">
      <CardHeader className="flex flex-row flex-wrap items-end justify-between gap-2">
        <div>
          <CardTitle className="text-base">{t("missingTitle", { day: d ? date(d.date) : "…" })}</CardTitle>
          {d ? (
            <p className="text-sm text-muted-foreground" data-testid="sv-missing-count" data-required={d.required} data-completed={d.completed}>
              {d.working_day ? t("missingCount", { done: show(d.completed), required: show(d.required) }) : t("restDay")}
            </p>
          ) : null}
        </div>
        <DateFilter id="pu-day" label={t("day")} value={day} onChange={(v) => s.set({ day: v })} />
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {q.isError ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : !d ? (
          <LoadingState rows={2} />
        ) : d.items.length === 0 ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <CheckCircle2 aria-hidden className="size-4 text-success" />
            {t("noneMissing")}
          </p>
        ) : (
          <>
            <ul className="flex flex-wrap gap-2" data-testid="sv-missing-contractors">
              {d.by_contractor
                .filter((c) => c.missing > 0)
                .map((c) => (
                  <li key={c.engagement?.id ?? "none"} className="rounded-full border px-2.5 py-1 text-xs" data-testid="sv-missing-contractor" data-code={c.engagement?.short_code ?? ""} data-missing={c.missing}>
                    <Code className="font-medium">{c.engagement?.short_code ?? "—"}</Code> · {t("missingN", { n: show(c.missing), required: show(c.required) })}
                  </li>
                ))}
            </ul>
            <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {(allMissing ? d.items : d.items.slice(0, MISSING_FOLD)).map((m) => (
                <li key={m.vehicle.id} className="flex items-center justify-between gap-2 rounded-lg border p-2 text-sm" data-testid="sv-missing-vehicle" data-vehicle={m.vehicle.vehicle_no}>
                  <span className="min-w-0">
                    <VehicleRefText v={m.vehicle} />
                    {m.engagement ? (
                      <span className="block text-xs text-muted-foreground">
                        <Code>{m.engagement.short_code}</Code>
                      </span>
                    ) : null}
                  </span>
                  {caps.record ? (
                    <Button asChild size="sm" variant="outline">
                      <Link href={`/site-vehicles/checks/new?vehicle=${m.vehicle.id}${day ? `&date=${day}` : ""}`} aria-label={t("recordFor", { no: m.vehicle.vehicle_no })}>
                        <ClipboardCheck aria-hidden />
                        {t("record")}
                      </Link>
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
            {d.items.length > MISSING_FOLD ? (
              <div>
                <Button type="button" variant="ghost" size="sm" className="min-h-11" aria-expanded={allMissing} onClick={() => setAllMissing((x) => !x)} data-testid="sv-missing-more">
                  {allMissing ? <ChevronUp aria-hidden /> : <ChevronDown aria-hidden />}
                  {allMissing ? td("showFewer") : td("showAll", { n: show(d.items.length) })}
                </Button>
              </div>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}

/* ═════════════ record a pre-use check (6d template, PU-2…PU-6) ═════════════ */

export function PreUseCheckNewPage() {
  return <SvGate>{(p) => <CheckForm project={p} />}</SvGate>;
}

function CheckForm({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("sv.check");
  const tn = useTranslations("sv.nav");
  const tc = useTranslations("common");
  const tv = useTranslations("validation");
  const l = useSvLabels();
  const bi = useBi();
  const router = useRouter();
  const refresh = useSvRefresh();
  const warn = useWarningToasts();
  const caps = useSvCaps(project.id);
  const td = useTranslations("svDesign.form");
  const show = useDisplay(project.id);
  const sp = useSearchParams();
  const [vehicleId, setVehicleId] = useState(sp.get("vehicle") ?? "");
  const [dep, setDep] = useState<S["DeploymentRead"] | null>(null);
  const [day, setDay] = useState(sp.get("date") ?? todayInZone());
  const [source, setSource] = useState<S["SiteVehCheckSource"]>("app");
  const [photo, setPhoto] = useState<S["PhotoInput"][]>([]);
  const [answers, setAnswers] = useState<Record<string, Ans>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const vehicles = useSiteVehicles(project.id, { page_size: 200 });
  const form = usePreUseForm(project.id, vehicleId);
  const tpl = form.data?.template;
  const items = useMemo(() => {
    if (!tpl) return [] as { code: string; title: string; items: Item[] }[];
    return [...tpl.sections]
      .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
      .map((s) => ({ code: s.code, title: bi(s.title_en, s.title_ar), items: tpl.items.filter((i) => i.section_code === s.code).sort((a, b) => (a.order ?? 0) - (b.order ?? 0)) }))
      .filter((x) => x.items.length);
  }, [tpl, bi]);
  const all = items.flatMap((x) => x.items);
  const a = (code: string): Ans => answers[code] ?? { answer: "", note: "" };
  const setA = (code: string, p: Partial<Ans>) => setAnswers((x) => ({ ...x, [code]: { ...a(code), ...p } }));
  const open = all.filter((i) => !a(i.item_code).answer);
  const failing = all.filter((i) => a(i.item_code).answer === "non_compliant");
  const criticalFail = failing.some((i) => i.critical);
  const pick = (vehicles.data?.items ?? []).filter((v) => v.status !== "withdrawn");

  async function submit() {
    const e: Record<string, string> = {};
    if (!vehicleId) e.vehicle = tv("required");
    if (!dep) e.driver = tv("required");
    if (open.length) e.answers = t("answerAll", { n: open.length });
    for (const i of failing) if (a(i.item_code).note.trim().length < 10) e[`note-${i.item_code}`] = t("noteMin");
    if (source === "paper" && !photo.length) e.photo = t("photoRequired");
    setErrors(e);
    if (Object.keys(e).length || !tpl || !dep) return;
    setBusy(true);
    setError(null);
    const body: S["SiteVehCheckCreate"] = {
      vehicle_id: vehicleId,
      driver_worker_id: dep.worker_id,
      check_date: day || null,
      source,
      paper_photo: source === "paper" ? (photo[0] ?? null) : null,
      answers: all.map((i) => {
        const x = a(i.item_code);
        return { item_code: i.item_code, answer: x.answer || null, note: x.note.trim() || null, photos: [], fixed_on_spot: false, ca_required: false };
      }),
    };
    try {
      const c = await unwrap(api.POST("/api/v1/projects/{project_id}/pre-use-checks", { params: { path: { project_id: project.id } }, body }));
      await refresh();
      warn(c.warnings);
      toast.success(t("saved", { no: c.check_no }));
      router.push(`/site-vehicles/checks/${c.id}`);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }
  if (!caps.record) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  return (
    <div className="flex max-w-3xl flex-col gap-5" data-testid="sv-check-form">
      <div>
        <Breadcrumbs items={[{ label: tn("checks"), href: "/site-vehicles/checks" }, { label: t("new") }]} />
        <PageHeader title={t("new")} badge={<PrototypeBadge />} description={t("intro")} />
      </div>
      <Card>
        <CardContent className="grid gap-4 pt-5 sm:grid-cols-2">
          <FormField id="pu-vehicle" label={t("vehicle")} required error={errors.vehicle}>
            <Select
              value={vehicleId}
              onChange={(e) => {
                setVehicleId(e.target.value);
                setAnswers({});
              }}
              data-testid="pu-vehicle"
            >
              <option value="">{tc("select")}</option>
              {pick.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.vehicle_no} · {v.fleet_no} · {l.useClass(v.use_class)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="pu-date" label={t("date")} required>
            <Input type="date" className="ltr" value={day} onChange={(e) => setDay(e.target.value)} data-testid="pu-date" />
          </FormField>
          <div className="sm:col-span-2">
            <DeploymentPicker id="pu-driver" projectId={project.id} value={dep} onChange={setDep} status={["mobilised"]} label={t("driver")} required error={errors.driver} />
          </div>
          <FormField id="pu-source" label={t("source")} hint={source === "paper" ? t("paperHint") : undefined}>
            <Select value={source} onChange={(e) => setSource(e.target.value as S["SiteVehCheckSource"])} data-testid="pu-source">
              {(["app", "paper"] as const).map((x) => (
                <option key={x} value={x}>
                  {l.source(x)}
                </option>
              ))}
            </Select>
          </FormField>
          {source === "paper" ? (
            <div className="flex flex-col gap-1">
              <span className="text-sm font-medium">
                {t("paperPhoto")} <span className="text-danger">*</span>
              </span>
              <PhotoPicker value={photo} onChange={setPhoto} max={1} testId="pu-paper-photo" required />
              {errors.photo ? <span className="text-xs font-medium text-destructive">{errors.photo}</span> : null}
            </div>
          ) : null}
        </CardContent>
      </Card>
      {vehicleId && form.isError ? <ErrorState error={form.error} onRetry={() => form.refetch()} /> : null}
      {form.data ? (
        <>
          <div className="flex flex-wrap items-center gap-2 text-sm" data-testid="pu-template">
            <Code className="font-semibold">
              {form.data.template.template_code} v{form.data.template.version}
            </Code>
            <span className="font-medium">{bi(form.data.template.title_en, form.data.template.title_ar)}</span>
            <ReadinessBadge readiness={form.data.readiness} />
          </div>
          {form.data.existing_check_no && !form.data.on_defect_hold ? (
            <Alert tone="warning" data-testid="pu-existing">
              {t("existing", { no: form.data.existing_check_no })}
            </Alert>
          ) : null}
          {form.data.on_defect_hold ? (
            <Alert tone="info" data-testid="pu-on-hold">
              {t("onHold")}
            </Alert>
          ) : null}
          <div className="flex justify-end">
            <Button
              type="button"
              variant="outline"
              className="min-h-11"
              onClick={() => setAnswers(Object.fromEntries(all.map((i) => [i.item_code, { answer: "compliant", note: "" } satisfies Ans])))}
              data-testid="pu-all-ok"
            >
              <CheckCircle2 aria-hidden />
              {t("allOk")}
            </Button>
          </div>
          {items.map((sec) => (
            <section key={sec.code} className="flex flex-col gap-2">
              <h2 className="text-sm font-semibold text-muted-foreground">{sec.title}</h2>
              <ol className="flex flex-col gap-2">
                {sec.items.map((it) => {
                  const x = a(it.item_code);
                  const fail = x.answer === "non_compliant";
                  return (
                    <li
                      key={it.item_code}
                      className={cn("flex flex-col gap-2 rounded-lg border p-3", fail && "border-danger/50 bg-danger-bg/30", it.critical && "border-s-4 border-s-danger")}
                      data-testid="pu-item"
                      data-code={it.item_code}
                      data-state={x.answer || "open"}
                    >
                      <div className="flex items-start gap-2 text-sm">
                        <Code className="shrink-0 font-semibold">{it.item_code}</Code>
                        <span className="flex-1 font-medium">{bi(it.text_en, it.text_ar)}</span>
                        {it.critical ? <CriticalMark /> : null}
                      </div>
                      {/* 6d convention: radio-style answers with a filled / empty mark, not only a fill colour */}
                      <div role="radiogroup" aria-label={bi(it.text_en, it.text_ar)} className="grid grid-cols-2 gap-2 sm:flex">
                        <Button
                          type="button"
                          role="radio"
                          aria-checked={x.answer === "compliant"}
                          variant={x.answer === "compliant" ? "default" : "outline"}
                          className="min-h-12 justify-start sm:min-w-32"
                          onClick={() => setA(it.item_code, { answer: "compliant" })}
                          data-testid={`pu-ok-${it.item_code}`}
                        >
                          <ChoiceMark on={x.answer === "compliant"} />
                          {t("ok")}
                        </Button>
                        <Button
                          type="button"
                          role="radio"
                          aria-checked={fail}
                          variant={fail ? "destructive" : "outline"}
                          className={cn("min-h-12 justify-start sm:min-w-32", !fail && "border-danger/40")}
                          onClick={() => setA(it.item_code, { answer: "non_compliant" })}
                          data-testid={`pu-fail-${it.item_code}`}
                        >
                          <ChoiceMark on={fail} />
                          {t("defect")}
                        </Button>
                      </div>
                      {fail ? (
                        <FormField id={`pu-note-${it.item_code}`} label={t("note")} required error={errors[`note-${it.item_code}`]} hint={t("noteHint")}>
                          <Textarea maxLength={500} value={x.note} onChange={(e) => setA(it.item_code, { note: e.target.value })} data-testid={`pu-note-${it.item_code}`} />
                        </FormField>
                      ) : null}
                    </li>
                  );
                })}
              </ol>
            </section>
          ))}
          {criticalFail ? (
            <Alert tone="danger" data-testid="pu-critical">
              <span className="inline-flex items-center gap-2">
                <OctagonAlert aria-hidden className="size-4" />
                {t("criticalWarn")}
              </span>
            </Alert>
          ) : null}
          {errors.answers ? (
            <p role="alert" className="text-sm font-medium text-destructive">
              {errors.answers}
            </p>
          ) : null}
        </>
      ) : vehicleId && form.isLoading ? (
        <LoadingState />
      ) : null}
      <MutationError error={error} />
      <div className="glass-bar sticky bottom-0 z-10 -mx-4 flex flex-wrap items-center gap-2 border-t px-4 py-3 sm:static sm:mx-0 sm:border-0 sm:bg-transparent sm:p-0 sm:shadow-none sm:backdrop-blur-none">
        {all.length ? (
          <p className="w-full text-xs text-muted-foreground" aria-live="polite" data-testid="pu-progress" data-open={open.length}>
            {td("answered", { done: show(all.length - open.length), total: show(all.length) })}
            {failing.length ? <span className="font-medium text-danger"> · {td("defects", { n: show(failing.length) })}</span> : null}
          </p>
        ) : null}
        <Button type="button" className="min-h-12 flex-1 sm:flex-none" disabled={busy || !form.data} onClick={() => void submit()} data-testid="pu-submit">
          {busy ? tc("saving") : t("submit")}
        </Button>
        <Button type="button" variant="outline" className="min-h-12" onClick={() => router.push("/site-vehicles/checks")}>
          {tc("cancel")}
        </Button>
      </div>
    </div>
  );
}

/* ═════════════ one check: result, findings, defect hold (PU-3, PU-4) ═════════════ */

export function PreUseCheckDetailPage({ id }: { id: string }) {
  return <SvGate>{(p) => <Detail project={p} id={id} />}</SvGate>;
}

function Detail({ project, id }: { project: S["ProjectRead"]; id: string }) {
  const t = useTranslations("sv.check");
  const tn = useTranslations("sv.nav");
  const te = useTranslations("enums");
  const l = useSvLabels();
  const q = usePreUseCheck(id);
  const { date, dateTime } = useFormatters(project.id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const c = q.data;
  return (
    <div className="flex flex-col gap-6" data-testid="sv-check-detail" data-passed={c.passed} data-hold={c.hold_set}>
      <div>
        <Breadcrumbs items={[{ label: tn("checks"), href: "/site-vehicles/checks" }, { label: c.check_no }]} />
        <PageHeader
          title={<bdi className="ltr">{c.check_no}</bdi>}
          badge={
            <>
              <CheckResultBadge passed={c.passed} critical={c.critical_fail_count} />
              <PrototypeBadge />
            </>
          }
          description={`${date(c.check_date)} · ${c.template_code}`}
        />
      </div>
      {c.hold_set ? (
        <Alert tone="danger" data-testid="sv-check-hold">
          <span className="flex flex-col gap-1">
            <span className="font-semibold">{c.hold_cleared_at ? t("holdCleared", { at: dateTime(c.hold_cleared_at) }) : t("holdSetLong")}</span>
            {c.hold_repair_note ? <span dir="auto">{c.hold_repair_note}</span> : null}
            <Link href={`/site-vehicles/${c.vehicle.id}`} className="font-medium underline">
              {t("openVehicle", { no: c.vehicle.vehicle_no })}
            </Link>
          </span>
        </Alert>
      ) : null}
      {c.phase4_defect_no ? (
        <Alert tone="danger" data-testid="sv-check-defect">
          {t("phase4Defect")}{" "}
          {c.phase4_defect_id ? (
            <Link href={`/defects/${c.phase4_defect_id}`} className="font-medium underline">
              <bdi className="ltr">{c.phase4_defect_no}</bdi>
            </Link>
          ) : (
            <bdi className="ltr">{c.phase4_defect_no}</bdi>
          )}
        </Alert>
      ) : null}
      <ApiWarnings warnings={c.warnings} />
      <Card>
        <CardContent className="pt-5">
          <FieldList>
            <FieldItem label={t("vehicle")}>
              <Link href={`/site-vehicles/${c.vehicle.id}`} className="text-primary hover:underline">
                <VehicleRefText v={c.vehicle} />
              </Link>
            </FieldItem>
            <FieldItem label={t("driver")}>
              <DriverText w={c.driver} />
              <AuthorisedMark ok={c.driver_authorised} />
              {c.authorisation_no ? (
                <span className="block text-xs text-muted-foreground">
                  <bdi className="ltr">{c.authorisation_no}</bdi>
                </span>
              ) : null}
            </FieldItem>
            <FieldItem label={t("group")}>{l.group(c.driver_group)}</FieldItem>
            <FieldItem label={t("source")}>{l.source(c.source)}</FieldItem>
            <FieldItem label={t("recordedBy")}>
              {c.recorded_by?.full_name_en ?? "—"} · {dateTime(c.completed_at)}
            </FieldItem>
            <FieldItem label={t("failedItems")}>{c.failed_items.length ? <bdi className="ltr">{c.failed_items.join(", ")}</bdi> : "—"}</FieldItem>
          </FieldList>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("findings")}</CardTitle>
        </CardHeader>
        <CardContent>
          {c.findings.length ? (
            <Table data-testid="sv-findings">
              <THead>
                <TR>
                  <TH>{t("findingNo")}</TH>
                  <TH>{t("item")}</TH>
                  <TH>{t("severity")}</TH>
                  <TH>{t("ca")}</TH>
                </TR>
              </THead>
              <TBody>
                {c.findings.map((f) => (
                  <TR key={f.finding_no} data-testid="sv-finding" data-item={f.item_code ?? ""}>
                    <TD label={t("findingNo")}>
                      <Code>{f.finding_no}</Code>
                    </TD>
                    <TD label={t("item")}>
                      <Code>{f.item_code ?? "—"}</Code>
                      {f.critical_item ? <CriticalMark /> : null}
                    </TD>
                    <TD label={t("severity")}>{te.has(`findingSeverityPtw.${f.severity}` as "findingSeverityPtw.minor") ? te(`findingSeverityPtw.${f.severity}` as "findingSeverityPtw.minor") : f.severity}</TD>
                    <TD label={t("ca")}>
                      {f.ca_id ? (
                        <Link href={`/actions/${f.ca_id}`} className="text-primary hover:underline" data-testid="sv-finding-ca">
                          <bdi className="ltr">{f.ca_ref}</bdi>
                        </Link>
                      ) : (
                        "—"
                      )}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          ) : (
            <p className="text-sm text-muted-foreground">{t("noFindings")}</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
