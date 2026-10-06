"use client";
import { Pencil, Trash2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiWarnings } from "@/components/common/api-warnings";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList, YesNo } from "@/components/common/field-list";
import { HistoryPanel } from "@/components/common/history-panel";
import { ErrorState, LoadingState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { TransitionActions } from "@/components/common/transition-actions";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { hk, useWorkforceReturn } from "@/lib/api/hse";
import { useDisplay } from "@/lib/digits";
import { useErrorMessage, useLocalizedName } from "@/lib/i18n-helpers";
import { can, canWrite } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";
import { WORKFORCE_FLOW } from "@/lib/workflows";

export function WorkforceDetail({ id }: { id: string }) {
  const t = useTranslations("workforce");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tn = useTranslations("nav");
  const me = useMeData();
  const qc = useQueryClient();
  const router = useRouter();
  const msg = useErrorMessage();
  const name = useLocalizedName();
  const q = useWorkforceReturn(id);
  const pid = q.data?.project_id ?? null;
  const show = useDisplay(pid);
  const { date, dateTime } = useFormatters(pid);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const r = q.data;
  const edges = WORKFORCE_FLOW[r.status].filter((e) => canWrite(me, e.cap, r.project_id));
  const editable = canWrite(me, "workforce.edit", r.project_id) && (r.status === "draft" || r.status === "submitted");

  async function transition(to: Schemas["WorkforceStatus"], reason: string | null) {
    const res = await unwrap(api.POST("/api/v1/workforce-returns/{return_id}/transitions", { params: { path: { return_id: r.id } }, body: { to_status: to, reason } }));
    qc.setQueryData(hk.ret(r.id), res);
    await qc.invalidateQueries({ queryKey: ["workforce-returns"] });
    await qc.invalidateQueries({ queryKey: ["history"] });
  }

  async function remove() {
    if (!window.confirm(tc("confirmDelete"))) return;
    try {
      await unwrap(api.DELETE("/api/v1/workforce-returns/{return_id}", { params: { path: { return_id: r.id } } }));
      await qc.invalidateQueries({ queryKey: ["workforce-returns"] });
      toast.success(tc("deleted"));
      router.push("/workforce");
    } catch (e) {
      toast.error(msg(e));
    }
  }

  return (
    <div>
      <Breadcrumbs items={[{ label: tn("workforce"), href: "/workforce" }, { label: `${date(r.work_date)} · ${r.engagement.short_code}` }]} />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-6 lg:col-span-2">
          <Card>
            <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
              <CardTitle className="flex flex-wrap items-center gap-2">
                <span data-testid="return-title">{t("detailTitle")}</span>
                <StatusBadge status={r.status} label={te(`workforceStatus.${r.status}`)} />
              </CardTitle>
              <div className="flex gap-2">
                {editable ? (
                  <Button variant="outline" size="sm" asChild>
                    <Link href={`/workforce/${r.id}/edit`} data-testid="edit-return">
                      <Pencil aria-hidden />
                      {tc("edit")}
                    </Link>
                  </Button>
                ) : null}
                {editable && r.status === "draft" ? (
                  <Button variant="outline" size="sm" onClick={() => void remove()}>
                    <Trash2 aria-hidden />
                    {tc("delete")}
                  </Button>
                ) : null}
              </div>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <ApiWarnings warnings={r.warnings} />
              <FieldList>
                <FieldItem label={t("fields.work_date")}>{date(r.work_date)}</FieldItem>
                <FieldItem label={t("fields.shift")}>{te(`shift.${r.shift}`)}</FieldItem>
                <FieldItem label={t("fields.site")}>
                  <span className="ltr">{r.site.code}</span> — {name(r.site.name_en, r.site.name_ar)}
                </FieldItem>
                <FieldItem label={t("fields.zone")}>{r.zone ? `${r.zone.code} — ${name(r.zone.name_en, r.zone.name_ar)}` : "—"}</FieldItem>
                <FieldItem label={t("fields.engagement")}>
                  <span className="ltr">{r.engagement.short_code}</span> — {name(r.engagement.name_en, r.engagement.name_ar)}
                </FieldItem>
                <FieldItem label={t("fields.tier_class")}>{te(`tierClass.${r.tier_class}`)}</FieldItem>
                <FieldItem label={t("fields.no_work")}>
                  <YesNo value={r.no_work} yes={tc("yes")} no={tc("no")} />
                </FieldItem>
                <FieldItem label={t("fields.headcount")}>{show(r.headcount)}</FieldItem>
                <FieldItem label={t("fields.man_hours")}>{show(r.man_hours)}</FieldItem>
                <FieldItem label={t("fields.toolbox_talks")}>{show(r.toolbox_talks)}</FieldItem>
                <FieldItem label={t("fields.toolbox_attendees")}>{show(r.toolbox_attendees)}</FieldItem>
                <FieldItem label={t("fields.inductions")}>{show(r.inductions)}</FieldItem>
                <FieldItem label={t("fields.training_hours")}>{show(r.training_hours)}</FieldItem>
                <FieldItem label={t("fields.source")}>
                  {te(`workforceSource.${r.source}`)}
                  {r.import_batch_id ? (
                    <>
                      {" · "}
                      <Link className="text-primary hover:underline" href={`/workforce/imports/${r.import_batch_id}`}>
                        {t("fromImport")}
                      </Link>
                    </>
                  ) : null}
                </FieldItem>
                <FieldItem label={t("fields.created_by")}>{r.created_by ? name(r.created_by.full_name_en, r.created_by.full_name_ar) : "—"}</FieldItem>
                <FieldItem label={t("fields.verified_by")}>
                  {r.verified_by ? `${name(r.verified_by.full_name_en, r.verified_by.full_name_ar)} · ${dateTime(r.verified_at)}` : "—"}
                </FieldItem>
                <FieldItem label={t("fields.remarks")}>{r.remarks}</FieldItem>
              </FieldList>
            </CardContent>
          </Card>
        </div>
        <div className="flex flex-col gap-6">
          {edges.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>{t("fields.status")}</CardTitle>
              </CardHeader>
              <CardContent>
                <TransitionActions
                  current={r.status}
                  options={edges.map((e) => ({ to: e.to, label: t(`actions.${e.kind as "submit"}`), reasonRequired: e.reasonRequired }))}
                  statusLabel={(x) => te(`workforceStatus.${x}`)}
                  onTransition={transition}
                />
              </CardContent>
            </Card>
          ) : null}
          {can(me, "history.view", r.project_id) ? <HistoryPanel entityType="workforce_return" entityId={r.id} projectId={r.project_id} /> : null}
        </div>
      </div>
    </div>
  );
}
