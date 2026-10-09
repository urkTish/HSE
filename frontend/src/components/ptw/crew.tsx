"use client";
import { ChevronDown, Plus, ShieldCheck, Trash2, TriangleAlert, X } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { FormField } from "@/components/common/form-field";
import { MutationError } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { DeploymentPicker, EligibilityItems, StepDialog, VehicleSelect } from "@/components/access/common";
import { EquipmentPicker } from "@/components/cert/deployments";
import { HookConditions } from "@/components/cert/hook-ui";
import { Link } from "@/i18n/navigation";
import { useMeData } from "@/components/shell/me-context";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useCertCatalogue } from "@/lib/api/cert";
import { useAppointments, usePtwRefresh } from "@/lib/api/ptw";
import { can } from "@/lib/permissions";
import { DOCUMENT_TYPES, EQUIPMENT_CATEGORIES, EQUIPMENT_USES, PTW_CREW_ROLES } from "@/lib/ptw-enums";
import { useFormatters } from "@/lib/use-formatters";
import { cn } from "@/lib/utils";
import { WorkerRefLabel, userLabel } from "./common";

type S = Schemas;
type Permit = S["PermitRead"];

const EDITABLE: S["PermitStatus"][] = ["draft", "requested", "reviewed", "approved", "issued", "active", "suspended"];
const APPT_ROLES: Partial<Record<S["PtwCrewRole"], { fn: S["AppointmentFunction"]; disc?: S["AppointmentDiscipline"] }>> = {
  gas_tester: { fn: "gas_tester" },
  competent_person: { fn: "authorised_person" },
  rpo: { fn: "authorised_person", disc: "radiation_protection_officer" },
  lift_supervisor: { fn: "authorised_person", disc: "lift_supervisor" },
  rescue_lead: { fn: "authorised_person", disc: "cse_rescue_lead" },
};

export function canEditLines(me: S["Me"], p: Permit): boolean {
  return EDITABLE.includes(p.status) && (can(me, "permit.prepare", p.project_id) || can(me, "permit.receive", p.project_id) || can(me, "permit.issue", p.project_id));
}

/** Crew eligibility for one line. Redacted items (no capability for the detail) read "Not eligible — HSE check". */
function CrewEligibility({ items, projectId }: { items: S["CrewEligibilityItem"][]; projectId: string }) {
  const t = useTranslations("permitCrew");
  const redacted = items.filter((i) => i.redacted);
  const shown = items.filter((i) => !i.redacted);
  return (
    <div className="flex flex-col gap-2">
      {redacted.length ? (
        <p className="flex items-center gap-1.5 text-sm text-danger" data-testid="eligibility-redacted">
          <TriangleAlert aria-hidden className="size-4" />
          {t("hseCheck")}
        </p>
      ) : null}
      <EligibilityItems items={shown} projectId={projectId} />
    </div>
  );
}

