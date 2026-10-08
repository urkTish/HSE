"use client";
import { AlarmClock, CircleCheck, Flame, Info, PenLine, ShieldAlert, ShieldCheck, TriangleAlert, Wind } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState, type ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/common/status-badge";
import { SubNav } from "@/components/access/common";
import { useMeData } from "@/components/shell/me-context";
import { Link } from "@/i18n/navigation";
import type { Schemas } from "@/lib/api/client";
import { utcToZonedInput, zonedInputToUtc } from "@/lib/datetime";
import { can, type Capability } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";
import { useCurrentProject } from "@/lib/current-project";
import { cn } from "@/lib/utils";

type S = Schemas;

/* ───────────── navigation ───────────── */

/** Section tabs of the PTW module (permits | board | suspensions). */
export function PermitsSubNav() {
  const t = useTranslations("ptw.nav");
  return (
    <SubNav
      items={[
        { href: "/permits", label: t("permits"), testId: "sub-permits" },
        { href: "/ptw-board", label: t("board"), testId: "sub-ptw-board" },
        { href: "/permit-suspensions", label: t("suspensions"), testId: "sub-permit-suspensions" },
        { href: "/simops-conflicts", label: t("simops"), testId: "sub-simops" },
      ]}
    />
  );
}

export function GasSubNav() {
  const t = useTranslations("ptw.nav");
  return (
    <SubNav
      items={[
        { href: "/gas-tests", label: t("gasTests"), testId: "sub-gas-tests" },
        { href: "/gas-detectors", label: t("detectors"), testId: "sub-gas-detectors" },
      ]}
    />
  );
}

export function IsolationSubNav() {
  const t = useTranslations("ptw.nav");
  return (
    <SubNav
      items={[
        { href: "/isolations", label: t("isolations"), testId: "sub-isolations" },
        { href: "/locks", label: t("locks"), testId: "sub-locks" },
      ]}
    />
  );
}

export function SetupSubNav() {
  const t = useTranslations("ptw.nav");
  return (
    <SubNav
      items={[
        { href: "/ptw-setup/types", label: t("types"), testId: "sub-setup-types" },
        { href: "/ptw-setup/zones", label: t("zones"), testId: "sub-setup-zones" },
        { href: "/ptw-setup/adjacency", label: t("adjacency"), testId: "sub-setup-adjacency" },
        { href: "/ptw-setup/simops-rules", label: t("simopsRules"), testId: "sub-setup-simops" },
        { href: "/ptw-setup/risk-matrix", label: t("riskMatrix"), testId: "sub-setup-matrix" },
        { href: "/ptw-setup/settings", label: t("settings"), testId: "sub-setup-settings" },
      ]}
    />
  );
}

/* ───────────── capability helpers ───────────── */

/** True when the signed-in user holds any of the capabilities in the project. */
export function useCanAny() {
  const me = useMeData();
  return (pid: string | null | undefined, ...cs: Capability[]) => cs.some((c) => can(me, c, pid));
}

/* ───────────── labels ───────────── */

export function userLabel(u: { full_name_en: string; full_name_ar?: string | null } | null | undefined, locale: string): string {
  if (!u) return "—";
  return locale === "ar" && u.full_name_ar ? u.full_name_ar : u.full_name_en;
}

/** Worker reference: number plus name when the caller may see names (capability 46), else "Worker". */
export function WorkerRefLabel({ w }: { w: S["WorkerRef"] | null | undefined }) {
  const t = useTranslations("ptw");
  const locale = useLocale();
  if (!w) return <span className="text-muted-foreground">{t("workerHidden")}</span>;
  const n = locale === "ar" ? w.full_name_ar || w.full_name_en : w.full_name_en || w.full_name_ar;
  return (
    <span>
      <bdi className="ltr text-muted-foreground">{w.worker_no}</bdi>
      {n ? <span className="ms-1.5">{n}</span> : null}
    </span>
  );
}

export function PermitNo({ p, link = true }: { p: Pick<S["PermitRef"], "id" | "display_no">; link?: boolean }) {
  const body = <bdi className="ltr font-medium">{p.display_no}</bdi>;
  return link ? (
    <Link href={`/permits/${p.id}`} className="text-primary hover:underline" data-testid="permit-link">
      {body}
    </Link>
  ) : (
    body
  );
}

