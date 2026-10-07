"use client";
import { useQueryClient } from "@tanstack/react-query";
import { Ban, Copy, DoorOpen, KeyRound, Pencil, Plus, ScanLine, ShieldAlert } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { ExportButtons } from "@/components/common/export-buttons";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { CheckboxField, FormField, FormSection } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { ProjectById, ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { useMeData } from "@/components/shell/me-context";
import { Link } from "@/i18n/navigation";
import { AREA_CATEGORIES, CREW_ROLES, GATE_REASON_CODES, GATE_RESULTS, GATE_SUBJECT_KINDS, GATE_TYPES, HOOK_KINDS, HOOK_POLICIES, SUSPENDED_CONTRACTOR_GATE_MODES, VEHICLE_CATEGORIES } from "@/lib/access-enums";
import { ak, useAccessSettings, useGate, useGateLog, useGates } from "@/lib/api/access";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { riyadhDayBoundary } from "@/lib/datetime";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { can, canWrite } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { Code, ReasonChips, StepDialog, SubNav } from "./common";
import { HookEditor } from "./setup";

type Gate = Schemas["GateRead"];
const PAGE_SIZE = 50;

function GateSubNav() {
  const t = useTranslations("gates");
  const me = useMeData();
  return (
    <SubNav
      items={[
        { href: "/gates", label: t("title"), testId: "sub-gates", show: can(me, "gate.manage") },
        { href: "/gate-log", label: t("log"), testId: "sub-gate-log", show: can(me, "gate_log.view") },
        { href: "/gate", label: t("openCheck"), testId: "sub-gate-check", show: can(me, "gate.check") },
      ]}
    />
  );
}

/* ───────────────────────────── Gates ───────────────────────────── */

export function GateListPage() {
  return <ProjectGate>{(p) => <GateList project={p} />}</ProjectGate>;
}

function GateList({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("gates");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const name = useLocalizedName();
  const q = useGates(project.id);
  const [create, setCreate] = useState(false);
  const canManage = canWrite(me, "gate.manage", project.id);
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          canManage ? (
            <Button onClick={() => setCreate(true)} data-testid="new-gate">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <GateSubNav />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <Table data-testid="gates-table">
          <THead>
            <TR>
              <TH>{t("fields.gate_code")}</TH>
              <TH>{t("fields.name")}</TH>
              <TH>{tc("site")}</TH>
              <TH>{t("fields.protected_zones")}</TH>
              <TH>{t("fields.gate_type")}</TH>
              <TH>{t("devices")}</TH>
              <TH>{tc("status")}</TH>
            </TR>
          </THead>
          <TBody>
            {items.map((g) => (
              <TR key={g.id} data-testid="gate-row" data-gate={g.gate_code}>
                <TD label={t("fields.gate_code")}>
                  <Link href={`/gates/${g.id}`} className="ltr font-medium text-primary hover:underline">
                    {g.gate_code}
                  </Link>
                </TD>
                <TD label={t("fields.name")}>{name(g.name_en, g.name_ar)}</TD>
                <TD label={tc("site")}>
                  <Code>{g.site.code}</Code>
                </TD>
                <TD label={t("fields.protected_zones")}>{g.protected_zones.length ? <span className="ltr">{g.protected_zones.map((z) => z.code).join(", ")}</span> : <span className="text-muted-foreground">{t("wholeSite")}</span>}</TD>
                <TD label={t("fields.gate_type")}>{te(`gateType.${g.gate_type}`)}</TD>
                <TD label={t("devices")}>{g.devices.filter((d) => !d.revoked_at).length}</TD>
                <TD label={tc("status")}>
                  <StatusBadge status={g.status} label={te(`gateStatus.${g.status}`)} />
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : (
        <EmptyState />
      )}
      {create ? <GateDialog project={project} onClose={() => setCreate(false)} /> : null}
    </div>
  );
}

function GateDialog({ project, gate, onClose }: { project: Schemas["ProjectRead"]; gate?: Gate; onClose: () => void }) {
  const t = useTranslations("gates");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tv = useTranslations("validation");
  const qc = useQueryClient();
  const opts = useProjectOptions(project.id);
  const [code, setCode] = useState(gate?.gate_code ?? "");
  const [nameEn, setNameEn] = useState(gate?.name_en ?? "");
  const [nameAr, setNameAr] = useState(gate?.name_ar ?? "");
  const [site, setSite] = useState(gate?.site.id ?? "");
  const [zones, setZones] = useState<string[]>(gate?.protected_zones.map((z) => z.id) ?? []);
  const [type, setType] = useState<Schemas["GateType"]>(gate?.gate_type ?? "site_gate");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const siteZones = opts.zones.filter((z) => z.siteId === site);
  async function save() {
    const e: Record<string, string> = {};
    if (!gate && !code.trim()) e.code = tv("required");
    if (!nameEn.trim()) e.nameEn = tv("required");
    if (!nameAr.trim()) e.nameAr = tv("required");
    if (!site) e.site = tv("required");
    if (type !== "site_gate" && zones.length === 0) e.zones = t("zonesRequired");
    setErrors(e);
    if (Object.keys(e).length) return;
    setBusy(true);
    setError(null);
    try {
      const saved = gate
        ? await unwrap(api.PATCH("/api/v1/gates/{gate_id}", { params: { path: { gate_id: gate.id } }, body: { name_en: nameEn.trim(), name_ar: nameAr.trim(), protected_zone_ids: zones, gate_type: type } }))
        : await unwrap(
            api.POST("/api/v1/projects/{project_id}/gates", {
              params: { path: { project_id: project.id } },
              body: { gate_code: code.trim().toUpperCase(), name_en: nameEn.trim(), name_ar: nameAr.trim(), site_id: site, protected_zone_ids: zones, gate_type: type },
            }),
          );
      qc.setQueryData(ak.gate(saved.id), saved);
      await qc.invalidateQueries({ queryKey: ["gates"] });
      toast.success(tc("saved"));
      onClose();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent closeLabel={tc("close")} className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{gate ? t("edit") : t("new")}</DialogTitle>
          <DialogDescription>{t("formHint")}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField id="g-code" label={t("fields.gate_code")} required error={errors.code}>
            <Input className="ltr uppercase" maxLength={12} disabled={Boolean(gate)} value={code} onChange={(e) => setCode(e.target.value)} />
          </FormField>
          <FormField id="g-type" label={t("fields.gate_type")} required>
            <Select value={type} onChange={(e) => setType(e.target.value as Schemas["GateType"])}>
              {GATE_TYPES.map((x) => (
                <option key={x} value={x}>
                  {te(`gateType.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="g-name-en" label={t("fields.name_en")} required error={errors.nameEn}>
            <Input dir="ltr" maxLength={120} value={nameEn} onChange={(e) => setNameEn(e.target.value)} />
          </FormField>
          <FormField id="g-name-ar" label={t("fields.name_ar")} required error={errors.nameAr}>
            <Input dir="rtl" maxLength={120} value={nameAr} onChange={(e) => setNameAr(e.target.value)} />
          </FormField>
          <FormField id="g-site" label={tc("site")} required error={errors.site}>
            <Select
              disabled={Boolean(gate)}
              value={site}
              onChange={(e) => {
                setSite(e.target.value);
                setZones([]);
              }}
            >
              <option value="">{tc("select")}</option>
              {opts.sites.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </Select>
          </FormField>
          <div className="flex flex-col gap-1">
            <MultiSelect id="g-zones" label={t("fields.protected_zones")} options={siteZones.map((z) => ({ value: z.value, label: z.label }))} value={zones} onChange={setZones} allLabel={t("wholeSite")} className="lg:w-full" />
            {errors.zones ? <p className="text-sm text-destructive">{errors.zones}</p> : <p className="text-xs text-muted-foreground">{t("zonesHint")}</p>}
          </div>
        </div>
        <MutationError error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button onClick={() => void save()} disabled={busy} data-testid="save-gate">
            {tc("save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function GateDetail({ id }: { id: string }) {
  const q = useGate(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const g = q.data;
  return <ProjectById id={g.project_id}>{(p) => <GateView project={p} gate={g} />}</ProjectById>;
}

function GateView({ project, gate: g }: { project: Schemas["ProjectRead"]; gate: Gate }) {
  const t = useTranslations("gates");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const qc = useQueryClient();
  const name = useLocalizedName();
  const { dateTime } = useFormatters(project.id);
  const canManage = canWrite(me, "gate.manage", project.id);
  const [edit, setEdit] = useState(false);
  const [register, setRegister] = useState(false);
  const [revoke, setRevoke] = useState<Schemas["GateDeviceRead"] | null>(null);
  const [toggle, setToggle] = useState(false);
  async function refresh(u?: Gate) {
    if (u) qc.setQueryData(ak.gate(u.id), u);
    else await qc.invalidateQueries({ queryKey: ak.gate(g.id) });
    await qc.invalidateQueries({ queryKey: ["gates"] });
  }
  return (
    <div className="flex flex-col gap-4">
      <div>
        <Breadcrumbs items={[{ href: "/gates", label: t("title") }, { label: g.gate_code }]} />
        <PageHeader
          title={`${g.gate_code} · ${name(g.name_en, g.name_ar)}`}
          description={te(`gateType.${g.gate_type}`)}
          actions={
            <>
              {can(me, "gate.check", project.id) && g.status === "active" ? (
                <Button variant="outline" asChild>
                  <Link href={`/gate?gate=${g.id}`} data-testid="open-gate-check">
                    <ScanLine aria-hidden />
                    {t("openCheck")}
                  </Link>
                </Button>
              ) : null}
              {canManage ? (
                <>
                  <Button variant="outline" onClick={() => setEdit(true)} data-testid="edit-gate">
                    <Pencil aria-hidden />
                    {tc("edit")}
                  </Button>
                  <Button variant="outline" onClick={() => setToggle(true)} data-testid="toggle-gate">
                    <DoorOpen aria-hidden />
                    {g.status === "active" ? t("deactivate") : t("activate")}
                  </Button>
                </>
              ) : null}
            </>
          }
        />
      </div>
      <Card>
        <CardContent className="pt-6">
          <FieldList>
            <FieldItem label={tc("status")}>
              <StatusBadge status={g.status} label={te(`gateStatus.${g.status}`)} />
            </FieldItem>
            <FieldItem label={tc("site")}>
              <Code>{g.site.code}</Code> {name(g.site.name_en, g.site.name_ar)}
            </FieldItem>
            <FieldItem label={t("fields.protected_zones")} wide>
              {g.protected_zones.length ? (
                <ul className="flex flex-wrap gap-2">
                  {g.protected_zones.map((z) => (
                    <li key={z.id}>
                      <Code>{z.code}</Code> {name(z.name_en, z.name_ar)}
                    </li>
                  ))}
                </ul>
              ) : (
                t("wholeSite")
              )}
            </FieldItem>
          </FieldList>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">{t("devices")}</CardTitle>
          {canManage && g.status === "active" ? (
            <Button size="sm" onClick={() => setRegister(true)} data-testid="register-device">
              <KeyRound aria-hidden />
              {t("registerDevice")}
            </Button>
          ) : null}
        </CardHeader>
        <CardContent>
          <p className="mb-3 text-sm text-muted-foreground">{t("devicesHint")}</p>
          {g.devices.length ? (
            <Table data-testid="devices-table">
              <THead>
                <TR>
                  <TH>{t("fields.device_id")}</TH>
                  <TH>{t("fields.label")}</TH>
                  <TH>{t("fields.registered_at")}</TH>
                  <TH>{t("fields.last_seen_at")}</TH>
                  <TH>{tc("status")}</TH>
                  <TH>
                    <span className="sr-only">{tc("actions")}</span>
                  </TH>
                </TR>
              </THead>
              <TBody>
                {g.devices.map((d) => (
                  <TR key={d.id} data-testid="device-row" data-device={d.device_id}>
                    <TD label={t("fields.device_id")}>
                      <Code>{d.device_id}</Code>
                    </TD>
                    <TD label={t("fields.label")}>{d.label}</TD>
                    <TD label={t("fields.registered_at")}>
                      {dateTime(d.registered_at)}
                      {d.registered_by ? <span className="block text-xs text-muted-foreground">{name(d.registered_by.full_name_en, d.registered_by.full_name_ar ?? null)}</span> : null}
                    </TD>
                    <TD label={t("fields.last_seen_at")}>{d.last_seen_at ? dateTime(d.last_seen_at) : "—"}</TD>
                    <TD label={tc("status")}>
                      {d.revoked_at ? (
                        <span>
                          <StatusBadge status="revoked" label={t("revoked")} />
                          <span className="block text-xs text-muted-foreground">{dateTime(d.revoked_at)}</span>
                        </span>
                      ) : (
                        <StatusBadge status="active" label={t("activeDevice")} />
                      )}
                    </TD>
                    <TD label={tc("actions")}>
                      {canManage && !d.revoked_at ? (
                        <Button size="sm" variant="outline" onClick={() => setRevoke(d)} data-testid="revoke-device">
                          <Ban aria-hidden />
                          {t("revoke")}
                        </Button>
                      ) : null}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          ) : (
            <EmptyState message={t("noDevices")} />
          )}
        </CardContent>
      </Card>
      <HistoryPanel entityType="gate" entityId={g.id} />
      {edit ? <GateDialog project={project} gate={g} onClose={() => setEdit(false)} /> : null}
      {register ? <RegisterDeviceDialog gate={g} onDone={() => void refresh()} onClose={() => setRegister(false)} /> : null}
      {revoke ? (
        <StepDialog
          title={t("revokeTitle", { device: revoke.device_id })}
          description={t("revokeHint")}
          destructive
          confirmLabel={t("revoke")}
          testId="revoke-confirm"
          onClose={() => setRevoke(null)}
          onConfirm={async () => {
            await unwrap(api.POST("/api/v1/gates/{gate_id}/devices/{device_pk}/revoke", { params: { path: { gate_id: g.id, device_pk: revoke.id } } }));
            await refresh();
            toast.success(t("revokedDone"));
          }}
        >
          {null}
        </StepDialog>
      ) : null}
      {toggle ? (
        <StepDialog
          title={g.status === "active" ? t("deactivate") : t("activate")}
          description={g.status === "active" ? t("deactivateHint") : t("activateHint")}
          destructive={g.status === "active"}
          confirmLabel={g.status === "active" ? t("deactivate") : t("activate")}
          testId="toggle-confirm"
          onClose={() => setToggle(false)}
          onConfirm={async () => {
            const u = await unwrap(api.PATCH("/api/v1/gates/{gate_id}", { params: { path: { gate_id: g.id } }, body: { status: g.status === "active" ? "inactive" : "active" } }));
            await refresh(u);
            toast.success(tc("saved"));
          }}
        >
          {null}
        </StepDialog>
      ) : null}
    </div>
  );
}

function RegisterDeviceDialog({ gate, onDone, onClose }: { gate: Gate; onDone: () => void; onClose: () => void }) {
  const t = useTranslations("gates");
  const tc = useTranslations("common");
  const tv = useTranslations("validation");
  const [deviceId, setDeviceId] = useState("");
  const [label, setLabel] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function save() {
    const e: Record<string, string> = {};
    if (!deviceId.trim()) e.deviceId = tv("required");
    if (!label.trim()) e.label = tv("required");
    setErrors(e);
    if (Object.keys(e).length) return;
    setBusy(true);
    setError(null);
    try {
      const r = await unwrap(api.POST("/api/v1/gates/{gate_id}/devices", { params: { path: { gate_id: gate.id } }, body: { device_id: deviceId.trim().toUpperCase(), label: label.trim() } }));
      setToken(r.device_token);
      onDone();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent closeLabel={tc("close")} className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("registerDevice")}</DialogTitle>
          <DialogDescription>{token ? t("tokenOnce") : t("registerHint", { gate: gate.gate_code })}</DialogDescription>
        </DialogHeader>
        {token ? (
          <div className="flex flex-col gap-3">
            <Alert tone="warning">{t("tokenWarning")}</Alert>
            <code className="ltr block break-all rounded-md border bg-muted p-3 font-mono text-sm" data-testid="device-token">
              {token}
            </code>
            <Button
              variant="outline"
              onClick={() => {
                void navigator.clipboard?.writeText(token).then(
                  () => toast.success(t("copied")),
                  () => toast.error(t("copyFailed")),
                );
              }}
            >
              <Copy aria-hidden />
              {t("copyToken")}
            </Button>
            <p className="text-sm text-muted-foreground">{t("tokenUse")}</p>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField id="dv-id" label={t("fields.device_id")} required error={errors.deviceId} hint={t("deviceIdHint")}>
              <Input className="ltr uppercase" maxLength={40} value={deviceId} onChange={(e) => setDeviceId(e.target.value)} />
            </FormField>
            <FormField id="dv-label" label={t("fields.label")} required error={errors.label}>
              <Input maxLength={80} value={label} onChange={(e) => setLabel(e.target.value)} />
            </FormField>
          </div>
        )}
        <MutationError error={error} />
        <DialogFooter>
          {token ? (
            <Button onClick={onClose} data-testid="token-done">
              {t("tokenSaved")}
            </Button>
          ) : (
            <>
              <Button variant="outline" onClick={onClose}>
                {tc("cancel")}
              </Button>
              <Button onClick={() => void save()} disabled={busy} data-testid="save-device">
                {t("registerDevice")}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ───────────────────────────── Gate log ───────────────────────────── */

export function GateLogPage() {
  return <ProjectGate>{(p) => <GateLog project={p} />}</ProjectGate>;
}

const RESULT_TONE: Record<Schemas["GateResult"], string> = {
  GRANTED: "active",
  GRANTED_WITH_WARNING: "granted_note",
  DENIED: "rejected",
  PENDING_ESCORT: "pending",
  PENDING_DRIVER: "pending",
  PENDING_ESCORT_VEHICLE: "pending",
  EXIT_RECORDED: "closed",
  WAP_VIEW: "draft",
};

export function GateResultBadge({ result }: { result: Schemas["GateResult"] }) {
  const te = useTranslations("enums");
  return <StatusBadge status={RESULT_TONE[result]} label={te(`gateResult.${result}`)} />;
}

function GateLog({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("gates");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const name = useLocalizedName();
  const { dateTime } = useFormatters(project.id);
  const gates = useGates(project.id);
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const gateIds = s.getAll("gate_id");
  const results = s.getAll("result") as Schemas["GateResult"][];
  const reasons = s.getAll("reason_code") as Schemas["GateReasonCode"][];
  const engs = s.getAll("engagement_id");
  // A day picked here, or an exact instant from an action-panel link (e.g. `since=2026-09-30T21:47:34+00:00`).
  const sinceRaw = s.get("since") ?? "";
  const untilRaw = s.get("until") ?? "";
  const since = sinceRaw.slice(0, 10);
  const until = untilRaw.slice(0, 10);
  const sinceAt = sinceRaw.includes("T") ? sinceRaw : since ? riyadhDayBoundary(since, false) : "";
  const untilAt = untilRaw.includes("T") ? untilRaw : until ? riyadhDayBoundary(until, true) : "";
  const query = useGateLog(project.id, {
    gate_id: gateIds.length ? gateIds : null,
    result: results.length ? results : null,
    reason_code: reasons.length ? reasons : null,
    engagement_id: engs.length ? engs : null,
    direction: (s.get("direction") as Schemas["GateDirection"] | null) || null,
    subject_kind: (s.get("subject_kind") as Schemas["GateSubjectKind"] | null) || null,
    admitted_despite_denial: s.getBool("admitted_despite_denial") ?? null,
    late_exit: s.getBool("late_exit") ?? null,
    since: sinceAt || null,
    until: untilAt || null,
    page,
    page_size: PAGE_SIZE,
  });
  const items = query.data?.items ?? [];
  const exportParams: Record<string, string> = { project_id: project.id };
  if (sinceAt) exportParams.since = sinceAt;
  if (untilAt) exportParams.until = untilAt;
  return (
    <div>
      <PageHeader title={t("log")} description={t("logSubtitle")} />
      <GateSubNav />
      <ListToolbar actions={can(me, "export.access", project.id) ? <ExportButtons dataset="gate_log" params={exportParams} /> : null}>
        <MultiSelect id="gl-gate" label={t("gate")} options={(gates.data?.items ?? []).map((g) => ({ value: g.id, label: g.gate_code }))} value={gateIds} onChange={(v) => s.set({ gate_id: v })} />
        <MultiSelect id="gl-result" label={t("result")} options={GATE_RESULTS.map((x) => ({ value: x, label: te(`gateResult.${x}`) }))} value={results} onChange={(v) => s.set({ result: v })} />
        <MultiSelect id="gl-reason" label={t("reason")} options={GATE_REASON_CODES.map((x) => ({ value: x, label: te(`gateReason.${x}`) }))} value={reasons} onChange={(v) => s.set({ reason_code: v })} />
        <MultiSelect id="gl-eng" label={tc("contractor")} options={opts.engagements} value={engs} onChange={(v) => s.set({ engagement_id: v })} allLabel={tc("anyContractor")} />
        <SelectFilter id="gl-dir" label={t("direction")} value={(s.get("direction") ?? "") as Schemas["GateDirection"] | ""} onChange={(v) => s.set({ direction: v })} options={(["in", "out"] as const).map((x) => ({ value: x, label: te(`gateDirection.${x}`) }))} />
        <SelectFilter id="gl-kind" label={t("subject")} value={(s.get("subject_kind") ?? "") as Schemas["GateSubjectKind"] | ""} onChange={(v) => s.set({ subject_kind: v })} options={GATE_SUBJECT_KINDS.map((x) => ({ value: x, label: te(`gateSubjectKind.${x}`) }))} />
        <SelectFilter id="gl-admitted" label={t("admittedDespiteDenial")} value={s.get("admitted_despite_denial") === "true" ? "true" : ""} onChange={(v) => s.set({ admitted_despite_denial: v })} options={[{ value: "true", label: tc("yes") }]} />
        <SelectFilter id="gl-late" label={t("lateExit")} value={s.get("late_exit") === "true" ? "true" : ""} onChange={(v) => s.set({ late_exit: v })} options={[{ value: "true", label: tc("yes") }]} />
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-muted-foreground">{tc("from")}</span>
          <Input type="date" value={since} onChange={(e) => s.set({ since: e.target.value })} className="w-auto" data-testid="gl-since" />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-muted-foreground">{tc("to")}</span>
          <Input type="date" value={until} onChange={(e) => s.set({ until: e.target.value })} className="w-auto" data-testid="gl-until" />
        </label>
      </ListToolbar>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="gate-log-table">
            <THead>
              <TR>
                <TH>{t("occurredAt")}</TH>
                <TH>{t("gate")}</TH>
                <TH>{t("subject")}</TH>
                <TH>{tc("zone")}</TH>
                <TH>{t("result")}</TH>
                <TH>{t("reason")}</TH>
                <TH>{t("by")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((r) => (
                <TR key={r.id} data-testid="gate-log-row" data-result={r.result} data-admitted={r.admitted_despite_denial ? "true" : "false"}>
                  <TD label={t("occurredAt")}>
                    {/* One wrapper per cell: on phones the stacked card puts each child of a cell on its own grid row. */}
                    <span className="flex flex-col items-start">
                      <span className="tabular-nums">{dateTime(r.occurred_at)}</span>
                      <span className="text-xs text-muted-foreground">{te(`gateDirection.${r.direction}`)}</span>
                    </span>
                  </TD>
                  <TD label={t("gate")}>
                    <Code>{r.gate_code}</Code>
                  </TD>
                  <TD label={t("subject")}>
                    <span className="flex flex-col items-start">
                      <span className="text-xs text-muted-foreground">{te(`gateSubjectKind.${r.subject_kind}`)}</span>
                      {r.subject_ref ? <bdi className="ltr block font-medium whitespace-nowrap">{r.subject_ref}</bdi> : null}
                      {r.subject_name_en || r.subject_name_ar ? <span>{name(r.subject_name_en ?? "", r.subject_name_ar ?? "")}</span> : null}
                    </span>
                  </TD>
                  <TD label={tc("zone")}>{r.zone ? <Code>{r.zone.code}</Code> : "—"}</TD>
                  <TD label={t("result")}>
                    <span className="flex flex-col items-start gap-1">
                      <GateResultBadge result={r.result} />
                      {r.late_exit ? <span className="text-xs text-warning">{t("lateExit")}</span> : null}
                      {r.admitted_despite_denial ? (
                        <span className="flex items-start gap-1 text-xs font-medium text-danger" data-testid="admitted-flag">
                          <ShieldAlert aria-hidden className="mt-0.5 size-3.5 shrink-0" />
                          <span>
                            {t("admittedDespiteDenial")}
                            {r.admitted_reason ? <span className="block font-normal text-muted-foreground">{r.admitted_reason}</span> : null}
                          </span>
                        </span>
                      ) : null}
                    </span>
                  </TD>
                  <TD label={t("reason")}>{r.reason_codes.length ? <ReasonChips codes={r.reason_codes} /> : "—"}</TD>
                  <TD label={t("by")}>{r.device_id ? <Code>{r.device_id}</Code> : r.user ? name(r.user.full_name_en, r.user.full_name_ar ?? null) : "—"}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={query.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState />
      )}
    </div>
  );
}

/* ───────────────────────────── Access settings ───────────────────────────── */

type Settings = Schemas["AccessSettingsRead"];
type Upd = Schemas["AccessSettingsUpdate"];
type IntKey = {
  [K in keyof Settings & keyof Upd]: Settings[K] extends number ? (K extends string ? K : never) : never;
}[keyof Settings & keyof Upd];

const RANGES: Partial<Record<IntKey | "reinduction_absence_days", [number, number]>> = {
  induction_pass_mark_pct: [50, 100],
  induction_retest_wait_hours: [0, 72],
  induction_max_attempts_30d: [1, 5],
  reinduction_absence_days: [30, 365],
  reinduction_grace_days: [0, 90],
  pass_max_validity_months: [1, 36],
  temp_escorted_pass_max_days: [1, 90],
  visitor_pass_max_days: [1, 7],
  bg_recheck_months: [12, 60],
  application_stale_days: [7, 90],
  id_copy_retention_days: [0, 180],
  pass_return_days: [1, 14],
  lost_report_hours: [1, 72],
  escort_ratio_max_apron: [1, 10],
  escort_ratio_max_manoeuvring: [1, 10],
  escort_ratio_max_other: [1, 10],
  vehicle_escort_ratio_max_apron: [1, 5],
  vehicle_escort_ratio_max_manoeuvring: [1, 5],
  escort_pairing_seconds: [30, 600],
  adp_validity_months: [6, 36],
  adp_theory_pass_pct: [50, 100],
  adp_points_threshold: [3, 24],
  adp_points_window_days: [90, 730],
  adp_suspension_days: [7, 180],
  adp_revoke_after_suspensions: [1, 5],
  adp_revoke_after_suspensions_window_days: [365, 1095],
  avp_validity_months: [1, 24],
  wap_max_days: [1, 90],
  wap_exit_grace_minutes: [0, 60],
  notam_request_lead_days: [1, 30],
  airac_lead_days: [28, 84],
  obstacle_clearance_lead_days: [3, 90],
  raised_suspension_max_hours: [4, 168],
  gate_log_retention_months: [3, 60],
  worker_retention_years: [1, 15],
  induction_coverage_warning_pct: [80, 100],
};
const DEC_RANGES = { obstacle_height_threshold_m: [10, 150], ols_buffer_m: [0, 30] } as const;

const SECTIONS: { key: string; airport?: boolean; fields: IntKey[] }[] = [
  { key: "induction", fields: ["induction_pass_mark_pct", "induction_retest_wait_hours", "induction_max_attempts_30d", "reinduction_grace_days", "induction_coverage_warning_pct"] },
  { key: "passes", airport: true, fields: ["pass_max_validity_months", "temp_escorted_pass_max_days", "visitor_pass_max_days", "bg_recheck_months", "application_stale_days", "id_copy_retention_days", "pass_return_days", "lost_report_hours"] },
  { key: "escort", fields: ["escort_ratio_max_apron", "escort_ratio_max_manoeuvring", "escort_ratio_max_other", "vehicle_escort_ratio_max_apron", "vehicle_escort_ratio_max_manoeuvring", "escort_pairing_seconds"] },
  { key: "driving", airport: true, fields: ["adp_validity_months", "adp_theory_pass_pct", "adp_points_threshold", "adp_points_window_days", "adp_suspension_days", "adp_revoke_after_suspensions", "adp_revoke_after_suspensions_window_days", "avp_validity_months"] },
  { key: "works", fields: ["wap_max_days", "wap_exit_grace_minutes", "notam_request_lead_days", "airac_lead_days", "obstacle_clearance_lead_days"] },
  { key: "lifecycle", fields: ["raised_suspension_max_hours", "gate_log_retention_months", "worker_retention_years"] },
];

function parseList(s: string): number[] | null {
  const parts = s
    .split(/[,،\s]+/)
    .map((x) => x.trim())
    .filter(Boolean);
  if (!parts.every((x) => /^\d+$/.test(x))) return null;
  return parts.map(Number);
}

type HookMapKey = "hook_requirements_by_adp_category" | "hook_requirements_by_vehicle_category" | "hook_requirements_by_crew_role";

export function AccessSettingsPage() {
  return <ProjectGate>{(p) => <AccessSettingsView project={p} />}</ProjectGate>;
}

function AccessSettingsView({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("accessSettings");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tv = useTranslations("validation");
  const me = useMeData();
  const qc = useQueryClient();
  const name = useLocalizedName();
  const { dateTime } = useFormatters(project.id);
  const q = useAccessSettings(project.id);
  const editable = canWrite(me, "access_settings.edit", project.id);
  const [edits, setEdits] = useState<Partial<Settings>>({});
  const [longText, setLongText] = useState<string | null>(null);
  const [shortText, setShortText] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const base = q.data;
  const d: Settings = { ...base, ...edits };
  const set = <K extends keyof Settings>(k: K, v: Settings[K]) => setEdits((e) => ({ ...e, [k]: v }));
  const dirty = Object.keys(edits).length > 0 || longText !== null || shortText !== null;

  async function save() {
    const e: Record<string, string> = {};
    for (const [k, r] of Object.entries(RANGES) as [IntKey | "reinduction_absence_days", [number, number]][]) {
      const v = d[k];
      if (k === "reinduction_absence_days" && v === null) continue;
      if (typeof v !== "number" || !Number.isInteger(v) || v < r[0] || v > r[1]) e[k] = tv("range", { min: r[0], max: r[1] });
    }
    for (const [k, r] of Object.entries(DEC_RANGES) as ["obstacle_height_threshold_m" | "ols_buffer_m", readonly [number, number]][]) {
      const v = Number(d[k]);
      if (!/^\d+(\.\d+)?$/.test(String(d[k])) || v < r[0] || v > r[1]) e[k] = tv("range", { min: r[0], max: r[1] });
    }
    const longList = longText !== null ? parseList(longText) : d.alert_schedule_long_days;
    const shortList = shortText !== null ? parseList(shortText) : d.alert_schedule_short_hours;
    if (!longList || longList.length === 0) e.alert_schedule_long_days = t("listInvalid");
    if (!shortList || shortList.length === 0) e.alert_schedule_short_hours = t("listInvalid");
    setErrors(e);
    if (Object.keys(e).length) return;
    const body: Upd = {};
    for (const [k, v] of Object.entries(edits)) {
      if (k === "hook_providers" || k === "updated_at" || k === "updated_by" || k === "project_id") continue;
      (body as Record<string, unknown>)[k] = v;
    }
    if (longText !== null) body.alert_schedule_long_days = longList;
    if (shortText !== null) body.alert_schedule_short_hours = shortList;
    setBusy(true);
    setError(null);
    try {
      const next = await unwrap(api.PATCH("/api/v1/projects/{project_id}/access-settings", { params: { path: { project_id: project.id } }, body }));
      qc.setQueryData(ak.accessSettings(project.id), next);
      await qc.invalidateQueries({ queryKey: ["hook-providers"] });
      setEdits({});
      setLongText(null);
      setShortText(null);
      toast.success(tc("saved"));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const num = (k: IntKey) => {
    const r = RANGES[k];
    return (
      <FormField key={k} id={`as-${k}`} label={t(`fields.${k}`)} error={errors[k]} hint={r ? t("rangeHint", { min: r[0], max: r[1] }) : undefined}>
        <Input inputMode="numeric" className="ltr" disabled={!editable} value={String(d[k])} onChange={(e) => set(k, Number(e.target.value.replace(/\D/g, "") || 0) as Settings[typeof k])} />
      </FormField>
    );
  };
  const dec = (k: "obstacle_height_threshold_m" | "ols_buffer_m") => (
    <FormField id={`as-${k}`} label={t(`fields.${k}`)} error={errors[k]} hint={t("rangeHint", { min: DEC_RANGES[k][0], max: DEC_RANGES[k][1] })}>
      <Input inputMode="decimal" className="ltr" disabled={!editable} value={String(d[k])} onChange={(e) => set(k, e.target.value.replace(/[^\d.]/g, ""))} />
    </FormField>
  );
  const hookMap = (k: HookMapKey, keys: readonly string[], label: (x: string) => string) => {
    const m = (d[k] ?? {}) as Record<string, Schemas["HookRequirement"][]>;
    return (
      <div className="flex flex-col gap-3 sm:col-span-2">
        <p className="text-sm font-medium">{t(`fields.${k}`)}</p>
        {keys.map((x) => (
          <div key={x} className="rounded-md border p-3">
            <p className="mb-2 text-sm">{label(x)}</p>
            {editable ? (
              <HookEditor id={`as-${k}-${x}`} value={m[x] ?? []} onChange={(v) => set(k, { ...m, [x]: v } as Settings[HookMapKey])} />
            ) : (
              <span className="flex flex-wrap gap-1">{(m[x] ?? []).length ? (m[x] ?? []).map((h) => <Code key={`${h.kind}-${h.code}`}>{h.code}</Code>) : <span className="text-sm text-muted-foreground">—</span>}</span>
            )}
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="flex flex-col gap-6" data-testid="access-settings">
      <PageHeader title={t("title")} description={t("subtitle")} />
      {!editable ? <Alert tone="info">{t("readOnly")}</Alert> : null}
      {base.updated_at ? (
        <p className="text-sm text-muted-foreground">
          {t("lastUpdated", { at: dateTime(base.updated_at), by: base.updated_by ? name(base.updated_by.full_name_en, base.updated_by.full_name_ar ?? null) : "—" })}
        </p>
      ) : null}
      <FormSection title={t("section.induction")} description={t("sectionHint.induction")}>
        {(SECTIONS[0]?.fields ?? []).map(num)}
        <FormField id="as-reinduction_absence_days" label={t("fields.reinduction_absence_days")} error={errors.reinduction_absence_days} hint={t("absenceHint")}>
          <Input
            inputMode="numeric"
            className="ltr"
            disabled={!editable}
            value={d.reinduction_absence_days == null ? "" : String(d.reinduction_absence_days)}
            placeholder={t("off")}
            onChange={(e) => {
              const v = e.target.value.replace(/\D/g, "");
              set("reinduction_absence_days", v ? Number(v) : null);
            }}
          />
        </FormField>
        <CheckboxField id="as-id-expiry" label={t("fields.id_expiry_blocks_access")}>
          <Checkbox disabled={!editable} checked={d.id_expiry_blocks_access} onChange={(e) => set("id_expiry_blocks_access", e.target.checked)} />
        </CheckboxField>
      </FormSection>
      {SECTIONS.slice(1).map((sec) =>
        sec.airport && !project.is_airport ? null : (
          <FormSection key={sec.key} title={t(`section.${sec.key as "induction"}`)} description={t(`sectionHint.${sec.key as "induction"}`)}>
            {sec.fields.map(num)}
            {sec.key === "works" ? (
              <>
                {dec("obstacle_height_threshold_m")}
                {dec("ols_buffer_m")}
              </>
            ) : null}
            {sec.key === "lifecycle" ? (
              <FormField id="as-suspended-contractor" label={t("fields.suspended_contractor_gate")} hint={t("suspendedContractorHint")}>
                <Select disabled={!editable} value={d.suspended_contractor_gate} onChange={(e) => set("suspended_contractor_gate", e.target.value as Schemas["SuspendedContractorGateMode"])}>
                  {SUSPENDED_CONTRACTOR_GATE_MODES.map((x) => (
                    <option key={x} value={x}>
                      {te(`suspendedContractorGate.${x}`)}
                    </option>
                  ))}
                </Select>
              </FormField>
            ) : null}
          </FormSection>
        ),
      )}
      <FormSection title={t("section.alerts")} description={t("sectionHint.alerts")}>
        <FormField id="as-long" label={t("fields.alert_schedule_long_days")} error={errors.alert_schedule_long_days} hint={t("listHint")}>
          <Input className="ltr" disabled={!editable} value={longText ?? d.alert_schedule_long_days.join(", ")} onChange={(e) => setLongText(e.target.value)} />
        </FormField>
        <FormField id="as-short" label={t("fields.alert_schedule_short_hours")} error={errors.alert_schedule_short_hours} hint={t("listHint")}>
          <Input className="ltr" disabled={!editable} value={shortText ?? d.alert_schedule_short_hours.join(", ")} onChange={(e) => setShortText(e.target.value)} />
        </FormField>
      </FormSection>
      <FormSection title={t("section.hooks")} description={t("sectionHint.hooks")}>
        <div className="flex flex-col gap-3 sm:col-span-2" data-testid="hook-policy">
          {HOOK_KINDS.map((k) => {
            const prov = base.hook_providers.find((p) => p.kind === k);
            const policy = (d.hook_policy as Record<string, Schemas["HookPolicy"]>)[k] ?? "warn";
            return (
              <div key={k} className="flex flex-wrap items-center gap-3">
                <span className="min-w-48 text-sm font-medium">{te(`hookKind.${k}`)}</span>
                <Select
                  aria-label={t("policyFor", { kind: te(`hookKind.${k}`) })}
                  data-testid={`hook-policy-${k}`}
                  disabled={!editable}
                  value={policy}
                  onChange={(e) => set("hook_policy", { ...(d.hook_policy as Record<string, Schemas["HookPolicy"]>), [k]: e.target.value as Schemas["HookPolicy"] })}
                  className="w-auto"
                >
                  {HOOK_POLICIES.map((x) => (
                    <option key={x} value={x}>
                      {te(`hookPolicy.${x}`)}
                    </option>
                  ))}
                </Select>
                {prov ? prov.registered ? <StatusBadge status="active" label={t("providerLive")} /> : <StatusBadge status="warn" label={t("providerFrom", { phase: prov.available_from_phase })} /> : null}
              </div>
            );
          })}
          <p className="text-xs text-muted-foreground">{t("blockHint")}</p>
        </div>
        {project.is_airport ? hookMap("hook_requirements_by_adp_category", AREA_CATEGORIES, (x) => te(`areaCategory.${x as Schemas["AreaCategory"]}`)) : null}
        {project.is_airport ? hookMap("hook_requirements_by_vehicle_category", VEHICLE_CATEGORIES, (x) => te(`vehicleCategory.${x as Schemas["VehicleCategory"]}`)) : null}
        {hookMap("hook_requirements_by_crew_role", CREW_ROLES, (x) => te(`crewRole.${x as Schemas["CrewRole"]}`))}
      </FormSection>
      <MutationError error={error} />
      {editable ? (
        <div className="sticky bottom-0 flex justify-end gap-2 border-t bg-background py-3">
          <Button
            variant="outline"
            disabled={!dirty || busy}
            onClick={() => {
              setEdits({});
              setLongText(null);
              setShortText(null);
              setErrors({});
              setError(null);
            }}
          >
            {t("discard")}
          </Button>
          <Button onClick={() => void save()} disabled={!dirty || busy} data-testid="save-access-settings">
            {tc("save")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
