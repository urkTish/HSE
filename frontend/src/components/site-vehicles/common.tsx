"use client";
import { Ban, CalendarClock, CheckCircle2, CircleDashed, Clock, FlaskConical, OctagonAlert, PauseCircle, ShieldAlert, TriangleAlert, Wrench, XCircle } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import type { ComponentType, ReactNode, SVGProps } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge, type BadgeProps } from "@/components/ui/badge";
import { SubNav } from "@/components/access/common";
import { ProjectGate } from "@/components/common/project-gate";
import { ErrorState, LoadingState } from "@/components/common/states";
import { useMeData } from "@/components/shell/me-context";
import { Link } from "@/i18n/navigation";
import type { Schemas } from "@/lib/api/client";
import { useSvReference, useSvSettings } from "@/lib/api/site-vehicles";
import { can, canWrite, isReadOnly } from "@/lib/permissions";
import { cn } from "@/lib/utils";

type S = Schemas;
type Tone = NonNullable<BadgeProps["tone"]>;
type Icon = ComponentType<SVGProps<SVGSVGElement>>;

/* ───────────── capabilities (7b §5.7, 233–237) ───────────── */

export function useSvCaps(projectId?: string | null) {
  const me = useMeData();
  const pid = projectId ?? null;
  const roles = me?.projects.find((p) => p.project_id === pid)?.roles ?? [];
  const view = can(me, "site_vehicle.view", pid);
  return {
    view,
    /** Viewer / Client (read-only project access): K-138…K-140 aggregates only, every register is refused (P7b-1). */
    aggregatesOnly: view && !me.is_hse_manager && Boolean(pid) && isReadOnly(me, pid as string),
    manage: canWrite(me, "site_vehicle.manage", pid),
    auth: canWrite(me, "driver_auth.manage", pid),
    record: canWrite(me, "pre_use.record", pid),
    settings: canWrite(me, "site_vehicle.settings", pid),
    /** Contractor HSE Rep: own engagement only, cannot verify documents, proposes authorisations (draft). */
    rep: !me.is_hse_manager && roles.includes("contractor_hse_rep"),
  };
}

/** Any of 233–237 on the project (sidebar entry and dashboard tiles). */
export function useSvAny(projectId?: string | null) {
  const me = useMeData();
  const pid = projectId ?? null;
  return (["site_vehicle.view", "site_vehicle.manage", "driver_auth.manage", "pre_use.record", "site_vehicle.settings"] as const).some((c) => can(me, c, pid));
}

/* ───────────── "Prototype" badge (every 7b page) ───────────── */

export function PrototypeBadge({ className, compact }: { className?: string; compact?: boolean }) {
  const t = useTranslations("sv");
  return (
    <Badge tone="info" className={cn(compact && "px-1.5 py-0 text-[10px]", className)} data-testid="prototype-badge" title={t("prototypeHint")}>
      <FlaskConical aria-hidden />
      {t("prototype")}
    </Badge>
  );
}

/* ───────────── sub navigation ───────────── */

export function SvSubNav({ projectId }: { projectId: string }) {
  const t = useTranslations("sv.nav");
  const caps = useSvCaps(projectId);
  const reg = caps.view && !caps.aggregatesOnly;
  return (
    <SubNav
      items={[
        { href: "/site-vehicles", label: t("vehicles"), show: caps.view, testId: "sub-sv-vehicles" },
        { href: "/site-vehicles/authorisations", label: t("authorisations"), show: reg, testId: "sub-sv-auths" },
        { href: "/site-vehicles/checks", label: t("checks"), show: reg, testId: "sub-sv-checks" },
        { href: "/site-vehicles/journeys", label: t("journeys"), show: reg, testId: "sub-sv-journeys" },
        { href: "/site-vehicles/settings", label: t("settings"), show: caps.settings, testId: "sub-sv-settings" },
      ]}
    />
  );
}

/**
 * Project + 7b switch: with `site_vehicles_from` null every 7b endpoint answers SITE_VEHICLES_NOT_LIVE (AC1),
 * so the pages explain it instead (the HSE Manager gets a link to the settings that switch 7b on).
 */
export function SvGate({ children, allowOff = false }: { children: (project: S["ProjectRead"], settings: S["SiteVehSettingsRead"]) => ReactNode; allowOff?: boolean }) {
  return <ProjectGate>{(p) => <SvLive project={p} allowOff={allowOff}>{children}</SvLive>}</ProjectGate>;
}

