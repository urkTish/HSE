"use client";
import { Pencil } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";
import { TagStatusBadge } from "@/components/cert/common";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { CheckboxGroup } from "@/components/common/checkbox-group";
import { FieldItem, FieldList, YesNo } from "@/components/common/field-list";
import { CheckboxField, FormField } from "@/components/common/form-field";
import { MutationError } from "@/components/common/states";
import { useMeData } from "@/components/shell/me-context";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useDetectors, usePtwRefresh } from "@/lib/api/ptw";
import {
  ACCESS_METHODS,
  AIRCRAFT_PROXIMITIES,
  COMMUNICATION_METHODS,
  CYLINDER_KINDS,
  ENERGIZED_JUSTIFICATIONS,
  EXCAVATION_METHODS,
  EXTINGUISHER_TYPES,
  FALL_PROTECTIONS,
  HOT_WORK_KINDS,
  OPENINGS_PROTECTED,
  PROTECTIVE_SYSTEMS,
  PTW_EGRESSES,
  RADIATION_SOURCES,
  RESCUE_METHODS,
  SOIL_TYPES,
  SPACE_HAZARDS,
  VENTILATIONS,
  WORK_CONDITIONS,
} from "@/lib/ptw-enums";
import { useFormatters } from "@/lib/use-formatters";
import { DateTimeInput, DecimalInput } from "./common";

type S = Schemas;
type Permit = S["PermitRead"];
type Sec = Record<string, unknown> & { work_type?: S["PermitType"] };
export type SectionType = Exclude<S["PermitType"], "general">;

type EnumNs =
  | "hotWorkKind"
  | "openingsProtected"
  | "cylinderKind"
  | "spaceHazard"
  | "ventilation"
  | "rescueMethod"
  | "communicationMethod"
  | "accessMethod"
  | "fallProtection"
  | "excavationMethod"
  | "soilType"
  | "protectiveSystem"
  | "egress"
  | "workCondition"
  | "energizedJustification"
  | "radiationSource"
  | "aircraftProximity";

type Field =
  | { k: string; kind: "bool" | "dec" | "int" | "text" | "longtext" | "date" | "datetime"; req?: boolean }
  | { k: string; kind: "enum" | "multi"; values: readonly string[]; ns: EnumNs; req?: boolean }
  | { k: string; kind: "detector" | "extinguishers" | "heat" | "tfd" | "appliances" | "wap"; req?: boolean };