export function CrewPanel({ permit }: { permit: Permit }) {
  const t = useTranslations("permitCrew");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const refresh = usePtwRefresh();
  const [add, setAdd] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [remove, setRemove] = useState<S["PermitCrewRead"] | null>(null);
  const editable = canEditLines(me, permit);
  const namesVisible = permit.crew.some((c) => c.worker !== null) || permit.crew.length === 0;
  return (
    <Card data-testid="crew-panel">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="text-base">{t("title", { n: permit.crew_count })}</CardTitle>
        {editable ? (
          <Button size="sm" onClick={() => setAdd(true)} data-testid="add-crew">
            <Plus aria-hidden />
            {t("add")}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {!namesVisible ? (
          <div data-testid="crew-counts">
            <p className="mb-2 text-sm text-muted-foreground">{t("countsOnly")}</p>
            <ul className="flex flex-wrap gap-2">
              {Object.entries(permit.crew_roles).map(([role, n]) => (
                <li key={role} className="rounded-md border px-2 py-1 text-sm" data-testid="crew-role-count">
                  {te(`ptwCrewRole.${role as S["PtwCrewRole"]}`)} · <bdi className="ltr tabular-nums">{n}</bdi>
                </li>
              ))}
            </ul>
          </div>
        ) : permit.crew.length ? (
          <ul className="flex flex-col divide-y rounded-md border" data-testid="crew-list">
            {permit.crew.map((c) => (
              <li key={c.id} className={cn("p-2", c.status === "removed" && "opacity-60")} data-testid="crew-line" data-status={c.status} data-role={c.crew_role}>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  {c.eligible === null ? null : c.eligible ? (
                    <ShieldCheck aria-label={t("eligible")} className="size-4 shrink-0 text-success" />
                  ) : (
                    <X aria-label={t("notEligible")} className="size-4 shrink-0 text-danger" />
                  )}
                  <span className="min-w-0 flex-1 text-sm">
                    <WorkerRefLabel w={c.worker} />
                    <span className="block text-xs text-muted-foreground">
                      {te(`ptwCrewRole.${c.crew_role}`)}
                      {c.key_role ? ` · ${t("keyRole")}` : ""}
                      {c.appointment ? (
                        <>
                          {" "}
                          · <bdi className="ltr">{c.appointment.appointment_no}</bdi>
                        </>
                      ) : null}
                      {c.escort_worker ? <> · {t("escortedBy")} <WorkerRefLabel w={c.escort_worker} /></> : null}
                      {c.briefed_current_shift ? ` · ${t("briefed")}` : ""}
                    </span>
                  </span>
                  <StatusBadge status={c.status} label={te(`crewLineStatus.${c.status}`)} />
                  {c.eligibility.length ? (
                    <Button size="sm" variant="ghost" onClick={() => setOpen(open === c.id ? null : c.id)} aria-expanded={open === c.id} data-testid="toggle-eligibility">
                      <ChevronDown aria-hidden className={cn("transition-transform", open === c.id && "rotate-180")} />
                      {t("eligibility")}
                    </Button>
                  ) : null}
                  {editable && c.status !== "removed" ? (
                    <Button size="sm" variant="ghost" onClick={() => setRemove(c)} aria-label={tc("remove")} data-testid="remove-crew">
                      <Trash2 aria-hidden />
                    </Button>
                  ) : null}
                </div>
                {c.excluded_reason ? <p className="mt-1 text-xs text-danger">{c.excluded_reason}</p> : null}
                {open === c.id ? (
                  <div className="mt-2">
                    <CrewEligibility items={c.eligibility} projectId={permit.project_id} />
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">{t("none")}</p>
        )}
        {permit.supervisor ? (
          <p className="text-sm">
            {t("supervisor")}: <WorkerRefLabel w={permit.supervisor} />
          </p>
        ) : null}
      </CardContent>
      {add ? <AddCrewDialog permit={permit} onClose={() => setAdd(false)} /> : null}
      {remove ? (
        <StepDialog
          title={t("removeTitle")}
          confirmLabel={tc("remove")}
          destructive
          onClose={() => setRemove(null)}
          onConfirm={async () => {
            await unwrap(api.DELETE("/api/v1/permits/{permit_id}/crew/{line_id}", { params: { path: { permit_id: permit.id, line_id: remove.id } } }));
            await refresh();
          }}
        />
      ) : null}
    </Card>
  );
}

function AddCrewDialog({ permit, onClose }: { permit: Permit; onClose: () => void }) {
  const t = useTranslations("permitCrew");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const refresh = usePtwRefresh();
  const [dep, setDep] = useState<S["DeploymentRead"] | null>(null);
  const [role, setRole] = useState<S["PtwCrewRole"]>("worker");
  const [appt, setAppt] = useState("");
  const [escort, setEscort] = useState<S["DeploymentRead"] | null>(null);
  const need = APPT_ROLES[role];
  const appts = useAppointments(permit.project_id, { function: need ? [need.fn] : null, status: ["active"], page_size: 200 }, { enabled: Boolean(need) });
  const apptOptions = (appts.data?.items ?? []).filter((a) => !need?.disc || a.discipline === need.disc);
  const airside = permit.zones.some((z) => z.zone_type === "airside");
  return (
    <StepDialog
      title={t("add")}
      confirmLabel={t("addConfirm")}
      disabled={!dep || (Boolean(need) && !appt)}
      onClose={onClose}
      wide
      testId="save-crew"
      onConfirm={async () => {
        await unwrap(
          api.POST("/api/v1/permits/{permit_id}/crew", {
            params: { path: { permit_id: permit.id } },
            body: { worker_id: dep?.worker_id ?? "", crew_role: role, appointment_id: appt || null, escort_worker_id: escort?.worker_id ?? null },
          }),
        );
        await refresh();
        toast.success(t("added"));
      }}
    >
      <DeploymentPicker id="crew-worker" projectId={permit.project_id} value={dep} onChange={setDep} label={t("worker")} required status={["mobilised"]} />
      <FormField id="crew-role" label={t("role")} required>
        <Select value={role} onChange={(e) => { setRole(e.target.value as S["PtwCrewRole"]); setAppt(""); }} data-testid="crew-role">
          {PTW_CREW_ROLES.map((r) => (
            <option key={r} value={r}>
              {te(`ptwCrewRole.${r}`)}
            </option>
          ))}
        </Select>
      </FormField>
      {need ? (
        <FormField id="crew-appt" label={t("appointment")} required hint={t("appointmentHint")}>
          <Select value={appt} onChange={(e) => setAppt(e.target.value)} data-testid="crew-appointment">
            <option value="">{tc("select")}</option>
            {apptOptions.map((a) => (
              <option key={a.id} value={a.id}>
                {a.appointment_no} · {a.holder_user ? userLabel(a.holder_user, locale) : a.holder_worker?.worker_no}
              </option>
            ))}
          </Select>
        </FormField>
      ) : null}
      {airside ? <DeploymentPicker id="crew-escort" projectId={permit.project_id} value={escort} onChange={setEscort} label={t("escort")} status={["mobilised"]} /> : null}
    </StepDialog>
  );
}

/* ───────────── equipment ───────────── */

export function EquipmentPanel({ permit }: { permit: Permit }) {
  const t = useTranslations("permitCrew");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const refresh = usePtwRefresh();
  const [add, setAdd] = useState(false);
  const editable = canEditLines(me, permit);
  return (
    <Card data-testid="equipment-panel">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="text-base">{t("equipment", { n: permit.equipment.length })}</CardTitle>
        {editable ? (
          <Button size="sm" variant="outline" onClick={() => setAdd(true)} data-testid="add-equipment">
            <Plus aria-hidden />
            {t("addEquipment")}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent>
        {permit.equipment.length ? (
          <ul className="flex flex-col gap-2">
            {permit.equipment.map((e) => (
              <li key={e.id} className="rounded-md border p-2" data-testid="equipment-line">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="flex-1">
                    {e.vehicle ? (
                      <>
                        <bdi className="ltr font-medium">{e.vehicle.vehicle_no}</bdi> · {te(`vehicleCategory.${e.vehicle.category}`)}
                      </>
                    ) : e.equipment_tag ? (
                      <>
                        <bdi className="ltr font-medium">{e.equipment_tag.tag}</bdi> · {te(`equipmentCategory.${e.equipment_tag.category}`)}
                        {e.equipment_tag.description ? ` · ${e.equipment_tag.description}` : ""}
                      </>
                    ) : null}
                    <span className="block text-xs text-muted-foreground">
                      {te(`equipmentUse.${e.use}`)}
                      {e.max_working_height_m ? (
                        <>
                          {" "}
                          · <bdi className="ltr">{e.max_working_height_m} m</bdi>
                        </>
                      ) : null}
                    </span>
                  </span>
                  {editable ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={tc("remove")}
                      onClick={async () => {
                        await unwrap(api.DELETE("/api/v1/permits/{permit_id}/equipment/{equipment_id}", { params: { path: { permit_id: permit.id, equipment_id: e.id } } }));
                        await refresh();
                      }}
                    >
                      <Trash2 aria-hidden />
                    </Button>
                  ) : null}
                </div>
                {e.equipment_item || e.operator || e.swl_t ? (
                  <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs" data-testid="equipment-line-p4">
                    {e.equipment_item ? (
                      <Link href={`/equipment/${e.equipment_item.id}`} className="text-primary hover:underline">
                        <bdi className="ltr">{e.equipment_item.equipment_no}</bdi>
                        {e.deployment ? (
                          <>
                            {" "}
                            · <bdi className="ltr">{e.deployment.tag}</bdi>
                          </>
                        ) : null}
                      </Link>
                    ) : null}
                    {e.swl_t ? <span className="ltr">SWL ≤ {e.swl_t} t</span> : null}
                    {e.operator ? (
                      <span data-testid="equipment-operator">
                        {t("operator")}: <WorkerRefLabel w={e.operator} />
                      </span>
                    ) : null}
                  </div>
                ) : null}
                {e.hooks.length ? (
                  <div className="mt-2">
                    <EligibilityItems items={e.hooks} projectId={permit.project_id} />
                  </div>
                ) : null}
                {e.operator_hooks?.length ? (
                  <div className="mt-2" data-testid="operator-hooks">
                    <p className="mb-1 text-xs font-medium text-muted-foreground">{t("operatorChecks")}</p>
                    <EligibilityItems items={e.operator_hooks} projectId={permit.project_id} />
                  </div>
                ) : null}
                {e.conditions?.length ? (
                  <div className="mt-2">
                    <HookConditions items={e.conditions} />
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">{t("noEquipment")}</p>
        )}
      </CardContent>
      {add ? <AddEquipmentDialog permit={permit} onClose={() => setAdd(false)} /> : null}
    </Card>
  );
}

function AddEquipmentDialog({ permit, onClose }: { permit: Permit; onClose: () => void }) {
  const t = useTranslations("permitCrew");
  const te = useTranslations("enums");
  const refresh = usePtwRefresh();
  const [mode, setMode] = useState<"vehicle" | "tag">("vehicle");
  const [vehicle, setVehicle] = useState("");
  const [cat, setCat] = useState<S["EquipmentCategory"]>("tower_crane");
  const [tag, setTag] = useState("");
  const [desc, setDesc] = useState("");
  const [height, setHeight] = useState("");
  const [use, setUse] = useState<S["EquipmentUse"]>("lifting_appliance");
  const [item, setItem] = useState<S["EquipmentListItem"] | null>(null);
  const [operator, setOperator] = useState<S["DeploymentRead"] | null>(null);
  const catalogue = useCertCatalogue(permit.project_id);
  const opCodes = new Set((catalogue.data?.equipment_categories ?? []).filter((c) => c.operator_code).map((c) => c.code));
  const ptwToEqc = (catalogue.data?.ptw_mappings ?? []).find((m) => m.ptw_equipment_category === cat)?.eqc ?? [];
  const needsOperator = mode === "tag" && (item ? opCodes.has(item.category) : ptwToEqc.some((c) => opCodes.has(c)));
  function pickItem(x: S["EquipmentListItem"] | null) {
    setItem(x);
    if (!x) return;
    if (x.current_tag) setTag(x.current_tag);
    const m = (catalogue.data?.ptw_mappings ?? []).find((mm) => mm.ptw_equipment_category && mm.eqc.includes(x.category));
    if (m?.ptw_equipment_category) setCat(m.ptw_equipment_category);
  }
  return (
    <StepDialog
      title={t("addEquipment")}
      confirmLabel={t("addConfirm")}
      disabled={(mode === "vehicle" ? !vehicle : !tag.trim()) || (needsOperator && !operator)}
      onClose={onClose}
      testId="save-equipment"
      onConfirm={async () => {
        await unwrap(
          api.POST("/api/v1/permits/{permit_id}/equipment", {
            params: { path: { permit_id: permit.id } },
            body:
              mode === "vehicle"
                ? { vehicle_id: vehicle, use, operator_worker_id: operator?.worker_id ?? null }
                : { equipment_tag: { category: cat, tag: tag.trim(), description: desc || null, max_working_height_m: height || null }, use, equipment_item_id: item?.id ?? null, operator_worker_id: operator?.worker_id ?? null },
          }),
        );
        await refresh();
      }}
    >
      <fieldset className="flex flex-wrap gap-4 text-sm">
        <label className="flex min-h-touch items-center gap-2">
          <input type="radio" checked={mode === "vehicle"} onChange={() => setMode("vehicle")} />
          {t("registeredVehicle")}
        </label>
        <label className="flex min-h-touch items-center gap-2">
          <input type="radio" checked={mode === "tag"} onChange={() => setMode("tag")} data-testid="eq-mode-tag" />
          {t("equipmentTag")}
        </label>
      </fieldset>
      {mode === "vehicle" ? (
        <FormField id="eq-vehicle" label={t("vehicle")} required>
          <VehicleSelect id="eq-vehicle" projectId={permit.project_id} value={vehicle} onChange={(id) => setVehicle(id)} engagementId={permit.engagement.id} />
        </FormField>
      ) : (
        <>
          {catalogue.data ? <EquipmentPicker id="eq-item" label={t("registeredItem")} value={item} onChange={pickItem} projectId={permit.project_id} /> : null}
          <FormField id="eq-cat" label={t("category")} required>
            <Select value={cat} onChange={(e) => setCat(e.target.value as S["EquipmentCategory"])}>
              {EQUIPMENT_CATEGORIES.map((x) => (
                <option key={x} value={x}>
                  {te(`equipmentCategory.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="eq-tag" label={t("tag")} required>
            <Input className="ltr" value={tag} onChange={(e) => setTag(e.target.value)} maxLength={40} data-testid="eq-tag" />
          </FormField>
          <FormField id="eq-desc" label={t("description")}>
            <Input value={desc} onChange={(e) => setDesc(e.target.value)} maxLength={150} />
          </FormField>
          <FormField id="eq-height" label={t("maxHeight")}>
            <Input inputMode="decimal" className="ltr" value={height} onChange={(e) => setHeight(e.target.value.replace(/[^\d.]/g, ""))} />
          </FormField>
        </>
      )}
      <DeploymentPicker id="eq-operator" projectId={permit.project_id} value={operator} onChange={setOperator} label={needsOperator ? t("operatorRequired") : t("operatorOptional")} required={needsOperator} status={["mobilised"]} />
      <FormField id="eq-use" label={t("use")} required>
        <Select value={use} onChange={(e) => setUse(e.target.value as S["EquipmentUse"])} data-testid="eq-use">
          {EQUIPMENT_USES.map((x) => (
            <option key={x} value={x}>
              {te(`equipmentUse.${x}`)}
            </option>
          ))}
        </Select>
      </FormField>
    </StepDialog>
  );
}

/* ───────────── documents ───────────── */

export function DocumentsPanel({ permit }: { permit: Permit }) {
  const t = useTranslations("permitCrew");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const refresh = usePtwRefresh();
  const { date } = useFormatters(permit.project_id);
  const [add, setAdd] = useState(false);
  const editable = canEditLines(me, permit);
  return (
    <Card data-testid="documents-panel">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="text-base">{t("documents", { n: permit.documents.length })}</CardTitle>
        {editable ? (
          <Button size="sm" variant="outline" onClick={() => setAdd(true)} data-testid="add-document">
            <Plus aria-hidden />
            {t("addDocument")}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent>
        {permit.documents.length ? (
          <Table>
            <THead>
              <TR>
                <TH>{t("docType")}</TH>
                <TH>{t("ref")}</TH>
                <TH>{t("revision")}</TH>
                <TH>{t("approvedBy")}</TH>
                <TH>{t("validUntil")}</TH>
                {editable ? <TH>{tc("actions")}</TH> : null}
              </TR>
            </THead>
            <TBody>
              {permit.documents.map((d) => (
                <TR key={d.id} data-testid="document-row" data-type={d.doc_type}>
                  <TD label={t("docType")}>{te(`documentType.${d.doc_type}`)}</TD>
                  <TD label={t("ref")}>
                    <bdi className="ltr">{d.ref}</bdi>
                  </TD>
                  <TD label={t("revision")}>
                    <bdi className="ltr">{d.revision}</bdi>
                  </TD>
                  <TD label={t("approvedBy")}>{d.approved_by_text ?? "—"}</TD>
                  <TD label={t("validUntil")}>{d.valid_until ? date(d.valid_until) : "—"}</TD>
                  {editable ? (
                    <TD label={tc("actions")}>
                      <Button
                        size="sm"
                        variant="ghost"
                        aria-label={tc("remove")}
                        onClick={async () => {
                          await unwrap(api.DELETE("/api/v1/permits/{permit_id}/documents/{document_id}", { params: { path: { permit_id: permit.id, document_id: d.id } } }));
                          await refresh();
                        }}
                      >
                        <Trash2 aria-hidden />
                      </Button>
                    </TD>
                  ) : null}
                </TR>
              ))}
            </TBody>
          </Table>
        ) : (
          <p className="text-sm text-muted-foreground">{t("noDocuments")}</p>
        )}
      </CardContent>
      {add ? <AddDocumentDialog permit={permit} onClose={() => setAdd(false)} /> : null}
    </Card>
  );
}

function AddDocumentDialog({ permit, onClose }: { permit: Permit; onClose: () => void }) {
  const t = useTranslations("permitCrew");
  const te = useTranslations("enums");
  const refresh = usePtwRefresh();
  const [type, setType] = useState<S["DocumentType"]>("method_statement");
  const [ref, setRef] = useState("");
  const [rev, setRev] = useState("");
  const [by, setBy] = useState("");
  const [until, setUntil] = useState("");
  return (
    <StepDialog
      title={t("addDocument")}
      confirmLabel={t("addConfirm")}
      disabled={!ref.trim() || !rev.trim()}
      onClose={onClose}
      testId="save-document"
      onConfirm={async () => {
        await unwrap(
          api.POST("/api/v1/permits/{permit_id}/documents", {
            params: { path: { permit_id: permit.id } },
            body: { doc_type: type, ref: ref.trim(), revision: rev.trim(), approved_by_text: by || null, valid_until: until || null },
          }),
        );
        await refresh();
      }}
    >
      <FormField id="doc-type" label={t("docType")} required>
        <Select value={type} onChange={(e) => setType(e.target.value as S["DocumentType"])} data-testid="doc-type">
          {DOCUMENT_TYPES.map((x) => (
            <option key={x} value={x}>
              {te(`documentType.${x}`)}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField id="doc-ref" label={t("ref")} required>
        <Input className="ltr" value={ref} onChange={(e) => setRef(e.target.value)} maxLength={60} data-testid="doc-ref" />
      </FormField>
      <FormField id="doc-rev" label={t("revision")} required>
        <Input className="ltr" value={rev} onChange={(e) => setRev(e.target.value)} maxLength={10} data-testid="doc-rev" />
      </FormField>
      <FormField id="doc-by" label={t("approvedBy")}>
        <Input value={by} onChange={(e) => setBy(e.target.value)} maxLength={100} />
      </FormField>
      <FormField id="doc-until" label={t("validUntil")}>
        <Input type="date" className="ltr" value={until} onChange={(e) => setUntil(e.target.value)} />
      </FormField>
    </StepDialog>
  );
}

/* ───────────── checklists ───────────── */

export function ChecklistPanel({ permit, checklist }: { permit: Permit; checklist: S["ChecklistRead"] }) {
  const t = useTranslations("permitCrew");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const locale = useLocale();
  const refresh = usePtwRefresh();
  const { dateTime } = useFormatters(permit.project_id);
  const [answers, setAnswers] = useState<Record<string, { answer: S["ChecklistAnswer"] | ""; note: string }>>(() => Object.fromEntries(checklist.items.map((i) => [i.code, { answer: i.answer ?? "", note: i.note ?? "" }])));
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const live: S["PermitStatus"][] = checklist.kind === "pre_issue" ? ["draft", "requested", "reviewed", "approved", "suspended"] : ["active", "suspended"];
  const editable = live.includes(permit.status) && (can(me, "permit.issue", permit.project_id) || can(me, "permit.receive", permit.project_id) || can(me, "permit.prepare", permit.project_id));
  const dirty = checklist.items.some((i) => (answers[i.code]?.answer ?? "") !== (i.answer ?? "") || (answers[i.code]?.note ?? "") !== (i.note ?? ""));
  async function save() {
    setBusy(true);
    setError(null);
    try {
      await unwrap(
        api.PUT("/api/v1/permits/{permit_id}/checklist", {
          params: { path: { permit_id: permit.id } },
          body: {
            kind: checklist.kind,
            answers: Object.entries(answers)
              .filter(([, v]) => v.answer)
              .map(([code, v]) => ({ code: code as S["PreIssueItem"], answer: v.answer as S["ChecklistAnswer"], note: v.note || null })),
          },
        }),
      );
      await refresh();
      toast.success(tc("saved"));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card data-testid={`checklist-${checklist.kind}`} data-complete={checklist.complete ? "true" : "false"}>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="text-base">{checklist.kind === "pre_issue" ? t("preIssue") : t("closure")}</CardTitle>
        <StatusBadge status={checklist.complete ? "done" : "pending"} label={checklist.complete ? t("complete") : t("incomplete")} />
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <ol className="flex flex-col divide-y rounded-md border">
          {checklist.items.map((i) => {
            const v = answers[i.code] ?? { answer: "", note: "" };
            return (
              <li key={i.code} className="flex flex-col gap-2 p-2 sm:flex-row sm:items-start" data-testid="checklist-item" data-code={i.code} data-answer={i.answer ?? ""}>
                <span className="min-w-0 flex-1 text-sm">
                  <bdi className="ltr me-1.5 font-mono text-xs text-muted-foreground rtl:me-0 rtl:ms-1.5">{i.code}</bdi>
                  {locale === "ar" ? i.label_ar : i.label_en}
                  {i.answered_by ? (
                    <span className="block text-xs text-muted-foreground">
                      {userLabel(i.answered_by, locale)} · {i.answered_at ? dateTime(i.answered_at) : ""}
                    </span>
                  ) : null}
                </span>
                <span className="flex flex-wrap items-center gap-1" role="radiogroup" aria-label={i.code}>
                  {(["yes", "no", "n.a."] as const)
                    .filter((a) => a !== "n.a." || i.na_allowed)
                    .map((a) => (
                      <button
                        key={a}
                        type="button"
                        role="radio"
                        aria-checked={v.answer === a}
                        disabled={!editable}
                        onClick={() => setAnswers({ ...answers, [i.code]: { ...v, answer: a } })}
                        className={cn(
                          "min-h-touch min-w-12 rounded-md border px-2 text-sm",
                          v.answer === a ? (a === "yes" ? "border-success bg-success-bg font-semibold" : a === "no" ? "border-danger bg-danger-bg font-semibold" : "border-input bg-muted font-semibold") : "border-input",
                        )}
                        data-testid={`ans-${a === "n.a." ? "na" : a}`}
                      >
                        {te(`checklistAnswer.${a === "n.a." ? "na" : a}`)}
                      </button>
                    ))}
                </span>
                {v.answer === "no" || v.note ? (
                  <Textarea className="sm:w-56" value={v.note} disabled={!editable} onChange={(e) => setAnswers({ ...answers, [i.code]: { ...v, note: e.target.value } })} maxLength={300} aria-label={t("note")} placeholder={t("note")} />
                ) : null}
              </li>
            );
          })}
        </ol>
        <MutationError error={error} />
        {editable ? (
          <Button className="self-start" onClick={() => void save()} disabled={!dirty || busy} data-testid={`save-checklist-${checklist.kind}`}>
            {busy ? tc("saving") : t("saveChecklist")}
          </Button>
        ) : null}
        {!editable && !checklist.complete && permit.status === "approved" ? <Alert tone="info">{t("issuerCompletes")}</Alert> : null}
      </CardContent>
    </Card>
  );
}
