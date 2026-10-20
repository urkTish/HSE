"use client";
import { Ban, CalendarPlus, CheckCircle2, ClipboardCheck, ClipboardX, OctagonAlert, Pencil, Plus, Route, ShieldCheck, ShieldQuestion, TriangleAlert, Wrench } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Code, PLATE_DIGITS, PLATE_LETTERS_MAX, Plate, StepDialog } from "@/components/access/common";
import { ApiWarnings, useWarningToasts } from "@/components/common/api-warnings";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField, FormSection } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SearchFilter, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { RecordActions } from "@/components/common/record-actions";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Link, useRouter } from "@/i18n/navigation";
import { PLATE_TYPES, VEHICLE_CATEGORIES, VEHICLE_OWNER_TYPES } from "@/lib/access-enums";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useSiteVehicle, useSiteVehicles, useSvRefresh, useSvSummary } from "@/lib/api/site-vehicles";
import { useDisplay } from "@/lib/digits";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { DocChip, GROUPS, PrototypeBadge, READINESS, ReadinessBadge, SCOPES, SvGate, SvSubNav, USE_CLASSES, useSvCaps, useSvLabels, useUseClassRules } from "./common";

type S = Schemas;
type Vehicle = S["SiteVehRead"];
const PAGE_SIZE = 50;

/* ═════════════ register + readiness summary (§8, SV-1…SV-4) ═════════════ */

export function SiteVehiclesPage() {
  return <SvGate>{(p) => <Register project={p} />}</SvGate>;
}

