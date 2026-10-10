"use client";
import { Download, FileWarning, Info, Lock, ShieldAlert } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Code, StepDialog } from "@/components/access/common";
import { ApiWarnings } from "@/components/common/api-warnings";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { RecordActions } from "@/components/common/record-actions";
import { ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { StackedDate } from "@/components/medical/common";
import { Link } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useFuPack, useFuRefresh, useFuRequirements } from "@/lib/api/followup";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { useRefLists } from "@/lib/reference";
import { FrozenNote, FuBadge, useFuCaps } from "./common";
import { GeneratePackDialog } from "./actions";

type S = Schemas;

/** Frozen snapshot keys with their labels (PK-2); anything else is shown with its key. */
const SNAP_ORDER = [
  "incident_ref",
  "occurred_date",
  "occurred_time",
  "site",
  "location",
  "title",
  "activity",
  "incident_types",
  "airside_flags",
  "do_category",
  "actual_severity",
  "potential_severity",
  "responsible",
  "description",
  "immediate_actions",
  "causes",
  "root_cause_codes",
  "lesson_no",
] as const;
/** Never shown on a client / PMC copy whatever the snapshot holds (P6f-2: no ID, nationality or medical detail beyond category, body part and days off). */
const CLIENT_HIDDEN = new Set(["id_type", "id_number", "nationality", "nature", "treated_at", "first_day_off"]);
const CASE_KEYS = ["person_name", "id_type", "id_number", "nationality", "occupation", "category", "body_part", "nature", "treated_at", "first_day_off", "days_off"] as const;

