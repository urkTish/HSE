"use client";
import { AlarmClock, Ban, Copy, Flame, Hand, Handshake, OctagonAlert, Pause, PenLine, Play, Siren, Trash2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { CheckboxField, FormField } from "@/components/common/form-field";
import { UserSelect } from "@/components/common/pickers";
import { LoadingState } from "@/components/common/states";
import { StepDialog } from "@/components/access/common";
import { useMeData } from "@/components/shell/me-context";
import { useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useHandovers, usePtwRefresh, useReadiness } from "@/lib/api/ptw";
import { can } from "@/lib/permissions";
import { PAUSE_REASONS, STATUS_REASONS, WIND_SOURCES, WORK_STATUSES } from "@/lib/ptw-enums";
import { useFormatters } from "@/lib/use-formatters";
import { cn } from "@/lib/utils";
import { RecordActions } from "@/components/common/record-actions";
import { BlockerList, DateTimeInput, DecimalInput, WarningList, nowIso, useNow, userLabel } from "./common";
import { ReceiverCosign, SigningNotice, cosignBody, useSigned, type CosignState } from "./signing";

type S = Schemas;
type Permit = S["PermitRead"];

export type Step =
  | S["PermitAction"]
  | "accept"
  | "pause"
  | "pause_end"
  | "gas_alarm"
  | "hot_work_end"
  | "post_expiry"
  | "handover_accept"
  | "copy"
  | "delete"
  | "heat_resume"
  | "drill_resume";

/** Lifecycle actions offered by the server (allowed_actions) plus field actions derived from role and status. */
/** primary = the safe next step; outline = other steps; stop = stop work (always reachable); alarm = emergency;
 *  irreversible = cannot be undone (kept apart and outlined, never the loudest button); record = housekeeping. */
export type StepTone = "primary" | "outline" | "stop" | "alarm" | "irreversible" | "record";

export function usePermitSteps(p: Permit): { k: Step; tone: StepTone }[] {
  const me = useMeData();
  const now = useNow(30_000);
  const handovers = useHandovers(p.id, { enabled: p.status === "active" });
  const receiver = p.receiver.id === me.id;
  const issuer = p.issuer?.id === me.id;
  const a = new Set(p.allowed_actions);
  const out: { k: Step; tone: StepTone }[] = [];
  const order: [S["PermitAction"], StepTone][] = [
    ["request", "primary"],
    ["review", "primary"],
    ["hse_review", "primary"],
    ["approve", "primary"],
    ["issue", "primary"],
    ["start", "primary"],
    ["revalidate", "primary"],
    ["resume", "primary"],
    ["handover", "outline"],
    ["end_shift", "outline"],
    ["request_closure", "outline"],
    ["close", "primary"],
    ["return", "outline"],
    ["suspend", "stop"],
    ["cancel", "irreversible"],
  ];
  for (const [k, tone] of order) if (a.has(k)) out.push({ k, tone });
  const awaitingAcceptance = receiver && (p.status === "approved" || p.status === "suspended") && !(p.receiver_acceptance && new Date(p.receiver_acceptance.valid_until).getTime() > now);
  if (awaitingAcceptance && can(me, "permit.receive", p.project_id)) out.push({ k: "accept", tone: "outline" });
  // 6b PH-3: after a WBGT stop the receiver resumes (no issuer cause text) once HEAT_STOP clears.
  if (p.status === "suspended" && p.status_reason === "heat_stress_stop" && receiver && can(me, "permit.receive", p.project_id)) out.push({ k: "heat_resume", tone: "primary" });
  // 6c PE-2: after a drill the receiver resumes (no issuer cause text) once the drill is Conducted.
  if (p.status === "suspended" && p.status_reason === "emergency_drill" && receiver && can(me, "permit.receive", p.project_id)) out.push({ k: "drill_resume", tone: "primary" });
  if (p.status === "active" && receiver) {
    if (p.current_shift?.paused_now) out.push({ k: "pause_end", tone: "primary" });
    else out.push({ k: "pause", tone: "outline" });
    const hw = p.work_types.includes("hot_work") && !(p.sections as unknown as { work_type?: string; hot_work_ended_at?: string | null }[]).find((s) => s.work_type === "hot_work")?.hot_work_ended_at;
    if (hw) out.push({ k: "hot_work_end", tone: "outline" });
  }
  if (p.status === "active" && p.gas.required) out.push({ k: "gas_alarm", tone: "alarm" });
  if (p.status === "expired" && p.post_expiry_check_pending && issuer) out.push({ k: "post_expiry", tone: "primary" });
  const pending = (handovers.data?.items ?? []).find((h) => h.status === "initiated" && (h.to_receiver.id === me.id || h.to_issuer.id === me.id));
  if (pending) out.push({ k: "handover_accept", tone: "primary" });
  if (p.status === "draft" && can(me, "permit.prepare", p.project_id) && !p.first_requested_at) out.push({ k: "delete", tone: "irreversible" });
  if (can(me, "permit.prepare", p.project_id)) out.push({ k: "copy", tone: "record" });
  return out;
}

const ICON: Partial<Record<Step, typeof Play>> = {
  start: Play,
  heat_resume: Play,
  drill_resume: Play,
  pause: Pause,
  pause_end: Play,
  gas_alarm: Siren,
  hot_work_end: Flame,
  accept: PenLine,
  handover: Handshake,
  handover_accept: Handshake,
  copy: Copy,
  delete: Trash2,
  end_shift: AlarmClock,
  suspend: Hand,
  cancel: Ban,
};

/**
 * `part="main"` leaves the irreversible steps (Cancel / Delete) to `part="end"` at the page end, as long as there
 * is another step to show at the top; with nothing else they stay in the bar so the bar is never empty.
 * Stop-work (Suspend, Gas alarm) always stays at the top: it must be reachable at once.
 */
export function PermitActionBar({ permit, onStep, part = "all" }: { permit: Permit; onStep: (s: Step) => void; part?: "all" | "main" | "end" }) {
  const t = useTranslations("permitActions");
  const td = useTranslations("ptwDesign");
  const steps = usePermitSteps(permit);
  if (!steps.length) return null;
  const go = steps.filter((s) => s.tone === "primary");
  const more = steps.filter((s) => s.tone === "outline" || s.tone === "record");
  const stop = steps.filter((s) => s.tone === "stop" || s.tone === "alarm");
  const allEnd = steps.filter((s) => s.tone === "irreversible");
  const split = part !== "all" && go.length + more.length + stop.length > 0;
  const btn = (s: { k: Step; tone: StepTone }, cls?: string) => {
    const Icon = ICON[s.k];
    const variant = s.tone === "primary" || s.tone === "alarm" ? (s.tone === "alarm" ? "destructive" : "default") : s.tone === "stop" || s.tone === "irreversible" ? "destructive-outline" : s.tone === "record" ? "ghost" : "outline";
    return (
      <Button key={s.k} variant={variant} onClick={() => onStep(s.k)} data-testid={`act-${s.k}`} data-tone={s.tone} className={cn("h-auto min-h-control py-2 whitespace-normal", cls)}>
        {Icon ? <Icon aria-hidden /> : null}
        {t(`btn.${s.k}`)}
      </Button>
    );
  };
  if (part === "end") {
    if (!split || !allEnd.length) return null;
    return (
      <RecordActions label={td("endGroup")} testId="permit-end-actions">
        {allEnd.map((s) => btn(s))}
      </RecordActions>
    );
  }
  const end = split ? [] : allEnd;
  // Phone: the safe next step full width first, then the others two per row, then stop-work and the
  // irreversible actions in their own labelled rows. Desktop: one row, stop / irreversible pushed to the end.
  return (
    <div className="flex flex-col gap-3 lg:flex-row lg:flex-wrap lg:items-center" data-testid="permit-actions">
      {go.length ? <div className="grid gap-2 sm:flex sm:flex-wrap">{go.map((s) => btn(s, "min-h-12 text-base sm:min-h-control sm:text-sm"))}</div> : null}
      {more.length ? <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">{more.map((s) => btn(s))}</div> : null}
      {stop.length ? (
        <div role="group" aria-label={td("stopGroup")} className="flex flex-col gap-1.5 border-t pt-3 lg:ms-auto lg:flex-row lg:items-center lg:border-t-0 lg:pt-0">
          <span className="text-xs font-semibold text-muted-foreground lg:sr-only">{td("stopGroup")}</span>
          <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">{stop.map((s) => btn(s))}</div>
        </div>
      ) : null}
      {end.length ? (
        <div role="group" aria-label={td("endGroup")} className={cn("flex flex-col gap-1.5 border-t pt-3 lg:flex-row lg:items-center lg:border-t-0 lg:border-s lg:ps-3 lg:pt-0", !stop.length && "lg:ms-auto")}>
          <span className="text-xs font-semibold text-muted-foreground lg:sr-only">{td("endGroup")}</span>
          <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">{end.map((s) => btn(s))}</div>
        </div>
      ) : null}
    </div>
  );
}

/** Readiness preview for one action (blockers, warnings, other errors it would return). */
function Readiness({ permit, action }: { permit: Permit; action: S["PermitAction"] }) {
  const t = useTranslations("permitActions");
  const te = useTranslations("errors");
  const q = useReadiness(permit.id, action);
  if (q.isLoading) return <LoadingState rows={1} />;
  if (!q.data) return null;
  const r = q.data;
  return (
    <div className="flex flex-col gap-2" data-testid="readiness" data-allowed={r.allowed ? "true" : "false"}>
      {r.allowed ? null : <p className="flex items-center gap-1 text-sm font-medium text-danger"><OctagonAlert aria-hidden className="size-3.5 shrink-0" />{t("notReady")}</p>}
      {r.blockers.length ? <BlockerList items={r.blockers} /> : null}
      {r.errors.length ? (
        <ul className="list-inside list-disc text-sm text-danger" data-testid="readiness-errors">
          {r.errors.map((e) => (
            <li key={e} data-code={e}>
              {te.has(`code.${e}` as "code.UNKNOWN") ? te(`code.${e}` as "code.UNKNOWN") : e}
            </li>
          ))}
        </ul>
      ) : null}
      <WarningList items={r.warnings} />
    </div>
  );
}

type CrewSel = Record<string, { present: boolean; briefed: boolean }>;

/** Crew present at the start of a shift: tick who is here and briefed (SH-4). */
function CrewPresent({ permit, value, onChange }: { permit: Permit; value: CrewSel; onChange: (v: CrewSel) => void }) {
  const t = useTranslations("permitActions");
  const te = useTranslations("enums");
  const locale = useLocale();
  const lines = permit.crew.filter((c) => c.status === "listed");
  return (
    <fieldset className="flex flex-col gap-1 rounded-md border p-3" data-testid="crew-present">
      <legend className="px-1 text-sm font-medium">{t("crewPresent")}</legend>
      <p className="text-xs text-muted-foreground">{t("crewPresentHint")}</p>
      {lines.map((c) => {
        const w = c.worker;
        if (!w) return null;
        const v = value[w.id] ?? { present: false, briefed: false };
        const n = locale === "ar" ? w.full_name_ar || w.full_name_en : w.full_name_en || w.full_name_ar;
        return (
          <div key={c.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b py-1.5 last:border-0" data-testid="crew-present-row" data-worker-no={w.worker_no}>
            <span className="min-w-0 flex-1 text-sm">
              <bdi className="ltr text-muted-foreground">{w.worker_no}</bdi> {n} <span className="text-xs text-muted-foreground">· {te(`ptwCrewRole.${c.crew_role}`)}</span>
            </span>
            <label className="flex min-h-touch items-center gap-1.5 text-sm">
              <Checkbox checked={v.present} onChange={(e) => onChange({ ...value, [w.id]: { present: e.target.checked, briefed: e.target.checked ? v.briefed || true : false } })} data-testid="crew-present-check" />
              {t("present")}
            </label>
            <label className="flex min-h-touch items-center gap-1.5 text-sm">
              <Checkbox checked={v.briefed} disabled={!v.present} onChange={(e) => onChange({ ...value, [w.id]: { ...v, briefed: e.target.checked } })} data-testid="crew-briefed-check" />
              {t("briefed")}
            </label>
          </div>
        );
      })}
    </fieldset>
  );
}

function crewBody(v: CrewSel): S["CrewPresentInput"][] {
  return Object.entries(v)
    .filter(([, x]) => x.present)
    .map(([worker_id, x]) => ({ worker_id, briefed: x.briefed }));
}

type Wind = { on: boolean; at: string; speed: string; source: S["WindSource"]; ref: string };

function WindFields({ value, onChange }: { value: Wind; onChange: (v: Wind) => void }) {
  const t = useTranslations("permitActions");
  const te = useTranslations("enums");
  return (
    <fieldset className="flex flex-col gap-2 rounded-md border p-3" data-testid="wind-fields">
      <legend className="px-1 text-sm font-medium">{t("wind")}</legend>
      <CheckboxField id="wind-on" label={t("windRecord")}>
        <Checkbox checked={value.on} onChange={(e) => onChange({ ...value, on: e.target.checked })} data-testid="wind-on" />
      </CheckboxField>
      {value.on ? (
        <div className="grid gap-2 sm:grid-cols-2">
          <FormField id="wind-speed" label={t("windSpeed")} required>
            <DecimalInput value={value.speed} onChange={(s) => onChange({ ...value, speed: s })} data-testid="wind-speed" />
          </FormField>
          <FormField id="wind-at" label={t("measuredAt")}>
            <DateTimeInput value={value.at} onChange={(s) => onChange({ ...value, at: s })} />
          </FormField>
          <FormField id="wind-src" label={t("windSource")}>
            <Select value={value.source} onChange={(e) => onChange({ ...value, source: e.target.value as S["WindSource"] })}>
              {WIND_SOURCES.map((x) => (
                <option key={x} value={x}>
                  {te(`windSource.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="wind-ref" label={t("windRef")}>
            <Input className="ltr" value={value.ref} onChange={(e) => onChange({ ...value, ref: e.target.value })} />
          </FormField>
        </div>
      ) : null}
    </fieldset>
  );
}

function windBody(w: Wind): S["WindReadingInput"] | null {
  return w.on && w.speed ? { measured_at: w.at || nowIso(), speed_ms: w.speed, source: w.source, source_ref: w.ref || null } : null;
}

const needsWind = (p: Permit) => p.work_types.includes("lifting") || p.work_types.includes("work_at_height");
const outdoor = (p: Permit) => p.exposure !== "indoor";

/** One dialog per lifecycle / field action. Signing steps go through re-authentication; 422 blockers are listed in full. */
export function PermitStepDialog({ permit, step, onClose }: { permit: Permit; step: Step; onClose: () => void }) {
  const t = useTranslations("permitActions");
  const td = useTranslations("ptwDesign");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const locale = useLocale();
  const router = useRouter();
  const refresh = usePtwRefresh();
  const signed = useSigned();
  const { dateTime } = useFormatters(permit.project_id);
  const handovers = useHandovers(permit.id, { enabled: step === "handover_accept" });
  const [comment, setComment] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [confirm2, setConfirm2] = useState(false);
  const [reason, setReason] = useState<S["StatusReason"] | "">("");
  const [crew, setCrew] = useState<CrewSel>({});
  const [temp, setTemp] = useState("");
  const [wind, setWind] = useState<Wind>({ on: false, at: "", speed: "", source: "anemometer", ref: "" });
  const [cosign, setCosign] = useState<CosignState>({ mode: "device", password: "" });
  const [condEn, setCondEn] = useState(permit.conditions_en ?? "");
  const [condAr, setCondAr] = useState(permit.conditions_ar ?? "");
  const [special, setSpecial] = useState("");
  const [wapNo, setWapNo] = useState("");
  const [decision, setDecision] = useState<"accepted" | "returned">("accepted");
  const [workStatus, setWorkStatus] = useState<S["WorkStatus"]>("complete");
  const [pauseReason, setPauseReason] = useState<S["PauseReason"]>("break");
  const [at, setAt] = useState(nowIso());
  const [areaSafe, setAreaSafe] = useState(true);
  const [entrantsZero, setEntrantsZero] = useState(true);
  const [locksRemoved, setLocksRemoved] = useState(true);
  const [fireWatch, setFireWatch] = useState("");
  const [toReceiver, setToReceiver] = useState("");
  const [toIssuer, setToIssuer] = useState(permit.issuer?.id ?? "");
  const [copyFrom, setCopyFrom] = useState("");
  const [copyTo, setCopyTo] = useState("");
  const path = { params: { path: { permit_id: permit.id } } };
  const done = async (p: Permit | null, msg: string) => {
    await refresh(p ?? undefined);
    toast.success(msg);
  };
  const suspendReasons = STATUS_REASONS.filter((r) => !["shift_end", "rejected", "not_required", "duplicate", "shift_lapsed", "heat_stress_stop", "emergency_drill"].includes(r));
  const cancelReasons: S["StatusReason"][] = ["rejected", "not_required", "duplicate", "contractor_suspended", "contractor_blacklisted", "other"];
  const routineSuspension = permit.status_reason === "shift_end" || permit.status_reason === "shift_lapsed" || permit.status_reason === "midday_ban" || permit.status_reason === "heat_stress_stop" || permit.status_reason === "emergency_drill";
  const purpose: S["AcceptancePurpose"] = permit.status === "approved" ? "issue" : routineSuspension ? "revalidate" : "resume";
  const readinessAction: S["PermitAction"] | null = step === "heat_resume" || step === "drill_resume" ? "resume" : (["request", "review", "hse_review", "approve", "issue", "start", "end_shift", "revalidate", "resume", "request_closure", "close", "handover"] as const).includes(step as "request")
    ? (step as S["PermitAction"])
    : null;
  const title = t(`title.${step}`);
  const pending = (handovers.data?.items ?? []).find((h) => h.status === "initiated");

  let body: React.ReactNode = null;
  let run: () => Promise<unknown> = async () => undefined;
  let disabled = false;
  let destructive = false;
  let sign = false;
  // Steps that cannot be undone get a plain warning at the top of the dialog.
  const irreversible = step === "cancel" || step === "delete" || step === "close";

  switch (step) {
    case "request":
      sign = true;
      run = async () => done(await signed(() => unwrap(api.POST("/api/v1/permits/{permit_id}/request", { ...path, body: { comment: comment || null } }))), te("permitStatus.requested"));
      body = (
        <FormField id="st-comment" label={t("commentOptional")}>
          <Textarea value={comment} onChange={(e) => setComment(e.target.value)} maxLength={500} />
        </FormField>
      );
      break;
    case "return":
      disabled = comment.trim().length < 10;
      run = async () => done(await unwrap(api.POST("/api/v1/permits/{permit_id}/return", { ...path, body: { comment: comment.trim() } })), t("returned"));
      body = (
        <FormField id="st-comment" label={t("returnComment")} required hint={t("min10")}>
          <Textarea value={comment} onChange={(e) => setComment(e.target.value)} maxLength={500} data-testid="st-comment" />
        </FormField>
      );
      break;
    case "review":
      sign = true;
      disabled = !confirm || !confirm2;
      run = async () =>
        done(
          await signed(() =>
            unwrap(api.POST("/api/v1/permits/{permit_id}/review", { ...path, body: { area_conditions_known: true, simops_reviewed: true, special_area_hazards: special || null, wap_no_confirmed: wapNo || null } })),
          ),
          te("permitStatus.reviewed"),
        );
      body = (
        <>
          <CheckboxField id="st-area" label={t("areaConditionsKnown")}>
            <Checkbox checked={confirm} onChange={(e) => setConfirm(e.target.checked)} data-testid="st-area-known" />
          </CheckboxField>
          <CheckboxField id="st-simops" label={t("simopsReviewed")}>
            <Checkbox checked={confirm2} onChange={(e) => setConfirm2(e.target.checked)} data-testid="st-simops-reviewed" />
          </CheckboxField>
          <FormField id="st-special" label={t("specialHazards")}>
            <Textarea value={special} onChange={(e) => setSpecial(e.target.value)} maxLength={500} />
          </FormField>
          {permit.waps.length ? (
            <FormField id="st-wap" label={t("wapConfirm")}>
              <Input className="ltr" value={wapNo} onChange={(e) => setWapNo(e.target.value)} placeholder={permit.waps[0]?.wap_no} />
            </FormField>
          ) : null}
        </>
      );
      break;
    case "hse_review":
      sign = true;
      disabled = decision === "returned" && comment.trim().length < 10;
      run = async () => done(await signed(() => unwrap(api.POST("/api/v1/permits/{permit_id}/hse-review", { ...path, body: { decision, comment: comment || null } }))), t(`hse.${decision}`));
      body = (
        <>
          <fieldset className="flex flex-wrap gap-4 text-sm">
            <label className="flex min-h-touch items-center gap-2">
              <input type="radio" checked={decision === "accepted"} onChange={() => setDecision("accepted")} data-testid="hse-accept" />
              {t("hse.accepted")}
            </label>
            <label className="flex min-h-touch items-center gap-2">
              <input type="radio" checked={decision === "returned"} onChange={() => setDecision("returned")} data-testid="hse-return" />
              {t("hse.returned")}
            </label>
          </fieldset>
          <FormField id="st-comment" label={decision === "returned" ? t("returnComment") : t("commentOptional")} required={decision === "returned"}>
            <Textarea value={comment} onChange={(e) => setComment(e.target.value)} maxLength={500} />
          </FormField>
          {permit.high_risk_reasons_en.length ? (
            <Alert tone="info">
              {t("highRiskBecause")}: {permit.high_risk_reasons_en.join("; ")}
            </Alert>
          ) : null}
        </>
      );
      break;
    case "approve":
      sign = true;
      run = async () => done(await signed(() => unwrap(api.POST("/api/v1/permits/{permit_id}/approve", { ...path, body: { comment: comment || null } }))), te("permitStatus.approved"));
      body = (
        <FormField id="st-comment" label={t("commentOptional")}>
          <Textarea value={comment} onChange={(e) => setComment(e.target.value)} maxLength={500} />
        </FormField>
      );
      break;
    case "issue":
      sign = true;
      disabled = !confirm || (cosign.mode === "here" && !cosign.password);
      run = async () =>
        done(
          await signed(() =>
            unwrap(
              api.POST("/api/v1/permits/{permit_id}/issue", {
                ...path,
                body: { site_visit_confirmed: true, receiver_cosign: cosignBody(permit, cosign), conditions_en: condEn || null, conditions_ar: condAr || null, wind_reading: windBody(wind) },
              }),
            ),
          ),
          te("permitStatus.issued"),
        );
      body = (
        <>
          <CheckboxField id="st-site" label={t("siteVisit")}>
            <Checkbox checked={confirm} onChange={(e) => setConfirm(e.target.checked)} data-testid="st-site-visit" />
          </CheckboxField>
          <FormField id="st-cond-en" label={t("conditionsEn")}>
            <Textarea value={condEn} onChange={(e) => setCondEn(e.target.value)} maxLength={1000} />
          </FormField>
          <FormField id="st-cond-ar" label={t("conditionsAr")}>
            <Textarea dir="rtl" value={condAr} onChange={(e) => setCondAr(e.target.value)} maxLength={1000} />
          </FormField>
          {needsWind(permit) ? <WindFields value={wind} onChange={setWind} /> : null}
          <ReceiverCosign permit={permit} purpose="issue" value={cosign} onChange={setCosign} />
        </>
      );
      break;
    case "accept":
      sign = true;
      run = async () => {
        await signed(() => unwrap(api.POST("/api/v1/permits/{permit_id}/receiver-acceptance", { ...path, body: { purpose } })));
        await done(null, t("acceptedToast"));
      };
      body = <Alert tone="info">{t(`acceptFor.${purpose}`)}</Alert>;
      break;
    case "start":
      disabled = !Object.values(crew).some((x) => x.present) || (outdoor(permit) && !temp);
      run = async () => done(await unwrap(api.POST("/api/v1/permits/{permit_id}/start", { ...path, body: { crew_present: crewBody(crew), ambient_temp_c: temp || null, wind_reading: windBody(wind) } })), te("permitStatus.active"));
      body = (
        <>
          <CrewPresent permit={permit} value={crew} onChange={setCrew} />
          {outdoor(permit) ? (
            <FormField id="st-temp" label={t("ambientTemp")} required hint={t("ambientTempHint")}>
              <DecimalInput value={temp} onChange={setTemp} data-testid="st-temp" />
            </FormField>
          ) : null}
          {needsWind(permit) ? <WindFields value={wind} onChange={setWind} /> : null}
        </>
      );
      break;
    case "revalidate":
    case "resume": {
      sign = true;
      const nonRoutine = step === "resume" && !routineSuspension;
      disabled = !confirm || (step === "revalidate" && !confirm2) || !Object.values(crew).some((x) => x.present) || (nonRoutine && comment.trim().length < 20) || (outdoor(permit) && !temp) || (cosign.mode === "here" && !cosign.password);
      run = async () => {
        const common = { crew_present: crewBody(crew), ambient_temp_c: temp || null, wind_reading: windBody(wind), site_visit_confirmed: true as const, receiver_cosign: cosignBody(permit, cosign) };
        const p =
          step === "revalidate"
            ? await signed(() => unwrap(api.POST("/api/v1/permits/{permit_id}/revalidate", { ...path, body: { ...common, checklist_reconfirmed: true } })))
            : await signed(() => unwrap(api.POST("/api/v1/permits/{permit_id}/resume", { ...path, body: { ...common, cause_cleared_text: comment.trim() || null } })));
        await done(p, te("permitStatus.active"));
      };
      body = (
        <>
          {permit.status_reason ? <Alert tone="warning">{t("suspendedFor", { reason: te(`statusReason.${permit.status_reason}`) })}</Alert> : null}
          <CheckboxField id="st-site" label={t("siteVisit")}>
            <Checkbox checked={confirm} onChange={(e) => setConfirm(e.target.checked)} data-testid="st-site-visit" />
          </CheckboxField>
          {step === "revalidate" ? (
            <CheckboxField id="st-check" label={t("checklistReconfirmed")}>
              <Checkbox checked={confirm2} onChange={(e) => setConfirm2(e.target.checked)} data-testid="st-checklist-reconfirmed" />
            </CheckboxField>
          ) : null}
          {nonRoutine ? (
            <FormField id="st-cause" label={t("causeCleared")} required hint={t("min20")}>
              <Textarea value={comment} onChange={(e) => setComment(e.target.value)} maxLength={1000} data-testid="st-cause" />
            </FormField>
          ) : null}
          <CrewPresent permit={permit} value={crew} onChange={setCrew} />
          {outdoor(permit) ? (
            <FormField id="st-temp" label={t("ambientTemp")} required hint={t("ambientTempHint")}>
              <DecimalInput value={temp} onChange={setTemp} data-testid="st-temp" />
            </FormField>
          ) : null}
          {needsWind(permit) ? <WindFields value={wind} onChange={setWind} /> : null}
          <ReceiverCosign permit={permit} purpose={step === "revalidate" ? "revalidate" : "resume"} value={cosign} onChange={setCosign} />
        </>
      );
      break;
    }
    case "heat_resume":
      disabled = !Object.values(crew).some((x) => x.present) || (outdoor(permit) && !temp);
      run = async () => done(await unwrap(api.POST("/api/v1/permits/{permit_id}/heat-resume", { ...path, body: { crew_present: crewBody(crew), ambient_temp_c: temp || null, wind_reading: windBody(wind) } })), te("permitStatus.active"));
      body = (
        <>
          <Alert tone="warning">{t("suspendedFor", { reason: te("statusReason.heat_stress_stop") })}</Alert>
          <p className="text-sm text-muted-foreground" data-testid="heat-resume-hint">
            {t("heatResumeHint")}
          </p>
          <CrewPresent permit={permit} value={crew} onChange={setCrew} />
          {outdoor(permit) ? (
            <FormField id="st-temp" label={t("ambientTemp")} required hint={t("ambientTempHint")}>
              <DecimalInput value={temp} onChange={setTemp} data-testid="st-temp" />
            </FormField>
          ) : null}
          {needsWind(permit) ? <WindFields value={wind} onChange={setWind} /> : null}
        </>
      );
      break;
    case "drill_resume":
      disabled = !Object.values(crew).some((x) => x.present) || (outdoor(permit) && !temp);
      run = async () => done(await unwrap(api.POST("/api/v1/permits/{permit_id}/drill-resume", { ...path, body: { crew_present: crewBody(crew), ambient_temp_c: temp || null, wind_reading: windBody(wind) } })), te("permitStatus.active"));
      body = (
        <>
          <Alert tone="info">{t("suspendedFor", { reason: te("statusReason.emergency_drill") })}</Alert>
          <p className="text-sm text-muted-foreground" data-testid="drill-resume-hint">
            {t("drillResumeHint")}
          </p>
          <CrewPresent permit={permit} value={crew} onChange={setCrew} />
          {outdoor(permit) ? (
            <FormField id="st-temp" label={t("ambientTemp")} required hint={t("ambientTempHint")}>
              <DecimalInput value={temp} onChange={setTemp} data-testid="st-temp" />
            </FormField>
          ) : null}
          {needsWind(permit) ? <WindFields value={wind} onChange={setWind} /> : null}
        </>
      );
      break;
    case "end_shift":
      run = async () => done(await unwrap(api.POST("/api/v1/permits/{permit_id}/end-shift", { ...path, body: { note: comment || null } })), t("shiftEnded"));
      body = (
        <FormField id="st-note" label={t("noteOptional")}>
          <Textarea value={comment} onChange={(e) => setComment(e.target.value)} maxLength={500} />
        </FormField>
      );
      break;
    case "suspend":
      destructive = true;
      disabled = !reason || comment.trim().length < 5;
      run = async () => done(await unwrap(api.POST("/api/v1/permits/{permit_id}/suspend", { ...path, body: { reason: reason as S["StatusReason"], detail: comment.trim() } })), te("permitStatus.suspended"));
      body = (
        <>
          <Alert tone="warning">{t("suspendHint")}</Alert>
          <FormField id="st-reason" label={tc("reason")} required>
            <Select value={reason} onChange={(e) => setReason(e.target.value as S["StatusReason"])} data-testid="st-reason">
              <option value="">{tc("select")}</option>
              {suspendReasons.map((r) => (
                <option key={r} value={r}>
                  {te(`statusReason.${r}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="st-detail" label={t("detail")} required>
            <Textarea value={comment} onChange={(e) => setComment(e.target.value)} maxLength={500} data-testid="st-detail" />
          </FormField>
        </>
      );
      break;
    case "gas_alarm":
      destructive = true;
      run = async () => done(await unwrap(api.POST("/api/v1/permits/{permit_id}/gas-alarm", { ...path, body: { detail: comment || null } })), te("statusReason.gas_alarm"));
      body = (
        <>
          <Alert tone="danger">{t("gasAlarmHint")}</Alert>
          <FormField id="st-detail" label={t("detailOptional")}>
            <Textarea value={comment} onChange={(e) => setComment(e.target.value)} maxLength={500} />
          </FormField>
        </>
      );
      break;
    case "handover":
      disabled = !toReceiver || !toIssuer || comment.trim().length < 10;
      run = async () => {
        await unwrap(api.POST("/api/v1/permits/{permit_id}/handovers", { ...path, body: { to_receiver_user_id: toReceiver, to_issuer_user_id: toIssuer, notes_en: comment.trim() } }));
        await done(null, t("handoverOffered"));
      };
      body = (
        <>
          <p className="text-sm text-muted-foreground">{t("handoverHint")}</p>
          <FormField id="ho-receiver" label={t("incomingReceiver")} required>
            <UserSelect projectId={permit.project_id} role="permit_receiver" value={toReceiver} onChange={(e) => setToReceiver(e.target.value)} data-testid="ho-receiver" />
          </FormField>
          <FormField id="ho-issuer" label={t("incomingIssuer")} required>
            <UserSelect projectId={permit.project_id} role="permit_issuer" value={toIssuer} onChange={(e) => setToIssuer(e.target.value)} data-testid="ho-issuer" />
          </FormField>
          <FormField id="ho-notes" label={t("handoverNotes")} required hint={t("min10")}>
            <Textarea value={comment} onChange={(e) => setComment(e.target.value)} maxLength={1000} data-testid="ho-notes" />
          </FormField>
        </>
      );
      break;
    case "handover_accept":
      sign = true;
      disabled = !pending || !Object.values(crew).some((x) => x.present) || (outdoor(permit) && !temp);
      run = async () => {
        if (!pending) return;
        await signed(() =>
          unwrap(
            api.POST("/api/v1/permit-handovers/{handover_id}/accept", {
              params: { path: { handover_id: pending.id } },
              body: { crew_present: crewBody(crew), ambient_temp_c: temp || null, wind_reading: windBody(wind), cosign: cosign.mode === "here" && cosign.password ? { user_id: pending.to_receiver.id === me.id ? pending.to_issuer.id : pending.to_receiver.id, password: cosign.password } : null },
            }),
          ),
        );
        await done(null, t("handoverAccepted"));
      };
      body = pending ? (
        <>
          <Alert tone="info">
            {t("handoverFrom", { from: userLabel(pending.from_receiver, locale), deadline: dateTime(pending.deadline_at) })}
            <span className="mt-1 block whitespace-pre-wrap">{locale === "ar" && pending.notes_ar ? pending.notes_ar : pending.notes_en}</span>
          </Alert>
          <CrewPresent permit={permit} value={crew} onChange={setCrew} />
          {outdoor(permit) ? (
            <FormField id="st-temp" label={t("ambientTemp")} required hint={t("ambientTempHint")}>
              <DecimalInput value={temp} onChange={setTemp} data-testid="st-temp" />
            </FormField>
          ) : null}
          {needsWind(permit) ? <WindFields value={wind} onChange={setWind} /> : null}
          <fieldset className="flex flex-col gap-2 rounded-md border p-3">
            <legend className="px-1 text-sm font-medium">{t("otherSigner")}</legend>
            <label className="flex min-h-touch items-center gap-2 text-sm">
              <input type="radio" checked={cosign.mode === "device"} onChange={() => setCosign({ mode: "device", password: "" })} />
              {t("otherOwnDevice")}
            </label>
            <label className="flex min-h-touch items-center gap-2 text-sm">
              <input type="radio" checked={cosign.mode === "here"} onChange={() => setCosign({ mode: "here", password: "" })} />
              {t("otherHere", { name: userLabel(pending.to_receiver.id === me.id ? pending.to_issuer : pending.to_receiver, locale) })}
            </label>
            {cosign.mode === "here" ? <Input type="password" autoComplete="off" value={cosign.password} onChange={(e) => setCosign({ ...cosign, password: e.target.value })} aria-label={t("otherPassword")} /> : null}
          </fieldset>
        </>
      ) : (
        <LoadingState rows={1} />
      );
      break;
    case "request_closure":
      disabled = !confirm || (workStatus === "incomplete_area_safe" && comment.trim().length < 10);
      run = async () => done(await unwrap(api.POST("/api/v1/permits/{permit_id}/request-closure", { ...path, body: { work_status: workStatus, remaining_work: comment || null, crew_withdrawn: true } })), t("closureRequested"));
      body = (
        <>
          <FormField id="st-ws" label={t("workStatus")} required>
            <Select value={workStatus} onChange={(e) => setWorkStatus(e.target.value as S["WorkStatus"])} data-testid="st-work-status">
              {WORK_STATUSES.map((x) => (
                <option key={x} value={x}>
                  {te(`workStatus.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
          {workStatus === "incomplete_area_safe" ? (
            <FormField id="st-remaining" label={t("remainingWork")} required>
              <Textarea value={comment} onChange={(e) => setComment(e.target.value)} maxLength={1000} />
            </FormField>
          ) : null}
          <CheckboxField id="st-withdrawn" label={t("crewWithdrawn")}>
            <Checkbox checked={confirm} onChange={(e) => setConfirm(e.target.checked)} data-testid="st-crew-withdrawn" />
          </CheckboxField>
          <p className="text-xs text-muted-foreground">{t("closureChecklistHint")}</p>
        </>
      );
      break;
    case "close":
      sign = true;
      disabled = !confirm;
      run = async () => done(await signed(() => unwrap(api.POST("/api/v1/permits/{permit_id}/close", { ...path, body: { site_visit_confirmed: true, note: comment || null } }))), te("permitStatus.closed"));
      body = (
        <>
          <CheckboxField id="st-site" label={t("siteInspection")}>
            <Checkbox checked={confirm} onChange={(e) => setConfirm(e.target.checked)} data-testid="st-site-visit" />
          </CheckboxField>
          <FormField id="st-note" label={t("noteOptional")}>
            <Textarea value={comment} onChange={(e) => setComment(e.target.value)} maxLength={500} />
          </FormField>
        </>
      );
      break;
    case "cancel":
      destructive = true;
      sign = true;
      disabled = !reason || (permit.status === "issued" && !confirm);
      run = async () =>
        done(
          await signed(() => unwrap(api.POST("/api/v1/permits/{permit_id}/cancel", { ...path, body: { reason: reason as S["StatusReason"], detail: comment || null, site_visit_confirmed: permit.status === "issued" ? confirm : false } }))),
          te("permitStatus.cancelled"),
        );
      body = (
        <>
          <FormField id="st-reason" label={tc("reason")} required>
            <Select value={reason} onChange={(e) => setReason(e.target.value as S["StatusReason"])} data-testid="st-reason">
              <option value="">{tc("select")}</option>
              {cancelReasons.map((r) => (
                <option key={r} value={r}>
                  {te(`statusReason.${r}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="st-detail" label={t("detailOptional")}>
            <Textarea value={comment} onChange={(e) => setComment(e.target.value)} maxLength={500} />
          </FormField>
          {permit.status === "issued" ? (
            <CheckboxField id="st-site" label={t("areaLeftSafe")}>
              <Checkbox checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />
            </CheckboxField>
          ) : null}
        </>
      );
      break;
    case "post_expiry":
      disabled = !confirm || comment.trim().length < 10;
      run = async () =>
        done(
          await unwrap(
            api.POST("/api/v1/permits/{permit_id}/post-expiry-check", {
              ...path,
              body: {
                site_visit_confirmed: true,
                area_safe: areaSafe,
                area_note: comment.trim(),
                entrants_zero: permit.work_types.includes("confined_space") ? entrantsZero : null,
                personal_locks_removed: permit.isolations.length ? locksRemoved : null,
                fire_watch_status: permit.work_types.includes("hot_work") ? fireWatch || null : null,
              },
            }),
          ),
          t("postExpiryDone"),
        );
      body = (
        <>
          <CheckboxField id="pe-site" label={t("siteVisit")}>
            <Checkbox checked={confirm} onChange={(e) => setConfirm(e.target.checked)} data-testid="st-site-visit" />
          </CheckboxField>
          <CheckboxField id="pe-safe" label={t("areaSafe")}>
            <Checkbox checked={areaSafe} onChange={(e) => setAreaSafe(e.target.checked)} />
          </CheckboxField>
          {permit.work_types.includes("confined_space") ? (
            <CheckboxField id="pe-entrants" label={t("entrantsZero")}>
              <Checkbox checked={entrantsZero} onChange={(e) => setEntrantsZero(e.target.checked)} />
            </CheckboxField>
          ) : null}
          {permit.isolations.length ? (
            <CheckboxField id="pe-locks" label={t("locksRemoved")}>
              <Checkbox checked={locksRemoved} onChange={(e) => setLocksRemoved(e.target.checked)} />
            </CheckboxField>
          ) : null}
          {permit.work_types.includes("hot_work") ? (
            <FormField id="pe-fw" label={t("fireWatchStatus")}>
              <Input value={fireWatch} onChange={(e) => setFireWatch(e.target.value)} maxLength={200} />
            </FormField>
          ) : null}
          <FormField id="pe-note" label={t("areaNote")} required hint={t("min10")}>
            <Textarea value={comment} onChange={(e) => setComment(e.target.value)} maxLength={1000} data-testid="pe-note" />
          </FormField>
          {!areaSafe ? <Alert tone="warning">{t("areaUnsafeHint")}</Alert> : null}
        </>
      );
      break;
    case "pause":
      run = async () => done(await unwrap(api.POST("/api/v1/permits/{permit_id}/pause", { ...path, body: { reason: pauseReason, note: comment || null } })), t("paused"));
      body = (
        <>
          <FormField id="st-pause" label={tc("reason")} required>
            <Select value={pauseReason} onChange={(e) => setPauseReason(e.target.value as S["PauseReason"])} data-testid="st-pause-reason">
              {PAUSE_REASONS.map((r) => (
                <option key={r} value={r}>
                  {te(`pauseReason.${r}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="st-note" label={t("noteOptional")}>
            <Textarea value={comment} onChange={(e) => setComment(e.target.value)} maxLength={500} />
          </FormField>
          {permit.gas.required ? <p className="text-xs text-muted-foreground">{t("pauseGasHint")}</p> : null}
        </>
      );
      break;
    case "pause_end":
      run = async () => done(await unwrap(api.POST("/api/v1/permits/{permit_id}/pause/end", { ...path, body: { note: comment || null } })), t("resumedWork"));
      body = (
        <>
          {permit.gas.post_break_test_required ? <Alert tone="warning">{t("postBreakTest")}</Alert> : null}
          <FormField id="st-note" label={t("noteOptional")}>
            <Textarea value={comment} onChange={(e) => setComment(e.target.value)} maxLength={500} />
          </FormField>
        </>
      );
      break;
    case "hot_work_end":
      run = async () => done(await unwrap(api.POST("/api/v1/permits/{permit_id}/hot-work-end", { ...path, body: { ended_at: at } })), t("fireWatchStarted"));
      body = (
        <>
          <p className="text-sm">{t("hotWorkEndHint")}</p>
          <FormField id="st-at" label={t("endedAt")} required>
            <DateTimeInput value={at} onChange={setAt} data-testid="st-ended-at" />
          </FormField>
        </>
      );
      break;
    case "copy":
      disabled = !copyFrom || !copyTo;
      run = async () => {
        const p = await unwrap(api.POST("/api/v1/permits/{permit_id}/copy", { ...path, body: { valid_from_at: copyFrom, valid_to_at: copyTo } }));
        await refresh();
        toast.success(t("copied", { no: p.display_no }));
        router.push(`/permits/${p.id}`);
      };
      body = (
        <>
          <p className="text-sm text-muted-foreground">{t("copyHint")}</p>
          <FormField id="cp-from" label={t("validFrom")} required>
            <DateTimeInput value={copyFrom} onChange={setCopyFrom} />
          </FormField>
          <FormField id="cp-to" label={t("validTo")} required>
            <DateTimeInput value={copyTo} onChange={setCopyTo} />
          </FormField>
        </>
      );
      break;
    case "delete":
      destructive = true;
      run = async () => {
        await unwrap(api.DELETE("/api/v1/permits/{permit_id}", path));
        await refresh();
        toast.success(t("deleted"));
        router.push("/permits");
      };
      body = <p className="text-sm">{t("deleteHint")}</p>;
      break;
    default:
      body = null;
  }

  return (
    <StepDialog title={title} confirmLabel={t(`btn.${step}`)} destructive={destructive} disabled={disabled} onConfirm={run} onClose={onClose} wide testId="step-confirm" warning={irreversible ? td("irreversible") : undefined} dismissLabel={step === "cancel" ? td("keepPermit") : undefined}>
      {readinessAction ? <Readiness permit={permit} action={readinessAction} /> : null}
      {body}
      {sign ? <SigningNotice /> : null}
    </StepDialog>
  );
}