/** Permit status with its reason (e.g. Suspended · Gas test failed). */
export function PermitStatusBadge({ status, reason }: { status: S["PermitStatus"]; reason?: S["StatusReason"] | null }) {
  const te = useTranslations("enums");
  return (
    <span className="inline-flex flex-wrap items-center gap-1" data-testid="permit-status" data-status={status}>
      <StatusBadge status={status} label={te(`permitStatus.${status}`)} />
      {reason ? <span className="text-xs text-muted-foreground">{te(`statusReason.${reason}`)}</span> : null}
    </span>
  );
}

const TYPE_LETTER: Record<S["PermitType"], string> = {
  general: "GW",
  hot_work: "HW",
  confined_space: "CS",
  work_at_height: "WH",
  excavation: "EX",
  electrical_isolation: "EL",
  lifting: "LF",
  radiography: "RG",
  airside_works: "AW",
};

/** Work-type chips; the primary type first and bold. */
export function TypeChips({ types, primary, short }: { types: S["PermitType"][]; primary?: S["PermitType"]; short?: boolean }) {
  const te = useTranslations("enums");
  const ordered = primary ? [primary, ...types.filter((x) => x !== primary)] : types;
  return (
    <span className="inline-flex flex-wrap gap-1" data-testid="type-chips">
      {ordered.map((x) => (
        <span
          key={x}
          title={te(`permitType.${x}`)}
          className={cn("rounded border px-1.5 py-0.5 text-xs", x === primary ? "border-primary/40 bg-primary/10 font-semibold" : "border-input")}
          data-type={x}
        >
          {short ? <bdi className="ltr">{TYPE_LETTER[x]}</bdi> : te(`permitType.${x}`)}
        </span>
      ))}
    </span>
  );
}

export function HighRiskBadge({ show }: { show: boolean }) {
  const t = useTranslations("ptw");
  if (!show) return null;
  return (
    <Badge tone="danger" data-testid="high-risk">
      <ShieldAlert aria-hidden />
      {t("highRisk")}
    </Badge>
  );
}

const GAS_TONE: Record<S["GasStatus"], "success" | "warning" | "danger" | "neutral"> = {
  not_required: "neutral",
  valid: "success",
  due_soon: "warning",
  overdue: "danger",
  failed: "danger",
  missing: "warning",
};

export function GasStatusBadge({ status }: { status: S["GasStatus"] }) {
  const te = useTranslations("enums");
  const Icon = status === "valid" ? CircleCheck : status === "not_required" ? Info : TriangleAlert;
  return (
    <Badge tone={GAS_TONE[status]} data-testid="gas-status" data-status={status}>
      <Icon aria-hidden />
      {te(`gasStatus.${status}`)}
    </Badge>
  );
}

const BAND_CLS: Record<S["RiskBand"], string> = {
  low: "border-success/30 bg-success-bg text-success",
  medium: "border-warning/30 bg-warning-bg text-warning",
  high: "border-danger/30 bg-danger-bg text-danger",
  extreme: "border-danger bg-danger text-white",
};

/** 5×5 risk band chip (score optional). Colour plus text, never colour alone. */
export function RiskBandBadge({ band, score }: { band: S["RiskBand"] | null | undefined; score?: number | null }) {
  const te = useTranslations("enums");
  if (!band) return <span className="text-muted-foreground">—</span>;
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold whitespace-nowrap", BAND_CLS[band])} data-testid="risk-band" data-band={band}>
      {score !== undefined && score !== null ? <bdi className="ltr tabular-nums">{score}</bdi> : null}
      {te(`riskBand.${band}`)}
    </span>
  );
}

export function riskBandCellClass(band: S["RiskBand"]): string {
  return BAND_CLS[band];
}

const SIMOPS_TONE: Record<S["SimopsResult"], "danger" | "warning" | "success"> = { prohibited: "danger", conditional: "warning", allowed: "success" };

export function SimopsResultBadge({ result }: { result: S["SimopsResult"] }) {
  const te = useTranslations("enums");
  return (
    <Badge tone={SIMOPS_TONE[result]} data-testid="simops-result" data-result={result}>
      {result === "prohibited" ? <ShieldAlert aria-hidden /> : result === "conditional" ? <TriangleAlert aria-hidden /> : <ShieldCheck aria-hidden />}
      {te(`simopsResult.${result}`)}
    </Badge>
  );
}

/* ───────────── blockers and warnings ───────────── */