function SvLive({ project, allowOff, children }: { project: S["ProjectRead"]; allowOff: boolean; children: (project: S["ProjectRead"], settings: S["SiteVehSettingsRead"]) => ReactNode }) {
  const t = useTranslations("sv");
  const tc = useTranslations("common");
  const caps = useSvCaps(project.id);
  const allowed = caps.view || caps.settings || caps.manage || caps.record || caps.auth;
  const q = useSvSettings(project.id, { enabled: allowed });
  if (!allowed) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  if (!q.data.live && !allowOff)
    return (
      <Alert tone="info" data-testid="sv-not-live">
        <span className="flex flex-col gap-1">
          <span className="inline-flex items-center gap-2 font-medium">
            <PrototypeBadge compact />
            {t("notLive", { code: project.code })}
          </span>
          {caps.settings ? (
            <Link href="/site-vehicles/settings" className="text-primary hover:underline">
              {t("notLiveSettings")}
            </Link>
          ) : null}
        </span>
      </Alert>
    );
  return <>{children(project, q.data)}</>;
}

/* ───────────── labels (local EN/AR; the server reference adds the use-class rules) ───────────── */

export const USE_CLASSES = ["pool_car", "crew_pickup", "crew_bus", "tipper", "goods_heavy", "water_tanker", "earthmoving_plant", "other_plant"] as const satisfies readonly S["SiteVehUseClass"][];
export const GROUPS = ["light", "bus", "heavy", "plant"] as const satisfies readonly S["SiteVehDriverGroup"][];
export const READINESS = ["ready", "docs_expired", "not_certified", "defect_hold", "idle", "withdrawn"] as const satisfies readonly S["SiteVehReadiness"][];
export const AUTH_STATUSES = ["draft", "active", "suspended", "expired", "revoked"] as const satisfies readonly S["SiteVehAuthStatus"][];
export const JOURNEY_STATUSES = ["planned", "arrived", "cancelled"] as const satisfies readonly S["SiteVehJourneyStatus"][];
export const SCOPES = ["site", "both", "airside_only"] as const satisfies readonly S["SiteVehScope"][];

/** Use-class rules from GET /site-vehicles/reference (driver group, seats and operating card required). */
export function useUseClassRules() {
  const q = useSvReference();
  return (code: string | null | undefined) => q.data?.use_classes.find((u) => u.code === code) ?? null;
}

export function useSvLabels() {
  const t = useTranslations("sv.enum");
  return {
    useClass: (v: string | null | undefined) => (v ? t(`useClass.${v}` as "useClass.tipper") : "—"),
    group: (v: string | null | undefined) => (v ? t(`group.${v}` as "group.light") : "—"),
    groups: (vs: readonly string[]) => vs.map((v) => t(`group.${v}` as "group.light")),
    scope: (v: string | null | undefined) => (v ? t(`scope.${v}` as "scope.site") : "—"),
    readiness: (v: string) => t(`readiness.${v}` as "readiness.ready"),
    authStatus: (v: string) => t(`authStatus.${v}` as "authStatus.active"),
    journeyStatus: (v: string) => t(`journeyStatus.${v}` as "journeyStatus.planned"),
    limiting: (v: string | null | undefined) => (v ? t(`limiting.${v}` as "limiting.licence") : "—"),
    doc: (v: string) => (t.has(`doc.${v}` as "doc.istimara") ? t(`doc.${v}` as "doc.istimara") : v),
    hook: (v: string) => t(`hookResult.${v}` as "hookResult.met"),
    source: (v: string) => t(`source.${v}` as "source.app"),
    policy: (v: string) => t(`policy.${v}` as "policy.warn"),
  };
}

/* ───────────── badges: colour + icon + words ───────────── */

const READINESS_STYLE: Record<S["SiteVehReadiness"], { tone: Tone; Icon: Icon }> = {
  ready: { tone: "success", Icon: CheckCircle2 },
  docs_expired: { tone: "danger", Icon: TriangleAlert },
  not_certified: { tone: "danger", Icon: ShieldAlert },
  defect_hold: { tone: "danger", Icon: Wrench },
  idle: { tone: "neutral", Icon: PauseCircle },
  withdrawn: { tone: "neutral", Icon: Ban },
};

export function ReadinessBadge({ readiness, testId = "sv-readiness" }: { readiness: S["SiteVehReadiness"]; testId?: string }) {
  const l = useSvLabels();
  const s = READINESS_STYLE[readiness];
  return (
    <Badge tone={s.tone} data-testid={testId} data-readiness={readiness}>
      <s.Icon aria-hidden />
      {l.readiness(readiness)}
    </Badge>
  );
}

