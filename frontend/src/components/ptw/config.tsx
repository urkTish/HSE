"use client";
import { useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { CheckboxGroup } from "@/components/common/checkbox-group";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { CheckboxField, FormField, FormSection } from "@/components/common/form-field";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { useProjectOptions } from "@/components/common/pickers";
import { ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Code, StepDialog } from "@/components/access/common";
import { HookEditor } from "@/components/access/setup";
import { useMeData } from "@/components/shell/me-context";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { pk, useAppointments, usePermitTypes, usePtwSettings, useRiskMatrix, useSimopsRules, useZoneAdjacency, useZonePtwProfile } from "@/lib/api/ptw";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { canWrite } from "@/lib/permissions";
import { HAZARDOUS_AREA_CLASSES, PERMIT_TYPES, PTW_EXPOSURES, PTW_HAZARDS, SIMOPS_CONDITIONS, SIMOPS_RESULTS, SIMOPS_TYPE_SELECTORS, VERTICAL_RELATIONS } from "@/lib/ptw-enums";
import { useRefLists } from "@/lib/reference";
import { useFormatters } from "@/lib/use-formatters";
import { cn } from "@/lib/utils";
import { DecimalInput, RiskBandBadge, SetupSubNav, SimopsResultBadge, riskBandCellClass, userLabel } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];

function SetupHeader({ title, description }: { title: string; description?: string }) {
  const t = useTranslations("ptwSetup");
  return (
    <>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <SetupSubNav />
      <h2 className="mb-1 text-lg font-semibold">{title}</h2>
      {description ? <p className="mb-4 text-sm text-muted-foreground">{description}</p> : null}
    </>
  );
}

/* ───────────────────────── Permit types ───────────────────────── */

export function PermitTypesPage() {
  return <ProjectGate>{(p) => <PermitTypes project={p} />}</ProjectGate>;
}

