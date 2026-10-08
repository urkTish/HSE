"use client";
import { Camera, CircleAlert, CircleCheck, CircleHelp, CircleX, Fence, Search, TriangleAlert, Truck, UserRound } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/common/form-field";
import { PageHeader } from "@/components/common/page-header";
import { MutationError } from "@/components/common/states";
import { CameraScanner } from "@/components/gate/gate-check";
import { useCurrentProject } from "@/lib/current-project";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { DEFAULT_TIME_ZONE, formatDate } from "@/lib/datetime";
import { cn } from "@/lib/utils";
import { EquipmentLimitations, PersonnelLimitations, ServiceStatusBadge, TAG_BORDER, TAG_TONE, TagStatusBadge, useReasonLabel } from "./common";

type S = Schemas;

const VERDICT: Record<S["CertCheckResult"], string> = {
  in_service: "bg-verdict-granted text-verdict-granted-fg",
  restricted: "bg-verdict-note text-verdict-note-fg",
  not_usable: "bg-verdict-denied text-verdict-denied-fg",
  revoked_token: "bg-verdict-denied text-verdict-denied-fg",
  unknown: "bg-verdict-neutral text-verdict-neutral-fg",
};

/** Field check of an EQ / scaffold sticker or a worker's AC card (capability 121; VF-8, VF-9). Records nothing but the audit view. */
export function CertCheckPage() {
  const t = useTranslations("certCheck");
  const { projectId } = useCurrentProject();
  const [camera, setCamera] = useState(false);
  const [printedRef, setPrintedRef] = useState("");
  const [certNo, setCertNo] = useState("");
  const [tpiCode, setTpiCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [res, setRes] = useState<S["CertCheckResponse"] | null>(null);
  const submitRef = useRef<(b: S["CertCheckRequest"]) => Promise<void>>(async () => {});

  async function submit(body: S["CertCheckRequest"]) {
    if (!projectId) return;
    setBusy(true);
    setError(null);
    try {
      const r = await unwrap(api.POST("/api/v1/certification-checks", { body: { ...body, project_id: projectId } }));
      setRes(r);
      setCamera(false);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    submitRef.current = submit;
  });
  // Test hook: e2e feeds a QR payload as if the camera had read it (the camera itself is never driven in tests).
  // Installed only once the project is known, so a scan is never sent without project_id.
  useEffect(() => {
    if (!projectId) return;
    const w = window as unknown as { __hseCertScan?: (payload: string) => Promise<void> };
    w.__hseCertScan = (payload: string) => submitRef.current({ payload });
    return () => {
      delete w.__hseCertScan;
    };
  }, [projectId]);

  return (
    <div className="mx-auto max-w-2xl" data-testid="cert-check" data-ready={projectId ? "yes" : "no"}>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <Card className="mb-4">
        <CardContent className="flex flex-col gap-4 pt-5">
          {camera ? <CameraScanner onResult={(p) => void submit({ payload: p })} onClose={() => setCamera(false)} paused={busy} /> : null}
          {!camera ? (
            <Button size="lg" className="h-14 text-lg" onClick={() => setCamera(true)} data-testid="cc-camera">
              <Camera aria-hidden />
              {t("scan")}
            </Button>
          ) : null}
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (printedRef.trim()) void submit({ printed_ref: printedRef.trim().toUpperCase() });
            }}
          >
            <FormField id="cc-ref" label={t("printedRef")} hint={t("printedRefHint")} className="min-w-0 flex-1">
              <Input id="cc-ref" dir="ltr" value={printedRef} onChange={(e) => setPrintedRef(e.target.value)} placeholder="ANIA-EXP-RW-MC-03" data-testid="cc-ref" />
            </FormField>
            <Button type="submit" disabled={busy || !projectId || !printedRef.trim()} data-testid="cc-ref-check">
              <Search aria-hidden />
              {t("check")}
            </Button>
          </form>
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (certNo.trim()) void submit({ cert_no: certNo.trim(), tpi_code: tpiCode.trim() || null });
            }}
          >
            <FormField id="cc-cert" label={t("certNo")} className="min-w-0 flex-1">
              <Input id="cc-cert" dir="ltr" value={certNo} onChange={(e) => setCertNo(e.target.value)} data-testid="cc-cert" />
            </FormField>
            <FormField id="cc-tpi" label={t("tpiCode")} className="w-28">
              <Input id="cc-tpi" dir="ltr" value={tpiCode} onChange={(e) => setTpiCode(e.target.value.toUpperCase())} data-testid="cc-tpi" />
            </FormField>
            <Button type="submit" variant="outline" disabled={busy || !projectId || !certNo.trim()} data-testid="cc-cert-check">
              <Search aria-hidden />
              {t("check")}
            </Button>
          </form>
          <MutationError error={error} />
        </CardContent>
      </Card>
      {res ? <CertCheckResult res={res} /> : null}
    </div>
  );
}