export function PackPage({ id }: { id: string }) {
  const t = useTranslations("fu.pack");
  const tn = useTranslations("fu.nav");
  const te = useTranslations("enums");
  const td = useTranslations("fuDesign");
  const name = useLocalizedName();
  const refresh = useFuRefresh();
  const q = useFuPack(id);
  const pk = q.data;
  const caps = useFuCaps(pk?.project_id);
  const reqs = useFuRequirements(pk?.project_id ?? "", { page_size: 200 }, { enabled: Boolean(pk) });
  const [regen, setRegen] = useState(false);
  const [approve, setApprove] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!pk) return <LoadingState />;
  const req = reqs.data?.items.find((r) => r.id === pk.requirement_id);
  const identity = pk.field_set !== "none";
  const editable = caps.record && pk.status === "draft";
  // PK-6: a Contractor HSE Rep approves GOSI packs only; for any other pack the server refuses, so say who approves it.
  const rep = Boolean(caps.me?.projects.find((p) => p.project_id === pk.project_id)?.roles.includes("contractor_hse_rep")) && !caps.me?.is_hse_manager;
  const approver = caps.approve && !(rep && pk.form_code !== "GOSI-WIR");
  const canApprove = approver && pk.status === "draft";
  const canRegen = caps.record && pk.status !== "submitted" && pk.status !== "superseded" && Boolean(req);

  async function back() {
    setBusy(true);
    setError(null);
    try {
      await unwrap(api.POST("/api/v1/notification-packs/{pack_id}/transitions", { params: { path: { pack_id: pk!.id } }, body: { action: "return_to_draft" } }));
      await refresh();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function download() {
    try {
      const u = await unwrap(api.GET("/api/v1/notification-packs/{pack_id}/file-url", { params: { path: { pack_id: pk!.id } } }));
      window.open(u.url, "_blank", "noopener");
    } catch (e) {
      setError(e);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Breadcrumbs items={[{ label: tn("register"), href: "/notification-register" }, { label: pk.pack_no }]} />
      <div className="flex flex-col gap-2">
        <p className="text-sm text-muted-foreground">
          <Code data-testid="pack-no">{pk.pack_no}</Code> · {t("version", { v: pk.version })}
        </p>
        <h1 className="flex flex-wrap items-center gap-2 text-xl font-semibold">
          {te(`fuForm.${pk.form_code}`)}
          <FuBadge group="fuPackStatus" status={pk.status} testId="pack-status" />
        </h1>
        <p className="text-sm">
          {te(`externalBody.${pk.body}`)} · {te(`fuStage.${pk.stage}`)} · <Code>{pk.incident_ref}</Code>
        </p>
      </div>

      {pk.incident_changed ? (
        <Alert tone="warning" data-testid="pack-changed">
          <span className="flex flex-col gap-2">
            {t("changed")}
            {caps.record && pk.status !== "submitted" && req ? (
              <Button size="sm" variant="outline" className="w-fit" onClick={() => setRegen(true)} data-testid="pack-regenerate-changed">
                {t("regenerate")}
              </Button>
            ) : null}
          </span>
        </Alert>
      ) : null}
      {pk.identity_deleted ? <Alert tone="info">{t("identityDeleted")}</Alert> : null}
      {pk.status === "submitted" ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Lock aria-hidden className="size-4" />
          {t("immutable")}
        </p>
      ) : null}
      <ApiWarnings warnings={pk.warnings} />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("about")}</CardTitle>
        </CardHeader>
        <CardContent>
          <FieldList>
            <FieldItem label={t("fieldSet")}>
              <span className="inline-flex flex-wrap items-center gap-2" data-testid="pack-field-set" data-field-set={pk.field_set}>
                {identity ? <ShieldAlert aria-hidden className="size-4 text-warning" /> : null}
                {te(`fuFieldSet.${pk.field_set}`)}
              </span>
            </FieldItem>
            <FieldItem label={t("languages")}>{pk.languages.map((l) => t(`lang.${l as "en" | "ar"}`)).join(" + ")}</FieldItem>
            <FieldItem label={t("preparedBy")}>{pk.prepared_by ? name(pk.prepared_by.full_name_en, pk.prepared_by.full_name_ar) : "—"}</FieldItem>
            <FieldItem label={t("approvedBy")}>
              {pk.approved_by ? (
                <span className="flex flex-col">
                  {name(pk.approved_by.full_name_en, pk.approved_by.full_name_ar)}
                  <StackedDate v={pk.approved_at} time projectId={pk.project_id} />
                </span>
              ) : (
                "—"
              )}
            </FieldItem>
          </FieldList>
          {identity ? <p className="mt-3 text-xs text-muted-foreground">{t("identityNote")}</p> : null}
          {pk.body === "client" ? <p className="mt-3 text-xs text-muted-foreground" data-testid="pack-client-note">{t("clientNote")}</p> : null}
        </CardContent>
      </Card>

      <Snapshot pk={pk} />
      <Narrative key={`${pk.id}-${pk.status}`} pk={pk} editable={editable} />

      <div className="flex flex-wrap gap-2">
        {pk.has_file ? (
          <Button variant="outline" className="min-h-12 sm:min-h-control" onClick={() => void download()} data-testid="pack-download">
            <Download aria-hidden />
            {t("download")}
          </Button>
        ) : null}
        {approver && pk.status === "approved" ? (
          <Button variant="outline" className="min-h-12 sm:min-h-control" disabled={busy} onClick={() => void back()} data-testid="pack-return">
            {t("returnToDraft")}
          </Button>
        ) : null}
        {req ? (
          <Button asChild variant="outline" className="min-h-12 sm:min-h-control">
            <Link href={`/incidents/${req.incident_id}`} data-testid="pack-incident">
              {t("toIncident")}
            </Link>
          </Button>
        ) : null}
      </div>
      <MutationError error={error} />

      {caps.approve && !approver && pk.status === "draft" ? (
        <p className="flex items-start gap-2 text-sm text-muted-foreground" data-testid="pack-approver-note">
          <Info aria-hidden className="mt-0.5 size-4 shrink-0" />
          {td("pack.repApprovesGosi")}
        </p>
      ) : null}
      {canApprove || canRegen ? (
        <RecordActions label={canApprove ? td("pack.endLabel") : t("endLabel")} testId="pack-end">
          {canRegen ? (
            <Button variant="destructive-outline" onClick={() => setRegen(true)} data-testid="pack-regenerate">
              {t("regenerate")}
            </Button>
          ) : null}
          {canApprove ? (
            <Button className="min-h-12 sm:min-h-control" onClick={() => setApprove(true)} data-testid="pack-approve">
              {t("approve")}
            </Button>
          ) : null}
        </RecordActions>
      ) : null}
      {regen && req ? <GeneratePackDialog req={req} onClose={() => setRegen(false)} /> : null}
      {approve ? (
        <StepDialog
          title={t("approveTitle", { no: pk.pack_no })}
          description={t("approveBody")}
          confirmLabel={t("approve")}
          testId="pack-approve-confirm"
          onConfirm={async () => {
            await unwrap(api.POST("/api/v1/notification-packs/{pack_id}/transitions", { params: { path: { pack_id: pk.id } }, body: { action: "approve" } }));
            await refresh();
            toast.success(t("approved"));
          }}
          onClose={() => setApprove(false)}
        />
      ) : null}
    </div>
  );
}

