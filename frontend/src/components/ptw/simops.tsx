"use client";
import { useQueryClient } from "@tanstack/react-query";
import { Check, Clock, PenLine, Plus, Trash2 } from "lucide-react";
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
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { ExportButtons } from "@/components/common/export-buttons";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { ProjectById, ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { Code, StepDialog } from "@/components/access/common";
import { useMeData } from "@/components/shell/me-context";
import { Link } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { pk, useConflict, useConflicts, usePtwRefresh } from "@/lib/api/ptw";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { can, canWrite } from "@/lib/permissions";
import { SIMOPS_CONFLICT_STATUSES, SIMOPS_RESULTS } from "@/lib/ptw-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { PermitNo, PermitsSubNav, SimopsResultBadge, TypeChips, userLabel } from "./common";
import { SigningNotice, useSigned } from "./signing";

type S = Schemas;
const PAGE_SIZE = 50;

/** Result of a SIMOPS check (preview or stored): every rule match with distance, overlap and required controls. */
export function SimopsCheckView({ result }: { result: S["SimopsCheckResult"] }) {
  const t = useTranslations("simops");
  const te = useTranslations("enums");
  const name = useLocalizedName();
  const { dateTime } = useFormatters();
  if (!result.matches.length)
    return (
      <Alert tone="success" data-testid="simops-clear">
        {t("noConflicts")}
        {result.resolved_by_change.length ? <span className="block text-xs">{t("resolvedByChange", { list: result.resolved_by_change.join(", ") })}</span> : null}
      </Alert>
    );
  return (
    <div className="flex flex-col gap-2" data-testid="simops-matches">
      <p className="text-sm font-medium">
        {t("summary", { prohibited: result.prohibited, conditional: result.conditional })}
      </p>
      <ul className="flex flex-col gap-2">
        {result.matches.map((m, i) => (
          <li
            key={`${m.rule_code}-${m.other_permit.id}-${i}`}
            className={m.result === "prohibited" ? "rounded-md border border-danger/40 bg-danger-bg p-3 text-sm" : "rounded-md border border-warning/40 bg-warning-bg p-3 text-sm"}
            data-testid="simops-match"
            data-rule={m.rule_code}
            data-result={m.result}
          >
            <div className="flex flex-wrap items-center gap-2">
              <SimopsResultBadge result={m.result} />
              <Code>{m.rule_code}</Code>
              <span>{t("with")}</span>
              <PermitNo p={m.other_permit} />
              <TypeChips types={m.other_permit.work_types} primary={m.other_permit.primary_type} short />
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {m.distance_m !== null ? (
                <>
                  {t("distance")}: <bdi className="ltr tabular-nums">{m.distance_m} m</bdi> ({te(`distanceBasis.${m.distance_basis}`)})
                </>
              ) : (
                te(`distanceBasis.${m.distance_basis}`)
              )}
              {m.vertical_note ? <> · {m.vertical_note}</> : null} · {t("overlap")}: <span className="ltr">{dateTime(m.overlap_from)} – {dateTime(m.overlap_to)}</span>
            </p>
            {name(m.required_controls_en, m.required_controls_ar) ? (
              <p className="mt-1 text-sm">
                <span className="font-medium">{t("requiredControls")}:</span> {name(m.required_controls_en, m.required_controls_ar)}
              </p>
            ) : null}
            {m.conflict_id ? (
              <p className="mt-1 text-xs">
                <Link href={`/simops-conflicts/${m.conflict_id}`} className="text-primary hover:underline">
                  {t("openConflict")}
                </Link>{" "}
                {m.conflict_status ? `· ${te(`simopsConflictStatus.${m.conflict_status}`)}` : null} {m.coordinated ? `· ${t("coordinated")}` : null}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ───────────── conflict register ───────────── */

export function ConflictListPage() {
  return <ProjectGate>{(p) => <ConflictList project={p} />}</ProjectGate>;
}

function ConflictList({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("simops");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const opts = useProjectOptions(project.id);
  const { dateTime } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as S["SimopsConflictStatus"][];
  const q = useConflicts(project.id, {
    status: status.length ? status : null,
    result: (s.get("result") as S["SimopsResult"] | null) || null,
    zone_id: s.getAll("zone_id").length ? s.getAll("zone_id") : null,
    permit_id: s.get("permit_id") || null,
    awaiting_me: s.getBool("awaiting_me") ?? undefined,
    page,
    page_size: PAGE_SIZE,
  });
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <PermitsSubNav />
      <ListToolbar actions={can(me, "export.ptw", project.id) ? <ExportButtons dataset="simops_conflicts" params={{ project_id: project.id }} /> : null}>
        <MultiSelect id="sc-status" label={tc("status")} options={SIMOPS_CONFLICT_STATUSES.map((x) => ({ value: x, label: te(`simopsConflictStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
        <SelectFilter id="sc-result" label={t("result")} value={(s.get("result") ?? "") as S["SimopsResult"] | ""} onChange={(v) => s.set({ result: v })} options={SIMOPS_RESULTS.map((x) => ({ value: x, label: te(`simopsResult.${x}`) }))} />
        <SelectFilter id="sc-zone" label={tc("zone")} value={s.get("zone_id") ?? ""} onChange={(v) => s.set({ zone_id: v })} options={opts.zones.map((z) => ({ value: z.value, label: z.label }))} />
        <SelectFilter id="sc-awaiting" label={t("awaitingMe")} value={s.get("awaiting_me") === "true" ? "true" : ""} onChange={(v) => s.set({ awaiting_me: v })} options={[{ value: "true", label: tc("yes") }]} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="conflicts-table">
            <THead>
              <TR>
                <TH>{t("conflictNo")}</TH>
                <TH>{t("permits")}</TH>
                <TH>{t("rule")}</TH>
                <TH>{t("distance")}</TH>
                <TH>{t("overlap")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((c) => (
                <TR key={c.id} data-testid="conflict-row" data-no={c.conflict_no}>
                  <TD label={t("conflictNo")}>
                    <Link href={`/simops-conflicts/${c.id}`} className="ltr font-medium text-primary hover:underline">
                      {c.conflict_no}
                    </Link>
                  </TD>
                  <TD label={t("permits")}>
                    <span className="flex flex-col">
                      <PermitNo p={c.permit_a} />
                      <PermitNo p={c.permit_b} />
                    </span>
                  </TD>
                  <TD label={t("rule")}>
                    <Code>{c.rule_code}</Code> <SimopsResultBadge result={c.result} />
                  </TD>
                  <TD label={t("distance")}>{c.distance_m !== null ? <bdi className="ltr tabular-nums">{c.distance_m} m</bdi> : te(`distanceBasis.${c.distance_basis}`)}</TD>
                  <TD label={t("overlap")}>
                    <span className="text-xs">{c.overlap_from ? `${dateTime(c.overlap_from)} – ${dateTime(c.overlap_to)}` : "—"}</span>
                  </TD>
                  <TD label={tc("status")}>
                    <StatusBadge status={c.status} label={te(`simopsConflictStatus.${c.status}`)} />
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

/* ───────────── conflict detail + coordination ───────────── */

export function ConflictDetail({ id }: { id: string }) {
  const q = useConflict(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  return <ProjectById id={q.data.project_id}>{(p) => <ConflictView project={p} c={q.data} />}</ProjectById>;
}

function ConflictView({ project, c }: { project: S["ProjectRead"]; c: S["SimopsConflictRead"] }) {
  const t = useTranslations("simops");
  const te = useTranslations("enums");
  const me = useMeData();
  const locale = useLocale();
  const name = useLocalizedName();
  const qc = useQueryClient();
  const refresh = usePtwRefresh();
  const signed = useSigned();
  const { dateTime } = useFormatters(project.id);
  const [create, setCreate] = useState(false);
  const [sign, setSign] = useState(false);
  const coord = c.coordination;
  const mayCoordinate = canWrite(me, "simops.coordinate", project.id);
  const pendingMine = coord ? coord.signatures.some((x) => x.user.id === me.id && !x.signed_at) : false;
  const requiredMine = c.required_signers.some((x) => x.user.id === me.id);
  async function done() {
    await qc.invalidateQueries({ queryKey: pk.conflict(c.id) });
    await refresh();
  }
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Breadcrumbs items={[{ label: t("title"), href: "/simops-conflicts" }, { label: c.conflict_no }]} />
        <PageHeader
          title={c.conflict_no}
          description={`${c.rule_code} · ${te(`simopsResult.${c.result}`)}`}
          actions={
            <>
              <span data-testid="conflict-status" data-status={c.status}>
                <StatusBadge status={c.status} label={te(`simopsConflictStatus.${c.status}`)} />
              </span>
              {c.status === "open" && c.result === "conditional" && !coord && mayCoordinate && requiredMine ? (
                <Button onClick={() => setCreate(true)} data-testid="create-coordination">
                  <Plus aria-hidden />
                  {t("createCoordination")}
                </Button>
              ) : null}
              {coord && pendingMine ? (
                <Button onClick={() => setSign(true)} data-testid="sign-coordination">
                  <PenLine aria-hidden />
                  {t("signCoordination")}
                </Button>
              ) : null}
            </>
          }
        />
      </div>
      {c.result === "prohibited" && c.status === "open" ? <Alert tone="danger">{t("prohibitedHint")}</Alert> : null}
      {c.result === "conditional" && c.status === "open" ? <Alert tone="warning">{t("conditionalHint")}</Alert> : null}
      <Card>
        <CardContent className="pt-5">
          <FieldList>
            <FieldItem label={t("permitA")}>
              <PermitNo p={c.permit_a} /> <TypeChips types={c.permit_a.work_types} primary={c.permit_a.primary_type} short />
            </FieldItem>
            <FieldItem label={t("permitB")}>
              <PermitNo p={c.permit_b} /> <TypeChips types={c.permit_b.work_types} primary={c.permit_b.primary_type} short />
            </FieldItem>
            <FieldItem label={t("distance")}>
              {c.distance_m !== null ? <bdi className="ltr tabular-nums">{c.distance_m} m</bdi> : "—"} ({te(`distanceBasis.${c.distance_basis}`)})
            </FieldItem>
            <FieldItem label={t("overlap")}>{c.overlap_from ? `${dateTime(c.overlap_from)} – ${dateTime(c.overlap_to)}` : "—"}</FieldItem>
            <FieldItem label={t("detected")}>{dateTime(c.detected_at)}</FieldItem>
            {c.resolved_at ? <FieldItem label={t("resolved")}>{dateTime(c.resolved_at)}</FieldItem> : null}
            <FieldItem label={t("requiredControls")} wide>
              {name(c.required_controls_en, c.required_controls_ar) || "—"}
            </FieldItem>
          </FieldList>
        </CardContent>
      </Card>
      <Card data-testid="coordination">
        <CardHeader>
          <CardTitle className="text-base">{t("coordinationTitle")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {coord ? (
            <>
              <p className="text-sm">
                <StatusBadge status={coord.status === "signed" ? "approved" : coord.status === "expired" ? "expired" : "pending"} label={te(`coordinationStatus.${coord.status}`)} />{" "}
                <span className="text-xs text-muted-foreground">{t("validUntil", { at: dateTime(coord.valid_until) })}</span>
              </p>
              <p className="text-sm whitespace-pre-wrap">{name(coord.agreed_controls_en, coord.agreed_controls_ar)}</p>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">{t("noCoordination")}</p>
          )}
          <SignerList signers={coord ? coord.signatures : c.required_signers} />
        </CardContent>
      </Card>
      {create ? (
        <CoordinationDialog
          conflict={c}
          onClose={() => setCreate(false)}
          onDone={done}
          signed={signed}
          meId={me.id}
          locale={locale}
        />
      ) : null}
      {sign && coord ? (
        <StepDialog
          title={t("signCoordination")}
          description={name(coord.agreed_controls_en, coord.agreed_controls_ar)}
          confirmLabel={t("sign")}
          onClose={() => setSign(false)}
          testId="confirm-sign-coordination"
          onConfirm={async () => {
            await signed(() => unwrap(api.POST("/api/v1/simops-coordinations/{coordination_id}/sign", { params: { path: { coordination_id: coord.id } }, body: {} })));
            await done();
            toast.success(t("signedToast"));
          }}
        >
          <SigningNotice />
        </StepDialog>
      ) : null}
    </div>
  );
}

function SignerList({ signers }: { signers: S["CoordinationSignature"][] }) {
  const te = useTranslations("enums");
  const t = useTranslations("simops");
  const locale = useLocale();
  const { dateTime } = useFormatters();
  return (
    <ul className="flex flex-col divide-y rounded-md border" data-testid="coordination-signers">
      {signers.map((s) => (
        <li key={`${s.role}-${s.user.id}`} className="flex items-center gap-2 p-2 text-sm" data-testid="coordination-signer" data-signed={s.signed_at ? "true" : "false"}>
          {s.signed_at ? <Check aria-label={t("signed")} className="size-4 text-success" /> : <Clock aria-label={t("pending")} className="size-4 text-warning" />}
          <span className="flex-1">
            {userLabel(s.user, locale)} <span className="text-xs text-muted-foreground">· {te(`coordinationRole.${s.role}`)}</span>
          </span>
          <span className="text-xs text-muted-foreground">{s.signed_at ? dateTime(s.signed_at) : t("pending")}</span>
        </li>
      ))}
    </ul>
  );
}

function CoordinationDialog({
  conflict,
  onClose,
  onDone,
  signed,
  meId,
  locale,
}: {
  conflict: S["SimopsConflictRead"];
  onClose: () => void;
  onDone: () => Promise<void>;
  signed: ReturnType<typeof useSigned>;
  meId: string;
  locale: string;
}) {
  const t = useTranslations("simops");
  const tc = useTranslations("common");
  const others = conflict.required_signers.filter((s) => s.user.id !== meId);
  const [en, setEn] = useState(conflict.required_controls_en ?? "");
  const [ar, setAr] = useState(conflict.required_controls_ar ?? "");
  const [cos, setCos] = useState<{ user_id: string; password: string }[]>([]);
  const free = others.filter((o) => !cos.some((c) => c.user_id === o.user.id));
  return (
    <StepDialog
      title={t("createCoordination")}
      description={t("createHint")}
      confirmLabel={t("signAndSave")}
      disabled={en.trim().length < 30 || cos.some((c) => !c.user_id || !c.password)}
      onClose={onClose}
      wide
      testId="save-coordination"
      onConfirm={async () => {
        await signed(() =>
          unwrap(
            api.POST("/api/v1/simops-conflicts/{conflict_id}/coordination", {
              params: { path: { conflict_id: conflict.id } },
              body: { agreed_controls_en: en.trim(), agreed_controls_ar: ar.trim() || null, cosigners: cos },
            }),
          ),
        );
        await onDone();
        toast.success(t("createdToast"));
      }}
    >
      <FormField id="co-en" label={t("agreedEn")} required hint={t("min30")}>
        <Textarea value={en} onChange={(e) => setEn(e.target.value)} maxLength={2000} rows={4} data-testid="co-agreed-en" />
      </FormField>
      <FormField id="co-ar" label={t("agreedAr")}>
        <Textarea dir="rtl" value={ar} onChange={(e) => setAr(e.target.value)} maxLength={2000} rows={3} />
      </FormField>
      <div className="flex flex-col gap-2 rounded-md border p-3">
        <p className="text-sm font-medium">{t("cosignersTitle")}</p>
        <p className="text-xs text-muted-foreground">{t("cosignersHint")}</p>
        {cos.map((c, i) => (
          <div key={i} className="grid gap-2 sm:grid-cols-[1fr_1fr_auto] sm:items-end" data-testid="cosigner-row">
            <FormField id={`co-user-${i}`} label={t("cosigner")}>
              <Select value={c.user_id} onChange={(e) => setCos(cos.map((x, j) => (j === i ? { ...x, user_id: e.target.value } : x)))}>
                <option value="">{tc("select")}</option>
                {others
                  .filter((o) => o.user.id === c.user_id || free.includes(o))
                  .map((o) => (
                    <option key={o.user.id} value={o.user.id}>
                      {userLabel(o.user, locale)}
                    </option>
                  ))}
              </Select>
            </FormField>
            <FormField id={`co-pw-${i}`} label={t("cosignerPassword")}>
              <Input type="password" autoComplete="off" value={c.password} onChange={(e) => setCos(cos.map((x, j) => (j === i ? { ...x, password: e.target.value } : x)))} data-testid={`co-pw-${i}`} />
            </FormField>
            <Button type="button" variant="ghost" onClick={() => setCos(cos.filter((_, j) => j !== i))} aria-label={tc("remove")}>
              <Trash2 aria-hidden />
            </Button>
          </div>
        ))}
        {free.length ? (
          <Button type="button" variant="outline" size="sm" className="self-start" onClick={() => setCos([...cos, { user_id: free[0]?.user.id ?? "", password: "" }])} data-testid="add-cosigner">
            <Plus aria-hidden />
            {t("addCosigner")}
          </Button>
        ) : null}
      </div>
      <SigningNotice />
    </StepDialog>
  );
}
