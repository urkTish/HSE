"use client";
import { CalendarClock, Eye, EyeOff, Info, Plane, ShieldCheck, TriangleAlert, Users } from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import QRCode from "qrcode";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { FormField } from "@/components/common/form-field";
import { MutationError } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { useMeData } from "@/components/shell/me-context";
import { Link, usePathname } from "@/i18n/navigation";
import { UNMASK_REASONS } from "@/lib/access-enums";
import { useDeployments, useVehicles } from "@/lib/api/access";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useCurrentProject } from "@/lib/current-project";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { can } from "@/lib/permissions";
import { useDebounced } from "@/lib/use-debounced";
import { useFormatters } from "@/lib/use-formatters";
import { cn } from "@/lib/utils";

/** Section tabs inside an access module (e.g. Applications | Passes). */
export function SubNav({ items }: { items: { href: string; label: string; show?: boolean; testId?: string }[] }) {
  const pathname = usePathname();
  const t = useTranslations("access");
  const visible = items.filter((i) => i.show !== false);
  if (visible.length < 2) return null;
  return (
    <nav aria-label={t("sections")} className="-mx-4 mb-5 overflow-x-auto border-b px-4 [scrollbar-width:none] sm:mx-0 sm:px-0">
      <ul className="flex gap-1">
        {visible.map((i) => {
          const active = pathname === i.href || pathname.startsWith(`${i.href}/`);
          return (
            <li key={i.href}>
              <Link
                href={i.href}
                data-testid={i.testId}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "-mb-px inline-flex min-h-touch items-center border-b-[3px] px-3 text-sm whitespace-nowrap transition-colors",
                  active ? "border-primary font-semibold text-foreground" : "border-transparent text-muted-foreground hover:border-input hover:text-foreground",
                )}
              >
                {i.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/** Airport-only registers (AP-2): explain instead of calling the API on a non-airport project. */
export function AirportOnly({ project, children }: { project: Schemas["ProjectRead"]; children: ReactNode }) {
  const t = useTranslations("access");
  if (!project.is_airport)
    return (
      <Alert tone="info" data-testid="not-airport">
        <span className="inline-flex items-center gap-2">
          <Plane aria-hidden className="size-4" />
          {t("airportOnly", { code: project.code })}
        </span>
      </Alert>
    );
  return <>{children}</>;
}

/** Code-like values (worker_no, permit numbers, NOTAM ids) stay LTR inside Arabic text. */
export function Code({ children, className, "data-testid": testId }: { children: ReactNode; className?: string; "data-testid"?: string }) {
  return (
    <bdi className={cn("ltr whitespace-nowrap", className)} data-testid={testId}>
      {children}
    </bdi>
  );
}

/** Saudi plate: Arabic letters (RTL) + LTR digits, with the Latin letters muted (AC74). */
export function Plate({ ar, en, digits, display }: { ar?: string | null; en?: string | null; digits?: string | null; display?: string | null }) {
  if (!digits && !ar && !display) return <>—</>;
  if (!digits && display) return <bdi className="ltr">{display}</bdi>;
  return (
    <span className="inline-flex items-baseline gap-1.5 rounded border px-1.5 py-0.5 font-medium" data-testid="plate">
      {ar ? (
        <span dir="rtl" lang="ar">
          {ar}
        </span>
      ) : null}
      <bdi className="ltr tabular-nums">{digits}</bdi>
      {en ? <bdi className="ltr text-xs text-muted-foreground">{en}</bdi> : null}
    </span>
  );
}

/** Days-left chip (colour + icon + text): expired red, ≤ 30 days amber. */
export function DaysLeft({ days }: { days: number | null | undefined }) {
  const t = useTranslations("access");
  if (days === null || days === undefined) return null;
  const expired = days < 0;
  const soon = !expired && days <= 30;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium whitespace-nowrap",
        expired ? "bg-danger-bg text-danger" : soon ? "bg-warning-bg text-warning" : "text-muted-foreground",
      )}
      data-testid="days-left"
    >
      {expired ? <TriangleAlert aria-hidden className="size-3.5" /> : <CalendarClock aria-hidden className="size-3.5" />}
      {expired ? t("daysExpired", { days: -days }) : t("daysLeft", { days })}
    </span>
  );
}

export function ValidityBadge({ status }: { status: Schemas["ValidityStatus"] | null | undefined }) {
  const te = useTranslations("enums");
  if (!status) return <>—</>;
  return <StatusBadge status={status === "pending" ? "pending" : status} label={te(`validityStatus.${status}`)} />;
}

/** Effective validity with the limiting factor (§6.2) and custody (§4.9). */
export function ValidityLine({ v, projectId }: { v: Schemas["ValidityBlock"]; projectId: string }) {
  const t = useTranslations("access");
  const te = useTranslations("enums");
  const { date } = useFormatters(projectId);
  return (
    <div className="flex flex-col gap-1 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <ValidityBadge status={v.validity_status} />
        {v.effective_valid_until ? (
          <span>
            {t("validUntil")}: <span className="font-medium">{date(v.effective_valid_until)}</span>
          </span>
        ) : null}
        <DaysLeft days={v.validity_status === "active" ? v.days_left : null} />
      </div>
      {v.limiting_factor ? (
        <span className="text-xs text-muted-foreground" data-testid="limiting-factor" data-factor={v.limiting_factor}>
          {t("limitedBy", { factor: te(`limitingFactor.${v.limiting_factor}`) })}
        </span>
      ) : null}
      {v.custody_status && v.custody_status !== "held" ? (
        <span className="flex flex-wrap items-center gap-2">
          <StatusBadge status={v.return_overdue ? "return_overdue" : v.custody_status} label={v.return_overdue ? t("returnOverdue") : te(`custodyStatus.${v.custody_status}`)} />
          {v.return_due_on ? <span className="text-xs text-muted-foreground">{t("returnDueOn", { date: date(v.return_due_on) })}</span> : null}
        </span>
      ) : null}
    </div>
  );
}

/** Eligibility / prerequisite items. Hook "warn" items are amber information, never errors. */
export function EligibilityItems({ items, projectId }: { items: Schemas["EligibilityItem"][]; projectId?: string | null }) {
  const te = useTranslations("enums");
  const ar = useLocale() === "ar";
  const { date } = useFormatters(projectId);
  if (items.length === 0) return null;
  return (
    <ul className="flex flex-col divide-y rounded-lg border" data-testid="eligibility-items">
      {items.map((i, idx) => {
        const msg = ar ? i.message_ar : i.message_en;
        return (
          <li key={`${i.kind}-${i.code ?? ""}-${idx}`} className={cn("flex flex-wrap items-center justify-between gap-2 p-2.5 text-sm", i.status === "warn" && i.reason_code !== "HOOK_NOT_AVAILABLE" && "bg-warning-bg/50")} data-testid="eligibility-item" data-status={i.status} data-reason={i.reason_code ?? ""}>
            <span className="min-w-0">
              <span className="font-medium">{te(`requirementKind.${i.kind}`)}</span>
              {i.code ? (
                <>
                  {" · "}
                  <Code>{i.code}</Code>
                </>
              ) : null}
              {i.ref ? (
                <span className="ms-2 text-xs text-muted-foreground">
                  <Code>{i.ref}</Code>
                </span>
              ) : null}
              {msg || i.reason_code ? <span className="block text-xs text-muted-foreground">{msg || (i.reason_code ? te(`gateReason.${i.reason_code}`) : "")}</span> : null}
            </span>
            <span className="flex items-center gap-2">
              {i.valid_until ? <span className="text-xs text-muted-foreground">{date(i.valid_until)}</span> : null}
              <StatusBadge status={i.status} label={te(`requirementStatus.${i.status}`)} />
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/** QR image rendered in the browser from the opaque payload (no personal data in it, §3.20). */
export function QrImage({ payload, size = 180, label }: { payload: string; size?: number; label: string }) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    QRCode.toDataURL(payload, { errorCorrectionLevel: "M", margin: 1, width: size * 2, color: { dark: "#000000", light: "#ffffff" } })
      .then((url) => {
        if (live) setSrc(url);
      })
      .catch(() => setSrc(null));
    return () => {
      live = false;
    };
  }, [payload, size]);
  return src ? (
    // eslint-disable-next-line @next/next/no-img-element -- data URL generated locally
    <img src={src} width={size} height={size} alt={label} className="rounded bg-white p-1" data-testid="qr-image" data-payload-kind={payload.split(":")[1] ?? ""} />
  ) : (
    <div style={{ width: size, height: size }} className="animate-pulse rounded bg-muted" aria-hidden />
  );
}

const REVEAL_SECONDS = 30;

/**
 * Masked ID with an audited, reason-bound reveal (WK-5). The full number lives only in component
 * state for 30 s: it is never written to the query cache, storage or a form.
 */
export function MaskedIdNumber({ worker }: { worker: Pick<Schemas["WorkerRead"], "id" | "id_number_masked" | "id_type"> }) {
  const t = useTranslations("workers");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<Schemas["UnmaskReason"] | "">("");
  const [text, setText] = useState("");
  const [shown, setShown] = useState<string | null>(null);
  const [left, setLeft] = useState(0);
  const timer = useRef<number | null>(null);
  const reveal = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/workers/{worker_id}/id-number/unmask", {
          params: { path: { worker_id: worker.id } },
          body: { reason: reason as Schemas["UnmaskReason"], reason_text: reason === "other" ? text.trim() : text.trim() || null },
        }),
      ),
    gcTime: 0,
    onSuccess: (r) => {
      setShown(r.id_number);
      setLeft(REVEAL_SECONDS);
      setOpen(false);
      setText("");
      setReason("");
    },
  });
  const { reset } = reveal;
  useEffect(() => {
    if (shown === null) return;
    timer.current = window.setInterval(() => {
      setLeft((l) => {
        if (l <= 1) {
          setShown(null);
          reset();
          return 0;
        }
        return l - 1;
      });
    }, 1000);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [shown, reset]);
  useEffect(() => () => setShown(null), []);
  const canReveal = can(me, "worker.unmask_id");
  const valid = reason !== "" && (reason !== "other" || text.trim().length >= 10);
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      {worker.id_type ? <span className="text-muted-foreground">{te(`workerIdType.${worker.id_type}`)}</span> : null}
      <bdi className="ltr font-mono tabular-nums" data-testid={shown ? "id-number-full" : "id-number-masked"}>
        {shown ?? worker.id_number_masked ?? "—"}
      </bdi>
      {shown ? (
        <>
          <span className="text-xs text-warning" role="timer" aria-live="off">
            {t("hidesIn", { seconds: left })}
          </span>
          <Button size="sm" variant="ghost" onClick={() => { setShown(null); reset(); }} data-testid="hide-id">
            <EyeOff aria-hidden />
            {t("hideId")}
          </Button>
        </>
      ) : canReveal && worker.id_number_masked ? (
        <Button size="sm" variant="outline" onClick={() => setOpen(true)} data-testid="reveal-id">
          <Eye aria-hidden />
          {t("revealId")}
        </Button>
      ) : null}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent closeLabel={tc("close")}>
          <DialogHeader>
            <DialogTitle>{t("revealTitle")}</DialogTitle>
            <DialogDescription>{t("revealBody")}</DialogDescription>
          </DialogHeader>
          <FormField id="unmask-reason" label={tc("reason")} required>
            <Select value={reason} onChange={(e) => setReason(e.target.value as Schemas["UnmaskReason"] | "")}>
              <option value="">{tc("select")}</option>
              {UNMASK_REASONS.map((r) => (
                <option key={r} value={r}>
                  {te(`unmaskReason.${r}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="unmask-text" label={reason === "other" ? t("revealDetails") : t("revealDetailsOptional")} required={reason === "other"} hint={reason === "other" ? t("min10") : undefined}>
            <Textarea value={text} onChange={(e) => setText(e.target.value)} maxLength={300} autoComplete="off" />
          </FormField>
          <MutationError error={reveal.error} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              {tc("cancel")}
            </Button>
            <Button onClick={() => reveal.mutate()} disabled={!valid || reveal.isPending} data-testid="reveal-confirm">
              {t("revealConfirm")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </span>
  );
}

/** Worker photo through a short-lived signed URL (never cached). */
export function WorkerPhoto({ attachmentId, name, size = 96 }: { attachmentId: string | null | undefined; name: string; size?: number }) {
  const [signed, setSigned] = useState<{ id: string; url: string } | null>(null);
  const url = signed && signed.id === attachmentId ? signed.url : null;
  useEffect(() => {
    let live = true;
    if (!attachmentId) return;
    unwrap(api.POST("/api/v1/attachments/{attachment_id}/signed-url", { params: { path: { attachment_id: attachmentId } } }))
      .then((r) => {
        if (live) setSigned({ id: attachmentId, url: r.url });
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [attachmentId]);
  return (
    <div className="shrink-0 overflow-hidden rounded-lg border bg-muted" style={{ width: size, height: size }}>
      {url ? (
        // eslint-disable-next-line @next/next/no-img-element -- signed URL, not optimisable
        <img src={url} alt={name} width={size} height={size} className="size-full object-cover" referrerPolicy="no-referrer" />
      ) : (
        <div className="flex size-full items-center justify-center text-muted-foreground">
          <Users aria-hidden className="size-1/2" />
        </div>
      )}
    </div>
  );
}

export function personName(w: { full_name_en?: string | null; full_name_ar?: string | null; worker_no: string }, locale: string): string {
  const n = locale === "ar" ? w.full_name_ar || w.full_name_en : w.full_name_en || w.full_name_ar;
  return n ?? w.worker_no;
}

/** "WKR-000002 · Rajesh Nair" (names hidden from roles without capability 46 → only the number). */
export function WorkerLabel({ w, link }: { w: { id?: string; worker_no: string; full_name_en?: string | null; full_name_ar?: string | null }; link?: boolean }) {
  const locale = useLocale();
  const n = w.full_name_en || w.full_name_ar ? personName(w, locale) : null;
  const body = (
    <>
      <Code className="text-muted-foreground">{w.worker_no}</Code>
      {n ? <span className="ms-1.5">{n}</span> : null}
    </>
  );
  return link && w.id ? (
    <Link href={`/workers/${w.id}`} className="text-primary hover:underline">
      {body}
    </Link>
  ) : (
    <span>{body}</span>
  );
}

/** Search the project's deployments (name or worker_no) and pick one. */
export function DeploymentPicker({
  id,
  projectId,
  value,
  onChange,
  status,
  engagementId,
  label,
  required,
  error,
}: {
  id: string;
  projectId: string;
  value: Schemas["DeploymentRead"] | null;
  onChange: (d: Schemas["DeploymentRead"] | null) => void;
  status?: Schemas["DeploymentStatus"][];
  engagementId?: string | null;
  label: string;
  required?: boolean;
  error?: string;
}) {
  const t = useTranslations("access");
  const tc = useTranslations("common");
  const locale = useLocale();
  const [q, setQ] = useState("");
  const dq = useDebounced(q, 300);
  const res = useDeployments(projectId, { q: dq || null, status: status ?? null, engagement_id: engagementId ? [engagementId] : null, page_size: 25 });
  const items = useMemo(() => {
    const list = res.data?.items ?? [];
    return value && !list.some((d) => d.id === value.id) ? [value, ...list] : list;
  }, [res.data, value]);
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={`${id}-q`}>
        {label}
        {required ? (
          <span className="ms-0.5 text-destructive" aria-hidden>
            *
          </span>
        ) : null}
      </Label>
      <div className="grid gap-2 sm:grid-cols-2">
        <Input id={`${id}-q`} type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("searchWorker")} autoComplete="off" data-testid={`${id}-search`} />
        <Select
          id={id}
          aria-label={label}
          aria-invalid={error ? true : undefined}
          value={value?.id ?? ""}
          onChange={(e) => onChange(items.find((d) => d.id === e.target.value) ?? null)}
          data-testid={id}
        >
          <option value="">{tc("select")}</option>
          {items.map((d) => (
            <option key={d.id} value={d.id}>
              {d.worker_no} — {personName({ ...d }, locale)}
              {d.engagement ? ` (${d.engagement.short_code})` : ""}
            </option>
          ))}
        </Select>
      </div>
      {error ? (
        <p role="alert" className="text-xs font-medium text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/** Pick a vehicle of the project (vehicle_no / fleet_no search). */
export function VehicleSelect({
  id,
  projectId,
  value,
  onChange,
  placeholder,
  engagementId,
}: {
  id: string;
  projectId: string;
  value: string;
  onChange: (id: string, v: Schemas["VehicleRead"] | null) => void;
  placeholder?: string;
  engagementId?: string | null;
}) {
  const tc = useTranslations("common");
  const te = useTranslations("enums");
  const q = useVehicles(projectId, { page_size: 200, engagement_id: engagementId ? [engagementId] : null });
  const items = q.data?.items ?? [];
  return (
    <Select id={id} value={value} onChange={(e) => onChange(e.target.value, items.find((v) => v.id === e.target.value) ?? null)} data-testid={id}>
      <option value="">{placeholder ?? tc("select")}</option>
      {items.map((v) => (
        <option key={v.id} value={v.id}>
          {v.vehicle_no} · {v.fleet_no} · {te(`vehicleCategory.${v.category}`)}
        </option>
      ))}
    </Select>
  );
}

/** Reasons returned with a gate check / exclusion (deny red, warn amber). */
export function ReasonChips({ codes }: { codes: Schemas["GateReasonCode"][] }) {
  const te = useTranslations("enums");
  if (codes.length === 0) return null;
  return (
    <span className="flex flex-wrap gap-1">
      {codes.map((c) => (
        // A hook with no provider yet is information, not a warning: neutral so airside rows are not all amber.
        <Badge key={c} tone={c === "HOOK_NOT_AVAILABLE" ? "neutral" : c === "EXPIRING_7D" || c === "LANGUAGE_MISMATCH" ? "warning" : "danger"} data-reason={c}>
          {c === "HOOK_NOT_AVAILABLE" ? <Info aria-hidden /> : null}
          {te(`gateReason.${c}`)}
        </Badge>
      ))}
    </span>
  );
}

/** WAP blockers (WA-13) with the API's EN/AR detail. */
export function Blockers({ blockers }: { blockers: Schemas["WapBlockerRead"][] }) {
  const t = useTranslations("waps");
  const te = useTranslations("enums");
  const ar = useLocale() === "ar";
  if (blockers.length === 0)
    return (
      <p className="inline-flex items-center gap-1.5 text-sm text-success" data-testid="no-blockers">
        <ShieldCheck aria-hidden className="size-4" />
        {t("noBlockers")}
      </p>
    );
  return (
    <ul className="flex flex-col gap-1.5" data-testid="blockers">
      {blockers.map((b, i) => (
        <li key={`${b.code}-${i}`} className="flex items-start gap-2 rounded-md border border-warning/40 bg-warning-bg p-2 text-sm" data-testid="blocker" data-code={b.code}>
          <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0 text-warning" />
          <span>
            <span className="font-medium">{te(`wapBlocker.${b.code}`)}</span>
            {(ar ? b.detail_ar : b.detail_en) ? <span className="block text-xs text-muted-foreground">{ar ? b.detail_ar : b.detail_en}</span> : null}
            {b.ref ? <Code className="text-xs">{b.ref}</Code> : null}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Localised name of a bilingual ref (zone, site, engagement). */
export function useRefName() {
  const name = useLocalizedName();
  return (r: { name_en: string; name_ar: string } | null | undefined) => (r ? name(r.name_en, r.name_ar) : "—");
}

/**
 * Drawn signature (finger, pen or mouse). Emits a base64 PNG (without the data: prefix) or null when cleared.
 * Tests draw on it with mouse moves like any user.
 */
export function SignaturePad({ id, onChange, label, error }: { id: string; onChange: (b64: string | null) => void; label: string; error?: string }) {
  const t = useTranslations("access");
  const ref = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);
  const [signed, setSigned] = useState(false);
  function pos(e: React.PointerEvent<HTMLCanvasElement>) {
    const c = ref.current!;
    const r = c.getBoundingClientRect();
    return { x: ((e.clientX - r.left) / r.width) * c.width, y: ((e.clientY - r.top) / r.height) * c.height };
  }
  function start(e: React.PointerEvent<HTMLCanvasElement>) {
    const ctx = ref.current?.getContext("2d");
    if (!ctx) return;
    drawing.current = true;
    ref.current?.setPointerCapture?.(e.pointerId);
    const p = pos(e);
    ctx.lineWidth = 3;
    ctx.lineCap = "round";
    ctx.strokeStyle = "#111827";
    ctx.beginPath();
    ctx.moveTo(p.x, p.y);
  }
  function move(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!drawing.current) return;
    const ctx = ref.current?.getContext("2d");
    if (!ctx) return;
    const p = pos(e);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
  }
  function end() {
    if (!drawing.current) return;
    drawing.current = false;
    setSigned(true);
    const data = ref.current?.toDataURL("image/png") ?? "";
    onChange(data.replace(/^data:image\/png;base64,/, ""));
  }
  function clear() {
    const c = ref.current;
    c?.getContext("2d")?.clearRect(0, 0, c.width, c.height);
    setSigned(false);
    onChange(null);
  }
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>
        {label}
        <span className="ms-0.5 text-destructive" aria-hidden>
          *
        </span>
      </Label>
      {/* Paper metaphor: always white with a dark pen (also in dark mode), a baseline to sign on. */}
      <div className="relative w-full max-w-md">
        <canvas
          id={id}
          ref={ref}
          width={480}
          height={160}
          role="img"
          aria-label={label}
          data-testid={id}
          data-signed={signed ? "true" : "false"}
          className={cn("block h-40 w-full touch-none rounded-md border-2 bg-white sm:h-32", signed ? "border-input" : "border-dashed border-input", error && "border-danger")}
          onPointerDown={start}
          onPointerMove={move}
          onPointerUp={end}
          onPointerLeave={end}
        />
        <span aria-hidden className="pointer-events-none absolute inset-x-6 bottom-8 flex items-end gap-1 border-b border-black/30 text-lg leading-none text-black/50 sm:bottom-6">
          ×
        </span>
      </div>
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span>{signed ? t("signed") : t("signHere")}</span>
        {signed ? (
          <Button type="button" size="sm" variant="ghost" onClick={clear} data-testid={`${id}-clear`}>
            {t("clearSignature")}
          </Button>
        ) : null}
      </div>
      {error ? (
        <p role="alert" className="text-xs font-medium text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/** Confirm dialog for a workflow step with its own extra fields (rendered as children). */
export function StepDialog({
  title,
  description,
  warning,
  children,
  confirmLabel,
  destructive,
  disabled,
  onConfirm,
  onClose,
  testId = "step-confirm",
  wide,
}: {
  title: string;
  description?: ReactNode;
  warning?: ReactNode;
  children?: ReactNode;
  confirmLabel: string;
  destructive?: boolean;
  disabled?: boolean;
  onConfirm: () => Promise<unknown>;
  onClose: () => void;
  testId?: string;
  wide?: boolean;
}) {
  const tc = useTranslations("common");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  async function go() {
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent closeLabel={tc("close")} className={wide ? "max-w-2xl" : undefined}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
        </DialogHeader>
        {warning ? <Alert tone="warning">{warning}</Alert> : null}
        {children ? <div className="flex flex-col gap-3">{children}</div> : null}
        <MutationError error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button variant={destructive ? "destructive" : "default"} onClick={() => void go()} disabled={busy || disabled} data-testid={testId}>
            {busy ? tc("saving") : confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ───────────────────────────── Print documents (access card, AVP sticker, WAP) ───────────────────────────── */

type BiKey = Parameters<ReturnType<typeof useTranslations<"accessPrint">>>[0];

/** "EN|AR" print message → both halves: printed credentials are bilingual whatever the screen language. */
export function useBi() {
  const t = useTranslations("accessPrint");
  return (key: BiKey) => {
    const [en = "", ar = ""] = t(key).split("|");
    return { en, ar };
  };
}

/** A label in both languages, English first (stacked when `stack`, else on one line with a separator). */
export function BiLabel({ k, stack, className }: { k: BiKey; stack?: boolean; className?: string }) {
  const bi = useBi();
  const v = bi(k);
  return (
    <span className={cn(stack ? "flex flex-col items-start leading-tight" : "inline-flex flex-wrap items-baseline gap-x-1.5", className)}>
      <span lang="en" dir="ltr">
        {v.en}
      </span>
      {stack ? null : <span aria-hidden>/</span>}
      <span lang="ar" dir="rtl">
        {v.ar}
      </span>
    </span>
  );
}

/**
 * Bilingual header for printed access documents: platform mark, project code and name, document title in
 * English (start) and Arabic (end). Always laid out LTR so the English side is on the left on paper.
 */
export function AccessPrintHeader({ title, projectId, variant = "wide" }: { title: BiKey; projectId?: string | null; variant?: "wide" | "narrow" | "card" }) {
  const bi = useBi();
  const { projects, project: current } = useCurrentProject();
  const p = projects.find((x) => x.id === projectId) ?? current;
  const v = bi(title);
  const mark = (
    <span aria-hidden className={cn("flex shrink-0 items-center justify-center rounded bg-black text-white", variant === "card" ? "size-5" : "size-8")}>
      <ShieldCheck className={variant === "card" ? "size-3.5" : "size-5"} />
    </span>
  );
  if (variant === "narrow") {
    // Sticker (90 mm): titles stacked and centred, so neither language is squeezed.
    return (
      <header dir="ltr" className="flex flex-col items-center gap-1 border-b-2 border-black pb-2 text-center" data-testid="print-doc-header">
        <span className="flex items-center gap-2">
          {mark}
          {p ? <span className="text-[9pt] font-semibold tracking-wide">{p.code}</span> : null}
        </span>
        <span lang="en" className="text-[12pt] leading-tight font-bold uppercase">
          {v.en}
        </span>
        <span lang="ar" dir="rtl" className="text-[13pt] leading-tight font-bold">
          {v.ar}
        </span>
      </header>
    );
  }
  const card = variant === "card";
  return (
    <header dir="ltr" className={cn("flex items-center justify-between gap-2 border-b-2 border-black", card ? "pb-1" : "pb-3")} data-testid="print-doc-header">
      <div lang="en" className="flex min-w-0 items-center gap-2">
        {mark}
        <span className="min-w-0">
          {p ? <span className={cn("block truncate font-semibold tracking-wide", card ? "text-[6.5pt]" : "text-[9pt]")}>{card ? p.code : `${p.code} — ${p.name_en}`}</span> : null}
          <span className={cn("block leading-tight font-bold uppercase", card ? "text-[7.5pt]" : "text-[15pt]")}>{v.en}</span>
        </span>
      </div>
      <span lang="ar" dir="rtl" className={cn("shrink-0 leading-tight font-bold", card ? "text-[8.5pt]" : "text-[16pt]")}>
        {v.ar}
        {p && !card ? <span className="block text-[9pt] font-medium">{p.name_ar || p.name_en}</span> : null}
      </span>
    </header>
  );
}
