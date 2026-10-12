"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Car, Download, FileText, FileUp, Info, Lock, Pencil, Plus, ShieldAlert, Trash2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ApiWarnings, useWarningToasts } from "@/components/common/api-warnings";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { useProjectOptions } from "@/components/common/pickers";
import { RecordActions } from "@/components/common/record-actions";
import { MutationError } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { SubmissionDialog } from "@/components/followup/actions";
import { useFuCaps } from "@/components/followup/common";
import { useMeData } from "@/components/shell/me-context";
import { Link } from "@/i18n/navigation";
import { api, postForm, unwrap, type Schemas } from "@/lib/api/client";
import { useFuRequirements } from "@/lib/api/followup";
import { hk } from "@/lib/api/hse";
import { useProjectSettings } from "@/lib/api/queries";
import { DEFAULT_TIME_ZONE, utcToZonedInput, zonedInputToUtc } from "@/lib/datetime";
import { groupDecimal, useDisplay } from "@/lib/digits";
import { useErrorMessage, useLocalizedName } from "@/lib/i18n-helpers";
import { canWrite } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";
import { cn } from "@/lib/utils";
import {
  LICENCE_CLASSES,
  LICENCE_ISSUERS,
  PLATE_TYPES,
  VEH_AUTHORITIES,
  VEH_CATEGORIES,
  VEH_COMMUTING,
  VEH_COMPANY_OWNERSHIPS,
  VEH_DAMAGES,
  VEH_DOC_STATES,
  VEH_DRIVER_KINDS,
  VEH_JOURNEY_PURPOSES,
  VEH_LIABILITY,
  VEH_LIGHTS,
  VEH_OWNERSHIPS,
  VEH_ROAD_TYPES,
  VEH_ROLES,
  VEH_SEAT_BELTS,
  VEH_SPEED_SOURCES,
  VEH_SURFACES,
  licenceCheckStatus,
  plateText,
} from "@/lib/vehicle-enums";

type S = Schemas;
type Incident = S["IncidentRead"];
type Row = S["VehIncidentVehicleRead"];
type Section = S["VehSectionRead"];

/* ───────────── shared bits ───────────── */

/** VA-13: "Recorded, not counted — commuting (OSHA)"; icon plus text, never colour alone. */
export function RecordedNotCountedBadge({ short, className }: { short?: boolean; className?: string }) {
  const t = useTranslations("veh.rnc");
  return (
    <Badge tone="info" className={cn("gap-1 whitespace-normal", className)} title={t("explain")} data-testid="rnc-badge">
      <Info aria-hidden className="size-3.5 shrink-0" />
      {short ? t("short") : t("badge")}
    </Badge>
  );
}

/** Plate: Latin letters and digits left-to-right; the Arabic letters beside them. Never mirrored. */
export function Plate({ r, className }: { r: { plate_letters_ar?: string | null; plate_letters_en?: string | null; plate_digits?: string | null }; className?: string }) {
  const latin = plateText(r);
  if (!latin && !r.plate_letters_ar) return <>—</>;
  return (
    <span className={cn("inline-flex flex-wrap items-center gap-1.5", className)} data-testid="plate">
      {latin ? (
        <bdi dir="ltr" className="ltr rounded border px-1.5 font-mono text-xs font-medium">
          {latin}
        </bdi>
      ) : null}
      {r.plate_letters_ar ? (
        <bdi dir="rtl" className="text-xs text-muted-foreground">
          {r.plate_letters_ar}
        </bdi>
      ) : null}
    </span>
  );
}

function useVehLabels() {
  const t = useTranslations("veh.enum");
  const te = useTranslations("enums");
  return {
    road: (v: S["VehRoadType"] | null | undefined) => (v ? t(`roadType.${v}`) : "—"),
    journey: (v: S["VehJourneyPurpose"] | null | undefined) => (v ? t(`journeyPurpose.${v}`) : "—"),
    light: (v: S["VehLight"] | null | undefined) => (v ? t(`light.${v}`) : null),
    surface: (v: S["VehSurface"] | null | undefined) => (v ? t(`surface.${v}`) : null),
    authority: (v: S["VehReportAuthority"] | null | undefined) => (v ? t(`authority.${v}`) : "—"),
    ownership: (v: S["VehOwnership"]) => t(`ownership.${v}`),
    role: (v: S["VehRole"]) => t(`role.${v}`),
    damage: (v: S["VehDamage"] | null | undefined) => (v ? t(`damage.${v}`) : "—"),
    doc: (v: S["VehDocState"]) => t(`docState.${v}`),
    seatBelt: (v: S["VehSeatBelt"] | null | undefined) => (v ? t(`seatBelt.${v}`) : "—"),
    speedSource: (v: S["VehSpeedSource"] | null | undefined) => (v ? t(`speedSource.${v}`) : null),
    driverKind: (v: S["VehDriverKind"] | null | undefined) => (v ? t(`driverKind.${v}`) : "—"),
    licenceCheck: (v: S["VehLicenceCheck"] | null | undefined) => (v ? t(`licenceCheck.${v}`) : "—"),
    category: (v: S["VehCategory"] | null | undefined) => (v ? te(`vehicleCategory.${v}`) : "—"),
    plateType: (v: S["PlateType"]) => te(`plateType.${v}`),
    issuer: (v: S["LicenceIssuer"]) => te(`licenceIssuer.${v}`),
    licenceClass: (v: S["LicenceClass"]) => te(`licenceClass.${v}`),
  };
}

function useVehRefresh(incidentId: string) {
  const qc = useQueryClient();
  return async () => {
    await qc.invalidateQueries({ queryKey: hk.incident(incidentId) });
    await qc.invalidateQueries({ queryKey: ["incidents"] });
    await qc.invalidateQueries({ queryKey: ["history"] });
  };
}

/** Vehicle rows and the report record are editable until the incident is Closed (7a §4, D-241). */
function useVehEdit(r: Incident) {
  const me = useMeData();
  return canWrite(me, "incident.report", r.project_id) && !["closed", "voided"].includes(r.status);
}

function MissingList({ title, items, testId }: { title: string; items: string[]; testId: string }) {
  const tm = useTranslations("veh.missing");
  if (!items.length) return null;
  return (
    <Alert tone="warning" data-testid={testId}>
      <p className="font-medium">{title}</p>
      <ul className="mt-1 flex flex-wrap gap-1.5">
        {items.map((m) => {
          const x = /^(V\d+)\.(.+)$/.exec(m);
          const field = x ? (x[2] ?? "") : m;
          return (
            <li key={m} data-missing={m} className="rounded bg-background/60 px-1.5 py-0.5 text-xs">
              {x ? <bdi className="ltr font-medium">{x[1]} · </bdi> : null}
              {tm.has(field as "road_type") ? tm(field as "road_type") : <bdi className="ltr font-mono">{field}</bdi>}
            </li>
          );
        })}
      </ul>
    </Alert>
  );
}

/* ───────────── incident page: "Vehicle accident" card ───────────── */