function useSnapValue(projectId?: string | null) {
  const te = useTranslations("enums");
  const ref = useRefLists();
  return function snapValue(k: string, v: unknown): ReactNode {
    if (v === null || v === undefined || v === "") return "—";
    if (Array.isArray(v)) {
      if (k === "incident_types") return v.map((x) => te(`incidentType.${x}` as "incidentType.injury_illness")).join(" · ");
      if (k === "airside_flags") return v.map((x) => te(`airsideFlag.${x}` as "airsideFlag.aircraft_involved")).join(" · ");
      if (k === "root_cause_codes") return <Code>{v.join(", ")}</Code>;
      return v.map(String).join(" · ");
    }
    if (typeof v === "object") return <Code>{JSON.stringify(v)}</Code>;
    const s = String(v);
    if (k === "activity") return ref.label("activity", s);
    if (k === "do_category") return te(`doCategory.${s}` as "doCategory.fire_explosion");
    if (k === "body_part") return ref.label("body_part", s);
    if (k === "nature") return ref.label("nature", s);
    if (k === "occupation" || k === "trade") return ref.label("trade", s);
    if (k === "category") return te(`caseCategory.${s}` as "caseCategory.LTI");
    if ((k === "occurred_date" || k === "first_day_off") && /^\d{4}-\d{2}-\d{2}$/.test(s)) return <StackedDate v={s} projectId={projectId} />;
    if (["incident_ref", "site", "location", "responsible", "lesson_no", "id_number", "occurred_date", "occurred_time", "first_day_off"].includes(k)) return <Code>{s}</Code>;
    return <span className="whitespace-pre-wrap">{s}</span>;
  };
}