/** Editable fields per work type (contract *SectionInput). Computed values are shown read-only from *SectionRead. */
const FIELDS: Record<SectionType, Field[]> = {
  hot_work: [
    { k: "hot_work_kind", kind: "multi", values: HOT_WORK_KINDS, ns: "hotWorkKind", req: true },
    { k: "combustibles_cleared_radius_m", kind: "dec", req: true },
    { k: "combustibles_protected_method", kind: "text" },
    { k: "fire_extinguishers", kind: "extinguishers", req: true },
    { k: "fire_blanket", kind: "bool" },
    { k: "work_height_above_floor_m", kind: "dec" },
    { k: "openings_below_protected", kind: "enum", values: OPENINGS_PROTECTED, ns: "openingsProtected" },
    { k: "fire_system_impairment", kind: "bool" },
    { k: "impairment_hours_24h", kind: "dec" },
    { k: "civil_defense_notified_at", kind: "datetime" },
    { k: "impairment_ref", kind: "text" },
    { k: "cylinders", kind: "enum", values: CYLINDER_KINDS, ns: "cylinderKind" },
    { k: "flashback_arrestors_both_ends", kind: "bool" },
  ],
  confined_space: [
    { k: "space_id_desc", kind: "text", req: true },
    { k: "space_hazards", kind: "multi", values: SPACE_HAZARDS, ns: "spaceHazard", req: true },
    { k: "isolations_required", kind: "bool" },
    { k: "ventilation", kind: "enum", values: VENTILATIONS, ns: "ventilation", req: true },
    { k: "ventilation_justification", kind: "text" },
    { k: "continuous_monitor_detector_id", kind: "detector", req: true },
    { k: "rescue_method", kind: "enum", values: RESCUE_METHODS, ns: "rescueMethod", req: true },
    { k: "rescue_response_minutes", kind: "int" },
    { k: "rescue_equipment_checked", kind: "bool" },
    { k: "communication_method", kind: "enum", values: COMMUNICATION_METHODS, ns: "communicationMethod", req: true },
    { k: "heat_controls", kind: "heat" },
  ],
  work_at_height: [
    { k: "max_fall_height_m", kind: "dec", req: true },
    { k: "access_method", kind: "multi", values: ACCESS_METHODS, ns: "accessMethod", req: true },
    { k: "fall_protection", kind: "enum", values: FALL_PROTECTIONS, ns: "fallProtection", req: true },
    { k: "anchor_desc", kind: "text" },
    { k: "anchor_rating_kn", kind: "dec" },
    { k: "engineered_anchor_cert_ref", kind: "text" },
    { k: "lanyard_length_m", kind: "dec" },
    { k: "manufacturer_deceleration_m", kind: "dec" },
    { k: "srl_required_clearance_m", kind: "dec" },
    { k: "available_clearance_m", kind: "dec" },
    { k: "scaffold_tag_ref", kind: "text" },
    { k: "drop_zone_controlled", kind: "bool" },
    { k: "tool_tethering", kind: "bool" },
  ],
  excavation: [
    { k: "max_depth_m", kind: "dec", req: true },
    { k: "method", kind: "enum", values: EXCAVATION_METHODS, ns: "excavationMethod", req: true },
    { k: "soil_type", kind: "enum", values: SOIL_TYPES, ns: "soilType" },
    { k: "protective_system", kind: "enum", values: PROTECTIVE_SYSTEMS, ns: "protectiveSystem", req: true },
    { k: "slope_ratio_h_v", kind: "dec" },
    { k: "pe_design_ref", kind: "text" },
    { k: "utility_clearance_ref", kind: "text" },
    { k: "services_within_hand_dig_zone", kind: "bool" },
    { k: "spoil_setback_m", kind: "dec", req: true },
    { k: "egress", kind: "enum", values: PTW_EGRESSES, ns: "egress", req: true },
    { k: "egress_travel_m", kind: "dec" },
    { k: "atmosphere_hazard", kind: "bool" },
    { k: "edge_barriers", kind: "bool" },
    { k: "night_lighting", kind: "bool" },
  ],
  electrical_isolation: [
    { k: "system_voltage_v", kind: "int", req: true },
    { k: "dc", kind: "bool" },
    { k: "work_condition", kind: "enum", values: WORK_CONDITIONS, ns: "workCondition" },
    { k: "test_for_dead", kind: "tfd" },
    { k: "hv_earths_applied", kind: "bool" },
    { k: "switching_programme_ref", kind: "text" },
    { k: "energized_justification", kind: "enum", values: ENERGIZED_JUSTIFICATIONS, ns: "energizedJustification" },
    { k: "energized_justification_text", kind: "text" },
    { k: "limited_approach_m", kind: "dec" },
    { k: "restricted_approach_m", kind: "dec" },
    { k: "incident_energy_cal_cm2", kind: "dec" },
    { k: "arc_ppe_category", kind: "int" },
    { k: "arc_ppe_rating_cal_cm2", kind: "dec" },
  ],
  lifting: [
    { k: "appliance_equipment_ids", kind: "appliances", req: true },
    { k: "tandem", kind: "bool" },
    { k: "load_desc", kind: "text", req: true },
    { k: "load_weight_t", kind: "dec", req: true },
    { k: "rigging_weight_t", kind: "dec" },
    { k: "radius_m", kind: "dec", req: true },
    { k: "rated_capacity_t", kind: "dec", req: true },
    { k: "personnel_lift", kind: "bool" },
    { k: "personnel_lift_justification", kind: "text" },
    { k: "wind_limit_ms", kind: "dec" },
    { k: "exclusion_radius_m", kind: "dec", req: true },
    { k: "landing_grid_x_m", kind: "dec" },
    { k: "landing_grid_y_m", kind: "dec" },
    { k: "slew_radius_m", kind: "dec" },
    { k: "appliance_grid_x_m", kind: "dec" },
    { k: "appliance_grid_y_m", kind: "dec" },
    { k: "ground_bearing_checked", kind: "bool" },
    { k: "overhead_lines_within_6m", kind: "bool" },
    { k: "passes_over_occupied_or_live", kind: "bool" },
    { k: "within_15m_of_operational_airside", kind: "bool" },
  ],
  radiography: [
    { k: "source_type", kind: "enum", values: RADIATION_SOURCES, ns: "radiationSource", req: true },
    { k: "activity_gbq", kind: "dec" },
    { k: "xray_dose_rate_1m_usv_h", kind: "dec" },
    { k: "collimator_transmission", kind: "dec" },
    { k: "planned_barrier_m", kind: "dec", req: true },
    { k: "nrrc_licence_no", kind: "text", req: true },
    { k: "licence_valid_until", kind: "date", req: true },
    { k: "dosimetry_confirmed", kind: "bool" },
  ],
  airside_works: [
    { k: "wap_id", kind: "wap" },
    { k: "operator_works_permit_ref", kind: "text" },
    { k: "fod_control_plan", kind: "bool" },
    { k: "aircraft_proximity", kind: "enum", values: AIRCRAFT_PROXIMITIES, ns: "aircraftProximity", req: true },
    { k: "hydrant_operator_clearance_ref", kind: "text" },
    { k: "hydrant_pit_distance_m", kind: "dec" },
    { k: "ops_handback_ref", kind: "text" },
  ],
};