/** Every blocker of a permit (or of a refused transition), in the page language. Issue-time blockers are marked. */
export function BlockerList({ items, empty }: { items: S["BlockerItem"][]; empty?: ReactNode }) {
  const t = useTranslations("ptw");
  const te = useTranslations("enums");
  const ar = useLocale() === "ar";
  if (items.length === 0)
    return empty === undefined ? (
      <p className="inline-flex items-center gap-1.5 text-sm text-success" data-testid="no-blockers">
        <ShieldCheck aria-hidden className="size-4" />
        {t("noBlockers")}
      </p>
    ) : (
      <>{empty}</>
    );
  return (
    <ul className="flex flex-col gap-1.5" data-testid="blockers">
      {items.map((b, i) => (
        <li key={`${b.code}-${i}`} className="flex items-start gap-2 rounded-md border border-danger/30 bg-danger-bg p-2 text-sm" data-testid="blocker" data-code={b.code}>
          <ShieldAlert aria-hidden className="mt-0.5 size-4 shrink-0 text-danger" />
          <span className="min-w-0">
            <span className="font-medium">{te(`permitBlocker.${b.code}`)}</span>
            {b.issue_time ? <span className="ms-1.5 rounded bg-surface px-1 text-xs text-muted-foreground">{t("atIssue")}</span> : null}
            {(ar ? b.detail_ar : b.detail_en) && (ar ? b.detail_ar : b.detail_en) !== te(`permitBlocker.${b.code}`) ? <span className="block text-xs text-muted-foreground">{ar ? b.detail_ar : b.detail_en}</span> : null}
            {b.ref ? <bdi className="ltr block font-mono text-xs text-muted-foreground">{b.ref}</bdi> : null}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Non-blocking permit warnings: amber; "not yet checkable" hooks as a calm neutral note with an info icon. */
export function WarningList({ items }: { items: S["WarningItem"][] }) {
  const t = useTranslations("ptw");
  const te = useTranslations("enums");
  const ar = useLocale() === "ar";
  if (items.length === 0) return null;
  const warnings = items.filter((w) => w.code !== "HOOK_NOT_AVAILABLE");
  const notes = items.filter((w) => w.code === "HOOK_NOT_AVAILABLE");
  const detail = (w: S["WarningItem"]) => (ar ? w.detail_ar : w.detail_en);
  return (
    <div className="flex flex-col gap-1.5" data-testid="permit-warnings">
      {warnings.length ? (
        <ul className="flex flex-col gap-1.5">
          {warnings.map((w, i) => (
            <li key={`${w.code}-${i}`} className="flex items-start gap-2 rounded-md border border-warning/40 bg-warning-bg p-2 text-sm" data-testid="permit-warning" data-code={w.code} data-tone="warning">
              <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0 text-warning" />
              <span className="min-w-0">
                <span className="font-medium">{te(`permitWarning.${w.code}`)}</span>
                {detail(w) ? <span className="block text-xs text-muted-foreground">{detail(w)}</span> : null}
                {w.ref ? <bdi className="ltr block font-mono text-xs text-muted-foreground">{w.ref}</bdi> : null}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      {notes.length ? (
        // "Not yet checkable" hooks (later phases): one calm, collapsible note instead of a wall of boxes.
        <details className="rounded-md border border-neutral/30 bg-neutral-bg p-2 text-sm" data-testid="hook-notes">
          <summary className="flex min-h-touch cursor-pointer items-center gap-2 font-medium">
            <Info aria-hidden className="size-4 shrink-0 text-neutral" />
            {t("hookNotes", { n: notes.length })}
          </summary>
          <ul className="mt-1 flex flex-col gap-1 ps-6">
            {notes.map((w, i) => (
              <li key={`${w.code}-${i}`} className="text-xs text-muted-foreground" data-testid="permit-warning" data-code={w.code} data-tone="note">
                {detail(w) ?? te(`permitWarning.${w.code}`)}
                {w.ref ? <bdi className="ltr ms-1 font-mono">{w.ref}</bdi> : null}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

/* ───────────── signatures ───────────── */

export function SignatureList({ items }: { items: S["SignatureRead"][] }) {
  const t = useTranslations("ptw");
  const te = useTranslations("enums");
  const locale = useLocale();
  const { dateTime } = useFormatters();
  if (items.length === 0) return <p className="text-sm text-muted-foreground">{t("noSignatures")}</p>;
  return (
    <ol className="flex flex-col divide-y rounded-md border" data-testid="signatures">
      {items.map((s) => (
        <li key={s.id} className="flex flex-wrap items-start gap-x-3 gap-y-0.5 p-2 text-sm" data-testid="signature" data-purpose={s.purpose}>
          <PenLine aria-hidden className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1">
            <span className="font-medium">{te(`signaturePurpose.${s.purpose}`)}</span> · {s.user ? userLabel(s.user, locale) : (s.worker_label ?? "—")}
            <span className="block text-xs text-muted-foreground">
              {s.role_label}
              {s.appointment_no ? (
                <>
                  {" "}
                  · <bdi className="ltr">{s.appointment_no}</bdi>
                </>
              ) : null}
              {s.co_signed_on_device_of ? <> · {t("coSignedOn", { name: userLabel(s.co_signed_on_device_of, locale) })}</> : null}
            </span>
          </span>
          <span className="text-xs text-muted-foreground">
            <span className="ltr">{dateTime(s.signed_at)}</span>
            <bdi className="ltr block font-mono text-[10px]" title={t("permitHash")}>
              #{s.permit_hash.slice(0, 12)}
            </bdi>
          </span>
        </li>
      ))}
    </ol>
  );
}

/* ───────────── time ───────────── */

/** Current time, re-rendered every `ms` (countdowns). */
export function useNow(ms = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), ms);
    return () => window.clearInterval(id);
  }, [ms]);
  return now;
}

function fmtDuration(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

/** Live countdown to `to`: amber in the last `warnMinutes`, red once overdue. */
export function Countdown({ to, label, warnMinutes = 10, icon = "clock", testId = "countdown" }: { to: string; label: string; warnMinutes?: number; icon?: "clock" | "fire" | "wind"; testId?: string }) {
  const t = useTranslations("ptw");
  const now = useNow();
  const left = new Date(to).getTime() - now;
  const overdue = left <= 0;
  const warn = !overdue && left <= warnMinutes * 60_000;
  const Icon = icon === "fire" ? Flame : icon === "wind" ? Wind : AlarmClock;
  return (
    <span
      role="timer"
      aria-live="off"
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-sm font-medium",
        overdue ? "border-danger/40 bg-danger-bg text-danger" : warn ? "border-warning/40 bg-warning-bg text-warning" : "border-input bg-surface",
      )}
      data-testid={testId}
      data-state={overdue ? "overdue" : warn ? "warn" : "ok"}
    >
      <Icon aria-hidden className="size-4" />
      <span>{label}</span>
      <bdi className="ltr tabular-nums">{overdue ? t("overdueBy", { d: fmtDuration(-left) }) : fmtDuration(left)}</bdi>
    </span>
  );
}

/** Local date-time input in the project's time zone; emits UTC ISO (or "" when empty). */
export function DateTimeInput({ value, onChange, id, ...rest }: { value: string; onChange: (iso: string) => void; id?: string; disabled?: boolean; min?: string; "data-testid"?: string }) {
  const tz = useProjectTimeZone();
  return (
    <Input
      id={id}
      type="datetime-local"
      className="ltr"
      value={value ? utcToZonedInput(value, tz) : ""}
      onChange={(e) => onChange(e.target.value ? zonedInputToUtc(e.target.value, tz) : "")}
      {...rest}
    />
  );
}

export function useProjectTimeZone(): string {
  const { prefs } = useFormatters();
  return prefs.timeZone;
}

/** Decimal input (strings to the API, LTR digits). */
export function DecimalInput({ value, onChange, id, placeholder, ...rest }: { value: string; onChange: (v: string) => void; id?: string; placeholder?: string; "data-testid"?: string; disabled?: boolean; className?: string }) {
  return (
    <Input
      id={id}
      inputMode="decimal"
      className={cn("ltr tabular-nums", rest.className)}
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value.replace(",", ".").replace(/[^0-9.\-]/g, ""))}
      data-testid={rest["data-testid"]}
      disabled={rest.disabled}
    />
  );
}

export function nowIso(): string {
  return new Date(Math.floor(Date.now() / 60_000) * 60_000).toISOString();
}

/** Current project id (PTW pages are project-scoped). */
export function useProjectId(): string | null {
  return useCurrentProject().projectId ?? null;
}