export function VehicleSectionCard({ incident: r }: { incident: Incident }) {
  const t = useTranslations("veh");
  const tc = useTranslations("common");
  const L = useVehLabels();
  const show = useDisplay(r.project_id);
  const ar = useLocale() === "ar";
  const msg = useErrorMessage();
  const refresh = useVehRefresh(r.id);
  const editable = useVehEdit(r);
  const [dialog, setDialog] = useState<{ row?: Row } | null>(null);
  const [roadOpen, setRoadOpen] = useState(false);
  const v = r.vehicle_section;
  if (!r.vehicle_involved || !v) return null;
  const redacted = v.vehicles.some((x) => x.redacted_groups.length > 0);
  const proposed = r.cases.filter((c) => v.commuting_proposed_case_ids.includes(c.id));
  const conditions = [L.light(v.light), L.surface(v.surface)].filter(Boolean).join(" · ");

  async function remove(row: Row) {
    if (!window.confirm(t("card.removeConfirm", { label: row.label }))) return;
    try {
      await unwrap(api.DELETE("/api/v1/incident-vehicles/{vehicle_row_id}", { params: { path: { vehicle_row_id: row.id } } }));
      toast.success(t("card.removed"));
      await refresh();
    } catch (e) {
      toast.error(msg(e));
    }
  }

  return (
    <Card data-testid="vehicle-section">
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-2">
        <div className="flex flex-col gap-1.5">
          <CardTitle className="flex flex-wrap items-center gap-2">
            <Car aria-hidden className="size-5 text-muted-foreground" />
            {t("section")}
          </CardTitle>
          {v.recorded_not_counted ? <RecordedNotCountedBadge /> : null}
        </div>
        {editable ? (
          <Button size="sm" variant="outline" onClick={() => setRoadOpen(true)} data-testid="veh-road-edit">
            <Pencil aria-hidden />
            {tc("edit")}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {v.recorded_not_counted ? <p className="text-xs text-muted-foreground">{t("rnc.explain")}</p> : null}
        <FieldList>
          <FieldItem label={t("fields.road_type")}>
            <span data-testid="veh-road-type" data-value={v.road_type ?? ""}>
              {L.road(v.road_type)}
            </span>
          </FieldItem>
          {v.road_location ? <FieldItem label={t("fields.road_location")}>{v.road_location}</FieldItem> : null}
          <FieldItem label={t("fields.journey_purpose")}>
            <span data-testid="veh-journey" data-value={v.journey_purpose ?? ""}>
              {L.journey(v.journey_purpose)}
            </span>
          </FieldItem>
          {conditions ? <FieldItem label={t("card.conditions")}>{conditions}</FieldItem> : null}
          {v.third_party_damage_desc || v.third_party_damage_cost_sar ? (
            <FieldItem label={t("fields.third_party_damage_desc")}>
              {v.third_party_damage_desc ? <span dir="auto">{v.third_party_damage_desc}</span> : null}
              {v.third_party_damage_cost_sar ? (
                <span className="block text-muted-foreground tabular-nums" data-testid="veh-tp-cost">
                  {t("card.cost", { cost: show(groupDecimal(v.third_party_damage_cost_sar)) })}
                </span>
              ) : null}
            </FieldItem>
          ) : null}
        </FieldList>
        <MissingList title={t("card.missingForReport")} items={v.missing_for_report} testId="veh-missing-report" />
        {r.status !== "draft" ? (
          <MissingList title={t("card.missingForInvestigation")} items={v.missing_for_investigation.filter((m) => !v.missing_for_report.includes(m))} testId="veh-missing-investigation" />
        ) : null}
        {v.investigation_prompts.length ? (
          <Alert tone="warning" data-testid="veh-prompts">
            <p className="flex items-center gap-1.5 font-medium">
              <ShieldAlert aria-hidden className="size-4" />
              {t("card.prompts")}
            </p>
            <ul className="mt-1 list-disc ps-5">
              {v.investigation_prompts.map((p, i) => (
                <li key={`${p.code}-${i}`} data-code={p.code}>
                  <bdi className="ltr font-medium">V{p.vehicle_seq}</bdi> — {ar ? p.message_ar : p.message_en}
                </li>
              ))}
            </ul>
            <p className="mt-1 text-xs">{t("card.promptsHint")}</p>
          </Alert>
        ) : null}
        {proposed.length ? (
          <Alert tone="info" data-testid="veh-commuting-proposed">
            {t("card.commutingProposed", { n: proposed.length })}{" "}
            <span className="inline-flex flex-wrap gap-2">
              {proposed.map((c) => (
                <Link key={c.id} href={`/injury-cases/${c.id}`} className="font-medium text-primary underline-offset-4 hover:underline">
                  {t("card.openCase", { no: c.case_no })}
                </Link>
              ))}
            </span>
          </Alert>
        ) : null}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">{t("card.title")}</h3>
          {editable && v.vehicles.length < 10 ? (
            <Button size="sm" onClick={() => setDialog({})} data-testid="veh-add">
              <Plus aria-hidden />
              {t("card.add")}
            </Button>
          ) : null}
        </div>
        {redacted ? <p className="text-xs text-muted-foreground" data-testid="veh-redacted">{t("card.driverHidden")}</p> : null}
        {v.vehicles.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("card.none")}</p>
        ) : (
          <ul className="grid gap-3 md:grid-cols-2" data-testid="veh-rows">
            {v.vehicles.map((row) => (
              <VehicleRowCard key={row.id} row={row} incident={r} editable={editable} onEdit={() => setDialog({ row })} onRemove={() => void remove(row)} />
            ))}
          </ul>
        )}
      </CardContent>
      {dialog ? <VehicleRowDialog incident={r} row={dialog.row} onClose={() => setDialog(null)} /> : null}
      {roadOpen ? <RoadDialog incident={r} section={v} onClose={() => setRoadOpen(false)} /> : null}
    </Card>
  );
}

function Line({ label, children, testId }: { label: string; children: ReactNode; testId?: string }) {
  return (
    <div className="flex min-w-0 flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 py-1" data-testid={testId}>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-end text-sm [overflow-wrap:anywhere]">{children}</dd>
    </div>
  );
}

