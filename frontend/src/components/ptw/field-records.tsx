"use client";
import { LogIn, LogOut, Plus, TriangleAlert } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { CheckboxField, FormField } from "@/components/common/form-field";
import { StatusBadge } from "@/components/common/status-badge";
import { StepDialog } from "@/components/access/common";
import { useMeData } from "@/components/shell/me-context";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useAppointments, usePtwRefresh } from "@/lib/api/ptw";
import { can } from "@/lib/permissions";
import { EXEMPTION_KINDS, MIDDAY_EXEMPTION_REASONS, WIND_SOURCES } from "@/lib/ptw-enums";
import { useFormatters } from "@/lib/use-formatters";
import { Countdown, DateTimeInput, DecimalInput, WorkerRefLabel, nowIso, userLabel } from "./common";
import { sectionOf } from "./sections";
import { SigningNotice, useSigned } from "./signing";

type S = Schemas;
type Permit = S["PermitRead"];
type Kind = "entry" | "wind" | "excavation" | "barrier" | "source" | "fod";

const LIVE: S["PermitStatus"][] = ["issued", "active", "suspended"];

/** Field records under the type sections: live counters, history and the record buttons. */
export function FieldRecords({ permit, type }: { permit: Permit; type: S["PermitType"] }) {
  const t = useTranslations("fieldRecords");
  const te = useTranslations("enums");
  const locale = useLocale();
  const me = useMeData();
  const { dateTime } = useFormatters(permit.project_id);
  const [open, setOpen] = useState<Kind | null>(null);
  const s = sectionOf(permit, type);
  const live = LIVE.includes(permit.status);
  const actor = permit.receiver.id === me.id || permit.issuer?.id === me.id || can(me, "permit.receive", permit.project_id) || can(me, "permit.issue", permit.project_id);
  const btn = (k: Kind, label: string) =>
    live && actor ? (
      <Button size="sm" variant="outline" onClick={() => setOpen(k)} data-testid={`record-${k}`}>
        <Plus aria-hidden />
        {label}
      </Button>
    ) : null;
  let content: React.ReactNode = null;
  if (type === "hot_work" && s) {
    const hw = s as unknown as S["HotWorkSectionRead"];
    content = hw.fire_watch_until ? (
      <div className="flex flex-wrap items-center gap-2" data-testid="fire-watch">
        <Countdown to={hw.fire_watch_until} label={t("fireWatch")} icon="fire" testId="fire-watch-timer" warnMinutes={15} />
        {hw.hot_work_late ? <StatusBadge status="late" label={t("hotWorkLate")} /> : null}
        <span className="text-xs text-muted-foreground">{t("hotWorkEndedAt", { at: dateTime(hw.hot_work_ended_at) })}</span>
      </div>
    ) : permit.status === "active" ? (
      <p className="text-sm text-muted-foreground">{t("latestEnd", { at: dateTime(hw.latest_compliant_end_at) })}</p>
    ) : null;
  }
  if (type === "confined_space" && s) {
    const cs = s as unknown as S["ConfinedSpaceSectionRead"];
    content = (
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-md border px-2 py-1 text-sm font-semibold" data-testid="persons-inside" data-count={cs.persons_inside}>
            {t("personsInside", { n: cs.persons_inside })}
          </span>
          {btn("entry", t("recordEntry"))}
        </div>
        {cs.entry_log.length ? (
          <ul className="flex flex-col divide-y rounded-md border text-sm" data-testid="entry-log">
            {cs.entry_log.map((e) => (
              <li key={e.id} className="flex flex-wrap items-center gap-2 p-2">
                <span className="flex-1">
                  <WorkerRefLabel w={e.worker} />
                </span>
                <span className="flex items-center gap-1 text-xs">
                  <LogIn aria-hidden className="size-3.5" /> <span className="[unicode-bidi:isolate]">{dateTime(e.in_at)}</span>
                </span>
                <span className="flex items-center gap-1 text-xs">
                  <LogOut aria-hidden className="size-3.5" /> {e.out_at ? <span className="[unicode-bidi:isolate]">{dateTime(e.out_at)}</span> : <span className="inline-flex items-center gap-1 font-semibold text-warning"><TriangleAlert aria-hidden className="size-3.5 shrink-0" />{t("inside")}</span>}
                </span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    );
  }
  if ((type === "lifting" || type === "work_at_height") && s) {
    const readings = ((s as unknown as S["LiftingSectionRead"]).wind_readings ?? []) as S["WindReadingRead"][];
    content = (
      <div className="flex flex-col gap-2">
        <div>{btn("wind", t("recordWind"))}</div>
        {readings.length ? (
          <ul className="flex flex-col divide-y rounded-md border text-sm" data-testid="wind-readings">
            {readings.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center gap-2 p-2" data-within={r.within_limit ? "true" : "false"}>
                <bdi className="ltr font-semibold tabular-nums">{r.speed_ms} m/s</bdi>
                <span className="text-xs text-muted-foreground">
                  {t("limit")} <bdi className="ltr">{r.limit_ms}</bdi> · {te(`windSource.${r.source}`)} · <span className="[unicode-bidi:isolate]">{dateTime(r.measured_at)}</span>
                </span>
                <StatusBadge status={r.within_limit ? "ok" : "failed"} label={r.within_limit ? t("withinLimit") : t("overLimit")} />
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    );
  }
  if (type === "excavation" && s) {
    const ex = s as unknown as S["ExcavationSectionRead"];
    content = (
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={ex.inspected_for_current_shift ? "done" : "due"} label={ex.inspected_for_current_shift ? t("inspectedShift") : t("inspectionDue")} />
          {btn("excavation", t("recordInspection"))}
        </div>
        {ex.inspections.length ? (
          <ul className="flex flex-col divide-y rounded-md border text-sm" data-testid="excavation-inspections">
            {ex.inspections.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center gap-2 p-2">
                <StatusBadge status={i.result === "safe" ? "ok" : "failed"} label={te(`inspectionOutcome.${i.result}`)} />
                <span className="text-xs">
                  <span className="[unicode-bidi:isolate]">{dateTime(i.inspected_at)}</span> · <bdi className="ltr">{i.appointment.appointment_no}</bdi>
                  {i.after_rain_or_event ? ` · ${t("afterRain")}` : ""}
                </span>
                {i.note ? <span className="w-full text-xs text-muted-foreground">{i.note}</span> : null}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    );
  }
  if (type === "radiography" && s) {
    const rg = s as unknown as S["RadiographySectionRead"];
    content = (
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={rg.barrier_verified ? "verified" : "pending"} label={rg.barrier_verified ? t("barrierVerified") : t("barrierNotVerified")} />
          {btn("barrier", t("recordSurvey"))}
          {rg.source_returned ? null : btn("source", t("recordSourceReturn"))}
        </div>
        {rg.barrier_surveys.length ? (
          <ul className="flex flex-col divide-y rounded-md border text-sm" data-testid="barrier-surveys">
            {rg.barrier_surveys.map((b) => (
              <li key={b.id} className="flex flex-wrap items-center gap-2 p-2">
                <bdi className="ltr font-semibold tabular-nums">{b.max_usv_h} µSv/h</bdi>
                <span className="text-xs text-muted-foreground">
                  <bdi className="ltr">{b.meter_tag}</bdi> · <span className="[unicode-bidi:isolate]">{dateTime(b.measured_at)}</span>
                </span>
                <StatusBadge status={b.within_limit ? "ok" : "failed"} label={b.within_limit ? t("withinLimit") : t("overLimit")} />
              </li>
            ))}
          </ul>
        ) : null}
        {rg.source_returned ? (
          <p className="text-sm" data-testid="source-returned">
            {t("sourceReturned", { at: dateTime(rg.source_returned.at), survey: rg.source_returned.survey_usv_h, bg: rg.source_returned.background_usv_h })}
          </p>
        ) : null}
      </div>
    );
  }
  if (type === "airside_works" && s) {
    const aw = s as unknown as S["AirsideSectionRead"];
    content = (
      <div className="flex flex-wrap items-center gap-2">
        {aw.fod_check ? (
          <span className="text-sm">
            {t("fodLast", { result: te(`fodResult.${aw.fod_check.result}`), at: dateTime(aw.fod_check.checked_at) })} {aw.fod_check.checked_by_user ? `· ${userLabel(aw.fod_check.checked_by_user, locale)}` : ""}
          </span>
        ) : (
          <span className="text-sm text-muted-foreground">{t("noFod")}</span>
        )}
        {btn("fod", t("recordFod"))}
      </div>
    );
  }
  if (!content) return null;
  return (
    <div className="flex flex-col gap-2 rounded-md border border-dashed p-3" data-testid={`field-records-${type}`}>
      <p className="text-xs font-medium text-muted-foreground">{t("title")}</p>
      {content}
      {open ? <FieldRecordDialog permit={permit} kind={open} onClose={() => setOpen(null)} /> : null}
    </div>
  );
}

function FieldRecordDialog({ permit, kind, onClose }: { permit: Permit; kind: Kind; onClose: () => void }) {
  const t = useTranslations("fieldRecords");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const refresh = usePtwRefresh();
  const [at, setAt] = useState(nowIso());
  const [worker, setWorker] = useState("");
  const [dir, setDir] = useState<S["EntryDirection"]>("in");
  const [num, setNum] = useState("");
  const [num2, setNum2] = useState("");
  const [text, setText] = useState("");
  const [source, setSource] = useState<S["WindSource"]>("anemometer");
  const [ok, setOk] = useState(true);
  const [flag, setFlag] = useState(false);
  const [appt, setAppt] = useState("");
  const appts = useAppointments(permit.project_id, { function: ["authorised_person"], status: ["active"], page_size: 200 }, { enabled: kind === "excavation" });
  const path = { params: { path: { permit_id: permit.id } } };
  const entrants = permit.crew.filter((c) => c.status === "listed" && c.worker && (c.crew_role === "entrant" || c.crew_role === "rescue_member" || c.crew_role === "rescue_lead"));
  let body: React.ReactNode = null;
  let disabled = false;
  let run: () => Promise<unknown> = async () => null;
  switch (kind) {
    case "entry":
      disabled = !worker;
      run = () => unwrap(api.POST("/api/v1/permits/{permit_id}/entry-log", { ...path, body: { worker_id: worker, direction: dir, at } }));
      body = (
        <>
          <FormField id="fr-worker" label={t("entrant")} required>
            <Select value={worker} onChange={(e) => setWorker(e.target.value)} data-testid="fr-worker">
              <option value="">{tc("select")}</option>
              {entrants.map((c) => (
                <option key={c.id} value={c.worker?.id}>
                  {c.worker?.worker_no} {c.worker?.full_name_en ?? ""}
                </option>
              ))}
            </Select>
          </FormField>
          <fieldset className="flex gap-4 text-sm">
            <label className="flex min-h-touch items-center gap-2">
              <input type="radio" checked={dir === "in"} onChange={() => setDir("in")} data-testid="fr-in" />
              {te("entryDirection.in")}
            </label>
            <label className="flex min-h-touch items-center gap-2">
              <input type="radio" checked={dir === "out"} onChange={() => setDir("out")} data-testid="fr-out" />
              {te("entryDirection.out")}
            </label>
          </fieldset>
        </>
      );
      break;
    case "wind":
      disabled = !num;
      run = () => unwrap(api.POST("/api/v1/permits/{permit_id}/wind-readings", { ...path, body: { measured_at: at, speed_ms: num, source, source_ref: text || null } }));
      body = (
        <>
          <FormField id="fr-speed" label={t("windSpeed")} required>
            <DecimalInput value={num} onChange={setNum} data-testid="fr-speed" />
          </FormField>
          <FormField id="fr-src" label={t("windSource")}>
            <Select value={source} onChange={(e) => setSource(e.target.value as S["WindSource"])}>
              {WIND_SOURCES.map((x) => (
                <option key={x} value={x}>
                  {te(`windSource.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="fr-ref" label={t("sourceRef")}>
            <Input className="ltr" value={text} onChange={(e) => setText(e.target.value)} />
          </FormField>
        </>
      );
      break;
    case "excavation":
      disabled = !appt;
      run = () => unwrap(api.POST("/api/v1/permits/{permit_id}/excavation-inspections", { ...path, body: { inspected_at: at, appointment_id: appt, result: ok ? "safe" : "unsafe", after_rain_or_event: flag, note: text || null } }));
      body = (
        <>
          <FormField id="fr-appt" label={t("competentPerson")} required>
            <Select value={appt} onChange={(e) => setAppt(e.target.value)} data-testid="fr-appt">
              <option value="">{tc("select")}</option>
              {(appts.data?.items ?? [])
                .filter((a) => a.discipline === "excavation_competent_person")
                .map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.appointment_no} · {a.holder_worker?.worker_no ?? a.holder_user?.full_name_en}
                  </option>
                ))}
            </Select>
          </FormField>
          <fieldset className="flex gap-4 text-sm">
            <label className="flex min-h-touch items-center gap-2">
              <input type="radio" checked={ok} onChange={() => setOk(true)} />
              {te("inspectionOutcome.safe")}
            </label>
            <label className="flex min-h-touch items-center gap-2">
              <input type="radio" checked={!ok} onChange={() => setOk(false)} />
              {te("inspectionOutcome.unsafe")}
            </label>
          </fieldset>
          <CheckboxField id="fr-rain" label={t("afterRain")}>
            <Checkbox checked={flag} onChange={(e) => setFlag(e.target.checked)} />
          </CheckboxField>
          <FormField id="fr-note" label={t("note")}>
            <Textarea value={text} onChange={(e) => setText(e.target.value)} maxLength={500} />
          </FormField>
        </>
      );
      break;
    case "barrier":
      disabled = !num || !text;
      run = () => unwrap(api.POST("/api/v1/permits/{permit_id}/barrier-surveys", { ...path, body: { measured_at: at, max_usv_h: num, meter_tag: text } }));
      body = (
        <>
          <FormField id="fr-max" label={t("maxDose")} required>
            <DecimalInput value={num} onChange={setNum} data-testid="fr-max" />
          </FormField>
          <FormField id="fr-meter" label={t("meterTag")} required>
            <Input className="ltr" value={text} onChange={(e) => setText(e.target.value)} data-testid="fr-meter" />
          </FormField>
        </>
      );
      break;
    case "source":
      disabled = !num || !num2;
      run = () => unwrap(api.POST("/api/v1/permits/{permit_id}/source-return", { ...path, body: { at, survey_usv_h: num, background_usv_h: num2 } }));
      body = (
        <>
          <FormField id="fr-survey" label={t("surveyDose")} required>
            <DecimalInput value={num} onChange={setNum} />
          </FormField>
          <FormField id="fr-bg" label={t("background")} required>
            <DecimalInput value={num2} onChange={setNum2} />
          </FormField>
        </>
      );
      break;
    case "fod":
      run = () => unwrap(api.POST("/api/v1/permits/{permit_id}/fod-check", { ...path, body: { checked_by_user_id: me.id, checked_at: at, result: ok ? "clear" : "not_clear" } }));
      body = (
        <fieldset className="flex gap-4 text-sm">
          <label className="flex min-h-touch items-center gap-2">
            <input type="radio" checked={ok} onChange={() => setOk(true)} data-testid="fr-fod-clear" />
            {te("fodResult.clear")}
          </label>
          <label className="flex min-h-touch items-center gap-2">
            <input type="radio" checked={!ok} onChange={() => setOk(false)} />
            {te("fodResult.not_clear")}
          </label>
        </fieldset>
      );
      break;
  }
  return (
    <StepDialog
      title={t(`dialog.${kind}`)}
      confirmLabel={tc("save")}
      disabled={disabled}
      onClose={onClose}
      testId="save-field-record"
      onConfirm={async () => {
        await run();
        await refresh();
        toast.success(tc("saved"));
      }}
    >
      {body}
      <FormField id="fr-at" label={t("at")} required>
        <DateTimeInput value={at} onChange={setAt} />
      </FormField>
    </StepDialog>
  );
}

/* ───────────── exemptions ───────────── */

export function ExemptionsPanel({ permit }: { permit: Permit }) {
  const t = useTranslations("fieldRecords");
  const te = useTranslations("enums");
  const me = useMeData();
  const locale = useLocale();
  const refresh = usePtwRefresh();
  const signed = useSigned();
  const { date, dateTime } = useFormatters(permit.project_id);
  const [req, setReq] = useState(false);
  const [decide, setDecide] = useState<{ ex: S["PermitRead"]["exemptions"][number]; d: "granted" | "refused" } | null>(null);
  const [note, setNote] = useState("");
  const grant = can(me, "ptw_exemption.grant", permit.project_id);
  const mayRequest = !["closed", "cancelled", "expired"].includes(permit.status) && (can(me, "permit.prepare", permit.project_id) || can(me, "permit.receive", permit.project_id) || can(me, "permit.issue", permit.project_id));
  return (
    <Card data-testid="exemptions-panel">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="text-base">{t("exemptions")}</CardTitle>
        {mayRequest ? (
          <Button size="sm" variant="outline" onClick={() => setReq(true)} data-testid="request-exemption">
            <Plus aria-hidden />
            {t("requestExemption")}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent>
        {permit.exemptions.length ? (
          <ul className="flex flex-col gap-2">
            {permit.exemptions.map((x) => (
              <li key={x.id} className="rounded-md border p-2 text-sm" data-testid="exemption" data-status={x.status}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{te(`exemptionKind.${x.kind}`)}</span>
                  {x.midday_reason ? <span className="text-xs text-muted-foreground">{te(`middayReason.${x.midday_reason}`)}</span> : null}
                  <StatusBadge status={x.status} label={te(`exemptionStatus.${x.status}`)} />
                  {x.valid_from ? (
                    <span className="text-xs text-muted-foreground">
                      {date(x.valid_from)} – {date(x.valid_to)}
                    </span>
                  ) : null}
                  {grant && x.status === "requested" ? (
                    <span className="ms-auto flex gap-1">
                      <Button size="sm" onClick={() => setDecide({ ex: x, d: "granted" })} data-testid="grant-exemption">
                        {t("grant")}
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => setDecide({ ex: x, d: "refused" })} data-testid="refuse-exemption">
                        {t("refuse")}
                      </Button>
                    </span>
                  ) : null}
                </div>
                <p className="mt-1" dir="auto">{x.reason_text}</p>
                {x.heat_controls_text ? <p className="text-xs text-muted-foreground" dir="auto">{x.heat_controls_text}</p> : null}
                <p className="mt-1 text-xs text-muted-foreground">
                  {t("requestedBy", { name: userLabel(x.requested_by, locale), at: dateTime(x.requested_at) })}
                  {x.decided_by ? ` · ${t("decidedBy", { name: userLabel(x.decided_by, locale), at: dateTime(x.decided_at) })}` : ""}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">{t("noExemptions")}</p>
        )}
      </CardContent>
      {req ? <ExemptionDialog permit={permit} onClose={() => setReq(false)} /> : null}
      {decide ? (
        <StepDialog
          title={decide.d === "granted" ? t("grantTitle") : t("refuseTitle")}
          description={te(`exemptionKind.${decide.ex.kind}`)}
          confirmLabel={decide.d === "granted" ? t("grant") : t("refuse")}
          destructive={decide.d === "refused"}
          onClose={() => {
            setDecide(null);
            setNote("");
          }}
          testId="confirm-exemption-decision"
          onConfirm={async () => {
            await signed(() => unwrap(api.POST("/api/v1/permit-exemptions/{exemption_id}/decision", { params: { path: { exemption_id: decide.ex.id } }, body: { decision: decide.d, note: note || null } })));
            await refresh();
          }}
        >
          <FormField id="ex-note" label={t("note")}>
            <Textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} />
          </FormField>
          <SigningNotice />
        </StepDialog>
      ) : null}
    </Card>
  );
}

function ExemptionDialog({ permit, onClose }: { permit: Permit; onClose: () => void }) {
  const t = useTranslations("fieldRecords");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const refresh = usePtwRefresh();
  const [kind, setKind] = useState<S["ExemptionKind"]>("midday_ban");
  const [mid, setMid] = useState<S["MiddayExemptionReason"] | "">("");
  const [reason, setReason] = useState("");
  const [heat, setHeat] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const midday = kind === "midday_ban";
  return (
    <StepDialog
      title={t("requestExemption")}
      confirmLabel={t("submit")}
      disabled={reason.trim().length < 10 || (midday && (!mid || heat.trim().length < 30))}
      onClose={onClose}
      wide
      testId="save-exemption"
      onConfirm={async () => {
        const p = await unwrap(
          api.POST("/api/v1/permits/{permit_id}/exemptions", {
            params: { path: { permit_id: permit.id } },
            body: { kind, midday_reason: midday ? (mid as S["MiddayExemptionReason"]) : null, reason_text: reason.trim(), heat_controls_text: heat.trim() || null, valid_from: from || null, valid_to: to || null },
          }),
        );
        void p;
        await refresh();
      }}
    >
      <FormField id="ex-kind" label={t("kind")} required>
        <Select value={kind} onChange={(e) => setKind(e.target.value as S["ExemptionKind"])} data-testid="ex-kind">
          {EXEMPTION_KINDS.map((x) => (
            <option key={x} value={x}>
              {te(`exemptionKind.${x}`)}
            </option>
          ))}
        </Select>
      </FormField>
      {midday ? (
        <FormField id="ex-mid" label={t("middayReason")} required>
          <Select value={mid} onChange={(e) => setMid(e.target.value as S["MiddayExemptionReason"])}>
            <option value="">{tc("select")}</option>
            {MIDDAY_EXEMPTION_REASONS.map((x) => (
              <option key={x} value={x}>
                {te(`middayReason.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
      ) : null}
      <FormField id="ex-reason" label={t("reasonText")} required hint={t("min10")}>
        <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={1000} data-testid="ex-reason" />
      </FormField>
      {midday ? (
        <FormField id="ex-heat" label={t("heatControls")} required hint={t("min30")}>
          <Textarea value={heat} onChange={(e) => setHeat(e.target.value)} maxLength={1000} />
        </FormField>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="ex-from" label={t("validFrom")}>
          <Input type="date" className="ltr" value={from} onChange={(e) => setFrom(e.target.value)} />
        </FormField>
        <FormField id="ex-to" label={t("validTo")}>
          <Input type="date" className="ltr" value={to} onChange={(e) => setTo(e.target.value)} />
        </FormField>
      </div>
    </StepDialog>
  );
}
