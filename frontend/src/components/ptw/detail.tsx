"use client";
import { Archive, CircleDashed, CirclePlay, CircleX, ClipboardList, Clock, FileCheck2, FileStack, Hand, Pause, Pencil, Printer, ShieldAlert, ShieldCheck, TriangleAlert } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Attachments } from "@/components/common/attachments";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { HistoryPanel } from "@/components/common/history-panel";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { PageHeader } from "@/components/common/page-header";
import { useMeData } from "@/components/shell/me-context";
import { HookConditions } from "@/components/cert/hook-ui";
import { Link } from "@/i18n/navigation";
import type { Schemas } from "@/lib/api/client";
import { useHandovers, usePermit, usePermitGasTests, useShifts, useSuspensions } from "@/lib/api/ptw";
import { joinList, useLocalizedName } from "@/lib/i18n-helpers";
import { can } from "@/lib/permissions";
import { RegimeBadge, RestMinutes } from "@/components/heat/common";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { PermitActionBar, PermitStepDialog, type Step } from "./actions";
import { BlockerList, Countdown, GasStatusBadge, HighRiskBadge, PermitNo, RiskBandBadge, SignatureList, SimopsResultBadge, TypeChips, WarningList, userLabel, WorkerRefLabel } from "./common";
import { canEditLines, ChecklistPanel, CrewPanel, DocumentsPanel, EquipmentPanel } from "./crew";
import { ExemptionsPanel, FieldRecords } from "./field-records";
import { CreatePermitJsa } from "./jsa";
import { EditSectionsButton, SectionsEditor, sectionTypes, SectionView } from "./sections";

type S = Schemas;
type Permit = S["PermitRead"];

const TABS = ["overview", "crew", "sections", "jsa", "gas", "isolations", "simops", "checklists", "shifts", "signatures", "history"] as const;
type Tab = (typeof TABS)[number];
const LIVE: S["PermitStatus"][] = ["issued", "active", "suspended"];

function hhmm(t: string): string {
  return t.slice(0, 5);
}