const plain = (x: string) => x.trim().replace(/[.。]$/, "").toLocaleLowerCase();

function CertCheckResult({ res }: { res: S["CertCheckResponse"] }) {
  const te = useTranslations("enums");
  const locale = useLocale();
  const reasonLabel = useReasonLabel();
  const ref = useRef<HTMLElement | null>(null);
  // On a phone the result renders below the scan and manual-entry forms: bring it into view on every new result.
  useEffect(() => {
    ref.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }, [res]);
  const Icon = res.result === "in_service" ? CircleCheck : res.result === "restricted" ? CircleAlert : res.result === "unknown" ? CircleHelp : CircleX;
  const word = te(`certCheckResult.${res.result}`);
  const message = locale === "ar" ? res.message_ar : res.message_en;
  const reason = res.reason_code ? reasonLabel(res.reason_code) : "";
  return (
    <section ref={ref} className="flex scroll-mt-20 flex-col gap-3" data-testid="cc-result" data-result={res.result} aria-live="assertive">
      <div className={cn("flex flex-col items-center gap-1 rounded-xl p-5 text-center shadow-md", VERDICT[res.result])} data-testid="cc-verdict">
        <Icon aria-hidden className="size-14 stroke-[3]" />
        <p className="text-3xl leading-tight font-black tracking-tight uppercase">{word}</p>
        {/* The server message often repeats the verdict word; then the reason in words is the useful second line. */}
        {message && plain(message) !== plain(word) ? <p className="text-base font-medium">{message}</p> : null}
        {reason && reason !== res.reason_code ? <p className="text-lg font-bold">{reason}</p> : null}
        {res.reason_code ? <p className="ltr text-xs opacity-80">{res.reason_code}</p> : null}
      </div>
      {res.equipment ? <EquipmentCheckCardView c={res.equipment} /> : null}
      {res.scaffold ? <ScaffoldCheckCardView c={res.scaffold} /> : null}
      {res.person ? <PersonCheckCardView c={res.person} /> : null}
    </section>
  );
}

/** Context-free date formatting: these cards also render on the gate device screen (no project context). */
function useLiteDate() {
  const locale = useLocale() === "ar" ? "ar" : "en";
  return (v: string | null | undefined) => formatDate(v, { locale, timeZone: DEFAULT_TIME_ZONE, showHijri: false, digits: "western", dateFormatEn: "DD MMM YYYY" });
}

const COLOUR: Record<string, string> = { green: "border-success", amber: "border-warning", red: "border-danger" };