/** Field values frozen at generation (PK-2), as the server holds them; identity fields only when the server sends them. */
function Snapshot({ pk }: { pk: S["FuPackRead"] }) {
  const t = useTranslations("fu.pack");
  const ts = useTranslations("fu.snap");
  const ar = useLocale() === "ar";
  const val = useSnapValue(pk.project_id);
  const snap = pk.snapshot as Record<string, unknown> | null;
  const has = (k: string) => (ts as unknown as { has: (k: string) => boolean }).has(k);
  const lbl = (k: string) => (has(k) ? ts(k as "title") : k);
  if (!snap) {
    return (
      <Alert tone="info" data-testid="pack-no-snapshot">
        <span className="inline-flex items-center gap-2">
          <FileWarning aria-hidden className="size-4" />
          {t("noSnapshot")}
        </span>
      </Alert>
    );
  }
  const keys = [...SNAP_ORDER.filter((k) => k in snap), ...Object.keys(snap).filter((k) => !(SNAP_ORDER as readonly string[]).includes(k) && !["cases", "employer", "corrective_actions"].includes(k))];
  const cases = (snap.cases as Record<string, unknown>[] | undefined) ?? [];
  const employer = snap.employer as Record<string, unknown> | undefined;
  const cas = (snap.corrective_actions as { ref: string; control_level: string; status: string }[] | undefined) ?? [];
  return (
    <Card data-testid="pack-snapshot">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center justify-between gap-2 text-base">
          {t("snapshot")}
          <FrozenNote />
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <FieldList>
          {keys.map((k) => (
            <FieldItem key={k} label={lbl(k)} wide={k === "description" || k === "immediate_actions" || k === "causes"}>
              {val(k, snap[k])}
            </FieldItem>
          ))}
          {employer ? (
            <FieldItem label={ts("employer")}>
              <span className="flex flex-col">
                <span>{String((ar ? employer.name_ar : employer.name_en) ?? employer.code ?? "—")}</span>
                {employer.cr_number ? (
                  <span className="text-xs text-muted-foreground">
                    {ts("cr")} <Code>{String(employer.cr_number)}</Code>
                  </span>
                ) : null}
              </span>
            </FieldItem>
          ) : null}
        </FieldList>
        {cases.length ? (
          <div className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold">{ts("cases")}</h3>
            <ul className="flex flex-col gap-2" data-testid="pack-cases">
              {cases.map((c, i) => (
                <li key={i} className="rounded-md border p-3 text-sm" data-testid="pack-case">
                  <p className="font-medium" data-testid="pack-case-label">
                    <bdi>{String((ar ? c.label_ar : c.label) ?? c.label ?? "")}</bdi>
                  </p>
                  <dl className="mt-1 grid gap-x-4 gap-y-1 sm:grid-cols-2">
                    {CASE_KEYS.filter((k) => k in c && !(pk.body === "client" && CLIENT_HIDDEN.has(k))).map((k) => (
                      <div key={k} className="flex gap-2">
                        <dt className="text-muted-foreground">{lbl(k)}</dt>
                        <dd>{val(k, c[k])}</dd>
                      </div>
                    ))}
                  </dl>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {cas.length ? (
          <Table>
            <THead>
              <TR>
                <TH>{ts("caRef")}</TH>
                <TH>{ts("controlLevel")}</TH>
              </TR>
            </THead>
            <TBody>
              {cas.map((c) => (
                <TR key={c.ref}>
                  <TD label={ts("caRef")}>
                    <Code>{c.ref}</Code>
                  </TD>
                  <TD label={ts("controlLevel")}>{c.control_level}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        ) : null}
      </CardContent>
    </Card>
  );
}

/** Narrative EN / AR side by side (Arabic RTL, English LTR whatever the page language); editable while Draft. */
function Narrative({ pk, editable }: { pk: S["FuPackRead"]; editable: boolean }) {
  const t = useTranslations("fu.pack");
  const refresh = useFuRefresh();
  const [en, setEn] = useState(pk.narrative_en ?? "");
  const [arText, setAr] = useState(pk.narrative_ar ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const dirty = en !== (pk.narrative_en ?? "") || arText !== (pk.narrative_ar ?? "");
  async function save() {
    setBusy(true);
    setError(null);
    try {
      await unwrap(api.PATCH("/api/v1/notification-packs/{pack_id}", { params: { path: { pack_id: pk.id } }, body: { narrative_en: en.trim() || null, narrative_ar: arText.trim() || null } }));
      await refresh();
      toast.success(t("saved"));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card data-testid="pack-narrative">
      <CardHeader>
        <CardTitle className="text-base">{t("narrative")}</CardTitle>
        <p className="text-xs text-muted-foreground">{t("narrativeHint")}</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="grid gap-4 md:grid-cols-2">
          <FormField id="pk-en" label={t("lang.en")}>
            <Textarea dir="ltr" lang="en" rows={6} value={en} disabled={!editable} onChange={(e) => setEn(e.target.value)} maxLength={3000} data-testid="pk-narrative-en" />
          </FormField>
          <FormField id="pk-ar" label={t("lang.ar")}>
            <Textarea dir="rtl" lang="ar" rows={6} value={arText} disabled={!editable} onChange={(e) => setAr(e.target.value)} maxLength={3000} data-testid="pk-narrative-ar" />
          </FormField>
        </div>
        <MutationError error={error} />
        {editable ? (
          <Button className="w-fit" disabled={busy || !dirty} onClick={() => void save()} data-testid="pk-save">
            {t("saveNarrative")}
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}
