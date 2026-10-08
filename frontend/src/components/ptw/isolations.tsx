"use client";
import { KeyRound, Lock, Plus, Scissors, Trash2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { DeploymentPicker, StepDialog } from "@/components/access/common";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { CheckboxGroup } from "@/components/common/checkbox-group";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { CheckboxField, FormField, FormSection } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SearchFilter, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useAppointments, useIsolation, useIsolations, useLocks, usePersonalLocks, usePtwRefresh } from "@/lib/api/ptw";
import { can, canWrite } from "@/lib/permissions";
import { ENERGY_TYPES, ISOLATION_METHODS, ISOLATION_STATUSES, LOCK_STATUSES, LOCK_TYPES, VERIFICATION_METHODS } from "@/lib/ptw-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { DateTimeInput, IsolationSubNav, nowIso, PermitNo, useNow, userLabel, WorkerRefLabel } from "./common";
import { useSigned } from "./signing";

type S = Schemas;
type Iso = S["IsolationRead"];
type PointIn = S["IsolationPointInput"];
const PAGE_SIZE = 50;

function IsoStatus({ status }: { status: S["IsolationStatus"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="iso-status" data-status={status}>
      <StatusBadge status={status} label={te(`isolationStatus.${status}`)} />
    </span>
  );
}

/* ───────────── register ───────────── */

export function IsolationListPage() {
  return <ProjectGate>{(p) => <IsolationList project={p} />}</ProjectGate>;
}

function IsolationList({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("isolations");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const locale = useLocale();
  const { dateTime } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as S["IsolationStatus"][];
  const energy = s.getAll("energy_type") as S["EnergyType"][];
  const q = useIsolations(project.id, {
    status: status.length ? status : null,
    energy_type: energy.length ? energy : null,
    permit_id: s.get("permit_id") || null,
    long_term: s.getBool("long_term") ?? null,
    review_due: s.getBool("review_due") ?? null,
    q: s.get("q") || null,
    page,
    page_size: PAGE_SIZE,
  });
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          canWrite(me, "isolation.manage", project.id) ? (
            <Button asChild>
              <Link href="/isolations/new" data-testid="new-isolation">
                <Plus aria-hidden />
                {t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <IsolationSubNav />
      <ListToolbar>
        <SearchFilter id="is-q" value={s.get("q") ?? ""} onChange={(v) => s.set({ q: v })} placeholder={t("searchHint")} />
        <MultiSelect id="is-status" label={tc("status")} options={ISOLATION_STATUSES.map((x) => ({ value: x, label: te(`isolationStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
        <MultiSelect id="is-energy" label={t("energy")} options={ENERGY_TYPES.map((x) => ({ value: x, label: te(`energyType.${x}`) }))} value={energy} onChange={(v) => s.set({ energy_type: v })} />
        <SelectFilter id="is-lt" label={t("longTerm")} value={s.get("long_term") === "true" ? "true" : ""} onChange={(v) => s.set({ long_term: v })} options={[{ value: "true", label: tc("yes") }]} />
        <SelectFilter id="is-rd" label={t("reviewDue")} value={s.get("review_due") === "true" ? "true" : ""} onChange={(v) => s.set({ review_due: v })} options={[{ value: "true", label: tc("yes") }]} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="isolations-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("equipment")}</TH>
                <TH>{t("energy")}</TH>
                <TH>{t("points")}</TH>
                <TH>{t("authority")}</TH>
                <TH>{t("permits")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((i) => (
                <TR key={i.id} data-testid="isolation-row" data-iso-no={i.iso_no}>
                  <TD label={t("no")}>
                    <Link href={`/isolations/${i.id}`} className="ltr font-medium text-primary hover:underline">
                      {i.iso_no}
                    </Link>
                    {i.hv ? <span className="ms-1 rounded bg-danger-bg px-1 text-xs text-danger">HV</span> : null}
                  </TD>
                  <TD label={t("equipment")}>{i.equipment_desc}</TD>
                  <TD label={t("energy")}>{i.energy_types.map((x) => te(`energyType.${x}`)).join(", ")}</TD>
                  <TD label={t("points")}>
                    <bdi className="ltr tabular-nums">{i.points.length}</bdi> · <Lock aria-label={t("personalLocks")} className="inline size-3" /> <bdi className="ltr tabular-nums">{i.personal_locks_applied.filter((x) => !x.removed_at).length}</bdi>
                  </TD>
                  <TD label={t("authority")}>{userLabel(i.isolation_authority, locale)}</TD>
                  <TD label={t("permits")}>
                    {i.permits.map((p) => (
                      <span key={p.id} className="me-1 block">
                        <PermitNo p={p} />
                      </span>
                    ))}
                  </TD>
                  <TD label={tc("status")}>
                    <IsoStatus status={i.status} />
                    {i.long_term ? <span className="block text-xs text-muted-foreground">{t("longTerm")}</span> : null}
                    {i.review_due_at ? <span className="ltr block text-xs text-warning">{t("reviewBy", { at: dateTime(i.review_due_at) })}</span> : null}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={q.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState />
      )}
    </div>
  );
}

/* ───────────── create ───────────── */

export function IsolationCreatePage() {
  return <ProjectGate>{(p) => <IsolationCreate project={p} />}</ProjectGate>;
}

function PointsEditor({ points, onChange }: { points: PointIn[]; onChange: (p: PointIn[]) => void }) {
  const t = useTranslations("isolations");
  const te = useTranslations("enums");
  const set = (i: number, p: Partial<PointIn>) => onChange(points.map((x, k) => (k === i ? { ...x, ...p } : x)));
  return (
    <div className="flex flex-col gap-3" data-testid="points-editor">
      {points.map((p, i) => (
        <div key={i} className="grid gap-2 rounded-md border p-3 sm:grid-cols-[10rem_10rem_1fr_12rem_auto]" data-testid="point-row">
          <FormField id={`pt-${i}-e`} label={t("energy")} required>
            <Select id={`pt-${i}-e`} value={p.energy_type} onChange={(e) => set(i, { energy_type: e.target.value as S["EnergyType"] })}>
              {ENERGY_TYPES.map((x) => (
                <option key={x} value={x}>
                  {te(`energyType.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id={`pt-${i}-tag`} label={t("deviceTag")} required>
            <Input id={`pt-${i}-tag`} className="ltr" value={p.device_tag} onChange={(e) => set(i, { device_tag: e.target.value })} />
          </FormField>
          <FormField id={`pt-${i}-loc`} label={t("location")} required>
            <Input id={`pt-${i}-loc`} value={p.location} onChange={(e) => set(i, { location: e.target.value })} />
          </FormField>
          <FormField id={`pt-${i}-m`} label={t("method")} required>
            <Select id={`pt-${i}-m`} value={p.method} onChange={(e) => set(i, { method: e.target.value as S["IsolationMethod"] })}>
              {ISOLATION_METHODS.map((x) => (
                <option key={x} value={x}>
                  {te(`isolationMethod.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <div className="flex items-end">
            <Button size="sm" variant="ghost" aria-label={t("removePoint")} onClick={() => onChange(points.filter((_, k) => k !== i))}>
              <Trash2 aria-hidden />
            </Button>
          </div>
        </div>
      ))}
      <div>
        <Button size="sm" variant="outline" onClick={() => onChange([...points, { energy_type: "electrical", device_tag: "", location: "", method: "isolator_open_locked" }])} data-testid="add-point">
          <Plus aria-hidden />
          {t("addPoint")}
        </Button>
      </div>
    </div>
  );
}

function IsolationCreate({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("isolations");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const router = useRouter();
  const locale = useLocale();
  const authorities = useAppointments(project.id, { function: ["isolation_authority"], status: ["active"], page_size: 200 });
  const boxes = useLocks(project.id, { lock_type: ["lockbox"], status: ["available"], page_size: 200 });
  const [desc, setDesc] = useState("");
  const [energy, setEnergy] = useState<S["EnergyType"][]>(["electrical"]);
  const [hv, setHv] = useState(false);
  const [auth, setAuth] = useState("");
  const [box, setBox] = useState("");
  const [sp, setSp] = useState("");
  const [points, setPoints] = useState<PointIn[]>([{ energy_type: "electrical", device_tag: "", location: "", method: "isolator_open_locked" }]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const users = (authorities.data?.items ?? []).filter((a) => a.holder_user);
  async function save() {
    setBusy(true);
    setError(null);
    try {
      const i = await unwrap(
        api.POST("/api/v1/projects/{project_id}/isolations", {
          params: { path: { project_id: project.id } },
          body: { equipment_desc: desc.trim(), energy_types: energy, hv, isolation_authority_user_id: auth, lockbox_id: box, points: points.map((p) => ({ ...p, device_tag: p.device_tag.trim(), location: p.location.trim() })), switching_programme_ref: sp.trim() || null },
        }),
      );
      toast.success(t("created", { no: i.iso_no }));
      router.push(`/isolations/${i.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex flex-col gap-5">
      <div>
        <Breadcrumbs items={[{ label: t("title"), href: "/isolations" }, { label: t("new") }]} />
        <PageHeader title={t("new")} description={t("newHint")} />
      </div>
      <FormSection title={t("certificate")}>
        <FormField id="ic-desc" label={t("equipment")} required className="sm:col-span-2">
          <Input id="ic-desc" value={desc} onChange={(e) => setDesc(e.target.value)} />
        </FormField>
        <CheckboxGroup id="ic-energy" legend={t("energy")} options={ENERGY_TYPES.map((x) => ({ value: x, label: te(`energyType.${x}`) }))} value={energy} onChange={(v) => setEnergy(v as S["EnergyType"][])} className="sm:col-span-2" />
        <CheckboxField id="ic-hv" label={<>{t("hv")} <span className="block text-xs font-normal text-muted-foreground">{t("hvHint")}</span></>}>
          <Checkbox id="ic-hv" checked={hv} onChange={(e) => setHv(e.target.checked)} />
        </CheckboxField>
        <FormField id="ic-auth" label={t("authority")} required hint={t("authorityHint")}>
          <Select id="ic-auth" value={auth} onChange={(e) => setAuth(e.target.value)}>
            <option value="">—</option>
            {users.map((a) => (
              <option key={a.id} value={a.holder_user?.id ?? ""}>
                {userLabel(a.holder_user, locale)} · {a.appointment_no}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="ic-box" label={t("lockbox")} required>
          <Select id="ic-box" value={box} onChange={(e) => setBox(e.target.value)}>
            <option value="">—</option>
            {(boxes.data?.items ?? []).map((l) => (
              <option key={l.id} value={l.id}>
                {l.lock_no}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="ic-sp" label={t("switchingProgramme")} required={hv}>
          <Input id="ic-sp" className="ltr" value={sp} onChange={(e) => setSp(e.target.value)} />
        </FormField>
      </FormSection>
      <FormSection title={t("isolationPoints")} description={t("pointsHint")}>
        <div className="sm:col-span-2">
          <PointsEditor points={points} onChange={setPoints} />
        </div>
      </FormSection>
      <MutationError error={error} />
      <div className="flex justify-end">
        <Button onClick={() => void save()} disabled={busy || !desc.trim() || !energy.length || !auth || !box || !points.length} data-testid="save-isolation">
          {busy ? tc("saving") : t("createPlanned")}
        </Button>
      </div>
    </div>
  );
}

/* ───────────── certificate page ───────────── */

type PStep = { kind: "apply" | "verify" | "remove"; point: S["IsolationPointRead"] } | { kind: "add" } | { kind: "transition"; to: S["IsolationStatus"] } | { kind: "review" } | { kind: "personal" };

export function IsolationDetail({ id }: { id: string }) {
  const t = useTranslations("isolations");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const me = useMeData();
  const q = useIsolation(id);
  const refresh = usePtwRefresh();
  const now = useNow(60_000);
  const [step, setStep] = useState<PStep | null>(null);
  const { dateTime } = useFormatters(q.data?.project_id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const i = q.data;
  const pid = i.project_id;
  const manage = canWrite(me, "isolation.manage", pid);
  const authorise = canWrite(me, "deisolation.authorise", pid);
  const personal = canWrite(me, "personal_lock.record", pid) || manage;
  const allApplied = i.points.length > 0 && i.points.every((p) => p.applied_at);
  const allVerified = i.points.length > 0 && i.points.every((p) => p.verified_at);
  const transitions: { to: S["IsolationStatus"]; show: boolean; tone: "default" | "outline" | "destructive" }[] = [
    { to: "isolated", show: i.status === "planned" && manage && allApplied, tone: "default" },
    { to: "verified", show: i.status === "isolated" && manage && allVerified, tone: "default" },
    { to: "deisolation_requested", show: i.status === "verified" && (manage || can(me, "permit.receive", pid)), tone: "outline" },
    { to: "deisolated", show: i.status === "deisolation_requested" && (authorise || manage) && i.points.every((p) => p.removed_at), tone: "default" },
    { to: "cancelled", show: i.status === "planned" && manage, tone: "destructive" },
  ];
  return (
    <div className="flex flex-col gap-5" data-testid="isolation-detail" data-status={i.status}>
      <div>
        <Breadcrumbs items={[{ label: t("title"), href: "/isolations" }, { label: i.iso_no }]} />
        <PageHeader title={<bdi className="ltr">{i.iso_no}</bdi>} description={i.equipment_desc} actions={<IsoStatus status={i.status} />} />
      </div>
      {transitions.some((x) => x.show) || (i.long_term && manage) ? (
        <div className="flex flex-wrap gap-2" data-testid="iso-actions">
          {transitions
            .filter((x) => x.show)
            .map((x) => (
              <Button key={x.to} variant={x.tone} onClick={() => setStep({ kind: "transition", to: x.to })} data-testid={`iso-${x.to}`}>
                {t(`to.${x.to}`)}
              </Button>
            ))}
          {i.long_term && i.status === "verified" && manage ? (
            <Button variant="outline" onClick={() => setStep({ kind: "review" })} data-testid="iso-review">
              {t("recordReview")}
            </Button>
          ) : null}
        </div>
      ) : null}
      {i.deisolation_blockers.length && (i.status === "verified" || i.status === "deisolation_requested") ? (
        <Alert tone="warning" data-testid="deisolation-blockers">
          {t("deisolationBlocked")}
          <ul className="mt-1 list-disc ps-5 text-xs">
            {i.deisolation_blockers.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        </Alert>
      ) : null}
      {i.review_due_at && new Date(i.review_due_at).getTime() < now ? <Alert tone="danger">{t("reviewOverdue")}</Alert> : null}
      <Card>
        <CardContent className="pt-5">
          <FieldList>
            <FieldItem label={t("energy")}>{i.energy_types.map((x) => te(`energyType.${x}`)).join(", ")}</FieldItem>
            <FieldItem label={t("hv")}>{i.hv ? tc("yes") : tc("no")}</FieldItem>
            <FieldItem label={t("authority")}>{userLabel(i.isolation_authority, locale)}</FieldItem>
            <FieldItem label={t("lockbox")}>
              <KeyRound aria-hidden className="me-1 inline size-3.5" />
              <bdi className="ltr">{i.lockbox_no}</bdi>
            </FieldItem>
            <FieldItem label={t("switchingProgramme")} ltr>
              {i.switching_programme_ref ?? "—"}
            </FieldItem>
            <FieldItem label={t("permits")}>
              {i.permits.length
                ? i.permits.map((p) => (
                    <span key={p.id} className="me-2">
                      <PermitNo p={p} />
                    </span>
                  ))
                : "—"}
            </FieldItem>
            <FieldItem label={t("verifiedSince")}>
              <span className="ltr">{i.verified_since ? dateTime(i.verified_since) : "—"}</span>
              {i.long_term ? <span className="ms-2 text-xs text-warning">{t("longTerm")}</span> : null}
            </FieldItem>
            {i.last_review ? (
              <FieldItem label={t("lastReview")}>
                {userLabel(i.last_review.reviewed_by, locale)} · <span className="ltr">{dateTime(i.last_review.reviewed_at)}</span> · {i.last_review.lock_tag_in_place ? t("inPlace") : t("notInPlace")}
              </FieldItem>
            ) : null}
            {i.deisolation_authorised_by ? (
              <FieldItem label={t("deisolationAuthorisedBy")}>
                {userLabel(i.deisolation_authorised_by, locale)} · <span className="ltr">{i.deisolation_authorised_at ? dateTime(i.deisolation_authorised_at) : ""}</span>
              </FieldItem>
            ) : null}
          </FieldList>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">{t("isolationPoints")}</CardTitle>
          {i.status === "planned" && manage ? (
            <Button size="sm" variant="outline" onClick={() => setStep({ kind: "add" })} data-testid="add-point">
              <Plus aria-hidden />
              {t("addPoint")}
            </Button>
          ) : null}
        </CardHeader>
        <CardContent>
          <ol className="flex flex-col divide-y rounded-md border" data-testid="iso-points">
            {i.points.map((p) => (
              <li key={p.id} className="flex flex-col gap-1 p-3 text-sm" data-testid="iso-point" data-applied={p.applied_at ? "true" : "false"} data-verified={p.verified_at ? "true" : "false"}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold tabular-nums">#{p.point_no}</span>
                  <bdi className="ltr font-mono">{p.device_tag}</bdi>
                  <span>{p.location}</span>
                  <span className="text-xs text-muted-foreground">
                    {te(`energyType.${p.energy_type}`)} · {te(`isolationMethod.${p.method}`)}
                  </span>
                </div>
                <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-muted-foreground">
                  <span>
                    {t("applied")}: {p.applied_at ? <>{userLabel(p.applied_by, locale)} · <span className="ltr">{dateTime(p.applied_at)}</span> · <Lock aria-hidden className="inline size-3" /> <bdi className="ltr">{p.isolation_lock_no}</bdi> · {t("tag")} <bdi className="ltr">{p.tag_no}</bdi></> : "—"}
                  </span>
                  <span>
                    {t("verified")}: {p.verified_at ? <>{p.verified_by_user ? userLabel(p.verified_by_user, locale) : <WorkerRefLabel w={p.verified_by_worker} />} · <span className="ltr">{dateTime(p.verified_at)}</span> · {p.verification_method ? te(`verificationMethod.${p.verification_method}`) : ""}</> : "—"}
                  </span>
                  {p.removed_at ? (
                    <span>
                      {t("removed")}: {userLabel(p.removed_by, locale)} · <span className="ltr">{dateTime(p.removed_at)}</span>
                    </span>
                  ) : null}
                </div>
                {manage ? (
                  <div className="flex flex-wrap gap-2">
                    {!p.applied_at && i.status === "planned" ? (
                      <Button size="sm" onClick={() => setStep({ kind: "apply", point: p })} data-testid="apply-point">
                        {t("apply")}
                      </Button>
                    ) : null}
                    {p.applied_at && !p.verified_at && (i.status === "isolated" || i.status === "planned") ? (
                      <Button size="sm" onClick={() => setStep({ kind: "verify", point: p })} data-testid="verify-point">
                        {t("verify")}
                      </Button>
                    ) : null}
                    {p.applied_at && !p.removed_at && i.status === "deisolation_requested" ? (
                      <Button size="sm" variant="outline" onClick={() => setStep({ kind: "remove", point: p })} data-testid="remove-point">
                        {t("remove")}
                      </Button>
                    ) : null}
                    {!p.applied_at && i.status === "planned" ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        aria-label={t("removePoint")}
                        onClick={async () => {
                          try {
                            await unwrap(api.DELETE("/api/v1/isolations/{isolation_id}/points/{point_id}", { params: { path: { isolation_id: i.id, point_id: p.id } } }));
                            await refresh();
                          } catch (e) {
                            toast.error(e instanceof Error ? e.message : String(e));
                          }
                        }}
                      >
                        <Trash2 aria-hidden />
                      </Button>
                    ) : null}
                  </div>
                ) : null}
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>

      <PersonalLocks iso={i} canApply={personal && (i.status === "verified" || i.status === "isolated")} onApply={() => setStep({ kind: "personal" })} />
      <HistoryPanel entityType="isolation_certificate" entityId={i.id} projectId={pid} />
      {step ? <IsoStepDialog iso={i} step={step} onClose={() => setStep(null)} /> : null}
    </div>
  );
}

function IsoStepDialog({ iso, step, onClose }: { iso: Iso; step: PStep; onClose: () => void }) {
  const t = useTranslations("isolations");
  const te = useTranslations("enums");
  const me = useMeData();
  const refresh = usePtwRefresh();
  const signed = useSigned();
  const locks = useLocks(iso.project_id, { lock_type: [step.kind === "personal" ? "personal_lock" : "isolation_lock"], status: ["available"], page_size: 200 }, { enabled: step.kind === "apply" || step.kind === "personal" });
  const [lock, setLock] = useState("");
  const [tag, setTag] = useState("");
  const [at, setAt] = useState(nowIso());
  const [method, setMethod] = useState<S["VerificationMethod"]>("test_for_dead");
  const [byWorker, setByWorker] = useState(false);
  const [dep, setDep] = useState<S["DeploymentRead"] | null>(null);
  const [comment, setComment] = useState("");
  const [inPlace, setInPlace] = useState(true);
  const [permit, setPermit] = useState(iso.permits[0]?.id ?? "");
  const [point, setPoint] = useState<PointIn[]>([{ energy_type: iso.energy_types[0] ?? "electrical", device_tag: "", location: "", method: "isolator_open_locked" }]);
  const path = { isolation_id: iso.id };
  let title = "";
  let disabled = false;
  let destructive = false;
  let body: React.ReactNode = null;
  let run: () => Promise<unknown>;
  switch (step.kind) {
    case "apply":
      title = t("applyTitle", { n: step.point.point_no });
      disabled = !lock || !tag.trim();
      run = async () => {
        await unwrap(api.POST("/api/v1/isolations/{isolation_id}/points/{point_id}/apply", { params: { path: { ...path, point_id: step.point.id } }, body: { isolation_lock_id: lock, tag_no: tag.trim(), applied_at: at } }));
        await refresh();
      };
      body = (
        <>
          <FormField id="ap-lock" label={t("isolationLock")} required>
            <Select id="ap-lock" value={lock} onChange={(e) => setLock(e.target.value)} data-testid="apply-lock">
              <option value="">—</option>
              {(locks.data?.items ?? []).map((l) => (
                <option key={l.id} value={l.id}>
                  {l.lock_no}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="ap-tag" label={t("tagNo")} required>
            <Input id="ap-tag" className="ltr" value={tag} onChange={(e) => setTag(e.target.value)} data-testid="apply-tag" />
          </FormField>
          <FormField id="ap-at" label={t("at")} required>
            <DateTimeInput id="ap-at" value={at} onChange={setAt} />
          </FormField>
        </>
      );
      break;
    case "verify":
      title = t("verifyTitle", { n: step.point.point_no });
      disabled = byWorker && !dep;
      run = async () => {
        await signed(() =>
          unwrap(
            api.POST("/api/v1/isolations/{isolation_id}/points/{point_id}/verify", {
              params: { path: { ...path, point_id: step.point.id } },
              body: { verified_by_user_id: byWorker ? null : me.id, verified_by_worker_id: byWorker ? (dep?.worker_id ?? null) : null, verified_at: at, verification_method: method },
            }),
          ),
        );
        await refresh();
      };
      body = (
        <>
          <p className="text-sm text-muted-foreground">{t("verifyHint")}</p>
          <FormField id="vf-method" label={t("verificationMethod")} required>
            <Select id="vf-method" value={method} onChange={(e) => setMethod(e.target.value as S["VerificationMethod"])}>
              {VERIFICATION_METHODS.map((x) => (
                <option key={x} value={x}>
                  {te(`verificationMethod.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <CheckboxField id="vf-worker" label={t("verifiedByWorker")}>
            <Checkbox id="vf-worker" checked={byWorker} onChange={(e) => setByWorker(e.target.checked)} />
          </CheckboxField>
          {byWorker ? <DeploymentPicker id="vf-dep" projectId={iso.project_id} value={dep} onChange={setDep} label={t("verifier")} required status={["mobilised"]} /> : null}
          <FormField id="vf-at" label={t("at")} required>
            <DateTimeInput id="vf-at" value={at} onChange={setAt} />
          </FormField>
        </>
      );
      break;
    case "remove":
      title = t("removeTitle", { n: step.point.point_no });
      run = async () => {
        await unwrap(api.POST("/api/v1/isolations/{isolation_id}/points/{point_id}/remove", { params: { path: { ...path, point_id: step.point.id } }, body: { removed_at: at } }));
        await refresh();
      };
      body = (
        <FormField id="rm-at" label={t("at")} required>
          <DateTimeInput id="rm-at" value={at} onChange={setAt} />
        </FormField>
      );
      break;
    case "add":
      title = t("addPoint");
      disabled = !point[0]?.device_tag.trim() || !point[0]?.location.trim();
      run = async () => {
        const p = point[0];
        if (!p) return;
        await unwrap(api.POST("/api/v1/isolations/{isolation_id}/points", { params: { path }, body: { ...p, device_tag: p.device_tag.trim(), location: p.location.trim() } }));
        await refresh();
      };
      body = <PointsEditor points={point} onChange={(v) => setPoint(v.slice(-1))} />;
      break;
    case "transition":
      title = t(`to.${step.to}`);
      destructive = step.to === "cancelled";
      run = async () => {
        await signed(() => unwrap(api.POST("/api/v1/isolations/{isolation_id}/transitions", { params: { path }, body: { to_status: step.to, comment: comment.trim() || null } })));
        await refresh();
        toast.success(te(`isolationStatus.${step.to}`));
      };
      body = (
        <>
          <p className="text-sm">{t(`toHint.${step.to}`)}</p>
          <FormField id="tr-comment" label={t("comment")}>
            <Textarea id="tr-comment" value={comment} onChange={(e) => setComment(e.target.value)} />
          </FormField>
        </>
      );
      break;
    case "review":
      title = t("recordReview");
      run = async () => {
        await unwrap(api.POST("/api/v1/isolations/{isolation_id}/reviews", { params: { path }, body: { lock_tag_in_place: inPlace, note: comment.trim() || null } }));
        await refresh();
      };
      body = (
        <>
          <CheckboxField id="rv-in" label={t("lockTagInPlace")}>
            <Checkbox id="rv-in" checked={inPlace} onChange={(e) => setInPlace(e.target.checked)} />
          </CheckboxField>
          {!inPlace ? <Alert tone="danger">{t("breachHint")}</Alert> : null}
          <FormField id="rv-note" label={t("comment")}>
            <Textarea id="rv-note" value={comment} onChange={(e) => setComment(e.target.value)} />
          </FormField>
        </>
      );
      break;
    case "personal":
      title = t("applyPersonal");
      disabled = !lock || !dep;
      run = async () => {
        await unwrap(api.POST("/api/v1/isolations/{isolation_id}/personal-locks", { params: { path }, body: { lock_id: lock, worker_id: dep?.worker_id ?? "", applied_at: at, permit_id: permit || null } }));
        await refresh();
      };
      body = (
        <>
          <DeploymentPicker id="pl-dep" projectId={iso.project_id} value={dep} onChange={setDep} label={t("worker")} required status={["mobilised"]} />
          <FormField id="pl-lock" label={t("personalLock")} required>
            <Select id="pl-lock" value={lock} onChange={(e) => setLock(e.target.value)} data-testid="personal-lock-select">
              <option value="">—</option>
              {(locks.data?.items ?? []).map((l) => (
                <option key={l.id} value={l.id}>
                  {l.lock_no}
                  {l.holder_worker ? ` · ${l.holder_worker.worker_no}` : ""}
                </option>
              ))}
            </Select>
          </FormField>
          {iso.permits.length ? (
            <FormField id="pl-permit" label={t("forPermit")}>
              <Select id="pl-permit" value={permit} onChange={(e) => setPermit(e.target.value)}>
                <option value="">—</option>
                {iso.permits.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.display_no}
                  </option>
                ))}
              </Select>
            </FormField>
          ) : null}
          <FormField id="pl-at" label={t("at")} required>
            <DateTimeInput id="pl-at" value={at} onChange={setAt} />
          </FormField>
        </>
      );
      break;
  }
  return (
    <StepDialog title={title} confirmLabel={title} disabled={disabled} destructive={destructive} onConfirm={run} onClose={onClose} wide={step.kind === "add"} testId="iso-step-confirm">
      {body}
    </StepDialog>
  );
}

/* ───────────── personal locks and lock cut ───────────── */

type LStep = { kind: "remove" | "cut" | "informed"; ev: S["PersonalLockEventRead"] };

function PersonalLocks({ iso, canApply, onApply }: { iso: Iso; canApply: boolean; onApply: () => void }) {
  const t = useTranslations("isolations");
  const te = useTranslations("enums");
  const me = useMeData();
  const q = usePersonalLocks(iso.id);
  const { dateTime } = useFormatters(iso.project_id);
  const [step, setStep] = useState<LStep | null>(null);
  const cut = can(me, "lock_cut.approve", iso.project_id);
  const record = can(me, "personal_lock.record", iso.project_id) || can(me, "isolation.manage", iso.project_id);
  const items = q.data?.items ?? iso.personal_locks_applied;
  return (
    <Card data-testid="personal-locks">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="text-base">{t("personalLocksN", { n: items.filter((x) => !x.removed_at).length })}</CardTitle>
        {canApply ? (
          <Button size="sm" onClick={onApply} data-testid="apply-personal-lock">
            <Lock aria-hidden />
            {t("applyPersonal")}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent>
        <p className="mb-2 text-xs text-muted-foreground">{t("groupLockHint", { box: iso.lockbox_no })}</p>
        {items.length ? (
          <ul className="flex flex-col divide-y rounded-md border text-sm">
            {items.map((ev) => (
              <li key={ev.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 p-2" data-testid="personal-lock" data-removed={ev.removed_at ? ev.removed_by ?? "yes" : "no"}>
                <Lock aria-hidden className="size-4 text-muted-foreground" />
                <bdi className="ltr font-mono">{ev.lock_no}</bdi>
                <WorkerRefLabel w={ev.worker} />
                {ev.permit ? <PermitNo p={ev.permit} /> : null}
                <span className="ltr text-xs text-muted-foreground">{dateTime(ev.applied_at)}</span>
                {ev.removed_at ? (
                  <span className="text-xs text-muted-foreground">
                    {ev.removed_by ? te(`lockRemoval.${ev.removed_by}`) : t("removed")} · <span className="ltr">{dateTime(ev.removed_at)}</span>
                  </span>
                ) : null}
                {ev.cut ? (
                  <span className="w-full text-xs text-danger">
                    {t("cutBy", { name: userLabel(ev.cut.approved_by, "en") })} · {ev.cut.worker_informed_at ? t("workerInformedAt", { at: dateTime(ev.cut.worker_informed_at) }) : t("workerNotInformed")}
                  </span>
                ) : null}
                <span className="ms-auto flex gap-2">
                  {!ev.removed_at && record ? (
                    <Button size="sm" variant="outline" onClick={() => setStep({ kind: "remove", ev })} data-testid="remove-personal-lock">
                      {t("holderRemoves")}
                    </Button>
                  ) : null}
                  {!ev.removed_at && cut ? (
                    <Button size="sm" variant="destructive" onClick={() => setStep({ kind: "cut", ev })} data-testid="cut-lock">
                      <Scissors aria-hidden />
                      {t("cut")}
                    </Button>
                  ) : null}
                  {ev.cut && !ev.cut.worker_informed_at && (cut || record) ? (
                    <Button size="sm" variant="outline" onClick={() => setStep({ kind: "informed", ev })} data-testid="worker-informed">
                      {t("recordInformed")}
                    </Button>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">{t("noPersonalLocks")}</p>
        )}
      </CardContent>
      {step ? <LockStepDialog iso={iso} step={step} onClose={() => setStep(null)} /> : null}
    </Card>
  );
}

function LockStepDialog({ iso, step, onClose }: { iso: Iso; step: LStep; onClose: () => void }) {
  const t = useTranslations("isolations");
  const refresh = usePtwRefresh();
  const signed = useSigned();
  const [at, setAt] = useState(nowIso());
  const [absentAt, setAbsentAt] = useState(nowIso());
  const [attempts, setAttempts] = useState("");
  const [sup, setSup] = useState<S["DeploymentRead"] | null>(null);
  const path = { params: { path: { event_id: step.ev.id } } };
  let title = "";
  let disabled = false;
  let body: React.ReactNode = null;
  let run: () => Promise<unknown>;
  if (step.kind === "remove") {
    title = t("holderRemoves");
    run = async () => {
      await unwrap(api.POST("/api/v1/personal-lock-events/{event_id}/remove", { ...path, body: { removed_at: at } }));
      await refresh();
    };
    body = (
      <>
        <p className="text-sm text-muted-foreground">{t("holderOnly")}</p>
        <FormField id="pr-at" label={t("at")} required>
          <DateTimeInput id="pr-at" value={at} onChange={setAt} />
        </FormField>
      </>
    );
  } else if (step.kind === "cut") {
    title = t("cutTitle", { lock: step.ev.lock_no });
    disabled = !sup || attempts.trim().length < 20;
    run = async () => {
      await signed(() => unwrap(api.POST("/api/v1/personal-lock-events/{event_id}/cut", { ...path, body: { supervisor_worker_id: sup?.worker_id ?? null, supervisor_confirmed_absent_at: absentAt, contact_attempts: attempts.trim() } })));
      await refresh();
      toast.success(t("cutToast"));
    };
    body = (
      <>
        <Alert tone="danger">{t("cutHint")}</Alert>
        <DeploymentPicker id="cut-sup" projectId={iso.project_id} value={sup} onChange={setSup} label={t("supervisor")} required />
        <FormField id="cut-absent" label={t("absentConfirmedAt")} required>
          <DateTimeInput id="cut-absent" value={absentAt} onChange={setAbsentAt} />
        </FormField>
        <FormField id="cut-attempts" label={t("contactAttempts")} required hint={t("min20")}>
          <Textarea id="cut-attempts" value={attempts} onChange={(e) => setAttempts(e.target.value)} data-testid="contact-attempts" />
        </FormField>
      </>
    );
  } else {
    title = t("recordInformed");
    run = async () => {
      await unwrap(api.POST("/api/v1/personal-lock-events/{event_id}/worker-informed", { ...path, body: { worker_informed_at: at } }));
      await refresh();
    };
    body = (
      <FormField id="wi-at" label={t("at")} required>
        <DateTimeInput id="wi-at" value={at} onChange={setAt} />
      </FormField>
    );
  }
  return (
    <StepDialog title={title} confirmLabel={title} disabled={disabled} destructive={step.kind === "cut"} onConfirm={run} onClose={onClose} testId="lock-step-confirm">
      {body}
    </StepDialog>
  );
}

/* ───────────── lock register ───────────── */

export function LockRegisterPage() {
  return <ProjectGate>{(p) => <LockRegister project={p} />}</ProjectGate>;
}

function LockRegister({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("isolations");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const types = s.getAll("lock_type") as S["LockType"][];
  const status = s.getAll("status") as S["LockStatus"][];
  const [creating, setCreating] = useState(false);
  const [lost, setLost] = useState<S["LockRead"] | null>(null);
  const q = useLocks(project.id, { lock_type: types.length ? types : null, status: status.length ? status : null, q: s.get("q") || null, page, page_size: PAGE_SIZE });
  const manage = canWrite(me, "isolation.manage", project.id) || canWrite(me, "personal_lock.record", project.id);
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("locks")}
        description={t("locksHint")}
        actions={
          manage ? (
            <Button onClick={() => setCreating(true)} data-testid="new-lock">
              <Plus aria-hidden />
              {t("newLock")}
            </Button>
          ) : null
        }
      />
      <IsolationSubNav />
      <ListToolbar>
        <SearchFilter id="lk-q" value={s.get("q") ?? ""} onChange={(v) => s.set({ q: v })} placeholder={t("lockSearch")} />
        <MultiSelect id="lk-type" label={t("lockType")} options={LOCK_TYPES.map((x) => ({ value: x, label: te(`lockType.${x}`) }))} value={types} onChange={(v) => s.set({ lock_type: v })} />
        <MultiSelect id="lk-status" label={tc("status")} options={LOCK_STATUSES.map((x) => ({ value: x, label: te(`lockStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="locks-table">
            <THead>
              <TR>
                <TH>{t("lockNo")}</TH>
                <TH>{t("lockType")}</TH>
                <TH>{t("holder")}</TH>
                <TH>{t("appliedOn")}</TH>
                <TH>{tc("status")}</TH>
                <TH>
                  <span className="sr-only">{tc("actions")}</span>
                </TH>
              </TR>
            </THead>
            <TBody>
              {items.map((l) => (
                <TR key={l.id} data-testid="lock-row" data-status={l.status}>
                  <TD label={t("lockNo")}>
                    <bdi className="ltr font-mono font-medium">{l.lock_no}</bdi>
                  </TD>
                  <TD label={t("lockType")}>{te(`lockType.${l.lock_type}`)}</TD>
                  <TD label={t("holder")}>
                    <WorkerRefLabel w={l.holder_worker} />
                  </TD>
                  <TD label={t("appliedOn")}>
                    <bdi className="ltr">{l.applied_on ?? "—"}</bdi>
                  </TD>
                  <TD label={tc("status")}>
                    <StatusBadge status={l.status} label={te(`lockStatus.${l.status}`)} />
                  </TD>
                  <TD label="">
                    {manage && (l.status === "available" || l.status === "applied") ? (
                      <Button size="sm" variant="ghost" onClick={() => setLost(l)} data-testid="report-lost">
                        {t("reportLost")}
                      </Button>
                    ) : null}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={q.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState />
      )}
      {creating ? <LockCreateDialog project={project} onClose={() => setCreating(false)} /> : null}
      {lost ? <LockLostDialog lock={lost} onClose={() => setLost(null)} /> : null}
    </div>
  );
}

function LockCreateDialog({ project, onClose }: { project: S["ProjectRead"]; onClose: () => void }) {
  const t = useTranslations("isolations");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const refresh = usePtwRefresh();
  const [type, setType] = useState<S["LockType"]>("personal_lock");
  const [no, setNo] = useState("");
  const [holder, setHolder] = useState<S["DeploymentRead"] | null>(null);
  return (
    <StepDialog
      title={t("newLock")}
      confirmLabel={tc("create")}
      onClose={onClose}
      testId="save-lock"
      onConfirm={async () => {
        const l = await unwrap(api.POST("/api/v1/projects/{project_id}/locks", { params: { path: { project_id: project.id } }, body: { lock_type: type, lock_no: no.trim() || null, holder_worker_id: type === "personal_lock" ? (holder?.worker_id ?? null) : null } }));
        await refresh();
        toast.success(t("lockCreated", { no: l.lock_no }));
      }}
    >
      <FormField id="lc-type" label={t("lockType")} required>
        <Select id="lc-type" value={type} onChange={(e) => setType(e.target.value as S["LockType"])}>
          {LOCK_TYPES.map((x) => (
            <option key={x} value={x}>
              {te(`lockType.${x}`)}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField id="lc-no" label={t("lockNo")} hint={t("lockNoHint")}>
        <Input id="lc-no" className="ltr" value={no} onChange={(e) => setNo(e.target.value)} />
      </FormField>
      {type === "personal_lock" ? <DeploymentPicker id="lc-holder" projectId={project.id} value={holder} onChange={setHolder} label={t("holder")} /> : null}
    </StepDialog>
  );
}

function LockLostDialog({ lock, onClose }: { lock: S["LockRead"]; onClose: () => void }) {
  const t = useTranslations("isolations");
  const refresh = usePtwRefresh();
  const [detail, setDetail] = useState("");
  return (
    <StepDialog
      title={t("lostTitle", { no: lock.lock_no })}
      confirmLabel={t("reportLost")}
      destructive
      disabled={detail.trim().length < 10}
      onClose={onClose}
      testId="lock-lost-confirm"
      onConfirm={async () => {
        await unwrap(api.POST("/api/v1/locks/{lock_id}/lost", { params: { path: { lock_id: lock.id } }, body: { detail: detail.trim() } }));
        await refresh();
      }}
    >
      {lock.status === "applied" ? <Alert tone="danger">{t("lostAppliedHint")}</Alert> : null}
      <FormField id="ll-detail" label={t("whatHappened")} required hint={t("min10")}>
        <Textarea id="ll-detail" value={detail} onChange={(e) => setDetail(e.target.value)} />
      </FormField>
    </StepDialog>
  );
}
