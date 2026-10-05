"use client";
import { Pencil } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FieldItem, FieldList, YesNo } from "@/components/common/field-list";
import { HistoryPanel } from "@/components/common/history-panel";
import { TransitionActions } from "@/components/common/transition-actions";
import { LoadingState } from "@/components/common/states";
import { useMeData } from "@/components/shell/me-context";
import { Link } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { keys, useProject } from "@/lib/api/queries";
import { can } from "@/lib/permissions";
import { PROJECT_FLOW } from "@/lib/workflows";
import { useFormatters } from "@/lib/use-formatters";

export function ProjectOverview({ projectId }: { projectId: string }) {
  const t = useTranslations("project");
  const tc = useTranslations("common");
  const me = useMeData();
  const qc = useQueryClient();
  const q = useProject(projectId);
  const { date, dateTime } = useFormatters(projectId);
  if (!q.data) return <LoadingState />;
  const p = q.data;
  const manage = can(me, "project.manage", p.id);

  async function transition(to: Schemas["ProjectStatus"], reason: string | null) {
    const res = await unwrap(
      api.POST("/api/v1/projects/{project_id}/transitions", { params: { path: { project_id: p.id } }, body: { to_status: to, reason } }),
    );
    qc.setQueryData(keys.project(p.id), res);
    await qc.invalidateQueries({ queryKey: ["projects"] });
    await qc.invalidateQueries({ queryKey: ["history"] });
  }

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card className="lg:col-span-2">
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>{tc("details")}</CardTitle>
          {manage && p.status !== "closed" ? (
            <Button variant="outline" size="sm" asChild>
              <Link href={`/projects/${p.id}/edit`} data-testid="edit-project">
                <Pencil aria-hidden />
                {tc("edit")}
              </Link>
            </Button>
          ) : null}
        </CardHeader>
        <CardContent>
          <FieldList>
            <FieldItem label={t("fields.code")} ltr>{p.code}</FieldItem>
            <FieldItem label={t("fields.project_type")}>{t(`type.${p.project_type}`)}</FieldItem>
            <FieldItem label={t("fields.is_airport")}>
              <YesNo value={p.is_airport} yes={tc("yes")} no={tc("no")} />
            </FieldItem>
            <FieldItem label={t("fields.name_en")}>{p.name_en}</FieldItem>
            <FieldItem label={t("fields.name_ar")}>
              <span lang="ar">{p.name_ar}</span>
            </FieldItem>
            <FieldItem label={t("fields.city")}>{p.city}</FieldItem>
            <FieldItem label={t("fields.client_name_en")}>{p.client_name_en}</FieldItem>
            <FieldItem label={t("fields.client_name_ar")}>
              <span lang="ar">{p.client_name_ar}</span>
            </FieldItem>
            {p.is_airport ? <FieldItem label={t("fields.airport_icao")} ltr>{p.airport_icao ?? "—"}</FieldItem> : null}
            <FieldItem label={t("fields.start_date")}>{date(p.start_date)}</FieldItem>
            <FieldItem label={t("fields.planned_end_date")}>{date(p.planned_end_date)}</FieldItem>
            {p.status_reason ? <FieldItem label={t("fields.status_reason")}>{p.status_reason}</FieldItem> : null}
            <FieldItem label={tc("createdAt")}>{dateTime(p.created_at)}</FieldItem>
            <FieldItem label={tc("updatedAt")}>{dateTime(p.updated_at)}</FieldItem>
          </FieldList>
        </CardContent>
      </Card>
      <div className="flex flex-col gap-6">
        {manage ? (
          <Card>
            <CardHeader>
              <CardTitle>{t("fields.status")}</CardTitle>
            </CardHeader>
            <CardContent>
              <TransitionActions
                current={p.status}
                options={PROJECT_FLOW[p.status].map((e) => ({ to: e.to, reasonRequired: e.reasonRequired, destructive: e.to === "closed" }))}
                statusLabel={(s) => t(`status.${s}`)}
                onTransition={transition}
              />
            </CardContent>
          </Card>
        ) : null}
        {can(me, "history.view", p.id) ? <HistoryPanel entityType="project" entityId={p.id} projectId={p.id} /> : null}
      </div>
    </div>
  );
}