/** The permit page: header, lifecycle bar, blockers, live timers and one tab per part of the permit. */
export function PermitDetail({ id }: { id: string }) {
  const t = useTranslations("permitDetail");
  const tc = useTranslations("common");
  const locale = useLocale();
  const me = useMeData();
  const s = useSearchState();
  const tab = (TABS as readonly string[]).includes(s.get("tab") ?? "") ? (s.get("tab") as Tab) : "overview";
  const q = usePermit(id, { refetchInterval: 30_000 });
  const [step, setStep] = useState<Step | null>(null);
  const { dateTime } = useFormatters(q.data?.project_id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const p = q.data;
  const live = LIVE.includes(p.status);
  const editDraft = p.status === "draft" && canEditLines(me, p);
  const counts: Partial<Record<Tab, number>> = {
    crew: p.crew_count,
    isolations: p.isolations.length,
    simops: p.simops.filter((c) => c.status === "open").length,
    signatures: p.signatures.length,
  };
  return (
    <div className="flex flex-col gap-5" data-testid="permit-detail" data-status={p.status}>
      <div>
        <Breadcrumbs items={[{ label: t("permits"), href: "/permits" }, { label: p.display_no }]} />
        <PageHeader
          title={<bdi className="ltr" data-testid="permit-no">{p.display_no}</bdi>}
          description={<span dir="auto">{p.title}</span>}
          actions={
            <>
              {editDraft ? (
                <Button variant="outline" asChild>
                  <Link href={`/permits/${p.id}/edit`} data-testid="edit-permit">
                    <Pencil aria-hidden />
                    {tc("edit")}
                  </Link>
                </Button>
              ) : null}
              {p.status !== "draft" ? (
                <Button variant="outline" asChild>
                  <Link href={`/permits/${p.id}/print`} data-testid="print-permit">
                    <Printer aria-hidden />
                    {tc("print")}
                  </Link>
                </Button>
              ) : null}
              {p.status === "closed" ? (
                <Button variant="outline" asChild>
                  <Link href={`/permits/${p.id}/closure-pack`} data-testid="closure-pack">
                    <FileStack aria-hidden />
                    {t("closurePack")}
                  </Link>
                </Button>
              ) : null}
            </>
          }
        />
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <TypeChips types={p.work_types} primary={p.primary_type} />
          <HighRiskBadge show={p.high_risk} />
          {p.gas.required ? <GasStatusBadge status={p.gas.status} /> : null}
        </div>
      </div>

      <PermitStatePanel p={p} />
      <PermitActionBar permit={p} onStep={setStep} />
      {step ? <PermitStepDialog permit={p} step={step} onClose={() => setStep(null)} /> : null}

      {p.post_expiry_check_pending ? (
        <Alert tone="warning" data-testid="post-expiry-pending">
          {t("postExpiryPending")}
        </Alert>
      ) : null}
      {p.closure_request && p.status === "active" ? (
        <Alert tone="info" data-testid="closure-requested">
          {t("closureRequested", { name: userLabel(p.closure_request.requested_by, locale), at: dateTime(p.closure_request.requested_at) })}
        </Alert>
      ) : null}
      {p.copied_from ? (
        <Alert tone="info">
          {t("copiedFrom")} <PermitNo p={p.copied_from} />
          {p.copied_conditions.length ? <span className="block text-xs">{t("copiedConditions", { list: p.copied_conditions.join(", ") })}</span> : null}
        </Alert>
      ) : null}

      <Card id="readiness">
        <CardHeader>
          <CardTitle className="text-base">{t("blockers")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <BlockerList items={p.blockers} />
          <WarningList items={p.warnings} />
          {p.hook_conditions?.length ? <HookConditions items={p.hook_conditions} /> : null}
        </CardContent>
      </Card>

      <nav aria-label={t("parts")} className="-mx-4 overflow-x-auto border-b px-4 [scrollbar-width:none] sm:mx-0 sm:px-0">
        <ul className="flex gap-1" role="tablist">
          {TABS.map((k) => (
            <li key={k}>
              <button
                type="button"
                role="tab"
                aria-selected={tab === k}
                data-testid={`tab-${k}`}
                onClick={() => s.set({ tab: k === "overview" ? null : k })}
                className={cn(
                  "-mb-px inline-flex min-h-touch items-center gap-1 border-b-[3px] px-3 text-sm whitespace-nowrap transition-colors",
                  tab === k ? "border-primary font-semibold text-foreground" : "border-transparent text-muted-foreground hover:border-input hover:text-foreground",
                )}
              >
                {t(`tab.${k}`)}
                {counts[k] ? <span className="rounded-full bg-muted px-1.5 text-xs tabular-nums">{counts[k]}</span> : null}
              </button>
            </li>
          ))}
        </ul>
      </nav>

      <div role="tabpanel" data-testid={`panel-${tab}`}>
        {tab === "overview" ? <Overview p={p} /> : null}
        {tab === "crew" ? (
          <div className="flex flex-col gap-5">
            <CrewPanel permit={p} />
            <EquipmentPanel permit={p} />
            <DocumentsPanel permit={p} />
          </div>
        ) : null}
        {tab === "sections" ? <SectionsTab p={p} /> : null}
        {tab === "jsa" ? <JsaTab p={p} /> : null}
        {tab === "gas" ? <GasTab p={p} /> : null}
        {tab === "isolations" ? <IsolationsTab p={p} /> : null}
        {tab === "simops" ? <SimopsTab p={p} /> : null}
        {tab === "checklists" ? (
          <div className="flex flex-col gap-5">
            <ChecklistPanel permit={p} checklist={p.pre_issue_checklist} />
            {["active", "suspended", "closed"].includes(p.status) ? <ChecklistPanel permit={p} checklist={p.closure_checklist} /> : null}
          </div>
        ) : null}
        {tab === "shifts" ? <ShiftsTab p={p} /> : null}
        {tab === "signatures" ? (
          <Card>
            <CardContent className="pt-5">
              <SignatureList items={p.signatures} />
            </CardContent>
          </Card>
        ) : null}
        {tab === "history" ? (
          <div className="flex flex-col gap-5">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">{t("attachments")}</CardTitle>
              </CardHeader>
              <CardContent>
                <Attachments ownerType="permit_attachment" ownerId={p.id} canUpload={canEditLines(me, p) || live} />
              </CardContent>
            </Card>
            <HistoryPanel entityType="permit" entityId={p.id} projectId={p.project_id} />
          </div>
        ) : null}
      </div>
    </div>
  );
}

const STATE_TONE: Record<S["PermitStatus"], "success" | "warning" | "danger" | "info" | "neutral"> = {
  draft: "info",
  requested: "info",
  reviewed: "info",
  approved: "info",
  issued: "info",
  active: "success",
  suspended: "warning",
  closed: "neutral",
  cancelled: "neutral",
  expired: "danger",
};
const STATE_ICON: Record<S["PermitStatus"], typeof CirclePlay> = {
  draft: CircleDashed,
  requested: Clock,
  reviewed: ShieldCheck,
  approved: ShieldCheck,
  issued: FileCheck2,
  active: CirclePlay,
  suspended: Hand,
  closed: Archive,
  cancelled: CircleX,
  expired: TriangleAlert,
};
const TONE_CLS = {
  success: "border-success/40 bg-success-bg [--tone:var(--status-success)]",
  warning: "border-warning/50 bg-warning-bg [--tone:var(--status-warning)]",
  danger: "border-danger/40 bg-danger-bg [--tone:var(--status-danger)]",
  info: "border-info/40 bg-info-bg [--tone:var(--status-info)]",
  neutral: "border-neutral/40 bg-neutral-bg [--tone:var(--status-neutral)]",
};

/**
 * One-glance permit state for the field: the status in large type with its own icon and a plain-language line
 * ("Work in progress", "Work stopped…", "Not valid for work until issued"), the reason, today's window, the
 * blocker count and the live countdowns. Colour is never alone (icon + word + sentence).
 */
function PermitStatePanel({ p }: { p: Permit }) {
  const t = useTranslations("ptwDesign");
  const te = useTranslations("enums");
  const { prefs, dateTime } = useFormatters(p.project_id);
  const paused = p.status === "active" && Boolean(p.current_shift?.paused_now);
  const tone = paused ? "warning" : STATE_TONE[p.status];
  const Icon = paused ? Pause : STATE_ICON[p.status];
  const hm = (iso: string) => new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: prefs.timeZone }).format(new Date(iso));
  const live = LIVE.includes(p.status);
  const n = p.blockers.length;
  return (
    <section
      className={cn("flex flex-col gap-3 rounded-xl border-2 border-s-8 p-4 [border-inline-start-color:var(--tone)]", TONE_CLS[tone])}
      data-testid="permit-status"
      data-status={p.status}
      data-tone={tone}
      aria-label={t("stateLabel")}
    >
      <div className="flex items-start gap-3">
        <Icon aria-hidden className="mt-0.5 size-9 shrink-0 text-[var(--tone)]" strokeWidth={2.25} />
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="text-2xl leading-tight font-bold text-[var(--tone)]" data-testid="permit-state-word">
              {te(`permitStatus.${p.status}`)}
            </span>
            {p.status_reason ? (
              <span className="text-base font-semibold" data-testid="status-reason">
                {te(`statusReason.${p.status_reason}`)}
              </span>
            ) : null}
            {paused ? <span className="text-base font-semibold">{t("pausedNow")}</span> : null}
          </p>
          <p className="mt-0.5 text-sm font-medium">{paused ? t("state.paused") : t(`state.${p.status}`)}</p>
          {p.status_detail && (p.status === "suspended" || p.status === "cancelled" || p.status === "expired") ? (
            <p className="mt-1 text-sm whitespace-pre-line text-muted-foreground" dir="auto">
              {p.status_detail}
            </p>
          ) : null}
          {live ? (
            <p className="mt-1 text-sm" data-testid="permit-window-state">
              {p.current_window ? (
                <>
                  {t("inWindow")} <bdi className="ltr font-semibold tabular-nums">{hm(p.current_window.end_at)}</bdi>
                </>
              ) : p.next_window ? (
                <>
                  {t("outsideWindow")} <span className="ltr font-semibold">{dateTime(p.next_window.start_at)}</span>
                </>
              ) : (
                t("noMoreWindows")
              )}
            </p>
          ) : null}
        </div>
      </div>
      {n || p.status === "draft" || ["requested", "reviewed", "approved", "issued", "suspended"].includes(p.status) ? (
        <a
          href="#readiness"
          className={cn(
            "inline-flex min-h-touch items-center gap-2 self-start rounded-md border px-3 text-sm font-semibold",
            n ? "border-danger/50 bg-surface text-danger" : "border-success/40 bg-surface text-success",
          )}
          data-testid="permit-blocker-count"
          data-count={n}
        >
          {n ? <ShieldAlert aria-hidden className="size-5" /> : <ShieldCheck aria-hidden className="size-5" />}
          {n ? t("blockersCount", { n }) : t("noBlockersShort")}
        </a>
      ) : null}
      <LiveTimers p={p} />
    </section>
  );
}