/** Server-computed values shown under each section. */
const COMPUTED: Partial<Record<SectionType, { k: string; kind: "dec" | "bool" | "datetime" | "text" | "reasons" | "voltage" }[]>> = {
  hot_work: [
    { k: "hot_work_ended_at", kind: "datetime" },
    { k: "fire_watch_until", kind: "datetime" },
    { k: "latest_compliant_end_at", kind: "datetime" },
    { k: "hot_work_late", kind: "bool" },
  ],
  confined_space: [
    { k: "internal_temp_c", kind: "dec" },
    { k: "persons_inside", kind: "dec" },
  ],
  work_at_height: [
    { k: "required_clearance_m", kind: "dec" },
    { k: "clearance_ok", kind: "bool" },
  ],
  excavation: [{ k: "inspected_for_current_shift", kind: "bool" }],
  electrical_isolation: [{ k: "voltage_class", kind: "voltage" }],
  lifting: [
    { k: "gross_t", kind: "dec" },
    { k: "capacity_pct", kind: "dec" },
    { k: "critical", kind: "bool" },
    { k: "critical_reasons", kind: "reasons" },
    { k: "effective_wind_limit_ms", kind: "dec" },
  ],
  radiography: [
    { k: "dose_rate_1m_usv_h", kind: "dec" },
    { k: "computed_barrier_m", kind: "dec" },
    { k: "barrier_verified", kind: "bool" },
  ],
};

export function sectionOf(permit: Permit, type: S["PermitType"]): Sec | null {
  const list = permit.sections as unknown as Sec[];
  return list.find((s) => s.work_type === type) ?? null;
}

export function sectionTypes(permit: Permit): SectionType[] {
  return permit.work_types.filter((x): x is SectionType => x !== "general");
}

function useSectionLabel() {
  const t = useTranslations("permitSections");
  return (type: SectionType, k: string): string => {
    const key = `f.${k}` as "f.max_depth_m";
    return t.has(key) ? t(key) : k;
  };
}

