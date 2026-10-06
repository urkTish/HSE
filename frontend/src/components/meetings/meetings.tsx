"use client";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Attachments } from "@/components/common/attachments";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList, YesNo } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { hk, useHseMeeting, useHseMeetings } from "@/lib/api/hse";
import { useDisplay } from "@/lib/digits";
import { MEETING_TYPES } from "@/lib/enums";
import { useErrorMessage } from "@/lib/i18n-helpers";
import { can, canWrite } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";

const PAGE_SIZE = 50;
/** Meetings have no capability of their own in §5.10; editing follows the HSE settings/officer roles (ASSUMPTION). */
const EDIT_CAP = "inspection.plan_manage" as const;

export function MeetingList({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("meetings");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const show = useDisplay(project.id);
  const { date } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const type = (s.get("meeting_type") ?? "") as Schemas["MeetingType"] | "";
  const q = { meeting_type: type || null, date_from: s.get("date_from") || null, date_to: s.get("date_to") || null, page, page_size: PAGE_SIZE };
  const query = useHseMeetings(project.id, q);
  const [creating, setCreating] = useState(false);
  const items = query.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          canWrite(me, EDIT_CAP, project.id) ? (
            <Button onClick={() => setCreating(true)} data-testid="new-meeting">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <ListToolbar>
        <div className="flex flex-col gap-1.5 lg:w-40">
          <Label htmlFor="mt-from">{tc("dateFrom")}</Label>
          <Input id="mt-from" type="date" value={q.date_from ?? ""} onChange={(e) => s.set({ date_from: e.target.value })} />
        </div>
        <div className="flex flex-col gap-1.5 lg:w-40">
          <Label htmlFor="mt-to">{tc("dateTo")}</Label>
          <Input id="mt-to" type="date" value={q.date_to ?? ""} onChange={(e) => s.set({ date_to: e.target.value })} />
        </div>
        <SelectFilter id="mt-type" label={t("fields.meeting_type")} value={type} onChange={(v) => s.set({ meeting_type: v })} options={MEETING_TYPES.map((x) => ({ value: x, label: te(`meetingType.${x}`) }))} />
      </ListToolbar>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState />
      ) : (
        <>
          <Table data-testid="meetings-table">
            <THead>
              <TR>
                <TH>{t("fields.planned_date")}</TH>
                <TH>{t("fields.meeting_type")}</TH>
                <TH>{t("fields.title")}</TH>
                <TH>{t("fields.engagement")}</TH>
                <TH>{t("fields.held_date")}</TH>
                <TH className="text-end">{t("fields.attended_count")}</TH>
                <TH>{t("fields.has_minutes")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((m) => (
                <TR key={m.id} data-testid="meeting-row">
                  <TD label={t("fields.planned_date")}>
                    <Link href={`/meetings/${m.id}`} className="font-medium text-primary hover:underline">
                      {date(m.planned_date)}
                    </Link>
                  </TD>
                  <TD label={t("fields.meeting_type")}>{te(`meetingType.${m.meeting_type}`)}</TD>
                  <TD label={t("fields.title")}>{m.title ?? "—"}</TD>
                  <TD label={t("fields.engagement")}>{m.engagement ? <span className="ltr">{m.engagement.short_code}</span> : "—"}</TD>
                  <TD label={t("fields.held_date")}>{date(m.held_date)}</TD>
                  <TD label={t("fields.attended_count")} className="text-end tabular-nums">
                    {m.attended_count === null ? "—" : `${show(m.attended_count)} / ${show(m.invited_count)}`}
                  </TD>
                  <TD label={t("fields.has_minutes")}>
                    <YesNo value={m.has_minutes} yes={tc("yes")} no={tc("no")} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={query.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      )}
      {creating ? <MeetingDialog projectId={project.id} onClose={() => setCreating(false)} /> : null}
    </div>
  );
}

function MeetingDialog({ projectId, meeting, onClose }: { projectId: string; meeting?: Schemas["HseMeetingRead"]; onClose: () => void }) {
  const t = useTranslations("meetings");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tv = useTranslations("validation");
  const qc = useQueryClient();
  const router = useRouter();
  const opts = useProjectOptions(projectId);
  const [v, setV] = useState({
    meeting_type: meeting?.meeting_type ?? "hse_committee",
    title: meeting?.title ?? "",
    engagement_id: meeting?.engagement?.id ?? "",
    planned_date: meeting?.planned_date ?? "",
    held_date: meeting?.held_date ?? "",
    invited_count: meeting ? String(meeting.invited_count) : "",
    attended_count: meeting?.attended_count === null || meeting?.attended_count === undefined ? "" : String(meeting.attended_count),
  });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const exceeds = v.attended_count !== "" && v.invited_count !== "" && Number(v.attended_count) > Number(v.invited_count);
  const attendedMissing = Boolean(v.held_date) && v.attended_count === "";
  const set = (k: keyof typeof v) => (e: { target: { value: string } }) => setV({ ...v, [k]: e.target.value });
  async function submit() {
    if (!v.planned_date || v.invited_count === "" || exceeds || attendedMissing) return;
    setBusy(true);
    setError(null);
    const body = {
      meeting_type: v.meeting_type as Schemas["MeetingType"],
      title: v.title.trim() || null,
      engagement_id: v.engagement_id || null,
      planned_date: v.planned_date,
      held_date: v.held_date || null,
      invited_count: Number(v.invited_count),
      attended_count: v.attended_count === "" ? null : Number(v.attended_count),
    };
    try {
      const saved = meeting
        ? await unwrap(api.PATCH("/api/v1/hse-meetings/{meeting_id}", { params: { path: { meeting_id: meeting.id } }, body }))
        : await unwrap(api.POST("/api/v1/projects/{project_id}/hse-meetings", { params: { path: { project_id: projectId } }, body }));
      qc.setQueryData(hk.meeting(saved.id), saved);
      await qc.invalidateQueries({ queryKey: ["hse-meetings"] });
      toast.success(meeting ? tc("saved") : tc("created"));
      onClose();
      if (!meeting) router.push(`/meetings/${saved.id}`);
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
          <DialogTitle>{meeting ? t("editTitle") : t("createTitle")}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2" data-testid="meeting-form">
          <FormField id="mt-type-f" label={t("fields.meeting_type")} required>
            <Select value={v.meeting_type} onChange={set("meeting_type")}>
              {MEETING_TYPES.map((x) => (
                <option key={x} value={x}>
                  {te(`meetingType.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="mt-eng" label={t("fields.engagement")}>
            <Select value={v.engagement_id} onChange={set("engagement_id")}>
              <option value="">{tc("anyContractor")}</option>
              {opts.engagements.map((e) => (
                <option key={e.value} value={e.value}>
                  {e.label}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="mt-title" label={t("fields.title")} className="sm:col-span-2">
            <Input maxLength={150} value={v.title} onChange={set("title")} />
          </FormField>
          <FormField id="mt-planned" label={t("fields.planned_date")} required error={!v.planned_date && busy ? tv("required") : undefined}>
            <Input type="date" value={v.planned_date} onChange={set("planned_date")} />
          </FormField>
          <FormField id="mt-held" label={t("fields.held_date")}>
            <Input type="date" value={v.held_date} onChange={set("held_date")} />
          </FormField>
          <FormField id="mt-invited" label={t("fields.invited_count")} required>
            <Input inputMode="numeric" className="ltr" value={v.invited_count} onChange={(e) => setV({ ...v, invited_count: e.target.value.replace(/\D/g, "") })} />
          </FormField>
          <FormField id="mt-attended" label={t("fields.attended_count")} required={Boolean(v.held_date)} error={exceeds ? t("attendedExceeds") : attendedMissing ? t("attendedRequired") : undefined}>
            <Input inputMode="numeric" className="ltr" value={v.attended_count} onChange={(e) => setV({ ...v, attended_count: e.target.value.replace(/\D/g, "") })} />
          </FormField>
        </div>
        <MutationError error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button onClick={() => void submit()} disabled={busy || !v.planned_date || v.invited_count === "" || exceeds || attendedMissing} data-testid="save-meeting">
            {tc("save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function MeetingDetail({ id }: { id: string }) {
  const t = useTranslations("meetings");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tn = useTranslations("nav");
  const me = useMeData();
  const qc = useQueryClient();
  const router = useRouter();
  const msg = useErrorMessage();
  const q = useHseMeeting(id);
  const pid = q.data?.project_id ?? null;
  const show = useDisplay(pid);
  const { date } = useFormatters(pid);
  const [editing, setEditing] = useState(false);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const m = q.data;
  const editable = canWrite(me, EDIT_CAP, m.project_id);
  async function remove() {
    if (!window.confirm(tc("confirmDelete"))) return;
    try {
      await unwrap(api.DELETE("/api/v1/hse-meetings/{meeting_id}", { params: { path: { meeting_id: m.id } } }));
      await qc.invalidateQueries({ queryKey: ["hse-meetings"] });
      toast.success(tc("deleted"));
      router.push("/meetings");
    } catch (e) {
      toast.error(msg(e));
    }
  }
  return (
    <div>
      <Breadcrumbs items={[{ label: tn("meetings"), href: "/meetings" }, { label: date(m.planned_date) }]} />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-6 lg:col-span-2">
          <Card>
            <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
              <CardTitle data-testid="meeting-title">{m.title ?? te(`meetingType.${m.meeting_type}`)}</CardTitle>
              {editable ? (
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => setEditing(true)} data-testid="edit-meeting">
                    <Pencil aria-hidden />
                    {tc("edit")}
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => void remove()}>
                    <Trash2 aria-hidden />
                    {tc("delete")}
                  </Button>
                </div>
              ) : null}
            </CardHeader>
            <CardContent>
              <FieldList>
                <FieldItem label={t("fields.meeting_type")}>{te(`meetingType.${m.meeting_type}`)}</FieldItem>
                <FieldItem label={t("fields.engagement")}>{m.engagement ? <span className="ltr">{m.engagement.short_code}</span> : "—"}</FieldItem>
                <FieldItem label={t("fields.planned_date")}>{date(m.planned_date)}</FieldItem>
                <FieldItem label={t("fields.held_date")}>{date(m.held_date)}</FieldItem>
                <FieldItem label={t("fields.invited_count")}>{show(m.invited_count)}</FieldItem>
                <FieldItem label={t("fields.attended_count")}>{show(m.attended_count)}</FieldItem>
              </FieldList>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>{t("minutes")}</CardTitle>
            </CardHeader>
            <CardContent>
              <Attachments ownerType="hse_meeting_minutes" ownerId={m.id} canUpload={editable} canDelete={editable} max={1} onChange={() => void qc.invalidateQueries({ queryKey: hk.meeting(m.id) })} />
            </CardContent>
          </Card>
        </div>
        <div>{can(me, "history.view", m.project_id) ? <HistoryPanel entityType="hse_meeting" entityId={m.id} projectId={m.project_id} /> : null}</div>
      </div>
      {editing ? <MeetingDialog projectId={m.project_id} meeting={m} onClose={() => setEditing(false)} /> : null}
    </div>
  );
}