/** Live countdowns: start window after the gas test, next periodic test, shift end and permit end. */
function LiveTimers({ p }: { p: Permit }) {
  const t = useTranslations("permitDetail");
  const timers: { key: string; to: string; label: string; warn: number }[] = [];
  if (p.status === "issued" && p.gas.required && p.gas.valid_for_start_until) timers.push({ key: "gas-start", to: p.gas.valid_for_start_until, label: t("gasStartBy"), warn: 10 });
  if (p.status === "active" && p.gas.next_due_at) timers.push({ key: "gas-retest", to: p.gas.next_due_at, label: t("gasRetest"), warn: 15 });
  if (p.current_shift && !p.current_shift.ended_at) timers.push({ key: "shift-end", to: p.current_shift.planned_end_at, label: t("shiftEnds"), warn: 30 });
  if (LIVE.includes(p.status)) timers.push({ key: "permit-end", to: p.valid_to_at, label: t("permitEnds"), warn: 60 });
  if (!timers.length) return null;
  return (
    <div className="flex flex-wrap gap-2" data-testid="live-timers">
      {timers.map((x) => (
        <Countdown key={x.key} to={x.to} label={x.label} warnMinutes={x.warn} testId={`timer-${x.key}`} icon="clock" size="lg" />
      ))}
    </div>
  );
}