function PermitTypes({ project }: { project: Project }) {
  const t = useTranslations("ptwSetup");
  const te = useTranslations("enums");
  const me = useMeData();
  const name = useLocalizedName();
  const q = usePermitTypes(project.id);
  const [edit, setEdit] = useState<S["PermitTypeConfigRead"] | null>(null);
  const editable = canWrite(me, "ptw_settings.edit", project.id);
  return (
    <div>
      <SetupHeader title={t("types.title")} description={t("types.subtitle")} />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2" data-testid="permit-types">
          {(q.data?.items ?? []).map((c) => (
            <Card key={c.type} data-testid="permit-type-card" data-type={c.type}>
              <CardHeader className="flex flex-row items-start justify-between gap-2">
                <CardTitle className="text-base">
                  <bdi className="ltr me-2 rounded bg-primary/10 px-1.5 py-0.5 text-sm rtl:me-0 rtl:ms-2">{c.ref_letter}</bdi>
                  {name(c.label_en, c.label_ar)}
                </CardTitle>
                {editable ? (
                  <Button size="sm" variant="outline" onClick={() => setEdit(c)} data-testid="edit-permit-type">
                    <Pencil aria-hidden />
                    {t("edit")}
                  </Button>
                ) : null}
              </CardHeader>
              <CardContent>
                <FieldList className="sm:grid-cols-2 lg:grid-cols-2">
                  <FieldItem label={t("types.maxDuration")}>
                    {t("types.days", { n: c.max_duration_days })}
                    {c.max_duration_days_critical ? ` · ${t("types.critical", { n: c.max_duration_days_critical })}` : ""}
                  </FieldItem>
                  <FieldItem label={t("types.maxShift")}>{t("types.hours", { n: c.max_shift_hours })}</FieldItem>
                  <FieldItem label={t("types.revalidation")}>{te(`revalidationRule.${c.revalidation}`)}</FieldItem>
                  <FieldItem label={t("types.gasRule")}>{name(c.gas_test_rule_en, c.gas_test_rule_ar)}</FieldItem>
                  <FieldItem label={t("types.hseRule")} wide>
                    {name(c.hse_review_rule_en, c.hse_review_rule_ar)}
                  </FieldItem>
                  <FieldItem label={t("types.roles")} wide>
                    {c.mandatory_crew_roles.length ? c.mandatory_crew_roles.map((r) => te(`ptwCrewRole.${r}`)).join(" · ") : "—"}
                  </FieldItem>
                  <FieldItem label={t("types.documents")} wide>
                    {c.mandatory_documents.length ? c.mandatory_documents.map((r) => te(`documentType.${r}`)).join(" · ") : "—"}
                  </FieldItem>
                  <FieldItem label={t("types.checklists")}>{t("types.checklistCounts", { pre: c.pre_issue_checklist.length, closure: c.closure_checklist.length })}</FieldItem>
                  <FieldItem label={t("types.hazards")}>{c.mandatory_hazards.length ? c.mandatory_hazards.map((h) => te(`hazard.${h}`)).join(" · ") : "—"}</FieldItem>
                  <FieldItem label={t("types.hooks")} wide>
                    <HookSummary byRole={c.hook_requirements_by_crew_role} byEquipment={c.hook_requirements_by_equipment} />
                  </FieldItem>
                </FieldList>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      {edit ? <PermitTypeDialog project={project} config={edit} onClose={() => setEdit(null)} /> : null}
    </div>
  );
}

function HookSummary({ byRole, byEquipment }: { byRole: Record<string, S["HookRequirementRead"][]>; byEquipment: Record<string, S["HookRequirementRead"][]> }) {
  const te = useTranslations("enums");
  const rows = [
    ...Object.entries(byRole).map(([k, v]) => [te(`ptwCrewRole.${k as S["PtwCrewRole"]}`), v] as const),
    ...Object.entries(byEquipment).map(([k, v]) => [te(`equipmentCategory.${k as S["EquipmentCategory"]}`), v] as const),
  ].filter(([, v]) => v.length);
  if (!rows.length) return <>—</>;
  return (
    <ul className="flex flex-col gap-0.5 text-xs">
      {rows.map(([label, v]) => (
        <li key={label}>
          {label}:{" "}
          {v.map((h) => (
            <Code key={`${h.kind}-${h.code}`} className="me-1">
              {h.code}
            </Code>
          ))}
        </li>
      ))}
    </ul>
  );
}

function PermitTypeDialog({ project, config, onClose }: { project: Project; config: S["PermitTypeConfigRead"]; onClose: () => void }) {
  const t = useTranslations("ptwSetup");
  const te = useTranslations("enums");
  const qc = useQueryClient();
  const refs = useRefLists();
  const name = useLocalizedName();
  const [pre, setPre] = useState<string[]>(config.pre_issue_checklist);
  const [closure, setClosure] = useState<string[]>(config.closure_checklist);
  const [hazards, setHazards] = useState<S["Hazard"][]>(config.mandatory_hazards);
  const [hooks, setHooks] = useState<Record<string, S["HookRequirement"][]>>(config.hook_requirements_by_crew_role);
  const forType = (list: "ptw_pre_issue_checklist" | "ptw_closure_checklist") =>
    refs.items(list).filter((i) => !i.permit_types?.length || i.permit_types.includes(config.type)).map((i) => ({ value: i.code, label: `${i.code} — ${name(i.label_en, i.label_ar)}` }));
  async function save() {
    const body: S["PermitTypeConfigUpdate"] = {
      pre_issue_checklist: pre as S["PreIssueItem"][],
      closure_checklist: closure as S["ClosureItem"][],
      mandatory_hazards: hazards,
      hook_requirements_by_crew_role: hooks,
    };
    await unwrap(api.PATCH("/api/v1/projects/{project_id}/permit-types/{permit_type}", { params: { path: { project_id: project.id, permit_type: config.type } }, body }));
    await qc.invalidateQueries({ queryKey: pk.permitTypes(project.id) });
    toast.success(t("saved"));
  }
  return (
    <StepDialog title={t("types.editTitle", { type: te(`permitType.${config.type}`) })} description={t("types.editHint")} confirmLabel={t("save")} onConfirm={save} onClose={onClose} wide testId="save-permit-type">
      <CheckboxGroup id="pt-pre" legend={t("types.preIssue")} options={forType("ptw_pre_issue_checklist")} value={pre} onChange={setPre} columns={1} />
      <CheckboxGroup id="pt-closure" legend={t("types.closure")} options={forType("ptw_closure_checklist")} value={closure} onChange={setClosure} columns={1} />
      <MultiSelect id="pt-hazards" label={t("types.hazards")} options={PTW_HAZARDS.map((h) => ({ value: h, label: te(`hazard.${h}`) }))} value={hazards} onChange={setHazards} />
      {config.mandatory_crew_roles.length ? (
        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium">{t("types.hooksByRole")}</p>
          {config.mandatory_crew_roles.map((r) => (
            <div key={r} className="rounded-md border p-2">
              <p className="mb-1 text-sm">{te(`ptwCrewRole.${r}`)}</p>
              <HookEditor id={`pt-hook-${r}`} value={hooks[r] ?? []} onChange={(v) => setHooks((h) => ({ ...h, [r]: v }))} />
            </div>
          ))}
        </div>
      ) : null}
    </StepDialog>
  );
}

/* ───────────────────────── Zone PTW profiles ───────────────────────── */

export function ZonePtwProfilesPage() {
  return <ProjectGate>{(p) => <ZonePtwProfiles project={p} />}</ProjectGate>;
}

function ZonePtwProfiles({ project }: { project: Project }) {
  const t = useTranslations("ptwSetup");
  const opts = useProjectOptions(project.id);
  const [zone, setZone] = useState<string>("");
  const zid = zone || opts.zones[0]?.value || "";
  return (
    <div>
      <SetupHeader title={t("zones.title")} description={t("zones.subtitle")} />
      {opts.isLoading ? (
        <LoadingState />
      ) : !opts.zones.length ? (
        <EmptyState />
      ) : (
        <div className="grid gap-4 md:grid-cols-[16rem_1fr]">
          <nav aria-label={t("zones.pick")} className="flex flex-col gap-1" data-testid="zone-list">
            {opts.zones.map((z) => (
              <button
                key={z.value}
                type="button"
                onClick={() => setZone(z.value)}
                aria-current={zid === z.value ? "true" : undefined}
                className={cn("min-h-touch rounded-md px-3 text-start text-sm hover:bg-muted", zid === z.value && "bg-primary/10 font-semibold")}
                data-testid="zone-item"
              >
                {z.label}
              </button>
            ))}
          </nav>
          {zid ? <ZonePtwProfileCard key={zid} project={project} zoneId={zid} /> : null}
        </div>
      )}
    </div>
  );
}

function ZonePtwProfileCard({ project, zoneId }: { project: Project; zoneId: string }) {
  const t = useTranslations("ptwSetup");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const locale = useLocale();
  const qc = useQueryClient();
  const { dateTime } = useFormatters(project.id);
  const q = useZonePtwProfile(zoneId);
  const authorities = useAppointments(project.id, { function: ["area_authority"], status: ["active"], page_size: 200 });
  const [edits, setEdits] = useState<S["ZonePtwProfileUpdate"]>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const editable = canWrite(me, "ptw_zone_profile.edit", project.id);
  const authOptions = useMemo(() => {
    const m = new Map<string, string>();
    for (const a of authorities.data?.items ?? []) if (a.holder_user) m.set(a.holder_user.id, userLabel(a.holder_user, locale));
    return [...m].map(([value, label]) => ({ value, label }));
  }, [authorities.data, locale]);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const p = q.data;
  const d = { ...p, ...Object.fromEntries(Object.entries(edits).filter(([, v]) => v !== undefined)) } as S["ZonePtwProfileRead"];
  const set = <K extends keyof S["ZonePtwProfileUpdate"]>(k: K, v: S["ZonePtwProfileUpdate"][K]) => setEdits((e) => ({ ...e, [k]: v }));
  async function save() {
    setBusy(true);
    setError(null);
    try {
      const next = await unwrap(api.PATCH("/api/v1/zones/{zone_id}/ptw-profile", { params: { path: { zone_id: zoneId } }, body: edits }));
      qc.setQueryData(pk.zonePtw(zoneId), next);
      setEdits({});
      toast.success(t("saved"));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card data-testid="zone-ptw-profile">
      <CardHeader>
        <CardTitle className="text-base">
          <Code>{p.zone.code}</Code> {locale === "ar" ? p.zone.name_ar : p.zone.name_en}
        </CardTitle>
        {p.in_movement_area ? <p className="text-xs text-muted-foreground">{t("zones.movementArea")}</p> : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {!editable ? <Alert tone="info">{t("readOnly")}</Alert> : null}
        <div className="grid gap-3 sm:grid-cols-2">
          <CheckboxField id="zp-all" label={t("zones.permitRequiredAll")}>
            <Checkbox disabled={!editable} checked={d.permit_required_all_work} onChange={(e) => set("permit_required_all_work", e.target.checked)} data-testid="zp-permit-required" />
          </CheckboxField>
          <CheckboxField id="zp-gas" label={t("zones.gasTestZone")}>
            <Checkbox disabled={!editable} checked={d.gas_test_zone} onChange={(e) => set("gas_test_zone", e.target.checked)} data-testid="zp-gas-zone" />
          </CheckboxField>
          <CheckboxField id="zp-fire" label={t("zones.fireProtection")}>
            <Checkbox disabled={!editable} checked={d.fire_protection_present} onChange={(e) => set("fire_protection_present", e.target.checked)} />
          </CheckboxField>
          <FormField id="zp-class" label={t("zones.hazardousClass")}>
            <Select disabled={!editable} value={d.hazardous_area_class} onChange={(e) => set("hazardous_area_class", e.target.value as S["HazardousAreaClass"])}>
              {HAZARDOUS_AREA_CLASSES.map((x) => (
                <option key={x} value={x}>
                  {te(`hazardousAreaClass.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="zp-note" label={t("zones.hazardousNote")} required={d.hazardous_area_class !== "none"}>
            <Input disabled={!editable} maxLength={200} value={d.hazardous_area_note ?? ""} onChange={(e) => set("hazardous_area_note", e.target.value || null)} />
          </FormField>
          <FormField id="zp-exposure" label={t("zones.exposure")}>
            <Select disabled={!editable} value={d.default_exposure} onChange={(e) => set("default_exposure", e.target.value as S["Exposure"])}>
              {PTW_EXPOSURES.map((x) => (
                <option key={x} value={x}>
                  {te(`exposure.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="zp-datum" label={t("zones.levelDatum")}>
            <Input disabled={!editable} maxLength={100} value={d.level_datum_note ?? ""} onChange={(e) => set("level_datum_note", e.target.value || null)} />
          </FormField>
          {editable ? (
            <MultiSelect
              id="zp-auth"
              label={t("zones.defaultAuthorities")}
              options={authOptions}
              value={d.default_area_authority_ids}
              onChange={(v) => set("default_area_authority_ids", v)}
            />
          ) : (
            <FieldItem label={t("zones.defaultAuthorities")}>{p.default_area_authorities.map((u) => userLabel(u, locale)).join(" · ") || "—"}</FieldItem>
          )}
        </div>
        {p.updated_at ? <p className="text-xs text-muted-foreground">{t("lastUpdated", { at: dateTime(p.updated_at), by: userLabel(p.updated_by, locale) })}</p> : null}
        <MutationError error={error} />
        {editable ? (
          <div className="flex gap-2">
            <Button onClick={() => void save()} disabled={busy || !Object.keys(edits).length} data-testid="save-zone-profile">
              {busy ? tc("saving") : t("save")}
            </Button>
            {Object.keys(edits).length ? (
              <Button variant="outline" onClick={() => setEdits({})}>
                {tc("cancel")}
              </Button>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

/* ───────────────────────── Zone adjacency ───────────────────────── */

export function ZoneAdjacencyPage() {
  return <ProjectGate>{(p) => <ZoneAdjacency project={p} />}</ProjectGate>;
}

function ZoneAdjacency({ project }: { project: Project }) {
  const t = useTranslations("ptwSetup");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const qc = useQueryClient();
  const q = useZoneAdjacency(project.id);
  const [dialog, setDialog] = useState<S["ZoneAdjacencyRead"] | "new" | null>(null);
  const [del, setDel] = useState<S["ZoneAdjacencyRead"] | null>(null);
  const editable = canWrite(me, "ptw_zone_profile.edit", project.id);
  const items = q.data ?? [];
  return (
    <div>
      <SetupHeader title={t("adjacency.title")} description={t("adjacency.subtitle")} />
      {editable ? (
        <Button className="mb-4" onClick={() => setDialog("new")} data-testid="new-adjacency">
          <Plus aria-hidden />
          {t("adjacency.new")}
        </Button>
      ) : null}
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <Table data-testid="adjacency-table">
          <THead>
            <TR>
              <TH>{t("adjacency.zoneA")}</TH>
              <TH>{t("adjacency.zoneB")}</TH>
              <TH>{t("adjacency.distance")}</TH>
              <TH>{t("adjacency.vertical")}</TH>
              {editable ? <TH>{tc("actions")}</TH> : null}
            </TR>
          </THead>
          <TBody>
            {items.map((a) => (
              <TR key={a.id} data-testid="adjacency-row">
                <TD label={t("adjacency.zoneA")}>
                  <Code>{a.zone_a.code}</Code>
                </TD>
                <TD label={t("adjacency.zoneB")}>
                  <Code>{a.zone_b.code}</Code>
                </TD>
                <TD label={t("adjacency.distance")}>
                  <bdi className="ltr tabular-nums">{a.distance_m} m</bdi>
                </TD>
                <TD label={t("adjacency.vertical")}>{te(`verticalRelation.${a.vertical_relation}`)}</TD>
                {editable ? (
                  <TD label={tc("actions")}>
                    <span className="flex gap-1">
                      <Button size="sm" variant="ghost" onClick={() => setDialog(a)} aria-label={tc("edit")}>
                        <Pencil aria-hidden />
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setDel(a)} aria-label={tc("delete")}>
                        <Trash2 aria-hidden />
                      </Button>
                    </span>
                  </TD>
                ) : null}
              </TR>
            ))}
          </TBody>
        </Table>
      ) : (
        <EmptyState />
      )}
      {dialog ? <AdjacencyDialog project={project} item={dialog === "new" ? null : dialog} onClose={() => setDialog(null)} /> : null}
      {del ? (
        <StepDialog
          title={t("adjacency.deleteTitle")}
          description={`${del.zone_a.code} ↔ ${del.zone_b.code}`}
          confirmLabel={tc("delete")}
          destructive
          onClose={() => setDel(null)}
          onConfirm={async () => {
            await unwrap(api.DELETE("/api/v1/zone-adjacency/{adjacency_id}", { params: { path: { adjacency_id: del.id } } }));
            await qc.invalidateQueries({ queryKey: pk.adjacency(project.id) });
          }}
        />
      ) : null}
    </div>
  );
}

function AdjacencyDialog({ project, item, onClose }: { project: Project; item: S["ZoneAdjacencyRead"] | null; onClose: () => void }) {
  const t = useTranslations("ptwSetup");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const opts = useProjectOptions(project.id);
  const [a, setA] = useState(item?.zone_a.id ?? "");
  const [b, setB] = useState(item?.zone_b.id ?? "");
  const [dist, setDist] = useState(item?.distance_m ?? "");
  const [rel, setRel] = useState<S["VerticalRelation"]>(item?.vertical_relation ?? "none");
  async function save() {
    if (item) await unwrap(api.PATCH("/api/v1/zone-adjacency/{adjacency_id}", { params: { path: { adjacency_id: item.id } }, body: { distance_m: dist, vertical_relation: rel } }));
    else await unwrap(api.POST("/api/v1/projects/{project_id}/zone-adjacency", { params: { path: { project_id: project.id } }, body: { zone_a_id: a, zone_b_id: b, distance_m: dist, vertical_relation: rel } }));
    await qc.invalidateQueries({ queryKey: pk.adjacency(project.id) });
    toast.success(t("saved"));
  }
  const zoneSelect = (id: string, v: string, on: (v: string) => void) => (
    <Select id={id} value={v} disabled={Boolean(item)} onChange={(e) => on(e.target.value)}>
      <option value="">{tc("select")}</option>
      {opts.zones.map((z) => (
        <option key={z.value} value={z.value}>
          {z.label}
        </option>
      ))}
    </Select>
  );
  return (
    <StepDialog title={item ? t("adjacency.edit") : t("adjacency.new")} confirmLabel={t("save")} onConfirm={save} onClose={onClose} disabled={!a || !b || a === b || !dist} testId="save-adjacency">
      <FormField id="adj-a" label={t("adjacency.zoneA")} required>
        {zoneSelect("adj-a", a, setA)}
      </FormField>
      <FormField id="adj-b" label={t("adjacency.zoneB")} required>
        {zoneSelect("adj-b", b, setB)}
      </FormField>
      <FormField id="adj-dist" label={t("adjacency.distanceM")} required hint={t("adjacency.distanceHint")}>
        <DecimalInput value={dist} onChange={setDist} data-testid="adj-distance" />
      </FormField>
      <FormField id="adj-rel" label={t("adjacency.vertical")}>
        <Select value={rel} onChange={(e) => setRel(e.target.value as S["VerticalRelation"])}>
          {VERTICAL_RELATIONS.map((x) => (
            <option key={x} value={x}>
              {te(`verticalRelation.${x}`)}
            </option>
          ))}
        </Select>
      </FormField>
    </StepDialog>
  );
}

/* ───────────────────────── SIMOPS rules ───────────────────────── */

export function SimopsRulesPage() {
  return <ProjectGate>{(p) => <SimopsRules project={p} />}</ProjectGate>;
}

function SimopsRules({ project }: { project: Project }) {
  const t = useTranslations("ptwSetup");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const qc = useQueryClient();
  const name = useLocalizedName();
  const q = useSimopsRules(project.id);
  const [dialog, setDialog] = useState<S["SimopsRuleRead"] | "new" | null>(null);
  const [del, setDel] = useState<S["SimopsRuleRead"] | null>(null);
  const editable = canWrite(me, "ptw_settings.edit", project.id);
  const items = q.data?.items ?? [];
  return (
    <div>
      <SetupHeader title={t("simops.title")} description={t("simops.subtitle")} />
      {editable ? (
        <Button className="mb-4" onClick={() => setDialog("new")} data-testid="new-simops-rule">
          <Plus aria-hidden />
          {t("simops.new")}
        </Button>
      ) : null}
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <Table data-testid="simops-rules-table">
          <THead>
            <TR>
              <TH>{t("simops.code")}</TH>
              <TH>{t("simops.typeA")}</TH>
              <TH>{t("simops.typeB")}</TH>
              <TH>{t("simops.condition")}</TH>
              <TH>{t("simops.result")}</TH>
              <TH>{t("simops.controls")}</TH>
              {editable ? <TH>{tc("actions")}</TH> : null}
            </TR>
          </THead>
          <TBody>
            {items.map((r) => (
              <TR key={r.id} data-testid="simops-rule-row" data-code={r.rule_code} className={r.active ? undefined : "opacity-60"}>
                <TD label={t("simops.code")}>
                  <Code>{r.rule_code}</Code>
                  {r.is_default ? <span className="ms-1 text-xs text-muted-foreground">{t("simops.default")}</span> : null}
                  {!r.active ? <span className="ms-1 text-xs text-muted-foreground">{t("simops.inactive")}</span> : null}
                </TD>
                <TD label={t("simops.typeA")}>{te(`simopsType.${r.type_a}`)}</TD>
                <TD label={t("simops.typeB")}>{te(`simopsType.${r.type_b}`)}</TD>
                <TD label={t("simops.condition")}>
                  {name(r.condition_en, r.condition_ar)}
                  {r.threshold_m ? <bdi className="ltr ms-1 tabular-nums rtl:ms-0 rtl:me-1">({r.threshold_m} m)</bdi> : null}
                </TD>
                <TD label={t("simops.result")}>
                  <SimopsResultBadge result={r.result} />
                </TD>
                <TD label={t("simops.controls")}>
                  <span className="text-xs">{name(r.required_controls_en, r.required_controls_ar) || "—"}</span>
                </TD>
                {editable ? (
                  <TD label={tc("actions")}>
                    <span className="flex gap-1">
                      <Button size="sm" variant="ghost" onClick={() => setDialog(r)} aria-label={tc("edit")} data-testid="edit-simops-rule">
                        <Pencil aria-hidden />
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setDel(r)} aria-label={tc("delete")} data-testid="delete-simops-rule">
                        <Trash2 aria-hidden />
                      </Button>
                    </span>
                  </TD>
                ) : null}
              </TR>
            ))}
          </TBody>
        </Table>
      ) : (
        <EmptyState />
      )}
      {dialog ? <SimopsRuleDialog project={project} rule={dialog === "new" ? null : dialog} onClose={() => setDialog(null)} /> : null}
      {del ? (
        <StepDialog
          title={t("simops.deleteTitle", { code: del.rule_code })}
          description={del.is_default ? t("simops.deleteDefault") : undefined}
          confirmLabel={tc("delete")}
          destructive
          onClose={() => setDel(null)}
          onConfirm={async () => {
            await unwrap(api.DELETE("/api/v1/simops-rules/{rule_id}", { params: { path: { rule_id: del.id } } }));
            await qc.invalidateQueries({ queryKey: pk.simopsRules(project.id) });
          }}
        />
      ) : null}
    </div>
  );
}

function SimopsRuleDialog({ project, rule, onClose }: { project: Project; rule: S["SimopsRuleRead"] | null; onClose: () => void }) {
  const t = useTranslations("ptwSetup");
  const te = useTranslations("enums");
  const qc = useQueryClient();
  const [a, setA] = useState<S["SimopsTypeSelector"]>(rule?.type_a ?? "hot_work");
  const [b, setB] = useState<S["SimopsTypeSelector"]>(rule?.type_b ?? "any");
  const [cond, setCond] = useState<S["SimopsCondition"]>(rule?.condition ?? "within_threshold");
  const [th, setTh] = useState(rule?.threshold_m ?? "");
  const [res, setRes] = useState<S["SimopsResult"]>(rule?.result ?? "conditional");
  const [en, setEn] = useState(rule?.required_controls_en ?? "");
  const [ar, setAr] = useState(rule?.required_controls_ar ?? "");
  const [active, setActive] = useState(rule?.active ?? true);
  async function save() {
    if (rule)
      await unwrap(
        api.PATCH("/api/v1/simops-rules/{rule_id}", {
          params: { path: { rule_id: rule.id } },
          body: { threshold_m: th || null, result: res, required_controls_en: en || null, required_controls_ar: ar || null, active },
        }),
      );
    else
      await unwrap(
        api.POST("/api/v1/projects/{project_id}/simops-rules", {
          params: { path: { project_id: project.id } },
          body: { type_a: a, type_b: b, condition: cond, threshold_m: th || null, result: res, required_controls_en: en || null, required_controls_ar: ar || null },
        }),
      );
    await qc.invalidateQueries({ queryKey: pk.simopsRules(project.id) });
    toast.success(t("saved"));
  }
  const sel = <V extends string>(id: string, v: V, on: (v: V) => void, values: readonly V[], ns: "simopsType" | "simopsCondition" | "simopsResult", disabled?: boolean) => (
    <Select id={id} value={v} disabled={disabled} onChange={(e) => on(e.target.value as V)}>
      {values.map((x) => (
        <option key={x} value={x}>
          {te(`${ns}.${x}` as "simopsResult.allowed")}
        </option>
      ))}
    </Select>
  );
  return (
    <StepDialog title={rule ? t("simops.editTitle", { code: rule.rule_code }) : t("simops.new")} description={t("simops.tightenHint")} confirmLabel={t("save")} onConfirm={save} onClose={onClose} wide testId="save-simops-rule">
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="sr-a" label={t("simops.typeA")}>
          {sel("sr-a", a, setA, SIMOPS_TYPE_SELECTORS, "simopsType", Boolean(rule))}
        </FormField>
        <FormField id="sr-b" label={t("simops.typeB")}>
          {sel("sr-b", b, setB, SIMOPS_TYPE_SELECTORS, "simopsType", Boolean(rule))}
        </FormField>
        <FormField id="sr-cond" label={t("simops.condition")}>
          {sel("sr-cond", cond, setCond, SIMOPS_CONDITIONS, "simopsCondition", Boolean(rule))}
        </FormField>
        <FormField id="sr-th" label={t("simops.thresholdM")}>
          <DecimalInput value={th} onChange={setTh} data-testid="sr-threshold" />
        </FormField>
        <FormField id="sr-res" label={t("simops.result")}>
          {sel("sr-res", res, setRes, SIMOPS_RESULTS, "simopsResult")}
        </FormField>
        {rule ? (
          <CheckboxField id="sr-active" label={t("simops.active")}>
            <Checkbox checked={active} onChange={(e) => setActive(e.target.checked)} />
          </CheckboxField>
        ) : null}
      </div>
      <FormField id="sr-en" label={t("simops.controlsEn")}>
        <Textarea value={en} onChange={(e) => setEn(e.target.value)} maxLength={500} />
      </FormField>
      <FormField id="sr-ar" label={t("simops.controlsAr")}>
        <Textarea dir="rtl" value={ar} onChange={(e) => setAr(e.target.value)} maxLength={500} />
      </FormField>
    </StepDialog>
  );
}

/* ───────────────────────── Risk matrix ───────────────────────── */

export function RiskMatrixPage() {
  const t = useTranslations("ptwSetup");
  return (
    <div>
      <SetupHeader title={t("matrix.title")} description={t("matrix.subtitle")} />
      <RiskMatrixView />
    </div>
  );
}

/**
 * The 5×5 matrix read from the server (likelihood rows 5→1, severity columns 1→5) with the band legend.
 * Each cell carries its score and band word (colour is never alone; high and extreme also differ in fill
 * weight). The axes are named in the page language and the grid mirrors in Arabic (severity grows to the
 * left), like the rest of the RTL layout. Highlighted cells (JSA lines) get a thick ring and a marker.
 */
export function RiskMatrixView({ highlight, compact }: { highlight?: { l: number; s: number }[]; compact?: boolean }) {
  const t = useTranslations("ptwSetup");
  const td = useTranslations("ptwDesign");
  const te = useTranslations("enums");
  const name = useLocalizedName();
  const q = useRiskMatrix();
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const cell = (l: number, s: number) => q.data.cells.find((c) => c.likelihood === l && c.severity === s);
  const cellCls = compact ? "h-11 w-12" : "h-14 w-16";
  return (
    <div className="flex flex-col gap-4">
      <div className="overflow-x-auto">
        <table className="border-separate border-spacing-1 text-sm" data-testid="risk-matrix">
          <caption className="sr-only">{t("matrix.title")}</caption>
          <thead>
            <tr>
              <th scope="col" rowSpan={2} className="p-1 align-bottom text-[11px] leading-tight font-medium text-muted-foreground">
                <span className="block">{td("likelihood")} ↓</span>
              </th>
              <th scope="colgroup" colSpan={5} className="p-1 text-center text-[11px] font-medium text-muted-foreground">
                {td("severity")} <span aria-hidden className="inline-block rtl:-scale-x-100">→</span>
              </th>
            </tr>
            <tr>
              {[1, 2, 3, 4, 5].map((s) => (
                <th key={s} scope="col" className="p-1 text-xs font-semibold">
                  <bdi className="ltr">S{s}</bdi>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[5, 4, 3, 2, 1].map((l) => (
              <tr key={l}>
                <th scope="row" className="p-1 text-xs font-semibold">
                  <bdi className="ltr">L{l}</bdi>
                </th>
                {[1, 2, 3, 4, 5].map((s) => {
                  const c = cell(l, s);
                  const hit = highlight?.some((h) => h.l === l && h.s === s);
                  return (
                    <td
                      key={s}
                      className={cn("relative rounded border text-center align-middle", cellCls, c ? riskBandCellClass(c.band) : "", hit && "outline-[3px] outline-offset-1 outline-foreground outline-solid")}
                      data-band={c?.band}
                      data-score={c?.score}
                      data-hit={hit ? "true" : undefined}
                      title={c ? `L${l} × S${s} = ${c.score} · ${te(`riskBand.${c.band}`)}` : undefined}
                    >
                      <span className={cn("block leading-none font-bold tabular-nums", compact ? "text-sm" : "text-base")}>{c?.score ?? ""}</span>
                      {c ? <span className={cn("block truncate px-0.5 leading-tight font-medium", compact ? "text-[9px]" : "text-[10px]")}>{te(`riskBand.${c.band}`)}</span> : null}
                      {hit ? (
                        <span aria-hidden className="absolute -top-1.5 -end-1.5 size-3 rounded-full border-2 border-surface bg-foreground" />
                      ) : null}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className={cn("grid gap-2", !compact && "sm:grid-cols-2")} data-testid="risk-bands">
        {q.data.bands.map((b) => (
          <li key={b.band} className="flex items-start gap-2 rounded-md border p-2 text-sm">
            <RiskBandBadge band={b.band} />
            <span>
              <bdi className="ltr tabular-nums">
                {b.min_score}–{b.max_score}
              </bdi>{" "}
              · {name(b.acceptance_en, b.acceptance_ar)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ───────────────────────── PTW settings ───────────────────────── */

type Settings = S["PtwSettingsRead"];
type Upd = S["PtwSettingsUpdate"];
type IntKey = { [K in keyof Settings]: Settings[K] extends number ? K : never }[keyof Settings];
type DecKey = { [K in keyof Upd]-?: NonNullable<Upd[K]> extends number | string ? (K extends IntKey ? never : K) : never }[keyof Upd];

const INT_RANGES: Partial<Record<IntKey, [number, number]>> = {
  ptw_shift_max_hours: [4, 12],
  issue_to_start_max_minutes: [15, 120],
  max_active_permits_per_receiver: [1, 10],
  gas_pre_start_validity_minutes: [10, 60],
  gas_break_retest_minutes: [15, 60],
  detector_calibration_interval_days: [30, 180],
  fire_watch_post_minutes: [60, 240],
  wah_rescue_max_minutes: [5, 15],
  cse_rescue_max_minutes: [2, 10],
  critical_lift_capacity_pct: [50, 90],
  midday_ban_prewarn_minutes: [5, 60],
  jsa_review_months: [3, 24],
  long_term_isolation_days: [1, 30],
  appointment_max_months: [1, 24],
  ptw_audit_min_per_week: [1, 50],
  ptw_critical_findings_warning: [1, 20],
  step_up_reauth_minutes: [5, 60],
  ptw_retention_years: [1, 15],
};

const DEC_RANGES: Partial<Record<DecKey, [number, number]>> = {
  hw_combustible_clearance_m: [11, 20],
  hw_extinguisher_max_m: [3, 9],
  airside_hotwork_separation_m: [15, 50],
  wah_permit_threshold_m: [1.2, 1.8],
  cse_heat_control_temp_c: [30, 40],
  ex_permit_depth_m: [0.6, 1.2],
  ex_protective_system_depth_m: [0.6, 1.2],
  ex_pe_design_depth_m: [3, 6],
  ex_spoil_setback_m: [0.6, 2],
  ex_egress_max_m: [3, 7.5],
  ex_hand_dig_distance_m: [0.5, 3],
  critical_lift_weight_t: [5, 50],
  lift_wind_limit_ms: [5, 20],
  man_basket_wind_limit_ms: [5, 9.8],
  rg_barrier_limit_usv_h: [0.5, 7.5],
  drop_zone_radius_m: [3, 20],
  vertical_separation_m: [1, 5],
  ptw_audit_warning_pct: [50, 100],
  ptw_closure_warning_pct: [50, 100],
};

const SECTIONS: { key: string; ints: IntKey[]; decs: DecKey[] }[] = [
  { key: "permits", ints: ["ptw_shift_max_hours", "issue_to_start_max_minutes", "max_active_permits_per_receiver", "step_up_reauth_minutes", "appointment_max_months", "ptw_retention_years"], decs: [] },
  { key: "gas", ints: ["gas_pre_start_validity_minutes", "gas_break_retest_minutes", "detector_calibration_interval_days"], decs: [] },
  { key: "hotWork", ints: ["fire_watch_post_minutes"], decs: ["hw_combustible_clearance_m", "hw_extinguisher_max_m", "airside_hotwork_separation_m"] },
  { key: "heights", ints: ["wah_rescue_max_minutes", "cse_rescue_max_minutes"], decs: ["wah_permit_threshold_m", "cse_heat_control_temp_c", "drop_zone_radius_m", "vertical_separation_m"] },
  { key: "excavation", ints: [], decs: ["ex_permit_depth_m", "ex_protective_system_depth_m", "ex_pe_design_depth_m", "ex_spoil_setback_m", "ex_egress_max_m", "ex_hand_dig_distance_m"] },
  { key: "lifting", ints: ["critical_lift_capacity_pct"], decs: ["critical_lift_weight_t", "lift_wind_limit_ms", "man_basket_wind_limit_ms", "rg_barrier_limit_usv_h"] },
  { key: "isolationJsa", ints: ["jsa_review_months", "long_term_isolation_days", "midday_ban_prewarn_minutes"], decs: [] },
  { key: "audits", ints: ["ptw_audit_min_per_week", "ptw_critical_findings_warning"], decs: ["ptw_audit_warning_pct", "ptw_closure_warning_pct"] },
];

const LIMIT_KEYS = ["o2_min_pct", "o2_max_pct", "lel_below_pct", "h2s_below_ppm", "co_below_ppm"] as const;

export function PtwSettingsPage() {
  return <ProjectGate>{(p) => <PtwSettingsView project={p} />}</ProjectGate>;
}

function PtwSettingsView({ project }: { project: Project }) {
  const t = useTranslations("ptwSetup");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tv = useTranslations("validation");
  const me = useMeData();
  const qc = useQueryClient();
  const locale = useLocale();
  const { dateTime } = useFormatters(project.id);
  const q = usePtwSettings(project.id);
  const editable = canWrite(me, "ptw_settings.edit", project.id);
  const [edits, setEdits] = useState<Upd>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const base = q.data;
  const val = <K extends keyof Upd>(k: K): unknown => (k in edits ? edits[k] : (base as unknown as Record<string, unknown>)[k as string]);
  const set = <K extends keyof Upd>(k: K, v: Upd[K]) => setEdits((e) => ({ ...e, [k]: v }));
  const dirty = Object.keys(edits).length > 0;
  const durations = (val("type_max_duration_days") ?? {}) as Record<string, number>;
  const retest = (val("gas_retest_interval_minutes") ?? {}) as Record<string, number>;
  const limits = (val("gas_limits") ?? base.gas_limits) as S["GasLimits-Input"];
  const period = (val("midday_ban_period") ?? base.midday_ban_period) as S["MiddayBanPeriod"];
  const hours = (val("midday_ban_hours") ?? base.midday_ban_hours) as S["MiddayBanHours"];

  async function save() {
    const e: Record<string, string> = {};
    for (const [k, r] of Object.entries(INT_RANGES) as [IntKey, [number, number]][]) {
      if (!(k in edits)) continue;
      const v = Number(val(k as keyof Upd));
      if (!Number.isInteger(v) || v < r[0] || v > r[1]) e[k] = tv("range", { min: r[0], max: r[1] });
    }
    for (const [k, r] of Object.entries(DEC_RANGES) as [DecKey, [number, number]][]) {
      if (!(k in edits)) continue;
      const raw = String(val(k) ?? "");
      const v = Number(raw);
      if (!/^\d+(\.\d+)?$/.test(raw) || v < r[0] || v > r[1]) e[k] = tv("range", { min: r[0], max: r[1] });
    }
    setErrors(e);
    if (Object.keys(e).length) return;
    setBusy(true);
    setError(null);
    try {
      const next = await unwrap(api.PATCH("/api/v1/projects/{project_id}/ptw-settings", { params: { path: { project_id: project.id } }, body: edits }));
      qc.setQueryData(pk.ptwSettings(project.id), next);
      setEdits({});
      toast.success(t("saved"));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const intField = (k: IntKey) => {
    const r = INT_RANGES[k];
    return (
      <FormField key={k} id={`ps-${k}`} label={t(`settings.f.${k}`)} error={errors[k]} hint={r ? t("rangeHint", { min: r[0], max: r[1] }) : undefined}>
        <Input inputMode="numeric" className="ltr" disabled={!editable} value={String(val(k as keyof Upd) ?? "")} onChange={(e) => set(k as keyof Upd, Number(e.target.value.replace(/\D/g, "") || 0) as never)} data-testid={`ps-${k}`} />
      </FormField>
    );
  };
  const decField = (k: DecKey) => {
    const r = DEC_RANGES[k];
    return (
      <FormField key={k} id={`ps-${k}`} label={t(`settings.f.${k}`)} error={errors[k]} hint={r ? t("rangeHint", { min: r[0], max: r[1] }) : undefined}>
        <DecimalInput disabled={!editable} value={String(val(k) ?? "")} onChange={(v) => set(k, v as never)} data-testid={`ps-${k}`} />
      </FormField>
    );
  };

  return (
    <div className="flex flex-col gap-6" data-testid="ptw-settings">
      <SetupHeader title={t("settings.title")} description={t("settings.subtitle")} />
      {!editable ? <Alert tone="info">{t("readOnly")}</Alert> : null}
      {base.updated_at ? <p className="text-sm text-muted-foreground">{t("lastUpdated", { at: dateTime(base.updated_at), by: userLabel(base.updated_by, locale) })}</p> : null}
      <FormSection title={t("settings.s.durations")} description={t("settings.h.durations")}>
        {PERMIT_TYPES.map((pt) => (
          <FormField key={pt} id={`ps-dur-${pt}`} label={te(`permitType.${pt}`)} hint={t("settings.daysHint")}>
            <Input
              inputMode="numeric"
              className="ltr"
              disabled={!editable}
              value={String(durations[pt] ?? "")}
              onChange={(e) => set("type_max_duration_days", { ...durations, [pt]: Number(e.target.value.replace(/\D/g, "") || 0) })}
              data-testid={`ps-dur-${pt}`}
            />
          </FormField>
        ))}
      </FormSection>
      {SECTIONS.map((sec) => (
        <FormSection key={sec.key} title={t(`settings.s.${sec.key as "permits"}`)}>
          {sec.ints.map(intField)}
          {sec.decs.map(decField)}
          {sec.key === "gas"
            ? Object.keys(base.gas_retest_interval_minutes).map((pt) => (
                <FormField key={pt} id={`ps-rt-${pt}`} label={t("settings.retestFor", { type: te(`permitType.${pt as S["PermitType"]}`) })} hint={t("rangeHint", { min: 15, max: 240 })}>
                  <Input
                    inputMode="numeric"
                    className="ltr"
                    disabled={!editable}
                    value={String(retest[pt] ?? "")}
                    onChange={(e) => set("gas_retest_interval_minutes", { ...retest, [pt]: Number(e.target.value.replace(/\D/g, "") || 0) })}
                  />
                </FormField>
              ))
            : null}
          {sec.key === "isolationJsa" ? (
            <>
              <FormField id="ps-mb-from" label={t("settings.middayFrom")} hint={t("settings.mmdd")}>
                <Input className="ltr" disabled={!editable} value={period.start_mmdd} onChange={(e) => set("midday_ban_period", { ...period, start_mmdd: e.target.value })} />
              </FormField>
              <FormField id="ps-mb-to" label={t("settings.middayTo")} hint={t("settings.mmdd")}>
                <Input className="ltr" disabled={!editable} value={period.end_mmdd} onChange={(e) => set("midday_ban_period", { ...period, end_mmdd: e.target.value })} />
              </FormField>
              <FormField id="ps-mb-start" label={t("settings.middayStart")}>
                <Input type="time" className="ltr" disabled={!editable} value={hours.start_local.slice(0, 5)} onChange={(e) => set("midday_ban_hours", { ...hours, start_local: e.target.value })} />
              </FormField>
              <FormField id="ps-mb-end" label={t("settings.middayEnd")}>
                <Input type="time" className="ltr" disabled={!editable} value={hours.end_local.slice(0, 5)} onChange={(e) => set("midday_ban_hours", { ...hours, end_local: e.target.value })} />
              </FormField>
            </>
          ) : null}
        </FormSection>
      ))}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("settings.s.gasLimits")}</CardTitle>
          <p className="text-sm text-muted-foreground">{t("settings.h.gasLimits")}</p>
        </CardHeader>
        <CardContent>
          <Table data-testid="gas-limits">
            <THead>
              <TR>
                <TH>{t("settings.profile")}</TH>
                {LIMIT_KEYS.map((k) => (
                  <TH key={k}>{t(`settings.limit.${k}`)}</TH>
                ))}
              </TR>
            </THead>
            <TBody>
              {Object.entries(limits.by_profile).map(([prof, l]) => (
                <TR key={prof}>
                  <TD label={t("settings.profile")}>{te(`gasProfile.${prof as S["GasLimitProfile"]}`)}</TD>
                  {LIMIT_KEYS.map((k) => (
                    <TD key={k} label={t(`settings.limit.${k}`)}>
                      <DecimalInput
                        className="w-20"
                        disabled={!editable}
                        value={String(l[k])}
                        onChange={(v) => set("gas_limits", { ...limits, by_profile: { ...limits.by_profile, [prof]: { ...l, [k]: v } } })}
                        data-testid={`limit-${prof}-${k}`}
                      />
                    </TD>
                  ))}
                </TR>
              ))}
            </TBody>
          </Table>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("settings.s.hooks")}</CardTitle>
          <p className="text-sm text-muted-foreground">{t("settings.h.hooks")}</p>
        </CardHeader>
        <CardContent>
          <FieldList>
            {Object.entries(base.hook_policy).map(([kind, pol]) => (
              <FieldItem key={kind} label={te(`hookKind.${kind as S["HookKind"]}`)}>
                {te(`hookPolicy.${pol}`)}
              </FieldItem>
            ))}
          </FieldList>
        </CardContent>
      </Card>
      <MutationError error={error} />
      {editable ? (
        <div className="sticky bottom-0 -mx-4 flex gap-2 border-t bg-background/95 px-4 py-3 backdrop-blur sm:static sm:mx-0 sm:border-0 sm:bg-transparent sm:p-0">
          <Button onClick={() => void save()} disabled={!dirty || busy} data-testid="save-ptw-settings">
            {busy ? tc("saving") : t("save")}
          </Button>
          {dirty ? (
            <Button
              variant="outline"
              onClick={() => {
                setEdits({});
                setErrors({});
              }}
            >
              {tc("cancel")}
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
