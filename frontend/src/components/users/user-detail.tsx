"use client";
import { Pencil, Plus } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList, YesNo } from "@/components/common/field-list";
import { HistoryPanel } from "@/components/common/history-panel";
import { PageHeader } from "@/components/common/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import { TransitionActions } from "@/components/common/transition-actions";
import { ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { useMeData } from "@/components/shell/me-context";
import { AssignmentFields, assignmentSchema, emptyAssignment, toAssignmentCreate, type AssignmentValue } from "@/components/users/assignment-fields";
import { Link } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { keys, useContractor, useEngagement, useRoleAssignments, useSites, useUser } from "@/lib/api/queries";
import { useCurrentProject } from "@/lib/current-project";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { can } from "@/lib/permissions";
import { USER_FLOW } from "@/lib/workflows";
import { useFormatters } from "@/lib/use-formatters";


type Kind = "deactivate" | "unlock" | "reactivate";

function SiteCodes({ projectId, ids }: { projectId: string; ids: string[] }) {
  const t = useTranslations("assignment.fields");
  const sites = useSites(projectId, { page_size: 100 });
  if (ids.length === 0) return <span className="text-muted-foreground">{t("allSites")}</span>;
  const m = new Map((sites.data?.items ?? []).map((s) => [s.id, s.code]));
  return <span className="ltr">{ids.map((i) => m.get(i) ?? "…").join(", ")}</span>;
}

function EngagementCode({ id }: { id: string }) {
  const e = useEngagement(id);
  return <span className="ltr">{e.data?.contractor.short_code ?? "…"}</span>;
}

function EmployerName({ id }: { id: string }) {
  const c = useContractor(id);
  const name = useLocalizedName();
  if (!c.data) return <>…</>;
  return (
    <Link href={`/contractors/${id}`} className="text-primary hover:underline">
      <span className="ltr">{c.data.short_code}</span> — {name(c.data.legal_name_en, c.data.legal_name_ar)}
    </Link>
  );
}

export function UserDetail({ userId }: { userId: string }) {
  const t = useTranslations("user");
  const ta = useTranslations("assignment");
  const tr = useTranslations("role");
  const tn = useTranslations("nav");
  const tc = useTranslations("common");
  const tv = useTranslations("validation");
  const me = useMeData();
  const qc = useQueryClient();
  const name = useLocalizedName();
  const { dateTime, date } = useFormatters();
  const { projects } = useCurrentProject();
  const projectCode = new Map(projects.map((p) => [p.id, p.code]));
  const q = useUser(userId);
  const assignments = useRoleAssignments(userId);
  const [assignOpen, setAssignOpen] = useState(false);
  const [draft, setDraft] = useState<AssignmentValue>(emptyAssignment);
  const [draftErrors, setDraftErrors] = useState<Partial<Record<keyof AssignmentValue, { message?: string }>>>({});
  const [revoking, setRevoking] = useState<Schemas["RoleAssignmentRead"] | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const u = q.data;
  const self = u.id === me.id;
  const canInvite = can(me, "user.invite") && !self;
  const canStatus = can(me, "user.manage_status") && !self;
  const list = assignments.data?.items ?? u.role_assignments;

  async function refresh() {
    await Promise.all([
      qc.invalidateQueries({ queryKey: keys.user(u.id) }),
      qc.invalidateQueries({ queryKey: keys.roleAssignments(u.id) }),
      qc.invalidateQueries({ queryKey: ["users"] }),
      qc.invalidateQueries({ queryKey: ["history"] }),
    ]);
  }

  async function transition(to: Schemas["UserStatus"], reason: string | null) {
    const res = await unwrap(api.POST("/api/v1/users/{user_id}/transitions", { params: { path: { user_id: u.id } }, body: { to_status: to, reason } }));
    qc.setQueryData(keys.user(u.id), res);
    await refresh();
  }

  async function resend() {
    setActionError(null);
    try {
      await unwrap(api.POST("/api/v1/users/{user_id}/resend-invite", { params: { path: { user_id: u.id } } }));
      toast.success(t("actions.inviteResent"));
      await refresh();
    } catch (e) {
      setActionError(e);
    }
  }

  async function submitAssign() {
    const parsed = assignmentSchema(tv).safeParse(draft);
    if (!parsed.success) {
      const errs: Partial<Record<keyof AssignmentValue, { message?: string }>> = {};
      for (const i of parsed.error.issues) errs[i.path[0] as keyof AssignmentValue] = { message: i.message };
      setDraftErrors(errs);
      return;
    }
    setDraftErrors({});
    setBusy(true);
    setActionError(null);
    try {
      await unwrap(api.POST("/api/v1/users/{user_id}/role-assignments", { params: { path: { user_id: u.id } }, body: toAssignmentCreate(draft) }));
      toast.success(ta("assigned"));
      setAssignOpen(false);
      setDraft(emptyAssignment);
      await refresh();
    } catch (e) {
      setActionError(e);
    } finally {
      setBusy(false);
    }
  }

  async function submitRevoke() {
    if (!revoking) return;
    setBusy(true);
    setActionError(null);
    try {
      await unwrap(
        api.POST("/api/v1/users/{user_id}/role-assignments/{assignment_id}/revoke", {
          params: { path: { user_id: u.id, assignment_id: revoking.id } },
        }),
      );
      toast.success(ta("revoked"));
      setRevoking(null);
      await refresh();
    } catch (e) {
      setActionError(e);
    } finally {
      setBusy(false);
    }
  }

  const options = canStatus ? USER_FLOW[u.status].map((e) => ({ to: e.to, reasonRequired: e.reasonRequired, label: t(`actions.${e.kind as Kind}`), destructive: e.to === "deactivated" })) : [];

  return (
    <div>
      <Breadcrumbs items={[{ label: tn("users"), href: "/users" }, { label: name(u.full_name_en, u.full_name_ar) }]} />
      <PageHeader
        title={<span data-testid="user-title">{name(u.full_name_en, u.full_name_ar)}</span>}
        badge={<StatusBadge status={u.status} label={t(`status.${u.status}`)} />}
        actions={
          canInvite ? (
            <Button variant="outline" asChild>
              <Link href={`/users/${u.id}/edit`}>
                <Pencil aria-hidden />
                {tc("edit")}
              </Link>
            </Button>
          ) : null
        }
      />
      {self ? (
        <Alert tone="info" className="mb-4" data-testid="self-note">
          {t("selfNote")}
        </Alert>
      ) : null}
      {!assignOpen && !revoking ? <MutationError error={actionError} /> : null}
      <div className="mt-4 grid gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-6 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>{tc("details")}</CardTitle>
            </CardHeader>
            <CardContent>
              <FieldList>
                <FieldItem label={t("fields.email")} ltr>{u.email ?? t("contactHidden")}</FieldItem>
                <FieldItem label={t("fields.mobile")} ltr>{u.mobile ?? "—"}</FieldItem>
                <FieldItem label={t("fields.full_name_en")}>{u.full_name_en}</FieldItem>
                <FieldItem label={t("fields.full_name_ar")}>{u.full_name_ar ?? "—"}</FieldItem>
                <FieldItem label={t("fields.employer_type")}>{t(`employerType.${u.employer_type}`)}</FieldItem>
                {u.employer_contractor_id ? (
                  <FieldItem label={t("fields.employer_contractor")}>
                    <EmployerName id={u.employer_contractor_id} />
                  </FieldItem>
                ) : null}
                <FieldItem label={t("fields.job_title")}>{u.job_title ?? "—"}</FieldItem>
                <FieldItem label={t("fields.preferred_language")}>{u.preferred_language === "ar" ? tc("arabic") : tc("english")}</FieldItem>
                <FieldItem label={t("fields.last_login_at")}>{u.last_login_at ? dateTime(u.last_login_at) : t("neverLoggedIn")}</FieldItem>
                {u.invite_expires_at ? <FieldItem label={t("fields.invite_expires_at")}>{dateTime(u.invite_expires_at)}</FieldItem> : null}
                {u.locked_until ? <FieldItem label={t("fields.locked_until")}>{dateTime(u.locked_until)}</FieldItem> : null}
                <FieldItem label={t("fields.mfa_enabled")}>
                  <YesNo value={u.mfa_enabled} yes={tc("yes")} no={tc("no")} />
                </FieldItem>
                <FieldItem label={t("fields.privacy_ack")}>
                  {u.privacy_notice_ack_at ? `${dateTime(u.privacy_notice_ack_at)} (${u.privacy_notice_version ?? ""})` : "—"}
                </FieldItem>
                {u.status_reason ? <FieldItem label={t("fields.status_reason")}>{u.status_reason}</FieldItem> : null}
              </FieldList>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
              <CardTitle>{ta("title")}</CardTitle>
              {canInvite && u.status !== "deactivated" ? (
                <Button size="sm" onClick={() => { setActionError(null); setAssignOpen(true); }} data-testid="assign-role">
                  <Plus aria-hidden />
                  {ta("assign")}
                </Button>
              ) : null}
            </CardHeader>
            <CardContent>
              {list.length === 0 ? (
                <p className="text-sm text-muted-foreground">{ta("none")}</p>
              ) : (
                <Table data-testid="assignments-table">
                  <THead>
                    <TR>
                      <TH>{ta("fields.role")}</TH>
                      <TH>{ta("fields.project")}</TH>
                      <TH>{ta("fields.sites")}</TH>
                      <TH>{ta("fields.contractor_engagement")}</TH>
                      <TH>{ta("fields.valid_from")}</TH>
                      <TH>{ta("fields.valid_to")}</TH>
                      <TH>{ta("fields.state")}</TH>
                      {canInvite ? <TH>{tc("actions")}</TH> : null}
                    </TR>
                  </THead>
                  <TBody>
                    {list.map((a) => (
                      <TR key={a.id} data-testid="assignment-row" data-role={a.role}>
                        <TD label={ta("fields.role")}>{tr(a.role)}</TD>
                        <TD label={ta("fields.project")}><span className="ltr">{a.project_id ? (projectCode.get(a.project_id) ?? "…") : ta("orgWide")}</span></TD>
                        <TD label={ta("fields.sites")}>{a.project_id ? <SiteCodes projectId={a.project_id} ids={a.site_ids} /> : "—"}</TD>
                        <TD label={ta("fields.contractor_engagement")}>{a.contractor_engagement_id ? <EngagementCode id={a.contractor_engagement_id} /> : "—"}</TD>
                        <TD label={ta("fields.valid_from")}>{date(a.valid_from)}</TD>
                        <TD label={ta("fields.valid_to")}>{date(a.valid_to)}</TD>
                        <TD label={ta("fields.state")}>
                          {a.revoked_at ? (
                            <Badge tone="neutral">{ta("revokedState")}</Badge>
                          ) : a.is_active ? (
                            <Badge tone="success">{ta("active")}</Badge>
                          ) : (
                            <Badge tone="warning">{ta("inactive")}</Badge>
                          )}
                        </TD>
                        {canInvite ? (
                          <TD label={tc("actions")}>
                            {!a.revoked_at ? (
                              <Button variant="outline" size="sm" onClick={() => { setActionError(null); setRevoking(a); }} data-testid="revoke-role">
                                {ta("revoke")}
                              </Button>
                            ) : null}
                          </TD>
                        ) : null}
                      </TR>
                    ))}
                  </TBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </div>
        <div className="flex flex-col gap-6">
          {options.length > 0 || (canInvite && u.status === "invited") ? (
            <Card>
              <CardHeader>
                <CardTitle>{t("fields.status")}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <TransitionActions current={u.status} options={options} statusLabel={(s) => t(`status.${s}`)} onTransition={transition} />
                {canInvite && u.status === "invited" ? (
                  <Button variant="outline" size="sm" onClick={resend} data-testid="resend-invite">
                    {t("actions.resendInvite")}
                  </Button>
                ) : null}
              </CardContent>
            </Card>
          ) : null}
          {can(me, "history.view") ? <HistoryPanel entityType="user" entityId={u.id} /> : null}
        </div>
      </div>
      <Dialog open={assignOpen} onOpenChange={setAssignOpen}>
        <DialogContent closeLabel={tc("close")} className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{ta("assignTitle")}</DialogTitle>
            <DialogDescription>{name(u.full_name_en, u.full_name_ar)}</DialogDescription>
          </DialogHeader>
          <AssignmentFields idPrefix="assign" value={draft} onChange={setDraft} errors={draftErrors} />
          <MutationError error={actionError} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setAssignOpen(false)}>
              {tc("cancel")}
            </Button>
            <Button onClick={submitAssign} disabled={busy} data-testid="assign-confirm">
              {busy ? tc("saving") : ta("assign")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={revoking !== null} onOpenChange={(v) => !v && setRevoking(null)}>
        {revoking ? (
          <DialogContent closeLabel={tc("close")}>
            <DialogHeader>
              <DialogTitle>{ta("revokeTitle")}</DialogTitle>
              <DialogDescription>
                {ta("revokeBody", {
                  role: tr(revoking.role),
                  scope: revoking.project_id ? (projectCode.get(revoking.project_id) ?? "…") : ta("orgWide"),
                })}
              </DialogDescription>
            </DialogHeader>
            <MutationError error={actionError} />
            <DialogFooter>
              <Button variant="outline" onClick={() => setRevoking(null)}>
                {tc("cancel")}
              </Button>
              <Button variant="destructive" onClick={submitRevoke} disabled={busy} data-testid="revoke-confirm">
                {ta("revoke")}
              </Button>
            </DialogFooter>
          </DialogContent>
        ) : null}
      </Dialog>
    </div>
  );
}