function Overview({ p }: { p: Permit }) {
  const t = useTranslations("permitDetail");
  const tp = useTranslations("permits");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const name = useLocalizedName();
  const { dateTime } = useFormatters(p.project_id);
  return (
    <div className="flex flex-col gap-5">
      <Card>
        <CardContent className="pt-5">
          <FieldList>
            <FieldItem label={tc("site")}>{`${p.site.code} — ${name(p.site.name_en, p.site.name_ar)}`}</FieldItem>
            <FieldItem label={tp("zones")}>
              {p.zones.map((z) => (
                <span key={z.id} className="me-2">
                  <bdi className="ltr font-mono text-xs">{z.code}</bdi> {name(z.name_en, z.name_ar)}
                </span>
              ))}
            </FieldItem>
            <FieldItem label={tp("location")}>
              <span dir="auto">{p.location_desc}</span>
            </FieldItem>
            <FieldItem label={t("grid")} ltr>
              {p.grid_x_m && p.grid_y_m ? `${p.grid_x_m}, ${p.grid_y_m}${p.elevation_m ? ` · ${p.level_code ?? ""} ${p.elevation_m} m` : ""}` : "—"}
            </FieldItem>
            <FieldItem label={tc("contractor")}>{p.engagement.short_code}</FieldItem>
            <FieldItem label={tp("exposure")}>{te(`exposure.${p.exposure}`)}</FieldItem>
            {p.heat_workload ? (
              <FieldItem label={tp("heatWorkload")}>
                <span data-testid="permit-heat-workload" data-workload={p.heat_workload}>
                  {te(`workload.${p.heat_workload}`)}
                </span>
                <span className="block text-xs text-muted-foreground">
                  {te(`clothing.${p.heat_clothing ?? "work_clothes"}`)}
                  {p.heat_hood ? ` · ${tp("heatHood")}` : ""}
                </span>
              </FieldItem>
            ) : null}
            {p.current_shift?.heat_regime ? (
              <FieldItem label={tp("heatRegimeNow")}>
                <span className="flex flex-wrap items-center gap-2" data-testid="permit-heat-regime">
                  <RegimeBadge regime={p.current_shift.heat_regime} />
                  <RestMinutes regime={p.current_shift.heat_regime} minutes={p.current_shift.rest_minutes_per_hour} />
                </span>
              </FieldItem>
            ) : null}
            <FieldItem label={tp("validity")}>
              <span className="ltr">{dateTime(p.valid_from_at)}</span> – <span className="ltr">{dateTime(p.valid_to_at)}</span>
            </FieldItem>
            <FieldItem label={t("windows")}>
              {p.windows.map((w, i) => (
                <span key={i} className="block text-sm">
                  <bdi className="ltr tabular-nums">
                    {hhmm(w.start_local)}–{hhmm(w.end_local)}
                  </bdi>{" "}
                  <span className="text-xs text-muted-foreground">{w.weekdays.length === 7 ? t("everyDay") : joinList(w.weekdays.map((d) => te(`weekday.${d}`)))}</span>
                </span>
              ))}
            </FieldItem>
            <FieldItem label={t("currentWindow")}>{p.current_window ? `${dateTime(p.current_window.start_at)} – ${dateTime(p.current_window.end_at)}` : "—"}</FieldItem>
            <FieldItem label={t("nextWindow")}>{p.next_window ? `${dateTime(p.next_window.start_at)} – ${dateTime(p.next_window.end_at)}` : "—"}</FieldItem>
            <FieldItem label={tp("receiver")}>{userLabel(p.receiver, locale)}</FieldItem>
            <FieldItem label={tp("areaAuthority")}>{p.area_authority ? userLabel(p.area_authority, locale) : "—"}</FieldItem>
            <FieldItem label={tp("issuer")}>{p.issuer ? userLabel(p.issuer, locale) : "—"}</FieldItem>
            {p.high_risk ? <FieldItem label={tp("hseReviewer")}>{p.hse_reviewer ? userLabel(p.hse_reviewer, locale) : "—"}</FieldItem> : null}
            <FieldItem label={t("supervisor")}>
              <WorkerRefLabel w={p.supervisor} />
            </FieldItem>
            {p.high_risk ? (
              <FieldItem label={t("highRiskReasons")}>
                <span dir="auto">{p.high_risk_reasons_en.join("; ") || "—"}</span>
              </FieldItem>
            ) : null}
            <FieldItem label={tp("flammables")}>{p.flammables_in_use ? tc("yes") : tc("no")}</FieldItem>
            <FieldItem label={tp("engine")}>{p.combustion_engine_plant ? tc("yes") : tc("no")}</FieldItem>
          </FieldList>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("scope")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 text-sm">
          <p className="whitespace-pre-line" dir="auto">
            {locale === "ar" && p.scope_ar ? p.scope_ar : p.scope_en}
          </p>
          {p.conditions_en || p.conditions_ar ? (
            <div>
              <p className="text-xs font-medium text-muted-foreground">{t("conditions")}</p>
              <p className="whitespace-pre-line" dir="auto">
                {locale === "ar" && p.conditions_ar ? p.conditions_ar : p.conditions_en}
              </p>
            </div>
          ) : null}
          <div>
            <p className="text-xs font-medium text-muted-foreground">{tp("emergency")}</p>
            <p className="whitespace-pre-line" dir="auto">
              {p.emergency_info}
            </p>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{tp("s.links")}</CardTitle>
        </CardHeader>
        <CardContent>
          <FieldList>
            <FieldItem label={tp("linkedWaps")}>
              {p.waps.length
                ? p.waps.map((w) => (
                    <span key={w.id} className="me-3 inline-flex items-center gap-1">
                      <Link href={`/waps/${w.id}`} className="ltr text-primary hover:underline">
                        {w.wap_no}
                      </Link>
                      <StatusBadge status={w.status} label={te(`wapStatus.${w.status}`)} />
                    </span>
                  ))
                : "—"}
            </FieldItem>
            <FieldItem label={tp("linkedObs")}>
              {p.obstacle_clearances.length
                ? p.obstacle_clearances.map((o) => (
                    <Link key={o.id} href={`/obstacle-clearances/${o.id}`} className="ltr me-3 text-primary hover:underline">
                      {o.obs_no}
                    </Link>
                  ))
                : "—"}
            </FieldItem>
            <FieldItem label={t("incidents")}>
              {p.incidents.length
                ? p.incidents.map((i) => (
                    <Link key={i.id} href={`/incidents/${i.id}`} className="ltr me-3 text-primary hover:underline">
                      {i.ref}
                    </Link>
                  ))
                : "—"}
            </FieldItem>
          </FieldList>
        </CardContent>
      </Card>
      <ExemptionsPanel permit={p} />
    </div>
  );
}