function Register({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("sv");
  const caps = useSvCaps(project.id);
  return (
    <div>
      <PageHeader
        title={t("vehicle.title")}
        badge={<PrototypeBadge />}
        description={t("vehicle.subtitle")}
        actions={
          caps.manage ? (
            <Button asChild>
              <Link href="/site-vehicles/new" data-testid="sv-new-vehicle">
                <Plus aria-hidden />
                {t("vehicle.new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <SvSubNav projectId={project.id} />
      <Summary project={project} />
      {caps.aggregatesOnly ? (
        <Alert tone="info" className="mt-4" data-testid="sv-aggregates-only">
          {t("aggregatesOnly")}
        </Alert>
      ) : (
        <VehicleTable project={project} />
      )}
    </div>
  );
}

/** Readiness counts and today's numbers as the server returns them (Viewer / Client included). */
function Summary({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("sv.summary");
  const td = useTranslations("svDesign.summary");
  const l = useSvLabels();
  const show = useDisplay(project.id);
  const caps = useSvCaps(project.id);
  const q = useSvSummary(project.id);
  const s = useSearchState();
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState rows={2} />;
  const d = q.data;
  const by = d.by_readiness as Record<string, number>;
  const link = !caps.aggregatesOnly;
  const tile = (key: string, label: string, value: number, tone: "danger" | "warning" | "ok" | "neutral", filter?: Record<string, string>) => {
    const alarm = (tone === "danger" || tone === "warning") && value > 0;
    const body = (
      <>
        <span className="text-xs text-muted-foreground">{label}</span>
        <span className="inline-flex items-center gap-1.5">
          <span className={cn("text-2xl font-semibold tabular-nums", tone === "danger" && value > 0 && "text-danger", tone === "warning" && value > 0 && "text-warning", tone === "ok" && "text-success")} data-testid="sv-sum-value">
            {show(value)}
          </span>
          {/* never colour alone: a red / amber count carries an icon too */}
          {alarm ? <TriangleAlert aria-hidden className={cn("size-4 shrink-0", tone === "danger" ? "text-danger" : "text-warning")} /> : null}
        </span>
      </>
    );
    return (
      <li key={key} data-testid="sv-sum" data-key={key} data-value={value}>
        {link && filter ? (
          <button type="button" onClick={() => s.set(filter)} className="glass flex min-h-touch w-full flex-col items-start rounded-lg border p-3 text-start hover:bg-accent/60">
            {body}
          </button>
        ) : (
          <div className="glass flex flex-col rounded-lg border p-3">{body}</div>
        )}
      </li>
    );
  };
  return (
    <section aria-label={t("label")} className="flex flex-col gap-2" data-testid="sv-summary">
      <h2 className="text-xs font-semibold tracking-[0.02em] text-muted-foreground">{td("readinessNow")}</h2>
      <ul className="grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-7">
        {tile("site_vehicles", t("vehicles"), d.site_vehicles, "neutral", { readiness: "" })}
        {READINESS.map((r) => tile(r, l.readiness(r), by[r] ?? 0, r === "ready" ? "ok" : r === "idle" || r === "withdrawn" ? "neutral" : "danger", { readiness: r }))}
      </ul>
      <h2 className="mt-2 text-xs font-semibold tracking-[0.02em] text-muted-foreground">{td("todayAhead")}</h2>
      <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
        {tile("docs_expiring_30d", t("docsExpiring"), d.docs_expiring_30d, "warning", { documents: "expiring_30d" })}
        {tile("docs_unverified", t("docsUnverified"), d.docs_unverified, "warning", { documents: "unverified" })}
        {tile("pre_use_today", t("preUseToday", { done: show(d.pre_use_done_today), required: show(d.pre_use_required_today) }), d.pre_use_required_today - d.pre_use_done_today, "warning")}
        {tile("active_auths", t("activeAuths"), d.active_authorisations, "neutral")}
        {tile("auths_expiring", t("authsExpiring"), d.authorisations_expiring_30d, "warning")}
        {tile("journeys_overdue", t("journeysOverdue", { planned: show(d.journeys_planned) }), d.journeys_overdue, "warning")}
      </ul>
    </section>
  );
}

function VehicleTable({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("sv.vehicle");
  const tc = useTranslations("common");
  const l = useSvLabels();
  const opts = useProjectOptions(project.id);
  const { date } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const readiness = (s.get("readiness") ?? "") as S["SiteVehReadiness"] | "";
  const group = (s.get("driver_group") ?? "") as S["SiteVehDriverGroup"] | "";
  const docs = (s.get("documents") ?? "") as S["SiteVehDocsFilter"] | "";
  const eng = s.get("engagement_id") ?? "";
  const q = useSiteVehicles(project.id, {
    readiness: readiness ? [readiness] : null,
    driver_group: group ? [group] : null,
    documents: docs || null,
    engagement_id: eng ? [eng] : null,
    q: s.get("q") || null,
    page,
    page_size: PAGE_SIZE,
  });
  const items = q.data?.items ?? [];
  return (
    <div className="mt-4">
      <ListToolbar>
        <SearchFilter id="sv-q" value={s.get("q") ?? ""} onChange={(v) => s.set({ q: v })} placeholder={t("searchHint")} />
        <SelectFilter id="sv-readiness" label={t("readiness")} value={readiness} onChange={(v) => s.set({ readiness: v })} options={READINESS.map((r) => ({ value: r, label: l.readiness(r) }))} />
        <SelectFilter id="sv-group" label={t("group")} value={group} onChange={(v) => s.set({ driver_group: v })} options={GROUPS.map((g) => ({ value: g, label: l.group(g) }))} />
        <SelectFilter
          id="sv-docs"
          label={t("documents")}
          value={docs}
          onChange={(v) => s.set({ documents: v })}
          options={(["expired", "expiring_30d", "unverified"] as const).map((d) => ({ value: d, label: t(`docsFilter.${d}`) }))}
        />
        <SelectFilter id="sv-eng" label={tc("contractor")} value={eng} onChange={(v) => s.set({ engagement_id: v })} options={opts.engagements} allLabel={tc("anyContractor")} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table compact data-testid="sv-vehicles">
            <THead>
              <TR>
                <TH>{t("vehicle")}</TH>
                <TH>{t("readiness")}</TH>
                <TH>{t("plate")}</TH>
                <TH>{t("useClass")}</TH>
                <TH>{tc("contractor")}</TH>
                <TH>{t("today")}</TH>
                <TH>{t("documents")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((v) => (
                <TR key={v.id} data-testid="sv-vehicle-row" data-vehicle={v.vehicle_no} data-readiness={v.readiness}>
                  <TD label={t("vehicle")} className="md:min-w-36">
                    <Link href={`/site-vehicles/${v.id}`} className="ltr font-medium whitespace-nowrap text-primary hover:underline">
                      {v.vehicle_no}
                    </Link>
                    <span className="block text-xs text-muted-foreground">
                      <bdi className="ltr whitespace-nowrap">{v.fleet_no}</bdi> · {v.make_model}
                    </span>
                  </TD>
                  <TD label={t("readiness")} className="max-md:order-1 max-md:ms-auto">
                    <ReadinessBadge readiness={v.readiness} />
                  </TD>
                  <TD label={t("plate")} className="max-md:order-2">
                    {v.plate_type === "none" ? <span className="text-xs text-muted-foreground">{t("noPlate")}</span> : <Plate ar={v.plate_letters_ar} en={v.plate_letters_en} digits={v.plate_digits} />}
                  </TD>
                  <TD label={t("useClass")} className="max-md:order-2">
                    {l.useClass(v.use_class)}
                    <span className="block text-xs text-muted-foreground max-md:ms-1 max-md:inline">{l.group(v.driver_group)}</span>
                  </TD>
                  <TD label={tc("contractor")} className="max-md:order-2">
                    <Code>{v.engagement.short_code}</Code>
                  </TD>
                  <TD label={t("today")} className="max-md:order-3">
                    <TodayCell v={v} inTable />
                  </TD>
                  <TD label={t("documents")} className="max-md:order-3 md:min-w-48">
                    <DocsCell v={v} date={date} />
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

/** The worst document only (expired or ≤ 30 days), else "valid"; unverified scans flagged. */
function DocsCell({ v, date }: { v: Vehicle; date: (d: string) => string }) {
  const t = useTranslations("sv.vehicle");
  const worst = [...v.documents].sort((a, b) => a.days_left - b.days_left)[0];
  return (
    <span className="flex flex-col items-start gap-1">
      {worst && worst.state !== "valid" ? <DocChip d={worst} date={date} wrap /> : v.documents.length ? <span className="text-xs text-muted-foreground">{t("docsValid")}</span> : <span className="text-xs text-muted-foreground">{v.phase4 ? t("phase4Docs") : "—"}</span>}
      {!v.docs_verified && v.documents.length ? (
        <span className="inline-flex items-center gap-1 text-xs font-medium text-warning" data-testid="sv-unverified">
          <ShieldQuestion aria-hidden className="size-3.5 shrink-0" />
          {t("unverified")}
        </span>
      ) : null}
    </span>
  );
}

/** Today's pre-use check: icon + words (never colour alone); "check" spelled out where the column name is not shown. */
function TodayCell({ v, inTable }: { v: Vehicle; inTable?: boolean }) {
  const t = useTranslations("sv.vehicle");
  const td = useTranslations("svDesign");
  if (v.today_check)
    return (
      <Link
        href={`/site-vehicles/checks/${v.today_check.check_id}`}
        className={cn("inline-flex items-center gap-1 text-xs font-medium hover:underline", v.today_check.passed ? "text-success" : "text-danger")}
        data-testid="sv-today-check"
      >
        {v.today_check.passed ? <CheckCircle2 aria-hidden className="size-3.5 shrink-0" /> : <OctagonAlert aria-hidden className="size-3.5 shrink-0" />}
        <bdi className="ltr">{v.today_check.check_no}</bdi> · {v.today_check.passed ? t("checkPassed") : t("checkFailed")}
      </Link>
    );
  return v.pre_use_required_today ? (
    <span className="inline-flex items-center gap-1 text-xs font-medium text-warning" data-testid="sv-today-missing" title={td("checkMissingLong")}>
      <ClipboardX aria-hidden className="size-3.5 shrink-0" />
      {t("checkMissing")}
      {inTable ? <span className="md:hidden">· {td("todaysCheck")}</span> : null}
    </span>
  ) : (
    <span className="text-xs text-muted-foreground">{t("checkNotRequired")}</span>
  );
}

/* ═════════════ register / edit a site vehicle (§3.1, SV-2, OPERATING_CARD_REQUIRED) ═════════════ */

export function SiteVehicleNewPage() {
  return <SvGate>{(p) => <VehicleForm project={p} />}</SvGate>;
}

function VehicleForm({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("sv.vehicle");
  const tf = useTranslations("sv.form");
  const tn = useTranslations("sv.nav");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tv = useTranslations("validation");
  const l = useSvLabels();
  const rules = useUseClassRules();
  const router = useRouter();
  const refresh = useSvRefresh();
  const warn = useWarningToasts();
  const caps = useSvCaps(project.id);
  const opts = useProjectOptions(project.id);
  const [f, setF] = useState({
    engagement_id: "",
    site_scope: "site" as S["SiteVehScope"],
    use_class: "" as S["SiteVehUseClass"] | "",
    seats: "",
    owner_type: "company" as S["VehicleOwnerType"],
    category: "pickup" as S["VehicleCategory"],
    plate_type: "private" as S["PlateType"],
    plate_letters_ar: "",
    plate_letters_en: "",
    plate_digits: "",
    fleet_no: "",
    serial_or_vin: "",
    make_model: "",
    year: String(new Date().getFullYear()),
    colour: "",
    istimara_expiry: "",
    insurance_policy_no: "",
    insurance_expiry: "",
    mvpi_expiry: "",
    operating_card_no: "",
    operating_card_expiry: "",
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  const rule = rules(f.use_class);
  const plated = f.plate_type !== "none";
  const engagement = f.engagement_id || (caps.rep && opts.engagements.length === 1 ? (opts.engagements[0]?.value ?? "") : "");

  async function save() {
    const e: Record<string, string> = {};
    const req = (k: keyof typeof f) => {
      if (!String(f[k]).trim()) e[k] = tv("required");
    };
    if (!engagement) e.engagement_id = tv("required");
    (["use_class", "fleet_no", "serial_or_vin", "make_model", "insurance_policy_no", "insurance_expiry"] as const).forEach(req);
    if (plated) (["plate_letters_ar", "plate_digits", "istimara_expiry", "mvpi_expiry"] as const).forEach(req);
    if (plated && f.plate_digits && !PLATE_DIGITS.test(f.plate_digits)) e.plate_digits = tf("plateDigitsHint");
    if (rule?.seats_required && !(Number(f.seats) >= 2 && Number(f.seats) <= 60)) e.seats = tf("seatsRange");
    setErrors(e);
    if (Object.keys(e).length) return;
    setBusy(true);
    setError(null);
    const body: S["SiteVehCreate"] = {
      engagement_id: engagement,
      site_scope: f.site_scope,
      use_class: f.use_class as S["SiteVehUseClass"],
      seats: f.seats ? Number(f.seats) : null,
      owner_type: f.owner_type,
      category: f.category,
      plate_type: f.plate_type,
      plate_letters_ar: plated ? f.plate_letters_ar.trim() : null,
      plate_letters_en: plated ? f.plate_letters_en.trim().toUpperCase() || null : null,
      plate_digits: plated ? f.plate_digits.trim() : null,
      fleet_no: f.fleet_no.trim(),
      serial_or_vin: f.serial_or_vin.trim().toUpperCase(),
      make_model: f.make_model.trim(),
      year: Number(f.year),
      colour: f.colour.trim() || "White",
      istimara_expiry: plated ? f.istimara_expiry || null : null,
      insurance_policy_no: f.insurance_policy_no.trim(),
      insurance_expiry: f.insurance_expiry,
      mvpi_expiry: plated ? f.mvpi_expiry || null : null,
      operating_card_no: f.operating_card_no.trim() || null,
      operating_card_expiry: f.operating_card_expiry || null,
    };
    try {
      const v = await unwrap(api.POST("/api/v1/projects/{project_id}/site-vehicles", { params: { path: { project_id: project.id } }, body }));
      await refresh();
      warn(v.warnings);
      toast.success(t("registered", { no: v.vehicle_no }));
      router.push(`/site-vehicles/${v.id}`);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }
  if (!caps.manage) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  return (
    <form
      className="flex max-w-3xl flex-col gap-6"
      noValidate
      autoComplete="off"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
      data-testid="sv-vehicle-form"
    >
      <div>
        <Breadcrumbs items={[{ label: tn("vehicles"), href: "/site-vehicles" }, { label: t("new") }]} />
        <PageHeader title={t("new")} badge={<PrototypeBadge />} description={tf("intro")} />
      </div>
      <MutationError error={error} />
      <FormSection title={tf("siteUse")}>
        <FormField id="sv-f-eng" label={tc("contractor")} required error={errors.engagement_id}>
          <Select value={engagement} onChange={set("engagement_id")} data-testid="sv-f-eng">
            <option value="">{tc("select")}</option>
            {opts.engagements.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="sv-f-scope" label={t("scope")} required>
          <Select value={f.site_scope} onChange={set("site_scope")} data-testid="sv-f-scope">
            {SCOPES.filter((x) => x !== "airside_only").map((x) => (
              <option key={x} value={x}>
                {l.scope(x)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="sv-f-class" label={t("useClass")} required error={errors.use_class} hint={rule ? tf("groupHint", { group: l.group(rule.driver_group) }) : undefined}>
          <Select value={f.use_class} onChange={set("use_class")} data-testid="sv-f-class">
            <option value="">{tc("select")}</option>
            {USE_CLASSES.map((u) => (
              <option key={u} value={u}>
                {l.useClass(u)}
              </option>
            ))}
          </Select>
        </FormField>
        {rule?.seats_required ? (
          <FormField id="sv-f-seats" label={t("seats")} required error={errors.seats} hint={tf("seatsRange")}>
            <Input type="number" inputMode="numeric" min={2} max={60} className="ltr" value={f.seats} onChange={set("seats")} data-testid="sv-f-seats" />
          </FormField>
        ) : null}
      </FormSection>
      <FormSection title={tf("identity")}>
        <FormField id="sv-f-owner" label={tf("ownerType")} required>
          <Select value={f.owner_type} onChange={set("owner_type")}>
            {VEHICLE_OWNER_TYPES.map((x) => (
              <option key={x} value={x}>
                {te(`vehicleOwnerType.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="sv-f-cat" label={tf("category")} required>
          <Select value={f.category} onChange={set("category")}>
            {VEHICLE_CATEGORIES.map((x) => (
              <option key={x} value={x}>
                {te(`vehicleCategory.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="sv-f-plate-type" label={tf("plateType")} required hint={plated ? undefined : tf("noPlateHint")}>
          <Select value={f.plate_type} onChange={set("plate_type")} data-testid="sv-f-plate-type">
            {PLATE_TYPES.map((x) => (
              <option key={x} value={x}>
                {te(`plateType.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        {plated ? (
          <>
            <FormField id="sv-f-pla" label={tf("plateLettersAr")} required error={errors.plate_letters_ar}>
              <Input dir="rtl" lang="ar" maxLength={PLATE_LETTERS_MAX} value={f.plate_letters_ar} onChange={set("plate_letters_ar")} data-testid="sv-f-pla" />
            </FormField>
            <FormField id="sv-f-ple" label={tf("plateLettersEn")}>
              <Input className="ltr uppercase" maxLength={PLATE_LETTERS_MAX} value={f.plate_letters_en} onChange={set("plate_letters_en")} data-testid="sv-f-ple" />
            </FormField>
            <FormField id="sv-f-pld" label={tf("plateDigits")} required error={errors.plate_digits}>
              <Input className="ltr" inputMode="numeric" maxLength={4} value={f.plate_digits} onChange={set("plate_digits")} data-testid="sv-f-pld" />
            </FormField>
          </>
        ) : null}
        <FormField id="sv-f-fleet" label={tf("fleetNo")} required error={errors.fleet_no}>
          <Input className="ltr" maxLength={20} value={f.fleet_no} onChange={set("fleet_no")} data-testid="sv-f-fleet" />
        </FormField>
        <FormField id="sv-f-vin" label={tf("serialOrVin")} required error={errors.serial_or_vin}>
          <Input className="ltr" maxLength={30} value={f.serial_or_vin} onChange={set("serial_or_vin")} data-testid="sv-f-vin" />
        </FormField>
        <FormField id="sv-f-make" label={tf("makeModel")} required error={errors.make_model}>
          <Input maxLength={80} value={f.make_model} onChange={set("make_model")} data-testid="sv-f-make" />
        </FormField>
        <FormField id="sv-f-year" label={tf("year")} required>
          <Input type="number" inputMode="numeric" className="ltr" min={1990} value={f.year} onChange={set("year")} />
        </FormField>
        <FormField id="sv-f-colour" label={tf("colour")}>
          <Input maxLength={30} value={f.colour} onChange={set("colour")} />
        </FormField>
      </FormSection>
      <FormSection title={tf("documents")} description={tf("documentsHint")}>
        {plated ? (
          <>
            <FormField id="sv-f-ist" label={l.doc("istimara")} required error={errors.istimara_expiry}>
              <Input type="date" className="ltr" value={f.istimara_expiry} onChange={set("istimara_expiry")} data-testid="sv-f-ist" />
            </FormField>
            <FormField id="sv-f-mvpi" label={l.doc("mvpi")} required error={errors.mvpi_expiry}>
              <Input type="date" className="ltr" value={f.mvpi_expiry} onChange={set("mvpi_expiry")} data-testid="sv-f-mvpi" />
            </FormField>
          </>
        ) : null}
        <FormField id="sv-f-ins-no" label={tf("insuranceNo")} required error={errors.insurance_policy_no}>
          <Input className="ltr" maxLength={40} value={f.insurance_policy_no} onChange={set("insurance_policy_no")} data-testid="sv-f-ins-no" />
        </FormField>
        <FormField id="sv-f-ins" label={l.doc("insurance")} required error={errors.insurance_expiry}>
          <Input type="date" className="ltr" value={f.insurance_expiry} onChange={set("insurance_expiry")} data-testid="sv-f-ins" />
        </FormField>
        <FormField id="sv-f-oc-no" label={tf("operatingCardNo")} required={rule?.operating_card_required} hint={rule?.operating_card_required ? tf("operatingCardHint") : undefined}>
          <Input className="ltr" maxLength={30} value={f.operating_card_no} onChange={set("operating_card_no")} data-testid="sv-f-oc-no" />
        </FormField>
        <FormField id="sv-f-oc" label={tf("operatingCardExpiry")} required={rule?.operating_card_required}>
          <Input type="date" className="ltr" value={f.operating_card_expiry} onChange={set("operating_card_expiry")} data-testid="sv-f-oc" />
        </FormField>
      </FormSection>
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={busy} data-testid="sv-vehicle-save">
          {busy ? tc("saving") : t("register")}
        </Button>
        <Button type="button" variant="outline" onClick={() => router.push("/site-vehicles")}>
          {tc("cancel")}
        </Button>
      </div>
    </form>
  );
}

/* ═════════════ one vehicle: readiness, documents, hold, Phase 4 link ═════════════ */

export function SiteVehicleDetailPage({ id }: { id: string }) {
  return <SvGate>{(p) => <Detail project={p} id={id} />}</SvGate>;
}

type Act = "edit" | "verify" | "clear" | "withdraw" | null;

function Detail({ project, id }: { project: S["ProjectRead"]; id: string }) {
  const t = useTranslations("sv.vehicle");
  const tn = useTranslations("sv.nav");
  const te = useTranslations("enums");
  const l = useSvLabels();
  const q = useSiteVehicle(id);
  const caps = useSvCaps(project.id);
  const { date, dateTime } = useFormatters(project.id);
  const name = useLocalizedName();
  const [act, setAct] = useState<Act>(null);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const v = q.data;
  const withdrawn = v.status === "withdrawn";
  const canVerify = caps.manage && !caps.rep && !v.docs_verified && v.documents.length > 0 && !withdrawn;
  return (
    <div className="flex flex-col gap-6" data-testid="sv-vehicle-detail" data-readiness={v.readiness}>
      <div>
        <Breadcrumbs items={[{ label: tn("vehicles"), href: "/site-vehicles" }, { label: v.vehicle_no }]} />
        <PageHeader
          title={<bdi className="ltr">{v.vehicle_no}</bdi>}
          badge={
            <>
              <ReadinessBadge readiness={v.readiness} />
              <PrototypeBadge />
            </>
          }
          description={`${v.make_model} · ${l.useClass(v.use_class)} · ${v.engagement.short_code}`}
          actions={
            withdrawn ? null : (
              <>
                {caps.record ? (
                  <Button asChild variant="outline">
                    <Link href={`/site-vehicles/checks/new?vehicle=${v.id}`} data-testid="sv-record-check">
                      <ClipboardCheck aria-hidden />
                      {t("recordCheck")}
                    </Link>
                  </Button>
                ) : null}
                {caps.record ? (
                  <Button asChild variant="outline">
                    <Link href={`/site-vehicles/journeys/new?vehicle=${v.id}`} data-testid="sv-plan-journey">
                      <Route aria-hidden />
                      {t("planJourney")}
                    </Link>
                  </Button>
                ) : null}
                {caps.manage ? (
                  <Button variant="outline" onClick={() => setAct("edit")} data-testid="sv-edit">
                    <Pencil aria-hidden />
                    {t("edit")}
                  </Button>
                ) : null}
                {canVerify ? (
                  <Button onClick={() => setAct("verify")} data-testid="sv-verify">
                    <ShieldCheck aria-hidden />
                    {t("verify")}
                  </Button>
                ) : null}
              </>
            )
          }
        />
      </div>
      {v.hold ? (
        <Alert tone="danger" data-testid="sv-hold">
          <span className="flex flex-col gap-1">
            <span className="inline-flex items-center gap-2 font-semibold">
              <Wrench aria-hidden className="size-4" />
              {t("holdTitle", { date: date(v.hold.set_on) })}
            </span>
            <span>
              {t("holdCheck")}{" "}
              <Link href={`/site-vehicles/checks/${v.hold.check_id}`} className="font-medium underline">
                <bdi className="ltr">{v.hold.check_no}</bdi>
              </Link>
              {" · "}
              {t("holdItems")} <bdi className="ltr">{v.hold.failed_items.join(", ")}</bdi>
              {v.hold.ca_ref ? (
                <>
                  {" · "}
                  {t("holdCa")}{" "}
                  {v.hold.ca_id ? (
                    <Link href={`/actions/${v.hold.ca_id}`} className="font-medium underline" data-testid="sv-hold-ca">
                      <bdi className="ltr">{v.hold.ca_ref}</bdi>
                    </Link>
                  ) : (
                    <bdi className="ltr">{v.hold.ca_ref}</bdi>
                  )}
                </>
              ) : null}
            </span>
            <span className="text-xs">{t("holdHint")}</span>
          </span>
        </Alert>
      ) : null}
      {v.readiness === "not_certified" && v.phase4 ? (
        <Alert tone="danger" data-testid="sv-not-certified">
          {t("notCertified", { no: v.phase4.equipment_no, status: te(`serviceStatus.${v.phase4.service_status}`) })}
        </Alert>
      ) : null}
      <ApiWarnings warnings={v.warnings} />
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("siteUse")}</CardTitle>
        </CardHeader>
        <CardContent>
          <FieldList>
            <FieldItem label={t("scope")}>{l.scope(v.site_scope)}</FieldItem>
            <FieldItem label={t("useClass")}>{l.useClass(v.use_class)}</FieldItem>
            <FieldItem label={t("group")}>{l.group(v.driver_group)}</FieldItem>
            {v.seats ? <FieldItem label={t("seats")}>{v.seats}</FieldItem> : null}
            <FieldItem label={t("readiness")}>
              <span className="flex flex-col items-start gap-1">
                <ReadinessBadge readiness={v.readiness} testId="sv-readiness-field" />
                {v.readiness_reasons.length ? <ReasonList reasons={v.readiness_reasons} /> : null}
              </span>
            </FieldItem>
            <FieldItem label={t("idle")}>{v.idle_from ? `${date(v.idle_from)} – ${v.idle_to ? date(v.idle_to) : "…"}` : "—"}</FieldItem>
            <FieldItem label={t("today")}>
              <TodayCell v={v} />
            </FieldItem>
            <FieldItem label={t("phase4")}>
              {v.phase4 ? (
                <span data-testid="sv-phase4">
                  <bdi className="ltr font-medium">{v.phase4.equipment_no}</bdi> · {te(`serviceStatus.${v.phase4.service_status}`)}
                  {v.phase4.operator_code ? (
                    <span className="block text-xs text-muted-foreground">
                      {t("operatorCode")} <bdi className="ltr">{v.phase4.operator_code}</bdi>
                    </span>
                  ) : null}
                  <span className="block text-xs text-muted-foreground">{t("phase4ReadOnly")}</span>
                </span>
              ) : (
                "—"
              )}
            </FieldItem>
            {withdrawn ? <FieldItem label={t("withdrawnOn")}>{date(v.withdrawn_on)}</FieldItem> : null}
          </FieldList>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("documents")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {v.documents.length ? (
            <ul className="flex flex-wrap gap-2" data-testid="sv-docs">
              {v.documents.map((d) => (
                <li key={d.kind}>
                  <DocChip d={d} date={date} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">{v.phase4 ? t("phase4Docs") : t("noDocs")}</p>
          )}
          <p className="text-sm" data-testid="sv-verified" data-verified={v.docs_verified}>
            {v.docs_verified ? (
              <span className="inline-flex items-center gap-1 font-medium text-success">
                <ShieldCheck aria-hidden className="size-4" />
                {t("verifiedBy", { by: v.docs_verified_by ? name(v.docs_verified_by.full_name_en, v.docs_verified_by.full_name_ar) : "—", at: dateTime(v.docs_verified_at) })}
              </span>
            ) : v.documents.length ? (
              <span className="inline-flex items-center gap-1 font-medium text-warning">
                <ShieldQuestion aria-hidden className="size-4" />
                {t("unverified")}
              </span>
            ) : null}
          </p>
          <FieldList>
            <FieldItem label={t("plate")}>{v.plate_type === "none" ? t("noPlate") : <Plate ar={v.plate_letters_ar} en={v.plate_letters_en} digits={v.plate_digits} />}</FieldItem>
            <FieldItem label={t("fleetNo")} ltr>
              {v.fleet_no}
            </FieldItem>
            <FieldItem label={t("serialOrVin")} ltr>
              {v.serial_or_vin}
            </FieldItem>
            <FieldItem label={t("insuranceNo")} ltr>
              {v.insurance_policy_no}
            </FieldItem>
            {v.operating_card_no ? (
              <FieldItem label={t("operatingCard")} ltr>
                {v.operating_card_no}
              </FieldItem>
            ) : null}
            <FieldItem label={t("phase2")}>
              <Link href={`/vehicles/${v.id}`} className="text-primary hover:underline">
                {t("phase2Link")}
              </Link>
            </FieldItem>
          </FieldList>
        </CardContent>
      </Card>
      <HistoryPanel entityType="vehicle" entityId={v.id} />
      {caps.manage && !withdrawn ? (
        <RecordActions testId="sv-record-actions">
          {v.readiness === "defect_hold" || v.hold ? (
            <Button variant="outline" onClick={() => setAct("clear")} data-testid="sv-clear-hold">
              <CalendarPlus aria-hidden />
              {t("clearHold")}
            </Button>
          ) : null}
          <Button variant="destructive-outline" onClick={() => setAct("withdraw")} data-testid="sv-withdraw">
            <Ban aria-hidden />
            {t("withdraw")}
          </Button>
        </RecordActions>
      ) : null}
      {act === "edit" ? <EditDialog v={v} onClose={() => setAct(null)} /> : null}
      {act === "verify" ? <VerifyDialog v={v} onClose={() => setAct(null)} /> : null}
      {act === "clear" ? <ClearHoldDialog v={v} onClose={() => setAct(null)} /> : null}
      {act === "withdraw" ? <WithdrawDialog v={v} onClose={() => setAct(null)} /> : null}
    </div>
  );
}

/** Readiness reasons: document kinds, "defect_hold:VPC-…", "phase4:out_of_service". */
function ReasonList({ reasons }: { reasons: string[] }) {
  const t = useTranslations("sv.vehicle");
  const te = useTranslations("enums");
  const l = useSvLabels();
  return (
    <ul className="text-xs text-muted-foreground" data-testid="sv-reasons">
      {reasons.map((r) => {
        const [k, v] = r.split(":");
        return (
          <li key={r}>
            {k === "defect_hold" ? (
              <>
                {t("reasonHold")} <bdi className="ltr">{v}</bdi>
              </>
            ) : k === "phase4" ? (
              <>
                {t("reasonPhase4")} {te.has(`serviceStatus.${v}` as "serviceStatus.in_service") ? te(`serviceStatus.${v}` as "serviceStatus.in_service") : v}
              </>
            ) : k === "withdrawn" || k === "idle" ? (
              l.readiness(k)
            ) : (
              t("reasonDoc", { doc: l.doc(k ?? r) })
            )}
          </li>
        );
      })}
    </ul>
  );
}

function EditDialog({ v, onClose }: { v: Vehicle; onClose: () => void }) {
  const t = useTranslations("sv.vehicle");
  const tf = useTranslations("sv.form");
  const l = useSvLabels();
  const rules = useUseClassRules();
  const refresh = useSvRefresh();
  const warn = useWarningToasts();
  const [f, setF] = useState({
    use_class: v.use_class ?? "",
    seats: v.seats ? String(v.seats) : "",
    istimara_expiry: v.istimara_expiry ?? "",
    insurance_expiry: v.insurance_expiry,
    mvpi_expiry: v.mvpi_expiry ?? "",
    operating_card_no: v.operating_card_no ?? "",
    operating_card_expiry: v.operating_card_expiry ?? "",
    idle_from: v.idle_from ?? "",
    idle_to: v.idle_to ?? "",
  });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  const rule = rules(f.use_class);
  const plated = v.plate_type !== "none";
  return (
    <StepDialog
      title={t("edit")}
      description={tf("editHint")}
      confirmLabel={t("save")}
      testId="sv-edit-save"
      wide
      onConfirm={async () => {
        const body: S["SiteVehUpdate"] = {
          use_class: (f.use_class || null) as S["SiteVehUseClass"] | null,
          seats: f.seats ? Number(f.seats) : null,
          insurance_expiry: f.insurance_expiry || null,
          operating_card_no: f.operating_card_no.trim() || null,
          operating_card_expiry: f.operating_card_expiry || null,
          idle_from: f.idle_from || null,
          idle_to: f.idle_to || null,
        };
        if (plated) {
          body.istimara_expiry = f.istimara_expiry || null;
          body.mvpi_expiry = f.mvpi_expiry || null;
        }
        const u = await unwrap(api.PATCH("/api/v1/site-vehicles/{vehicle_id}", { params: { path: { vehicle_id: v.id } }, body }));
        await refresh();
        warn(u.warnings);
        toast.success(t("saved"));
      }}
      onClose={onClose}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="sv-e-class" label={t("useClass")}>
          <Select value={f.use_class} onChange={set("use_class")} data-testid="sv-e-class">
            {USE_CLASSES.map((u) => (
              <option key={u} value={u}>
                {l.useClass(u)}
              </option>
            ))}
          </Select>
        </FormField>
        {rule?.seats_required ? (
          <FormField id="sv-e-seats" label={t("seats")} hint={tf("seatsRange")}>
            <Input type="number" inputMode="numeric" className="ltr" value={f.seats} onChange={set("seats")} data-testid="sv-e-seats" />
          </FormField>
        ) : null}
        {plated ? (
          <>
            <FormField id="sv-e-ist" label={l.doc("istimara")}>
              <Input type="date" className="ltr" value={f.istimara_expiry} onChange={set("istimara_expiry")} />
            </FormField>
            <FormField id="sv-e-mvpi" label={l.doc("mvpi")}>
              <Input type="date" className="ltr" value={f.mvpi_expiry} onChange={set("mvpi_expiry")} />
            </FormField>
          </>
        ) : null}
        <FormField id="sv-e-ins" label={l.doc("insurance")}>
          <Input type="date" className="ltr" value={f.insurance_expiry} onChange={set("insurance_expiry")} data-testid="sv-e-ins" />
        </FormField>
        <FormField id="sv-e-oc-no" label={tf("operatingCardNo")}>
          <Input className="ltr" maxLength={30} value={f.operating_card_no} onChange={set("operating_card_no")} data-testid="sv-e-oc-no" />
        </FormField>
        <FormField id="sv-e-oc" label={tf("operatingCardExpiry")}>
          <Input type="date" className="ltr" value={f.operating_card_expiry} onChange={set("operating_card_expiry")} data-testid="sv-e-oc" />
        </FormField>
        <FormField id="sv-e-idle-from" label={tf("idleFrom")} hint={tf("idleHint")}>
          <Input type="date" className="ltr" value={f.idle_from} onChange={set("idle_from")} data-testid="sv-e-idle-from" />
        </FormField>
        <FormField id="sv-e-idle-to" label={tf("idleTo")}>
          <Input type="date" className="ltr" value={f.idle_to} onChange={set("idle_to")} data-testid="sv-e-idle-to" />
        </FormField>
      </div>
      <p className="text-xs text-muted-foreground">{tf("docsResetHint")}</p>
    </StepDialog>
  );
}

function VerifyDialog({ v, onClose }: { v: Vehicle; onClose: () => void }) {
  const t = useTranslations("sv.vehicle");
  const refresh = useSvRefresh();
  return (
    <StepDialog
      title={t("verify")}
      description={t("verifyHint", { no: v.vehicle_no })}
      confirmLabel={t("verifyConfirm")}
      testId="sv-verify-confirm"
      onConfirm={async () => {
        await unwrap(api.POST("/api/v1/site-vehicles/{vehicle_id}/verify-documents", { params: { path: { vehicle_id: v.id } } }));
        await refresh();
        toast.success(t("verified"));
      }}
      onClose={onClose}
    />
  );
}

function ClearHoldDialog({ v, onClose }: { v: Vehicle; onClose: () => void }) {
  const t = useTranslations("sv.vehicle");
  const tf = useTranslations("fu.common");
  const refresh = useSvRefresh();
  const [note, setNote] = useState("");
  const n = note.trim().length;
  return (
    <StepDialog
      title={t("clearHold")}
      description={t("clearHoldHint")}
      confirmLabel={t("clearHoldConfirm")}
      testId="sv-clear-confirm"
      disabled={n < 10}
      onConfirm={async () => {
        await unwrap(api.POST("/api/v1/site-vehicles/{vehicle_id}/clear-hold", { params: { path: { vehicle_id: v.id } }, body: { repair_note: note.trim() } }));
        await refresh();
        toast.success(t("holdCleared"));
      }}
      onClose={onClose}
    >
      <FormField id="sv-repair" label={t("repairNote")} required hint={tf("reasonMin", { min: 10, n })}>
        <Textarea maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} data-testid="sv-repair-note" />
      </FormField>
    </StepDialog>
  );
}

function WithdrawDialog({ v, onClose }: { v: Vehicle; onClose: () => void }) {
  const t = useTranslations("sv.vehicle");
  const tf = useTranslations("fu.common");
  const refresh = useSvRefresh();
  const [reason, setReason] = useState("");
  const [on, setOn] = useState("");
  const n = reason.trim().length;
  return (
    <StepDialog
      title={t("withdraw")}
      description={t("withdrawHint", { no: v.vehicle_no })}
      confirmLabel={t("withdrawConfirm")}
      destructive
      testId="sv-withdraw-confirm"
      disabled={n < 10}
      onConfirm={async () => {
        await unwrap(api.POST("/api/v1/site-vehicles/{vehicle_id}/withdraw", { params: { path: { vehicle_id: v.id } }, body: { reason: reason.trim(), withdrawn_on: on || null } }));
        await refresh();
        toast.success(t("withdrawn"));
      }}
      onClose={onClose}
    >
      <FormField id="sv-wd-reason" label={tf("reason")} required hint={tf("reasonMin", { min: 10, n })}>
        <Textarea maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} data-testid="sv-withdraw-reason" />
      </FormField>
      <FormField id="sv-wd-on" label={t("withdrawnOn")}>
        <Input type="date" className="ltr" value={on} onChange={(e) => setOn(e.target.value)} />
      </FormField>
    </StepDialog>
  );
}