const AUTH_STYLE: Record<S["SiteVehAuthStatus"], { tone: Tone; Icon: Icon }> = {
  draft: { tone: "info", Icon: CircleDashed },
  active: { tone: "success", Icon: CheckCircle2 },
  suspended: { tone: "warning", Icon: PauseCircle },
  expired: { tone: "danger", Icon: TriangleAlert },
  revoked: { tone: "danger", Icon: Ban },
};

export function AuthStatusBadge({ status }: { status: S["SiteVehAuthStatus"] }) {
  const l = useSvLabels();
  const s = AUTH_STYLE[status];
  return (
    <Badge tone={s.tone} data-testid="sv-auth-status" data-status={status}>
      <s.Icon aria-hidden />
      {l.authStatus(status)}
    </Badge>
  );
}

const JOURNEY_STYLE: Record<S["SiteVehJourneyStatus"], { tone: Tone; Icon: Icon }> = {
  planned: { tone: "info", Icon: Clock },
  arrived: { tone: "success", Icon: CheckCircle2 },
  cancelled: { tone: "neutral", Icon: XCircle },
};

export function JourneyStatusBadge({ status, overdue }: { status: S["SiteVehJourneyStatus"]; overdue?: boolean }) {
  const t = useTranslations("sv");
  const l = useSvLabels();
  const s = JOURNEY_STYLE[status];
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <Badge tone={s.tone} data-testid="sv-journey-status" data-status={status}>
        <s.Icon aria-hidden />
        {l.journeyStatus(status)}
      </Badge>
      {overdue ? (
        <Badge tone="warning" data-testid="sv-overdue" title={t("journey.overdueHint")}>
          <CalendarClock aria-hidden />
          {t("journey.overdue")}
        </Badge>
      ) : null}
    </span>
  );
}

/** Pass / fail of a pre-use check (critical fails counted). */
export function CheckResultBadge({ passed, critical }: { passed: boolean; critical?: number }) {
  const t = useTranslations("sv.check");
  return (
    <Badge tone={passed ? "success" : "danger"} data-testid="sv-check-result" data-passed={passed}>
      {passed ? <CheckCircle2 aria-hidden /> : <OctagonAlert aria-hidden />}
      {passed ? t("pass") : critical ? t("failCritical", { n: critical }) : t("fail")}
    </Badge>
  );
}

/** One road document: kind, date and the state (valid / expiring ≤ 30 days / expired). */
export function DocChip({ d, date }: { d: S["SiteVehDocRead"]; date: (v: string) => string }) {
  const t = useTranslations("sv.vehicle");
  const l = useSvLabels();
  const expired = d.state === "expired";
  const soon = d.state === "expiring";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs whitespace-nowrap",
        expired ? "bg-danger-bg font-medium text-danger" : soon ? "bg-warning-bg font-medium text-warning" : "text-muted-foreground",
      )}
      data-testid="sv-doc"
      data-kind={d.kind}
      data-state={d.state}
    >
      {expired ? <TriangleAlert aria-hidden className="size-3.5" /> : soon ? <CalendarClock aria-hidden className="size-3.5" /> : <CheckCircle2 aria-hidden className="size-3.5" />}
      {l.doc(d.kind)} · {date(d.expiry)}
      {expired ? ` · ${t("docExpired")}` : soon ? ` · ${t("docDays", { n: d.days_left })}` : ""}
    </span>
  );
}

/** "VEH-0107 · FL-07 · Toyota Coaster": refs left-to-right inside Arabic text. */
export function VehicleRefText({ v }: { v: S["SiteVehVehicleRef"] }) {
  return (
    <span className="inline-flex flex-wrap items-baseline gap-x-1.5">
      <bdi className="ltr font-medium">{v.vehicle_no}</bdi>
      <bdi className="ltr text-xs text-muted-foreground">{v.fleet_no}</bdi>
      <span className="text-xs text-muted-foreground">{v.make_model}</span>
    </span>
  );
}

/** A worker as the 7b API returns it (names may be withheld). */
export function DriverText({ w }: { w: S["WorkerRef"] }) {
  const ar = useLocale() === "ar";
  const n = ar ? w.full_name_ar || w.full_name_en : w.full_name_en || w.full_name_ar;
  return (
    <span className="inline-flex flex-wrap items-baseline gap-x-1.5">
      <bdi className="ltr text-xs text-muted-foreground">{w.worker_no}</bdi>
      {n ? <span>{n}</span> : null}
    </span>
  );
}