function SectionsTab({ p }: { p: Permit }) {
  const t = useTranslations("permitDetail");
  const me = useMeData();
  const [editing, setEditing] = useState(false);
  const types = sectionTypes(p);
  const editable = p.status === "draft" && canEditLines(me, p);
  if (!types.length) return <EmptyState message={t("noSections")} />;
  if (editing) return <SectionsEditor permit={p} onDone={() => setEditing(false)} />;
  return (
    <div className="flex flex-col gap-5">
      {types.map((ty) => (
        <div key={ty} className="flex flex-col gap-3">
          <SectionView permit={p} type={ty} actions={editable ? <EditSectionsButton onClick={() => setEditing(true)} /> : undefined} />
          {p.status === "active" || p.status === "suspended" ? <FieldRecords permit={p} type={ty} /> : null}
        </div>
      ))}
    </div>
  );
}

function JsaTab({ p }: { p: Permit }) {
  const t = useTranslations("permitDetail");
  const te = useTranslations("enums");
  if (!p.jsa)
    return (
      <div className="flex flex-col items-start gap-3">
        <EmptyState message={t("noJsa")} />
        <CreatePermitJsa permit={p} />
      </div>
    );
  return (
    <Card data-testid="jsa-summary">
      <CardContent className="flex flex-wrap items-center gap-3 pt-5">
        <ClipboardList aria-hidden className="size-5 text-muted-foreground" />
        <Link href={`/jsas/${p.jsa.id}`} className="ltr font-semibold text-primary hover:underline" data-testid="open-jsa">
          {p.jsa.jsa_no}
        </Link>
        <StatusBadge status={p.jsa.status} label={te(`jsaStatus.${p.jsa.status}`)} />
        {p.jsa.governing_residual_band ? (
          <span className="inline-flex items-center gap-1 text-sm">
            {t("residual")} <RiskBandBadge band={p.jsa.governing_residual_band} />
          </span>
        ) : null}
        <StatusBadge status={p.jsa.residual_acceptance_complete ? "done" : "pending"} label={p.jsa.residual_acceptance_complete ? t("acceptanceDone") : t("acceptancePending")} />
        <Button size="sm" variant="outline" asChild className="ms-auto">
          <Link href={`/jsas/${p.jsa.id}`}>{t("openJsa")}</Link>
        </Button>
      </CardContent>
    </Card>
  );
}