/** EQ sticker card — also used on the gate screen (GE-5: no personal data). */
export function EquipmentCheckCardView({ c }: { c: S["EquipmentCheckCard"] }) {
  const t = useTranslations("certCheck");
  const te = useTranslations("enums");
  const date = useLiteDate();
  return (
    <article className={cn("rounded-xl border-2 bg-surface p-3", COLOUR[c.colour] ?? "border-border")} data-testid="equipment-card" data-colour={c.colour}>
      <div className="flex items-start gap-3">
        <Truck aria-hidden className="size-10 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="ltr text-xl font-bold">
            {c.project_code}-{c.tag}
          </p>
          <p className="text-sm text-muted-foreground">
            {te(`eqc.${c.category}`)} · <span className="ltr">{c.equipment_no}</span>
            {c.owner_short_code ? (
              <>
                {" "}
                · <span className="ltr">{c.owner_short_code}</span>
              </>
            ) : null}
          </p>
          <div className="mt-1">
            <ServiceStatusBadge status={c.service_status} reason={c.service_status_reason} />
          </div>
        </div>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
        <div>
          <dt className="text-xs text-muted-foreground">{t("certificate")}</dt>
          <dd className="ltr font-mono">{c.cert_no ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">{t("tpi")}</dt>
          <dd className="ltr">{c.tpi_code ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">{t("validUntil")}</dt>
          <dd data-testid="eq-valid-until">{c.valid_until ? date(c.valid_until) : "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">{t("swl")}</dt>
          <dd className="ltr">{c.swl_t ? `${c.swl_t} t` : "—"}</dd>
        </div>
      </dl>
      {c.arrival_inspection_due ? (
        <p className="mt-2 rounded bg-warning-bg px-2 py-1 text-sm font-medium" data-testid="arrival-due">
          {t("arrivalDue")}
        </p>
      ) : null}
      <div className="mt-2">
        <EquipmentLimitations items={c.limitations} />
      </div>
    </article>
  );
}

export function ScaffoldCheckCardView({ c }: { c: S["ScaffoldCheckCard"] }) {
  const t = useTranslations("certCheck");
  const te = useTranslations("enums");
  const locale = useLocale();
  const date = useLiteDate();
  const restrictions = locale === "ar" ? c.restrictions_ar : c.restrictions_en;
  return (
    <article className={cn("rounded-xl border-2 border-s-[10px] bg-surface p-3", TAG_BORDER[TAG_TONE[c.tag_status]])} data-testid="scaffold-card" data-usable={c.usable_today ? "1" : "0"}>
      <div className="flex items-start gap-3">
        <Fence aria-hidden className="size-10 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="ltr text-xl font-bold">
            {c.project_code}-{c.tag}
          </p>
          <p className="text-sm text-muted-foreground">
            <span className="ltr">{c.scaffold_no}</span> · <span className="ltr">{c.zone_code}</span> · {t("loadClass", { n: c.load_class })}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <TagStatusBadge status={c.tag_status} />
            <span className="text-sm">{te(`scaffoldStatus.${c.status}`)}</span>
          </div>
        </div>
      </div>
      <p className="mt-2 text-sm font-semibold">{c.usable_today ? t("usableToday") : t("notUsableToday")}</p>
      {c.tag_valid_until ? <p className="text-sm">{t("tagValidUntil", { d: date(c.tag_valid_until) })}</p> : null}
      {restrictions ? (
        <p className="mt-2 flex items-start gap-2 rounded-md border-2 border-tag-yellow bg-warning-bg px-2 py-1.5 text-base font-semibold" dir="auto">
          <TriangleAlert aria-hidden className="mt-0.5 size-5 shrink-0 text-warning" />
          {restrictions}
        </p>
      ) : null}
    </article>
  );
}

export function PersonCheckCardView({ c }: { c: S["PersonCheckCard"] }) {
  const t = useTranslations("certCheck");
  const te = useTranslations("enums");
  const locale = useLocale();
  const date = useLiteDate();
  return (
    <article className="rounded-xl border bg-surface p-3" data-testid="person-cert-card">
      <div className="flex gap-3">
        <div className="size-24 shrink-0 overflow-hidden rounded-lg border bg-muted">
          {c.photo_url ? (
            // eslint-disable-next-line @next/next/no-img-element -- short-lived signed URL, never cached
            <img src={c.photo_url} alt={c.full_name_en} className="size-full object-cover" referrerPolicy="no-referrer" />
          ) : (
            <div className="flex size-full items-center justify-center text-muted-foreground">
              <UserRound aria-hidden className="size-10" />
            </div>
          )}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-lg leading-tight font-bold" lang="en" dir="ltr">
            {c.full_name_en}
          </p>
          <p className="text-lg leading-tight font-bold" lang="ar" dir="rtl">
            {c.full_name_ar}
          </p>
          <p className="ltr mt-1 font-mono">{c.worker_no}</p>
          <p className="text-sm text-muted-foreground">
            {c.employer_short_code ? <span className="ltr">{c.employer_short_code}</span> : null}
            {c.trade ? <> · {te(`trade.${c.trade}`)}</> : null}
          </p>
        </div>
      </div>
      {c.certificates.length ? (
        <ul className="mt-3 flex flex-col gap-2">
          {c.certificates.map((x) => (
            <li key={`${x.tpi_code}-${x.cert_no}`} className={cn("rounded-lg border-2 p-2", x.in_force ? "border-success/60" : "border-danger/60 bg-danger-bg")} data-testid="person-cert" data-code={x.cert_type} data-in-force={x.in_force ? "1" : "0"}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-semibold">
                  {locale === "ar" ? x.cert_type_label_ar : x.cert_type_label_en} <span className="ltr text-xs text-muted-foreground">{x.cert_type}</span>
                </span>
                <Badge tone={x.in_force ? "success" : "danger"}>{x.in_force ? t("inForce") : t("notInForce")}</Badge>
              </div>
              <p className="text-sm">
                <span className="ltr">
                  {x.tpi_code} {x.cert_no}
                </span>
                {x.level ? <> · {te.has(`certLevel.${x.level as S["CertLevel"]}`) ? te(`certLevel.${x.level as S["CertLevel"]}`) : x.level}</> : null}
                {x.valid_until ? <> · {t("until", { d: date(x.valid_until) })}</> : null}
                {x.max_capacity_t ? <> · ≤ <span className="ltr">{x.max_capacity_t} t</span></> : null}
              </p>
              {x.scope_categories.length ? <p className="text-xs text-muted-foreground">{x.scope_categories.map((s) => te(`eqc.${s}`)).join(" · ")}</p> : null}
              {!x.in_force && x.not_in_force_reason ? (
                <p className="text-sm font-medium">{te.has(`hookReason.${x.not_in_force_reason as S["HookReasonCode"]}`) ? te(`hookReason.${x.not_in_force_reason as S["HookReasonCode"]}`) : x.not_in_force_reason}</p>
              ) : null}
              <PersonnelLimitations items={x.limitations} />
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-muted-foreground">{t("noCertificates")}</p>
      )}
    </article>
  );
}