/** Read-only display of one section with its computed values. */
export function SectionView({ permit, type, actions }: { permit: Permit; type: SectionType; actions?: ReactNode }) {
  const t = useTranslations("permitSections");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const label = useSectionLabel();
  const locale = useLocale();
  const { dateTime, date } = useFormatters(permit.project_id);
  const s = sectionOf(permit, type);
  const val = (f: Field, v: unknown): ReactNode => {
    if (v === null || v === undefined || v === "" || (Array.isArray(v) && v.length === 0)) return "—";
    if (f.k === "scaffold_tag_ref") {
      // v1.1 (Phase 4 SF-1): the reference resolved on the scaffold register, with its tag colour.
      const sc = (s as { scaffold?: S["ScaffoldRef"] | null } | null)?.scaffold;
      if (sc)
        return (
          <span className="inline-flex flex-wrap items-center gap-2" data-testid="wah-scaffold">
            <Link href={`/scaffolds/${sc.id}`} className="text-primary hover:underline">
              <bdi className="ltr">{sc.tag}</bdi> · <bdi className="ltr">{sc.scaffold_no}</bdi>
            </Link>
            <TagStatusBadge status={sc.tag_status} />
          </span>
        );
    }
    switch (f.kind) {
      case "bool":
        return <YesNo value={Boolean(v)} yes={tc("yes")} no={tc("no")} />;
      case "dec":
      case "int":
        return <bdi className="ltr tabular-nums">{String(v)}</bdi>;
      case "date":
        return date(String(v));
      case "datetime":
        return dateTime(String(v));
      case "enum":
        return te(`${f.ns}.${String(v) === "n.a." ? "na" : String(v)}` as "egress.ladder");
      case "multi":
        return (v as string[]).map((x) => te(`${f.ns}.${x}` as "egress.ladder")).join(" · ");
      case "extinguishers":
        return (v as S["ExtinguisherInput-Output"][]).map((e) => `${e.count} × ${te(`extinguisherType.${e.type}`)} @ ${e.distance_m} m`).join(" · ");
      case "heat": {
        const h = v as S["CseHeatControls"];
        return `${t("heat.stay", { n: h.stay_time_max_minutes })}${h.forced_cool_air_ventilation ? ` · ${t("heat.coolAir")}` : ""}${h.water_at_entry ? ` · ${t("heat.water")}` : ""}`;
      }
      case "tfd": {
        const x = v as S["TestForDeadInput"];
        return `${dateTime(x.done_at)} · ${x.instrument_tag}${x.live_dead_live ? ` · ${t("tfd.ldl")}` : ""}${x.proving_unit_used ? ` · ${t("tfd.proving")}` : ""}`;
      }
      case "detector": {
        const d = (s as { continuous_monitor?: S["DetectorRef"] | null } | null)?.continuous_monitor;
        return d ? <bdi className="ltr">{d.detector_no}</bdi> : String(v);
      }
      case "appliances":
        return permit.equipment
          .filter((e) => (v as string[]).includes(e.id))
          .map((e) => e.vehicle?.vehicle_no ?? e.equipment_tag?.tag ?? "")
          .join(", ");
      case "wap": {
        const w = permit.waps.find((x) => x.id === v);
        return w ? <bdi className="ltr">{w.wap_no}</bdi> : String(v);
      }
      default:
        return String(v);
    }
  };
  return (
    <Card data-testid="section-card" data-type={type}>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2">
        <CardTitle className="text-base">{te(`permitType.${type}`)}</CardTitle>
        {actions}
      </CardHeader>
      <CardContent>
        {!s ? (
          <p className="text-sm text-warning" data-testid="section-missing">
            {t("missing")}
          </p>
        ) : (
          <div className="flex flex-col gap-4">
            <FieldList>
              {FIELDS[type].map((f) => (
                <FieldItem key={f.k} label={label(type, f.k)}>
                  {val(f, s[f.k])}
                </FieldItem>
              ))}
            </FieldList>
            {COMPUTED[type]?.length ? (
              <div className="rounded-md border bg-surface p-3" data-testid="section-computed">
                <p className="mb-2 text-xs font-medium text-muted-foreground">{t("computed")}</p>
                <FieldList>
                  {COMPUTED[type]!.map((c) => {
                    const v = s[c.k];
                    return (
                      <FieldItem key={c.k} label={label(type, c.k)}>
                        <span data-testid={`computed-${c.k}`}>
                          {v === null || v === undefined
                            ? "—"
                            : c.kind === "bool"
                              ? <YesNo value={Boolean(v)} yes={tc("yes")} no={tc("no")} />
                              : c.kind === "datetime"
                                ? dateTime(String(v))
                                : c.kind === "reasons"
                                  ? (v as S["LiftCriticalReason"][]).map((x) => te(`liftCriticalReason.${x}`)).join(" · ") || "—"
                                  : c.kind === "voltage"
                                    ? te(`voltageClass.${v as S["VoltageClass"]}`)
                                    : <bdi className="ltr tabular-nums">{String(v)}</bdi>}
                        </span>
                      </FieldItem>
                    );
                  })}
                </FieldList>
              </div>
            ) : null}
            {type === "airside_works" ? <AirsideLinks s={s as unknown as S["AirsideSectionRead"]} locale={locale} /> : null}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function AirsideLinks({ s, locale }: { s: S["AirsideSectionRead"]; locale: string }) {
  const t = useTranslations("permitSections");
  const te = useTranslations("enums");
  const { dateTime } = useFormatters();
  void locale;
  return (
    <FieldList>
      <FieldItem label={t("airside.notams")}>
        {s.notams.length ? s.notams.map((n) => `${n.ntm_no} (${n.in_effect_now ? t("airside.inEffect") : t("airside.notInEffect")})`).join(" · ") : "—"}
      </FieldItem>
      <FieldItem label={t("airside.fod")}>{s.fod_check ? `${te(`fodResult.${s.fod_check.result}`)} · ${dateTime(s.fod_check.checked_at)}` : "—"}</FieldItem>
    </FieldList>
  );
}

/* ───────────── editing ───────────── */

function toInput(type: SectionType, s: Sec | null): Sec {
  const out: Sec = { work_type: type };
  for (const f of FIELDS[type]) {
    const v = s?.[f.k];
    if (v !== undefined && v !== null) out[f.k] = v;
  }
  return out;
}

/** Clean an edited section for PUT: drop empty strings, keep booleans / arrays. */
function clean(sec: Sec): Sec {
  const out: Sec = {};
  for (const [k, v] of Object.entries(sec)) {
    if (v === "" || v === undefined) continue;
    out[k] = v;
  }
  return out;
}

/** Edit every section of a Draft permit at once (PUT /sections replaces all). */
export function SectionsEditor({ permit, onDone }: { permit: Permit; onDone: () => void }) {
  const t = useTranslations("permitSections");
  const tc = useTranslations("common");
  const te = useTranslations("enums");
  const refresh = usePtwRefresh();
  const types = sectionTypes(permit);
  const [values, setValues] = useState<Record<string, Sec>>(() => Object.fromEntries(types.map((ty) => [ty, toInput(ty, sectionOf(permit, ty))])));
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    setError(null);
    try {
      const sections = types.map((ty) => clean(values[ty] ?? { work_type: ty })) as unknown as S["SectionsInput"]["sections"];
      const p = await unwrap(api.PUT("/api/v1/permits/{permit_id}/sections", { params: { path: { permit_id: permit.id } }, body: { sections } }));
      await refresh(p);
      toast.success(tc("saved"));
      onDone();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex flex-col gap-4" data-testid="sections-editor">
      {types.map((ty) => (
        <Card key={ty} data-testid="section-form" data-type={ty}>
          <CardHeader>
            <CardTitle className="text-base">{te(`permitType.${ty}`)}</CardTitle>
          </CardHeader>
          <CardContent>
            <SectionForm permit={permit} type={ty} value={values[ty] ?? { work_type: ty }} onChange={(v) => setValues((x) => ({ ...x, [ty]: v }))} />
          </CardContent>
        </Card>
      ))}
      <MutationError error={error} />
      <div className="flex gap-2">
        <Button onClick={() => void save()} disabled={busy} data-testid="save-sections">
          {busy ? tc("saving") : t("save")}
        </Button>
        <Button variant="outline" onClick={onDone}>
          {tc("cancel")}
        </Button>
      </div>
    </div>
  );
}

function SectionForm({ permit, type, value, onChange }: { permit: Permit; type: SectionType; value: Sec; onChange: (v: Sec) => void }) {
  const t = useTranslations("permitSections");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const label = useSectionLabel();
  const detectors = useDetectors(permit.project_id, { status: ["in_service"], page_size: 200 }, { enabled: type === "confined_space" });
  const set = (k: string, v: unknown) => onChange({ ...value, [k]: v });
  const id = (k: string) => `sec-${type}-${k}`;
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {FIELDS[type].map((f) => {
        const v = value[f.k];
        switch (f.kind) {
          case "bool":
            return (
              <CheckboxField key={f.k} id={id(f.k)} label={label(type, f.k)}>
                <Checkbox checked={Boolean(v)} onChange={(e) => set(f.k, e.target.checked)} data-testid={id(f.k)} />
              </CheckboxField>
            );
          case "dec":
            return (
              <FormField key={f.k} id={id(f.k)} label={label(type, f.k)} required={f.req}>
                <DecimalInput value={v === undefined || v === null ? "" : String(v)} onChange={(x) => set(f.k, x)} data-testid={id(f.k)} />
              </FormField>
            );
          case "int":
            return (
              <FormField key={f.k} id={id(f.k)} label={label(type, f.k)} required={f.req}>
                <Input inputMode="numeric" className="ltr" value={v === undefined || v === null ? "" : String(v)} onChange={(e) => set(f.k, e.target.value ? Number(e.target.value.replace(/\D/g, "")) : "")} data-testid={id(f.k)} />
              </FormField>
            );
          case "text":
          case "longtext":
            return (
              <FormField key={f.k} id={id(f.k)} label={label(type, f.k)} required={f.req}>
                {f.kind === "longtext" ? (
                  <Textarea value={String(v ?? "")} onChange={(e) => set(f.k, e.target.value)} />
                ) : (
                  <Input value={String(v ?? "")} onChange={(e) => set(f.k, e.target.value)} maxLength={200} data-testid={id(f.k)} />
                )}
              </FormField>
            );
          case "date":
            return (
              <FormField key={f.k} id={id(f.k)} label={label(type, f.k)} required={f.req}>
                <Input type="date" className="ltr" value={String(v ?? "")} onChange={(e) => set(f.k, e.target.value)} data-testid={id(f.k)} />
              </FormField>
            );
          case "datetime":
            return (
              <FormField key={f.k} id={id(f.k)} label={label(type, f.k)}>
                <DateTimeInput value={String(v ?? "")} onChange={(x) => set(f.k, x)} />
              </FormField>
            );
          case "enum":
            return (
              <FormField key={f.k} id={id(f.k)} label={label(type, f.k)} required={f.req}>
                <Select value={String(v ?? "")} onChange={(e) => set(f.k, e.target.value)} data-testid={id(f.k)}>
                  <option value="">{tc("select")}</option>
                  {f.values.map((x) => (
                    <option key={x} value={x}>
                      {te(`${f.ns}.${x === "n.a." ? "na" : x}` as "egress.ladder")}
                    </option>
                  ))}
                </Select>
              </FormField>
            );
          case "multi":
            return (
              <CheckboxGroup
                key={f.k}
                id={id(f.k)}
                legend={label(type, f.k)}
                required={f.req}
                options={f.values.map((x) => ({ value: x, label: te(`${f.ns}.${x}` as "egress.ladder") }))}
                value={(v as string[] | undefined) ?? []}
                onChange={(x) => set(f.k, x)}
                className="sm:col-span-2"
              />
            );
          case "detector":
            return (
              <FormField key={f.k} id={id(f.k)} label={label(type, f.k)} required>
                <Select value={String(v ?? "")} onChange={(e) => set(f.k, e.target.value)} data-testid={id(f.k)}>
                  <option value="">{tc("select")}</option>
                  {(detectors.data?.items ?? []).map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.detector_no} · {d.make_model}
                    </option>
                  ))}
                </Select>
              </FormField>
            );
          case "appliances":
            return (
              <CheckboxGroup
                key={f.k}
                id={id(f.k)}
                legend={label(type, f.k)}
                required
                hint={permit.equipment.length ? undefined : t("addEquipmentFirst")}
                options={permit.equipment.filter((e) => e.use === "lifting_appliance").map((e) => ({ value: e.id, label: e.vehicle ? `${e.vehicle.vehicle_no} · ${te(`vehicleCategory.${e.vehicle.category}`)}` : `${e.equipment_tag?.tag ?? ""} · ${e.equipment_tag ? te(`equipmentCategory.${e.equipment_tag.category}`) : ""}` }))}
                value={(v as string[] | undefined) ?? []}
                onChange={(x) => set(f.k, x)}
                className="sm:col-span-2"
              />
            );
          case "wap":
            return (
              <FormField key={f.k} id={id(f.k)} label={label(type, f.k)} hint={permit.waps.length ? undefined : t("linkWapFirst")}>
                <Select value={String(v ?? "")} onChange={(e) => set(f.k, e.target.value || null)}>
                  <option value="">{tc("select")}</option>
                  {permit.waps.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.wap_no}
                    </option>
                  ))}
                </Select>
              </FormField>
            );
          case "extinguishers": {
            const list = (v as { type: string; count: number; distance_m: string }[] | undefined) ?? [];
            return (
              <fieldset key={f.k} className="flex flex-col gap-2 rounded-md border p-3 sm:col-span-2" data-testid={id(f.k)}>
                <legend className="px-1 text-sm font-medium">{label(type, f.k)} *</legend>
                {list.map((x, i) => (
                  <div key={i} className="grid gap-2 sm:grid-cols-[1fr_6rem_8rem_auto] sm:items-end">
                    <FormField id={`${id(f.k)}-t-${i}`} label={t("ext.type")}>
                      <Select value={x.type} onChange={(e) => set(f.k, list.map((y, j) => (j === i ? { ...y, type: e.target.value } : y)))}>
                        {EXTINGUISHER_TYPES.map((et) => (
                          <option key={et} value={et}>
                            {te(`extinguisherType.${et}`)}
                          </option>
                        ))}
                      </Select>
                    </FormField>
                    <FormField id={`${id(f.k)}-c-${i}`} label={t("ext.count")}>
                      <Input inputMode="numeric" className="ltr" value={String(x.count)} onChange={(e) => set(f.k, list.map((y, j) => (j === i ? { ...y, count: Number(e.target.value.replace(/\D/g, "") || 0) } : y)))} />
                    </FormField>
                    <FormField id={`${id(f.k)}-d-${i}`} label={t("ext.distance")}>
                      <DecimalInput value={x.distance_m} onChange={(d) => set(f.k, list.map((y, j) => (j === i ? { ...y, distance_m: d } : y)))} data-testid={`${id(f.k)}-d-${i}`} />
                    </FormField>
                    <Button type="button" variant="ghost" onClick={() => set(f.k, list.filter((_, j) => j !== i))}>
                      {tc("remove")}
                    </Button>
                  </div>
                ))}
                <Button type="button" size="sm" variant="outline" className="self-start" onClick={() => set(f.k, [...list, { type: "dcp_abc_6kg", count: 1, distance_m: "" }])} data-testid="add-extinguisher">
                  {t("ext.add")}
                </Button>
              </fieldset>
            );
          }
          case "heat": {
            const h = (v as S["CseHeatControls"] | undefined) ?? null;
            return (
              <fieldset key={f.k} className="flex flex-col gap-2 rounded-md border p-3 sm:col-span-2">
                <legend className="px-1 text-sm font-medium">{label(type, f.k)}</legend>
                <CheckboxField id={`${id(f.k)}-on`} label={t("heat.needed")}>
                  <Checkbox checked={Boolean(h)} onChange={(e) => set(f.k, e.target.checked ? { forced_cool_air_ventilation: true, stay_time_max_minutes: 30, water_at_entry: true } : null)} />
                </CheckboxField>
                {h ? (
                  <div className="grid gap-2 sm:grid-cols-3">
                    <CheckboxField id={`${id(f.k)}-air`} label={t("heat.coolAir")}>
                      <Checkbox checked={h.forced_cool_air_ventilation} onChange={(e) => set(f.k, { ...h, forced_cool_air_ventilation: e.target.checked })} />
                    </CheckboxField>
                    <FormField id={`${id(f.k)}-stay`} label={t("heat.stayLabel")}>
                      <Input inputMode="numeric" className="ltr" value={String(h.stay_time_max_minutes)} onChange={(e) => set(f.k, { ...h, stay_time_max_minutes: Number(e.target.value.replace(/\D/g, "") || 0) })} />
                    </FormField>
                    <CheckboxField id={`${id(f.k)}-water`} label={t("heat.water")}>
                      <Checkbox checked={h.water_at_entry} onChange={(e) => set(f.k, { ...h, water_at_entry: e.target.checked })} />
                    </CheckboxField>
                  </div>
                ) : null}
              </fieldset>
            );
          }
          case "tfd": {
            const x = (v as S["TestForDeadInput"] | undefined) ?? null;
            return (
              <fieldset key={f.k} className="flex flex-col gap-2 rounded-md border p-3 sm:col-span-2" data-testid={id(f.k)}>
                <legend className="px-1 text-sm font-medium">{label(type, f.k)}</legend>
                <CheckboxField id={`${id(f.k)}-on`} label={t("tfd.done")}>
                  <Checkbox
                    checked={Boolean(x)}
                    onChange={(e) => set(f.k, e.target.checked ? { done_at: new Date().toISOString(), by_user_id: me.id, instrument_tag: "", proving_unit_used: true, live_dead_live: true } : null)}
                    data-testid={`${id(f.k)}-on`}
                  />
                </CheckboxField>
                {x ? (
                  <div className="grid gap-2 sm:grid-cols-2">
                    <FormField id={`${id(f.k)}-at`} label={t("tfd.at")}>
                      <DateTimeInput value={x.done_at} onChange={(d) => set(f.k, { ...x, done_at: d })} />
                    </FormField>
                    <FormField id={`${id(f.k)}-tag`} label={t("tfd.instrument")}>
                      <Input className="ltr" value={x.instrument_tag} onChange={(e) => set(f.k, { ...x, instrument_tag: e.target.value })} data-testid={`${id(f.k)}-tag`} />
                    </FormField>
                    <CheckboxField id={`${id(f.k)}-pu`} label={t("tfd.proving")}>
                      <Checkbox checked={x.proving_unit_used} onChange={(e) => set(f.k, { ...x, proving_unit_used: e.target.checked })} />
                    </CheckboxField>
                    <CheckboxField id={`${id(f.k)}-ldl`} label={t("tfd.ldl")}>
                      <Checkbox checked={x.live_dead_live} onChange={(e) => set(f.k, { ...x, live_dead_live: e.target.checked })} />
                    </CheckboxField>
                  </div>
                ) : null}
              </fieldset>
            );
          }
          default:
            return null;
        }
      })}
    </div>
  );
}

export function EditSectionsButton({ onClick }: { onClick: () => void }) {
  const t = useTranslations("permitSections");
  return (
    <Button size="sm" variant="outline" onClick={onClick} data-testid="edit-sections">
      <Pencil aria-hidden />
      {t("edit")}
    </Button>
  );
}