function GasTab({ p }: { p: Permit }) {
  const t = useTranslations("permitDetail");
  const te = useTranslations("enums");
  const me = useMeData();
  const q = usePermitGasTests(p.id);
  const { dateTime } = useFormatters(p.project_id);
  const locale = useLocale();
  const record = can(me, "gas_test.record", p.project_id) && ["issued", "active", "suspended"].includes(p.status);
  if (!p.gas.required) return <EmptyState message={t("gasNotRequired")} />;
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2 text-base">
          {t("gasTests")} <GasStatusBadge status={p.gas.status} prefix={false} />
        </CardTitle>
        {record ? (
          <Button size="sm" asChild>
            <Link href={`/gas-tests/new?permit_id=${p.id}`} data-testid="record-gas-test">
              {t("recordGasTest")}
            </Link>
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {p.gas.interval_minutes ? <p className="text-sm text-muted-foreground">{t("gasInterval", { n: p.gas.interval_minutes })}</p> : null}
        {p.gas.post_break_test_required ? <Alert tone="warning">{t("postBreakTest")}</Alert> : null}
        {q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : null}
        {q.data && q.data.items.length === 0 ? <p className="text-sm text-muted-foreground">{t("noGasTests")}</p> : null}
        {q.data?.items.length ? (
          <div className="overflow-x-auto">
            <Table>
              <THead>
                <TR>
                  <TH>{t("test")}</TH>
                  <TH>{t("testType")}</TH>
                  <TH>{t("tester")}</TH>
                  <TH>{t("result")}</TH>
                </TR>
              </THead>
              <TBody>
                {q.data.items.map((g) => (
                  <TR key={g.id} className={g.superseded ? "opacity-60" : undefined}>
                    <TD>
                      <Link href={`/gas-tests/${g.id}`} className="ltr font-medium text-primary hover:underline">
                        {g.test_no}
                      </Link>
                      <span className="ltr block text-xs text-muted-foreground">{dateTime(g.tested_at)}</span>
                    </TD>
                    <TD>{te(`gasTestType.${g.test_type}`)}</TD>
                    <TD>
                      {g.tester.holder_name_en ? (locale === "ar" && g.tester.holder_name_ar ? g.tester.holder_name_ar : g.tester.holder_name_en) : <bdi className="ltr">{g.tester.appointment_no}</bdi>}
                    </TD>
                    <TD>
                      <StatusBadge status={g.result === "pass" ? "ok" : "failed"} label={te(`gasResult.${g.result}`)} />
                      {g.superseded ? <span className="ms-1 text-xs text-muted-foreground">{t("superseded")}</span> : null}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function IsolationsTab({ p }: { p: Permit }) {
  const t = useTranslations("permitDetail");
  const te = useTranslations("enums");
  if (!p.isolations.length) return <EmptyState message={t("noIsolations")} />;
  return (
    <Card>
      <CardContent className="pt-5">
        <ul className="flex flex-col divide-y rounded-md border">
          {p.isolations.map((i) => (
            <li key={i.id} className="flex flex-wrap items-center gap-3 p-3 text-sm">
              <Link href={`/isolations/${i.id}`} className="ltr font-semibold text-primary hover:underline">
                {i.iso_no}
              </Link>
              <StatusBadge status={i.status} label={te.has(`isolationStatus.${i.status}` as "isolationStatus.planned") ? te(`isolationStatus.${i.status}` as "isolationStatus.planned") : i.status} />
              <span className="text-muted-foreground">{t("isoPoints", { n: i.points_count, locks: i.personal_locks_applied })}</span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function SimopsTab({ p }: { p: Permit }) {
  const t = useTranslations("permitDetail");
  const te = useTranslations("enums");
  const { dateTime } = useFormatters(p.project_id);
  if (!p.simops.length) return <EmptyState message={t("noSimops")} />;
  return (
    <Card>
      <CardContent className="pt-5">
        <ul className="flex flex-col divide-y rounded-md border" data-testid="permit-simops">
          {p.simops.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 p-3 text-sm" data-testid="permit-simops-row" data-result={c.result}>
              <Link href={`/simops-conflicts/${c.id}`} className="ltr font-semibold text-primary hover:underline">
                {c.conflict_no}
              </Link>
              <SimopsResultBadge result={c.result} />
              <StatusBadge status={c.status} label={te(`simopsConflictStatus.${c.status}`)} />
              <span>
                {t("with")} <PermitNo p={c.other_permit} /> <TypeChips types={c.other_permit.work_types} short />
              </span>
              <span className="w-full text-xs text-muted-foreground">
                <bdi className="ltr">{c.rule_code}</bdi>
                {c.distance_m ? <> · <bdi className="ltr">{c.distance_m} m</bdi></> : null}
                {c.overlap_from ? (
                  <>
                    {" "}
                    · <span className="ltr">{dateTime(c.overlap_from)}</span> – <span className="ltr">{c.overlap_to ? dateTime(c.overlap_to) : "…"}</span>
                  </>
                ) : null}
              </span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function ShiftsTab({ p }: { p: Permit }) {
  const t = useTranslations("permitDetail");
  const te = useTranslations("enums");
  const locale = useLocale();
  const { dateTime } = useFormatters(p.project_id);
  const shifts = useShifts(p.id);
  const handovers = useHandovers(p.id);
  const susp = useSuspensions(p.id);
  return (
    <div className="flex flex-col gap-5">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("shifts", { n: p.shifts_count })}</CardTitle>
        </CardHeader>
        <CardContent>
          {shifts.isError ? <ErrorState error={shifts.error} onRetry={() => shifts.refetch()} /> : null}
          {shifts.data?.items.length === 0 ? <p className="text-sm text-muted-foreground">{t("noShifts")}</p> : null}
          <ol className="flex flex-col divide-y rounded-md border empty:hidden" data-testid="shifts">
            {shifts.data?.items.map((x) => (
              <li key={x.id} className="flex flex-col gap-0.5 p-3 text-sm">
                <span className="font-medium">
                  {t("shiftNo", { n: x.shift_no })} · <span className="ltr">{dateTime(x.started_at)}</span> – <span className="ltr">{x.ended_at ? dateTime(x.ended_at) : dateTime(x.planned_end_at)}</span>
                  {x.end_type ? <span className="ms-2 text-xs text-muted-foreground">{te(`shiftEndType.${x.end_type}`)}</span> : null}
                </span>
                <span className="text-xs text-muted-foreground">
                  {userLabel(x.receiver, locale)} · {userLabel(x.issuer, locale)} · {t("crewPresent", { n: x.crew_present_count })}
                  {x.ambient_temp_c ? <> · <bdi className="ltr">{x.ambient_temp_c} °C</bdi></> : null}
                  {x.heat_regime ? (
                    <>
                      {" "}
                      · <RegimeBadge regime={x.heat_regime} short />
                    </>
                  ) : null}
                  {x.gas_compliant === false ? <span className="ms-1 text-danger">{t("gasNonCompliant")}</span> : null}
                </span>
                {x.pauses.length ? (
                  <span className="text-xs text-muted-foreground">
                    {x.pauses.map((pz, i) => (
                      <span key={i} className="me-2">
                        {te(`pauseReason.${pz.reason}`)} <span className="ltr">{dateTime(pz.from_at)}</span>
                        {pz.to_at ? <> – <span className="ltr">{dateTime(pz.to_at)}</span></> : null}
                      </span>
                    ))}
                  </span>
                ) : null}
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("handovers", { n: p.handovers_count })}</CardTitle>
        </CardHeader>
        <CardContent>
          {handovers.data?.items.length === 0 ? <p className="text-sm text-muted-foreground">{t("noHandovers")}</p> : null}
          <ol className="flex flex-col divide-y rounded-md border empty:hidden">
            {handovers.data?.items.map((h) => (
              <li key={h.id} className="flex flex-col gap-0.5 p-3 text-sm">
                <span className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">
                    {userLabel(h.from_receiver, locale)} → {userLabel(h.to_receiver, locale)}
                  </span>
                  <StatusBadge status={h.status} label={te(`handoverStatus.${h.status}`)} />
                </span>
                <span className="text-xs text-muted-foreground">
                  <span className="ltr">{dateTime(h.initiated_at)}</span> · {t("incomingIssuer", { name: userLabel(h.to_issuer, locale) })}
                </span>
                <span className="whitespace-pre-line">{locale === "ar" && h.notes_ar ? h.notes_ar : h.notes_en}</span>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("suspensions")}</CardTitle>
        </CardHeader>
        <CardContent>
          {susp.data?.items.length === 0 ? <p className="text-sm text-muted-foreground">{t("noSuspensions")}</p> : null}
          <ol className="flex flex-col divide-y rounded-md border empty:hidden" data-testid="suspensions">
            {susp.data?.items.map((x) => (
              <li key={x.id} className="flex flex-col gap-0.5 p-3 text-sm">
                <span className="flex flex-wrap items-center gap-2 font-medium">
                  {te(`statusReason.${x.reason}`)}
                  {x.routine ? <span className="text-xs text-muted-foreground">{t("routine")}</span> : null}
                </span>
                <span className="text-xs text-muted-foreground">
                  <span className="ltr">{dateTime(x.suspended_at)}</span>
                  {x.raised_by ? <> · {userLabel(x.raised_by, locale)}</> : x.auto_source_ref ? <> · <bdi className="ltr">{x.auto_source_ref}</bdi></> : null}
                  {x.resumed_at ? (
                    <>
                      {" "}
                      · {t("resumedAt")} <span className="ltr">{dateTime(x.resumed_at)}</span>
                    </>
                  ) : null}
                </span>
                {x.detail ? <span>{x.detail}</span> : null}
                {x.cause_cleared_text ? <span className="text-xs">{x.cause_cleared_text}</span> : null}
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
    </div>
  );
}