/** One vehicle as a compact card (works at 390 px). Personal fields are null without capability 29 (P7a-1). */
function VehicleRowCard({ row, incident: r, editable, onEdit, onRemove }: { row: Row; incident: Incident; editable: boolean; onEdit: () => void; onRemove: () => void }) {
  const t = useTranslations("veh");
  const td = useTranslations("vehDesign");
  const tc = useTranslations("common");
  const L = useVehLabels();
  const ar = useLocale() === "ar";
  const name = useLocalizedName();
  const show = useDisplay(r.project_id);
  const { date } = useFormatters(r.project_id);
  const docs = row.docs_valid_at_time;
  const speed =
    row.speed_kmh !== null
      ? row.speed_limit_kmh !== null
        ? t("card.speedOf", { speed: show(row.speed_kmh), limit: show(row.speed_limit_kmh) })
        : t("card.speedOnly", { speed: show(row.speed_kmh) })
      : null;
  const hasPlate = Boolean(row.plate_digits || row.plate_letters_en || row.plate_letters_ar);
  return (
    <li className="flex min-w-0 flex-col gap-2 rounded-lg border bg-surface p-3" data-testid="veh-row" data-label={row.label} data-ownership={row.ownership} data-licence-check={row.licence_check ?? ""}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <p className="flex flex-wrap items-center gap-2 text-sm font-semibold">
            <bdi className="ltr rounded bg-muted px-1.5 text-xs">{row.label}</bdi>
            {L.ownership(row.ownership)}
            {row.engagement ? <bdi className="ltr text-xs font-normal text-muted-foreground">{row.engagement.short_code}</bdi> : null}
          </p>
          <p className="text-xs text-muted-foreground">
            {L.role(row.role)} · {L.category(row.category)}
            {row.make_model ? ` · ${row.make_model}` : ""}
          </p>
        </div>
        {editable ? (
          <div className="-me-1 -mt-1 flex shrink-0 gap-1">
            <Button size="icon" variant="ghost" aria-label={`${tc("edit")} ${row.label}`} onClick={onEdit} data-testid="veh-edit">
              <Pencil aria-hidden />
            </Button>
            <Button size="icon" variant="ghost" aria-label={`${tc("delete")} ${row.label}`} onClick={onRemove} data-testid="veh-remove">
              <Trash2 aria-hidden />
            </Button>
          </div>
        ) : null}
      </div>
      <dl className="flex flex-col divide-y">
        <Line label={t("fields.plate")} testId="veh-plate">
          {hasPlate ? <Plate r={row} /> : row.redacted_groups.length && row.ownership === "third_party" ? <span className="text-xs text-muted-foreground">•••</span> : "—"}
          {row.vehicle ? (
            <span className="ms-1.5 text-xs text-muted-foreground">
              <bdi className="ltr">{row.vehicle.vehicle_no}</bdi>
            </span>
          ) : null}
        </Line>
        {row.suggested_vehicle && !row.vehicle ? (
          <Line label={t("fields.vehicle")}>
            <span className="text-xs text-warning">{t("card.suggested", { vehicle: row.suggested_vehicle.vehicle_no })}</span>
          </Line>
        ) : null}
        <Line label={t("fields.damage")}>
          {L.damage(row.damage)}
          {row.damage_cost_sar ? (
            <span className="text-muted-foreground tabular-nums" data-testid="veh-cost">
              {" "}
              · {t("card.cost", { cost: show(groupDecimal(row.damage_cost_sar)) })}
            </span>
          ) : null}
        </Line>
        <Line label={t("card.docsFrom")} testId="veh-docs">
          <span className="inline-flex flex-wrap justify-end gap-1" title={t(`enum.docSource.${docs.source === "register" ? "register" : "entered"}`)}>
            {(["istimara", "insurance", "mvpi"] as const).map((k) => (
              <span key={k} className="inline-flex items-center gap-1 text-xs" data-doc={k} data-state={docs[k]}>
                <StatusBadge status={docs[k] === "valid" ? "valid" : docs[k] === "expired" ? "expired" : "not_evaluated"} label={`${t(`fields.${k}`)}: ${L.doc(docs[k])}`} />
              </span>
            ))}
          </span>
        </Line>
        <Line label={t("fields.seat_belt")}>{L.seatBelt(row.seat_belt)}</Line>
        {speed ? (
          <Line label={t("fields.speed")}>
            {speed}
            {row.speed_source ? <span className="text-xs text-muted-foreground"> · {L.speedSource(row.speed_source)}</span> : null}
          </Line>
        ) : null}
        <Line label={t("fields.driver")} testId="veh-driver">
          <span className="flex flex-col items-end gap-1">
            {row.worker ? (
              <span data-testid="veh-driver-name">
                {name(row.worker.full_name_en, row.worker.full_name_ar)} <bdi className="ltr text-xs text-muted-foreground">{row.worker.worker_no}</bdi>
              </span>
            ) : row.external_driver_name ? (
              <span data-testid="veh-driver-name">{row.external_driver_name}</span>
            ) : null}
            <span className="text-xs text-muted-foreground" data-testid="veh-driver-summary">
              {ar ? row.driver_summary_ar : row.driver_summary_en}
            </span>
          </span>
        </Line>
        <Line label={t("fields.licence_check")}>
          <span data-testid="veh-licence-check" data-value={row.licence_check ?? ""}>
            <StatusBadge status={licenceCheckStatus(row.licence_check)} label={L.licenceCheck(row.licence_check)} />
          </span>
        </Line>
        {row.licence_class || row.licence_expiry || row.licence_issuer ? (
          <Line label={t("fields.licence_class")} testId="veh-licence">
            {[row.licence_issuer ? L.issuer(row.licence_issuer) : null, row.licence_class ? L.licenceClass(row.licence_class) : null].filter(Boolean).join(" · ")}
            {row.licence_expiry ? <span className="block text-xs text-muted-foreground">{td("licenceValidUntil", { date: date(row.licence_expiry) })}</span> : null}
            {row.licence_no ? (
              <span className="text-muted-foreground">
                {" "}
                · <bdi className="ltr">{row.licence_no}</bdi>
              </span>
            ) : null}
          </Line>
        ) : null}
        {row.hours_on_duty ? <Line label={t("fields.hours_on_duty")}>{t("card.hoursOnDuty", { h: show(row.hours_on_duty) })}</Line> : null}
        {row.insurer || row.policy_no ? (
          <Line label={t("fields.insurer")} testId="veh-insurer">
            {row.insurer ?? ""}
            {row.policy_no ? (
              <span className="text-muted-foreground">
                {" "}
                · <bdi className="ltr">{row.policy_no}</bdi>
              </span>
            ) : null}
          </Line>
        ) : null}
        {row.driver_case_no ? <Line label={t("fields.driver_case_no")}>{show(row.driver_case_no)}</Line> : null}
      </dl>
      <ApiWarnings warnings={row.warnings} />
    </li>
  );
}

/* ───────────── road / journey edit (incident page) ───────────── */

function RoadDialog({ incident: r, section: v, onClose }: { incident: Incident; section: Section; onClose: () => void }) {
  const t = useTranslations("veh");
  const td = useTranslations("vehDesign");
  const tc = useTranslations("common");
  const L = useVehLabels();
  const refresh = useVehRefresh(r.id);
  const warn = useWarningToasts();
  const needReason = Boolean(r.investigation?.approved_at);
  const [f, setF] = useState({
    road_type: v.road_type ?? "",
    road_location: v.road_location ?? "",
    journey_purpose: v.journey_purpose ?? "",
    light: v.light ?? "",
    surface: v.surface ?? "",
    third_party_damage_desc: v.third_party_damage_desc ?? "",
    third_party_damage_cost_sar: v.third_party_damage_cost_sar ?? "",
    reason: "",
  });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  async function save() {
    setBusy(true);
    setError(null);
    try {
      const next = await unwrap(
        api.PATCH("/api/v1/incidents/{incident_id}", {
          params: { path: { incident_id: r.id } },
          body: {
            road_type: (f.road_type || null) as S["VehRoadType"] | null,
            road_location: f.road_type === "public_road" ? f.road_location.trim() || null : null,
            journey_purpose: (f.journey_purpose || null) as S["VehJourneyPurpose"] | null,
            light: (f.light || null) as S["VehLight"] | null,
            surface: (f.surface || null) as S["VehSurface"] | null,
            third_party_damage_desc: f.third_party_damage_desc.trim() || null,
            third_party_damage_cost_sar: f.third_party_damage_cost_sar || null,
            reason: f.reason.trim() || null,
          },
        }),
      );
      warn(next.warnings);
      toast.success(tc("saved"));
      await refresh();
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent closeLabel={tc("close")} className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t("section")}</DialogTitle>
          <DialogDescription>{td("roadDialogHint")}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField id="vr-road_type" label={t("fields.road_type")} required>
            <Select value={f.road_type} onChange={set("road_type")} data-testid="vr-road-type">
              <option value="">{tc("select")}</option>
              {VEH_ROAD_TYPES.map((x) => (
                <option key={x} value={x}>
                  {L.road(x)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="vr-journey" label={t("fields.journey_purpose")} required hint={VEH_COMMUTING.includes(f.journey_purpose as S["VehJourneyPurpose"]) ? t("commutingHint") : undefined}>
            <Select value={f.journey_purpose} onChange={set("journey_purpose")} data-testid="vr-journey">
              <option value="">{tc("select")}</option>
              {VEH_JOURNEY_PURPOSES.map((x) => (
                <option key={x} value={x}>
                  {L.journey(x)}
                </option>
              ))}
            </Select>
          </FormField>
          {f.road_type === "public_road" ? (
            <FormField id="vr-road_location" label={t("fields.road_location")} required hint={t("fields.road_location_hint")} className="sm:col-span-2">
              <Input value={f.road_location} onChange={set("road_location")} maxLength={200} />
            </FormField>
          ) : null}
          <FormField id="vr-light" label={t("fields.light")}>
            <Select value={f.light} onChange={set("light")}>
              <option value="">{tc("select")}</option>
              {VEH_LIGHTS.map((x) => (
                <option key={x} value={x}>
                  {L.light(x)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="vr-surface" label={t("fields.surface")}>
            <Select value={f.surface} onChange={set("surface")}>
              <option value="">{tc("select")}</option>
              {VEH_SURFACES.map((x) => (
                <option key={x} value={x}>
                  {L.surface(x)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="vr-tpd" label={t("fields.third_party_damage_desc")}>
            <Input value={f.third_party_damage_desc} onChange={set("third_party_damage_desc")} maxLength={500} />
          </FormField>
          <FormField id="vr-tpc" label={t("fields.third_party_damage_cost_sar")}>
            <Input value={f.third_party_damage_cost_sar} onChange={set("third_party_damage_cost_sar")} inputMode="decimal" className="ltr" />
          </FormField>
          {needReason ? (
            <FormField id="vr-reason" label={t("fields.reason")} required hint={t("reasonHint")} className="sm:col-span-2">
              <Textarea value={f.reason} onChange={set("reason")} maxLength={500} />
            </FormField>
          ) : null}
        </div>
        <MutationError error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button onClick={() => void save()} disabled={busy || (needReason && f.reason.trim().length < 20)} data-testid="vr-save">
            {busy ? tc("saving") : tc("save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ───────────── vehicle row dialog ───────────── */

type RowForm = {
  ownership: string;
  role: string;
  engagement_id: string;
  vehicle_id: string;
  plate_type: string;
  plate_letters_ar: string;
  plate_letters_en: string;
  plate_digits: string;
  category: string;
  make_model: string;
  damage: string;
  damage_cost_sar: string;
  istimara: string;
  insurance: string;
  mvpi: string;
  insurer: string;
  policy_no: string;
  seat_belt: string;
  speed_kmh: string;
  speed_limit_kmh: string;
  speed_source: string;
  driver_kind: string;
  worker_id: string;
  external_driver_name: string;
  licence_issuer: string;
  licence_class: string;
  licence_expiry: string;
  licence_no: string;
  hours_on_duty: string;
  driver_case_no: string;
  reason: string;
};

const s = (v: string | number | null | undefined) => (v === null || v === undefined ? "" : String(v));

function VehicleRowDialog({ incident: r, row, onClose }: { incident: Incident; row?: Row; onClose: () => void }) {
  const t = useTranslations("veh");
  const td = useTranslations("vehDesign");
  const tc = useTranslations("common");
  const L = useVehLabels();
  const name = useLocalizedName();
  const refresh = useVehRefresh(r.id);
  const warn = useWarningToasts();
  const opts = useProjectOptions(r.project_id);
  const hideIdentity = Boolean(row?.redacted_groups.length);
  const needReason = Boolean(r.investigation?.approved_at);
  const [f, setF] = useState<RowForm>({
    ownership: row?.ownership ?? "",
    role: row?.role ?? "",
    engagement_id: row?.engagement?.id ?? "",
    vehicle_id: row?.vehicle?.id ?? "",
    plate_type: s(row?.plate_type),
    plate_letters_ar: s(row?.plate_letters_ar),
    plate_letters_en: s(row?.plate_letters_en),
    plate_digits: s(row?.plate_digits),
    category: s(row?.category),
    make_model: s(row?.make_model),
    damage: s(row?.damage),
    damage_cost_sar: s(row?.damage_cost_sar),
    istimara: row?.docs_valid_at_time.istimara ?? "unknown",
    insurance: row?.docs_valid_at_time.insurance ?? "unknown",
    mvpi: row?.docs_valid_at_time.mvpi ?? "unknown",
    insurer: s(row?.insurer),
    policy_no: s(row?.policy_no),
    seat_belt: s(row?.seat_belt),
    speed_kmh: s(row?.speed_kmh),
    speed_limit_kmh: s(row?.speed_limit_kmh),
    speed_source: s(row?.speed_source),
    driver_kind: s(row?.driver_kind),
    worker_id: row?.worker?.id ?? "",
    external_driver_name: s(row?.external_driver_name),
    licence_issuer: s(row?.licence_issuer),
    licence_class: s(row?.licence_class),
    licence_expiry: s(row?.licence_expiry),
    licence_no: s(row?.licence_no),
    hours_on_duty: s(row?.hours_on_duty),
    driver_case_no: s(row?.driver_case_no),
    reason: "",
  });
  const [workerQ, setWorkerQ] = useState("");
  const [prefillNote, setPrefillNote] = useState<string | null>(null);
  const [adpNote, setAdpNote] = useState<string | null>(row?.licence_prefilled_from_adp ? t("prefilledFromAdp", { adp: "" }).trim() : null);
  const [licenceNoField, setLicenceNoField] = useState(true);
  const [plateRegistered, setPlateRegistered] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const company = VEH_COMPANY_OWNERSHIPS.includes(f.ownership as S["VehOwnership"]);
  const thirdParty = f.ownership === "third_party";
  const vehicles = useQuery({
    queryKey: ["veh-register", r.project_id],
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/vehicles", { params: { path: { project_id: r.project_id }, query: { page_size: 200 } } })),
    enabled: company,
    retry: false,
    staleTime: 60_000,
  });
  const workers = useQuery({
    queryKey: ["veh-workers", r.project_id, workerQ],
    queryFn: () => unwrap(api.GET("/api/v1/workers", { params: { query: { project_id: r.project_id, q: workerQ || null, page_size: 25 } } })),
    enabled: f.driver_kind === "worker" && !hideIdentity,
    retry: false,
  });
  const workerOpts = (workers.data?.items ?? []).map((w) => ({ value: w.id, label: `${w.worker_no} — ${name(w.full_name_en, w.full_name_ar)}` }));
  if (row?.worker && !workerOpts.some((o) => o.value === row.worker?.id)) workerOpts.unshift({ value: row.worker.id, label: `${row.worker.worker_no} — ${name(row.worker.full_name_en, row.worker.full_name_ar)}` });

  const set = (k: keyof RowForm) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  const prefill = (query: { vehicle_id?: string; worker_id?: string; plate_letters_ar?: string; plate_letters_en?: string; plate_digits?: string }) =>
    unwrap(api.GET("/api/v1/incidents/{incident_id}/vehicle-prefill", { params: { path: { incident_id: r.id }, query } }));

  async function pickVehicle(id: string) {
    setF((x) => ({ ...x, vehicle_id: id }));
    setPrefillNote(null);
    if (!id) return;
    try {
      const p = await prefill({ vehicle_id: id });
      const v = p.vehicle;
      if (!v) return;
      setF((x) => ({
        ...x,
        vehicle_id: id,
        plate_type: v.plate_type,
        plate_letters_ar: v.plate_letters_ar ?? "",
        plate_letters_en: v.plate_letters_en ?? "",
        plate_digits: v.plate_digits ?? "",
        category: v.category,
        make_model: v.make_model,
        engagement_id: v.engagement?.id ?? x.engagement_id,
        istimara: v.docs_valid_at_time.istimara,
        insurance: v.docs_valid_at_time.insurance,
        mvpi: v.docs_valid_at_time.mvpi,
      }));
      setPrefillNote(t("prefilledFromVehicle", { vehicle: v.vehicle_no }));
    } catch {
      /* prefill is a convenience: the server computes the same values on save */
    }
  }

  async function pickWorker(id: string) {
    setF((x) => ({ ...x, worker_id: id }));
    setAdpNote(null);
    if (!id) return;
    try {
      const p = await prefill({ worker_id: id });
      const d = p.driver;
      if (d?.has_adp) {
        setF((x) => ({
          ...x,
          worker_id: id,
          licence_issuer: d.licence_issuer ?? x.licence_issuer,
          licence_class: d.licence_class ?? x.licence_class,
          licence_expiry: d.licence_expiry ?? x.licence_expiry,
          licence_no: d.licence_number_field ? x.licence_no : "",
        }));
        setLicenceNoField(d.licence_number_field);
        setAdpNote(t("prefilledFromAdp", { adp: d.adp_no ?? "" }));
      }
    } catch {
      /* identity prefill needs capability 29; the fields stay editable */
    }
  }

  async function checkPlate() {
    if (!thirdParty || !f.plate_digits) return setPlateRegistered(false);
    try {
      const p = await prefill({ plate_letters_ar: f.plate_letters_ar || undefined, plate_letters_en: f.plate_letters_en || undefined, plate_digits: f.plate_digits });
      setPlateRegistered(p.plate_registered);
    } catch {
      setPlateRegistered(false);
    }
  }

  async function save() {
    setBusy(true);
    setError(null);
    const n = (v: string) => (v.trim() ? v.trim() : null);
    const num = (v: string) => (v.trim() ? Number(v) : null);
    const plated = f.ownership !== "unknown";
    // Third-party plates are personal (P7a-1): without capability 29 they come back null, so they are not sent.
    const plate =
      hideIdentity && thirdParty
        ? {}
        : { plate_letters_ar: plated ? n(f.plate_letters_ar) : null, plate_letters_en: plated ? n(f.plate_letters_en) : null, plate_digits: plated ? n(f.plate_digits) : null };
    const identity = hideIdentity
      ? {}
      : {
          worker_id: f.driver_kind === "worker" ? f.worker_id || null : null,
          external_driver_name: f.driver_kind === "external" ? n(f.external_driver_name) : null,
          licence_issuer: f.driver_kind === "none" ? null : ((f.licence_issuer || null) as S["LicenceIssuer"] | null),
          licence_class: f.driver_kind === "none" ? null : ((f.licence_class || null) as S["LicenceClass"] | null),
          licence_expiry: f.driver_kind === "none" ? null : f.licence_expiry || null,
          licence_no: f.licence_issuer && f.licence_issuer !== "ksa" ? n(f.licence_no) : null,
          hours_on_duty: f.driver_kind === "none" ? null : n(f.hours_on_duty),
          insurer: thirdParty ? n(f.insurer) : null,
          policy_no: thirdParty ? n(f.policy_no) : null,
        };
    const common = {
      ownership: f.ownership as S["VehOwnership"],
      role: f.role as S["VehRole"],
      engagement_id: company ? f.engagement_id || null : null,
      vehicle_id: company ? f.vehicle_id || null : null,
      plate_type: plated ? ((f.plate_type || null) as S["PlateType"] | null) : null,
      ...plate,
      category: (f.category || null) as S["VehCategory"] | null,
      make_model: n(f.make_model),
      damage: (f.damage || null) as S["VehDamage"] | null,
      damage_cost_sar: n(f.damage_cost_sar),
      docs: f.vehicle_id && company ? null : { istimara: f.istimara as S["VehDocState"], insurance: f.insurance as S["VehDocState"], mvpi: f.mvpi as S["VehDocState"] },
      seat_belt: (f.seat_belt || null) as S["VehSeatBelt"] | null,
      speed_kmh: num(f.speed_kmh),
      speed_limit_kmh: num(f.speed_limit_kmh),
      speed_source: (f.speed_source || null) as S["VehSpeedSource"] | null,
      driver_kind: (f.driver_kind || null) as S["VehDriverKind"] | null,
      driver_case_no: num(f.driver_case_no),
      reason: n(f.reason),
    };
    try {
      const saved = row
        ? await unwrap(api.PATCH("/api/v1/incident-vehicles/{vehicle_row_id}", { params: { path: { vehicle_row_id: row.id } }, body: { ...common, ...identity } }))
        : await unwrap(api.POST("/api/v1/incidents/{incident_id}/vehicles", { params: { path: { incident_id: r.id } }, body: { ...common, ...identity } }));
      warn(saved.warnings);
      toast.success(row ? tc("saved") : tc("created"));
      await refresh();
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  const select = (id: keyof RowForm, label: string, options: readonly string[], lab: (v: string) => string, required = false, extra?: { onChange?: (v: string) => void; testId?: string; hint?: string; empty?: string }) => (
    <FormField id={`vd-${id}`} label={label} required={required} hint={extra?.hint}>
      <Select value={f[id]} onChange={extra?.onChange ? (e) => extra.onChange?.(e.target.value) : set(id)} data-testid={extra?.testId ?? `vd-${id}`}>
        <option value="">{extra?.empty ?? tc("select")}</option>
        {options.map((x) => (
          <option key={x} value={x}>
            {lab(x)}
          </option>
        ))}
      </Select>
    </FormField>
  );
  const text = (id: keyof RowForm, label: string, o: { ltr?: boolean; max?: number; type?: string; inputMode?: "decimal" | "numeric"; hint?: string; required?: boolean; onBlur?: () => void } = {}) => (
    <FormField id={`vd-${id}`} label={label} hint={o.hint} required={o.required}>
      <Input value={f[id]} onChange={set(id)} maxLength={o.max} type={o.type} inputMode={o.inputMode} className={o.ltr ? "ltr" : undefined} onBlur={o.onBlur} data-testid={`vd-${id}`} />
    </FormField>
  );
  const vehicleOptions = (vehicles.data?.items ?? []).filter((v) => !f.engagement_id || !v.engagement || v.engagement.id === f.engagement_id || f.ownership === "own_company");

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent closeLabel={tc("close")} className="max-w-3xl" data-testid="veh-dialog">
        <DialogHeader>
          <DialogTitle>{row ? t("card.editTitle", { label: row.label }) : t("card.addTitle")}</DialogTitle>
          <DialogDescription>{td("vehicleDialogHint")}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          {select("ownership", t("fields.ownership"), VEH_OWNERSHIPS, (x) => L.ownership(x as S["VehOwnership"]), true)}
          {select("role", t("fields.role"), VEH_ROLES, (x) => L.role(x as S["VehRole"]), true)}
          {company ? (
            <FormField id="vd-engagement_id" label={t("fields.engagement")} required>
              <Select value={f.engagement_id} onChange={set("engagement_id")} data-testid="vd-engagement_id">
                <option value="">{tc("select")}</option>
                {opts.engagements.map((e) => (
                  <option key={e.value} value={e.value}>
                    {e.label}
                  </option>
                ))}
              </Select>
            </FormField>
          ) : null}
          {company ? (
            <FormField id="vd-vehicle_id" label={t("fields.vehicle")} hint={prefillNote ?? undefined}>
              <Select value={f.vehicle_id} onChange={(e) => void pickVehicle(e.target.value)} data-testid="vd-vehicle_id">
                <option value="">{t("card.pickVehicle")}</option>
                {vehicleOptions.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.vehicle_no} — {v.make_model}
                    {v.plate_digits ? ` (${[v.plate_letters_en, v.plate_digits].filter(Boolean).join(" ")})` : ""}
                  </option>
                ))}
              </Select>
            </FormField>
          ) : null}
          {f.ownership !== "unknown" && !(hideIdentity && thirdParty) ? (
            <>
              {select("plate_type", t("fields.plate_type"), PLATE_TYPES, (x) => L.plateType(x as S["PlateType"]))}
              {f.plate_type !== "none" ? (
                <div className="grid grid-cols-3 gap-2 sm:col-span-2">
                  {text("plate_letters_ar", t("fields.plate_letters_ar"), { max: 5, onBlur: () => void checkPlate() })}
                  {text("plate_letters_en", t("fields.plate_letters_en"), { max: 5, ltr: true, onBlur: () => void checkPlate() })}
                  {text("plate_digits", t("fields.plate_digits"), { max: 4, ltr: true, inputMode: "numeric", onBlur: () => void checkPlate() })}
                </div>
              ) : null}
              {plateRegistered ? (
                <Alert tone="warning" className="sm:col-span-2" data-testid="vd-plate-registered">
                  {t("plateRegistered")}
                </Alert>
              ) : null}
            </>
          ) : null}
          {select("category", t("fields.category"), VEH_CATEGORIES, (x) => L.category(x as S["VehCategory"]), true)}
          {text("make_model", t("fields.make_model"), { max: 60 })}
          {select("damage", t("fields.damage"), VEH_DAMAGES, (x) => L.damage(x as S["VehDamage"]), true)}
          {text("damage_cost_sar", t("fields.damage_cost_sar"), { ltr: true, inputMode: "decimal" })}
          {!(f.vehicle_id && company) ? (
            <fieldset className="flex flex-col gap-2 sm:col-span-2">
              <legend className="mb-2 text-sm font-semibold">{t("fields.docs")}</legend>
              <div className="grid gap-2 sm:grid-cols-3">
              {(["istimara", "insurance", "mvpi"] as const).map((k) => (
                <FormField key={k} id={`vd-${k}`} label={t(`fields.${k}`)}>
                  <Select value={f[k]} onChange={set(k)}>
                    {VEH_DOC_STATES.map((x) => (
                      <option key={x} value={x}>
                        {L.doc(x)}
                      </option>
                    ))}
                  </Select>
                </FormField>
              ))}
              </div>
            </fieldset>
          ) : null}
          {thirdParty && !hideIdentity ? (
            <>
              {text("insurer", t("fields.insurer"), { max: 80 })}
              {text("policy_no", t("fields.policy_no"), { max: 40, ltr: true })}
            </>
          ) : null}
          {select("driver_kind", t("fields.driver_kind"), VEH_DRIVER_KINDS, (x) => L.driverKind(x as S["VehDriverKind"]), true)}
          {f.driver_kind !== "none" ? select("seat_belt", t("fields.seat_belt"), VEH_SEAT_BELTS, (x) => L.seatBelt(x as S["VehSeatBelt"]), true) : null}
          {hideIdentity ? (
            <p className="text-xs text-muted-foreground sm:col-span-2">{t("card.driverHidden")}</p>
          ) : (
            <>
              {f.driver_kind === "worker" ? (
                <>
                  <FormField id="vd-worker-q" label={t("fields.worker_search")}>
                    <Input value={workerQ} onChange={(e) => setWorkerQ(e.target.value)} data-testid="vd-worker-q" />
                  </FormField>
                  <FormField id="vd-worker_id" label={t("fields.worker")} required hint={adpNote ?? undefined}>
                    <Select value={f.worker_id} onChange={(e) => void pickWorker(e.target.value)} data-testid="vd-worker_id">
                      <option value="">{workerOpts.length ? tc("select") : t("card.noWorker")}</option>
                      {workerOpts.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </Select>
                  </FormField>
                </>
              ) : null}
              {f.driver_kind === "external" ? text("external_driver_name", t("fields.external_driver_name"), { max: 120, required: true }) : null}
              {f.driver_kind && f.driver_kind !== "none" ? (
                <>
                  {select("licence_issuer", t("fields.licence_issuer"), LICENCE_ISSUERS, (x) => L.issuer(x as S["LicenceIssuer"]), f.driver_kind === "worker", { hint: f.licence_issuer === "ksa" ? t("noKsaLicenceNo") : undefined })}
                  {select("licence_class", t("fields.licence_class"), LICENCE_CLASSES, (x) => L.licenceClass(x as S["LicenceClass"]), f.driver_kind === "worker")}
                  {text("licence_expiry", t("fields.licence_expiry"), { type: "date", required: f.driver_kind === "worker" })}
                  {f.licence_issuer && f.licence_issuer !== "ksa" && licenceNoField ? text("licence_no", t("fields.licence_no"), { max: 30, ltr: true }) : null}
                  {text("hours_on_duty", t("fields.hours_on_duty"), { ltr: true, inputMode: "decimal" })}
                </>
              ) : null}
            </>
          )}
          {f.driver_kind !== "none" ? (
            <>
              {text("speed_kmh", t("fields.speed_kmh"), { ltr: true, inputMode: "numeric" })}
              {text("speed_limit_kmh", t("fields.speed_limit_kmh"), { ltr: true, inputMode: "numeric" })}
              {select("speed_source", t("fields.speed_source"), VEH_SPEED_SOURCES, (x) => L.speedSource(x as S["VehSpeedSource"]) ?? x)}
            </>
          ) : null}
          {r.cases.length ? (
            <FormField id="vd-driver_case_no" label={t("fields.driver_case_no")}>
              <Select value={f.driver_case_no} onChange={set("driver_case_no")}>
                <option value="">—</option>
                {r.cases.map((c) => (
                  <option key={c.id} value={c.case_no.replace(/^.*-P/, "")}>
                    {c.case_no}
                  </option>
                ))}
              </Select>
            </FormField>
          ) : null}
          {needReason ? (
            <FormField id="vd-reason" label={t("fields.reason")} required hint={t("reasonHint")} className="sm:col-span-2">
              <Textarea value={f.reason} onChange={set("reason")} maxLength={500} />
            </FormField>
          ) : null}
        </div>
        <MutationError error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button onClick={() => void save()} disabled={busy || !f.ownership || !f.role || (needReason && f.reason.trim().length < 20)} data-testid="vd-save">
            {busy ? tc("saving") : tc("save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ───────────── accident report archive card (VA-14, VA-15) ───────────── */

function size(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function AccidentReportCard({ incident: r }: { incident: Incident }) {
  const t = useTranslations("veh");
  const td = useTranslations("vehDesign.report");
  const tc = useTranslations("common");
  const te = useTranslations("enums");
  const L = useVehLabels();
  const msg = useErrorMessage();
  const name = useLocalizedName();
  const { date, dateTime } = useFormatters(r.project_id);
  const refresh = useVehRefresh(r.id);
  const editable = useVehEdit(r);
  const me = useMeData();
  const canUpload = canWrite(me, "incident.report", r.project_id) && r.status !== "voided";
  const fileRef = useRef<HTMLInputElement>(null);
  const [supersedes, setSupersedes] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [offerOpen, setOfferOpen] = useState(false);
  const v = r.vehicle_section;
  if (!r.vehicle_involved || !v) return null;
  const a = v.accident_report;
  const offer = v.report_submission_offer;
  const files = [...a.files].sort((x, y) => Number(x.superseded) - Number(y.superseded) || y.created_at.localeCompare(x.created_at));
  const current = files.filter((x) => !x.superseded);

  async function upload(list: FileList | null) {
    const file = list?.[0];
    if (!file) return;
    setBusy(true);
    try {
      const form = new FormData();
      form.set("file", file);
      if (supersedes) form.set("supersedes_id", supersedes);
      await postForm<S["VehAccidentReportRead"]>(`/api/v1/incidents/${r.id}/accident-report/files`, form);
      toast.success(t("report.uploaded"));
      await refresh();
    } catch (e) {
      toast.error(msg(e));
    } finally {
      setBusy(false);
      setSupersedes(null);
      if (fileRef.current) fileRef.current.value = "";
    }
  }
  function pick(supersedesId: string | null) {
    setSupersedes(supersedesId);
    fileRef.current?.click();
  }
  async function open(id: string) {
    try {
      const sUrl = await unwrap(api.POST("/api/v1/attachments/{attachment_id}/signed-url", { params: { path: { attachment_id: id } } }));
      window.open(sUrl.url, "_blank", "noopener");
    } catch (e) {
      toast.error(msg(e));
    }
  }
  async function remove(id: string) {
    if (!window.confirm(tc("confirmDelete"))) return;
    try {
      await unwrap(api.DELETE("/api/v1/attachments/{attachment_id}", { params: { path: { attachment_id: id } } }));
      await refresh();
    } catch (e) {
      toast.error(msg(e));
    }
  }

  const state = !a.required_to_close
    ? { status: "not_required", label: t("report.notRequired") }
    : a.waived
      ? { status: "cleared", label: t("report.waived") }
      : a.missing_to_close.length
        ? { status: "missing", label: t("report.requiredToClose") }
        : { status: "ok", label: t("report.complete") };

  return (
    <Card data-testid="accident-report-card" data-locked={a.locked ? "true" : "false"}>
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-48 flex-1 basis-0 flex-col gap-1">
          <CardTitle>{t("report.title")}</CardTitle>
          <p className="text-xs text-muted-foreground">{t("report.internal")}</p>
        </div>
        {editable ? (
          <Button size="sm" variant="outline" onClick={() => setEditOpen(true)} data-testid="ar-edit">
            <Pencil aria-hidden />
            {t("report.edit")}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <FieldList className="sm:grid-cols-2 lg:grid-cols-2">
          <FieldItem label={t("fields.report_authority")}>
            <span data-testid="ar-authority">{L.authority(a.report_authority)}</span>
          </FieldItem>
          <FieldItem label={t("fields.report_no")}>
            {a.report_no ? (
              <bdi dir="ltr" className="ltr font-medium" data-testid="ar-number">
                {a.report_no}
              </bdi>
            ) : (
              "—"
            )}
          </FieldItem>
          <FieldItem label={t("fields.report_date")}>{date(a.report_date)}</FieldItem>
          <FieldItem label={t("fields.liability_pct_own")}>{a.liability_pct_own !== null ? <bdi className="ltr">{a.liability_pct_own} %</bdi> : "—"}</FieldItem>
        </FieldList>
        <div className="flex flex-wrap items-center gap-2" data-testid="ar-state" data-state={state.status}>
          <span className="text-xs text-muted-foreground">{td("closeCheck")}</span>
          <StatusBadge status={state.status} label={state.label} />
        </div>
        <MissingList title={t("report.requiredToClose")} items={a.required_to_close && !a.waived ? a.missing_to_close : []} testId="ar-missing" />
        {offer && canUpload ? (
          <Alert tone="info" data-testid="ar-offer" data-body={offer.body}>
            <p className="font-medium">{t("report.offerTitle", { body: te(`externalBody.${offer.body}`) })}</p>
            <p className="mt-1 text-sm">
              {t("report.offerBody", { ref: offer.reference_no, body: te(`externalBody.${offer.body}`) })}
            </p>
            <Button size="sm" className="mt-2" onClick={() => setOfferOpen(true)} data-testid="ar-offer-record">
              {t("report.offerAction")}
            </Button>
          </Alert>
        ) : null}
        {a.locked ? (
          <Alert tone="info" data-testid="ar-locked">
            {t("report.locked")}
          </Alert>
        ) : null}
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">{t("report.files")}</h3>
          {!a.files_visible ? (
            <p className="flex items-start gap-2 text-sm text-muted-foreground" data-testid="ar-files-hidden">
              <Lock aria-hidden className="mt-0.5 size-4 shrink-0" />
              <span>
                {t("report.filesHidden")} <span className="text-xs">({t("report.fileCount", { n: a.file_count })})</span>
              </span>
            </p>
          ) : files.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("report.noFiles")}</p>
          ) : (
            <ul className="flex flex-col divide-y rounded-lg border" data-testid="ar-files">
              {files.map((x) => (
                <li
                  key={x.id}
                  className={cn("flex flex-col gap-2 px-3 py-2.5 text-sm sm:flex-row sm:items-center", x.superseded && "bg-muted/40")}
                  data-testid="ar-file"
                  data-superseded={x.superseded ? "true" : "false"}
                >
                  <span className="flex min-w-0 flex-1 items-start gap-2">
                    <FileText aria-hidden className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                    <span className="min-w-0">
                      <bdi className={cn("ltr block font-medium [overflow-wrap:anywhere]", x.superseded && "font-normal text-muted-foreground line-through")}>{x.file_name}</bdi>
                      <span className="block text-xs text-muted-foreground">
                        {size(x.size_bytes)} · {t("report.uploadedBy", { name: name(x.uploaded_by.full_name_en, x.uploaded_by.full_name_ar), at: dateTime(x.created_at) })}
                      </span>
                    </span>
                  </span>
                  <span className="flex flex-wrap items-center gap-1 ps-6 sm:ps-0">
                    {x.superseded ? (
                      <StatusBadge status="superseded" label={x.superseded_at ? t("report.supersededOn", { at: date(x.superseded_at) }) : t("report.superseded")} />
                    ) : (
                      <StatusBadge status="valid" label={t("report.current")} />
                    )}
                    <Button variant="ghost" size="sm" onClick={() => void open(x.id)}>
                      <Download aria-hidden />
                      {tc("download")}
                    </Button>
                    {editable && !a.locked && !x.superseded ? (
                      <Button variant="ghost" size="icon" aria-label={`${tc("delete")} ${x.file_name}`} onClick={() => void remove(x.id)} data-testid="ar-delete">
                        <Trash2 aria-hidden />
                      </Button>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {a.files_visible && canUpload && a.file_count < 5 ? (
            <div>
              <Button size="sm" variant="outline" onClick={() => pick(null)} disabled={busy} data-testid="ar-upload">
                <FileUp aria-hidden />
                {t("report.upload")}
              </Button>
            </div>
          ) : null}
          <input ref={fileRef} type="file" accept="image/*,application/pdf" className="sr-only" onChange={(e) => void upload(e.target.files)} data-testid="ar-file-input" aria-label={t("report.upload")} />
        </div>
        {/* Superseding an archived report cannot be undone (the old file stays, marked superseded): record-actions band. */}
        {a.files_visible && canUpload && current.length ? (
          <RecordActions label={td("replaceBand")} testId="ar-record-actions" className="mt-2">
            {current.map((x) => (
              <Button key={x.id} variant="destructive-outline" size="sm" onClick={() => pick(x.id)} disabled={busy} data-testid="ar-replace" title={t("report.replaceHint")}>
                <FileUp aria-hidden />
                {current.length > 1 ? td("replaceNamed", { name: x.file_name }) : t("report.replace")}
              </Button>
            ))}
          </RecordActions>
        ) : null}
      </CardContent>
      {editOpen ? <ReportDialog incident={r} report={a} onClose={() => setEditOpen(false)} /> : null}
      {offerOpen && offer ? <OfferDialog incident={r} offer={offer} onClose={() => setOfferOpen(false)} /> : null}
    </Card>
  );
}

function ReportDialog({ incident: r, report: a, onClose }: { incident: Incident; report: S["VehAccidentReportRead"]; onClose: () => void }) {
  const t = useTranslations("veh");
  const tc = useTranslations("common");
  const L = useVehLabels();
  const refresh = useVehRefresh(r.id);
  const needReason = Boolean(r.investigation?.approved_at);
  const publicRoad = r.vehicle_section?.road_type === "public_road";
  const [f, setF] = useState({
    report_authority: a.report_authority ?? "",
    report_no: a.report_no ?? "",
    report_date: a.report_date ?? "",
    liability_pct_own: a.liability_pct_own === null ? "" : String(a.liability_pct_own),
    reason: "",
  });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  async function save() {
    setBusy(true);
    setError(null);
    try {
      await unwrap(
        api.PUT("/api/v1/incidents/{incident_id}/accident-report", {
          params: { path: { incident_id: r.id } },
          body: {
            report_authority: (f.report_authority || null) as S["VehReportAuthority"] | null,
            report_no: f.report_no.trim() || null,
            report_date: f.report_date || null,
            liability_pct_own: f.liability_pct_own === "" ? null : Number(f.liability_pct_own),
            reason: f.reason.trim() || null,
          },
        }),
      );
      toast.success(tc("saved"));
      await refresh();
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent closeLabel={tc("close")}>
        <DialogHeader>
          <DialogTitle>{t("report.editTitle")}</DialogTitle>
          <DialogDescription>{t("report.internal")}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <FormField id="ar-authority-in" label={t("fields.report_authority")} required={publicRoad}>
            <Select value={f.report_authority} onChange={set("report_authority")} data-testid="ar-authority-in">
              <option value="">{tc("select")}</option>
              {VEH_AUTHORITIES.filter((x) => !(publicRoad && x === "none_internal")).map((x) => (
                <option key={x} value={x}>
                  {L.authority(x)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="ar-no-in" label={t("fields.report_no")}>
            <Input value={f.report_no} onChange={set("report_no")} maxLength={40} className="ltr" dir="ltr" data-testid="ar-no-in" />
          </FormField>
          <FormField id="ar-date-in" label={t("fields.report_date")}>
            <Input type="date" value={f.report_date} onChange={set("report_date")} data-testid="ar-date-in" />
          </FormField>
          <FormField id="ar-liab-in" label={t("fields.liability_pct_own")}>
            <Select value={f.liability_pct_own} onChange={set("liability_pct_own")}>
              <option value="">—</option>
              {VEH_LIABILITY.map((x) => (
                <option key={x} value={String(x)}>
                  {x} %
                </option>
              ))}
            </Select>
          </FormField>
          {needReason ? (
            <FormField id="ar-reason" label={t("fields.reason")} required hint={t("reasonHint")}>
              <Textarea value={f.reason} onChange={set("reason")} maxLength={500} />
            </FormField>
          ) : null}
          <MutationError error={error} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button onClick={() => void save()} disabled={busy || (needReason && f.reason.trim().length < 20)} data-testid="ar-save">
            {busy ? tc("saving") : tc("save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** AC21: record the police / Najm submission with the report number (6f requirement, or the Phase 1 item). */
function OfferDialog({ incident: r, offer, onClose }: { incident: Incident; offer: S["VehSubmissionOffer"]; onClose: () => void }) {
  const caps = useFuCaps(r.project_id);
  const reqs = useFuRequirements(r.project_id, { incident_id: r.id, page_size: 100 }, { enabled: Boolean(offer.requirement_id) && caps.view });
  const req = reqs.data?.items.find((x) => x.id === offer.requirement_id);
  if (offer.requirement_id) {
    return req ? <SubmissionDialog req={req} initialRef={offer.reference_no} onClose={onClose} /> : null;
  }
  return <Phase1NotifyDialog incident={r} offer={offer} onClose={onClose} />;
}

function Phase1NotifyDialog({ incident: r, offer, onClose }: { incident: Incident; offer: S["VehSubmissionOffer"]; onClose: () => void }) {
  const t = useTranslations("incidents");
  const tv = useTranslations("veh");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const refresh = useVehRefresh(r.id);
  const settings = useProjectSettings(r.project_id);
  const tz = settings.data?.timezone ?? DEFAULT_TIME_ZONE;
  const [at, setAt] = useState(utcToZonedInput(new Date().toISOString(), tz));
  const [refNo, setRefNo] = useState(offer.reference_no);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await unwrap(
        api.PUT("/api/v1/incidents/{incident_id}/external-notifications/{body}", {
          params: { path: { incident_id: r.id, body: offer.body } },
          body: { notified_at: zonedInputToUtc(at, tz), reference_no: refNo.trim() || null },
        }),
      );
      toast.success(tc("saved"));
      await refresh();
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent closeLabel={tc("close")}>
        <DialogHeader>
          <DialogTitle>{t("recordNotification", { body: te(`externalBody.${offer.body}`) })}</DialogTitle>
          <DialogDescription>{tv("report.offerTitle", { body: te(`externalBody.${offer.body}`) })}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <FormField id="offer-at" label={t("notifiedAt")} required>
            <Input type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} />
          </FormField>
          <FormField id="offer-ref" label={t("referenceNo")}>
            <Input value={refNo} onChange={(e) => setRefNo(e.target.value)} maxLength={60} className="ltr" dir="ltr" data-testid="offer-ref" />
          </FormField>
          <MutationError error={error} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button onClick={() => void submit()} disabled={busy || !at} data-testid="offer-save">
            {tc("save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
