"use client";
import { Pencil } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert } from "@/components/ui/alert";
import { FieldItem, FieldList, YesNo } from "@/components/common/field-list";
import { HistoryPanel } from "@/components/common/history-panel";
import { StatusBadge } from "@/components/common/status-badge";
import { TransitionActions } from "@/components/common/transition-actions";
import { ErrorState, LoadingState } from "@/components/common/states";
import { useMeData } from "@/components/shell/me-context";
import { Link } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { keys, useProject, useSite, useZone } from "@/lib/api/queries";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { can, canWrite } from "@/lib/permissions";
import { ZONE_FLOW } from "@/lib/workflows";
import { useFormatters } from "@/lib/use-formatters";

export function ZoneDetail({ projectId, zoneId }: { projectId: string; zoneId: string }) {
  const t = useTranslations("zone");
  const ta = useTranslations("zone.airside");
  const tc = useTranslations("common");
  const me = useMeData();
  const qc = useQueryClient();
  const name = useLocalizedName();
  const { dateTime } = useFormatters(projectId);
  const project = useProject(projectId);
  const q = useZone(zoneId);
  const site = useSite(q.data?.site_id ?? "");
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const z = q.data;
  const manage = canWrite(me, "site_zone.manage", projectId) && project.data?.status !== "closed";
  const a = z.airside;
  const yn = (v: boolean | null | undefined) => <YesNo value={v} yes={tc("yes")} no={tc("no")} />;

  async function transition(to: Schemas["ZoneStatus"], reason: string | null) {
    const res = await unwrap(api.POST("/api/v1/zones/{zone_id}/transitions", { params: { path: { zone_id: z.id } }, body: { to_status: to, reason } }));
    qc.setQueryData(keys.zone(z.id), res);
    await qc.invalidateQueries({ queryKey: ["zones", projectId] });
    await qc.invalidateQueries({ queryKey: ["history"] });
  }

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="flex flex-col gap-6 lg:col-span-2">
        <Card>
          <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
            <CardTitle className="flex flex-wrap items-center gap-2">
              <span data-testid="zone-title">{name(z.name_en, z.name_ar)}</span>
              <StatusBadge status={z.status} label={t(`status.${z.status}`)} />
            </CardTitle>
            {manage && z.status !== "archived" ? (
              <Button variant="outline" size="sm" asChild>
                <Link href={`/projects/${projectId}/zones/${z.id}/edit`} data-testid="edit-zone">
                  <Pencil aria-hidden />
                  {tc("edit")}
                </Link>
              </Button>
            ) : null}
          </CardHeader>
          <CardContent>
            {z.status === "archived" ? <Alert tone="info" className="mb-4">{t("archivedNote")}</Alert> : null}
            <FieldList>
              <FieldItem label={t("fields.code")} ltr>{z.code}</FieldItem>
              <FieldItem label={t("fields.site")}>
                {site.data ? (
                  <Link href={`/projects/${projectId}/sites/${site.data.id}`} className="text-primary hover:underline">
                    <span className="ltr">{site.data.code}</span> — {name(site.data.name_en, site.data.name_ar)}
                  </Link>
                ) : (
                  "—"
                )}
              </FieldItem>
              <FieldItem label={t("fields.zone_type")}>{t(`type.${z.zone_type}`)}</FieldItem>
              <FieldItem label={t("fields.name_en")}>{z.name_en}</FieldItem>
              <FieldItem label={t("fields.name_ar")}>
                <span lang="ar">{z.name_ar}</span>
              </FieldItem>
              {z.status_reason ? <FieldItem label={t("fields.status_reason")}>{z.status_reason}</FieldItem> : null}
              <FieldItem label={tc("updatedAt")}>{dateTime(z.updated_at)}</FieldItem>
            </FieldList>
          </CardContent>
        </Card>
        {a ? (
          <Card data-testid="airside-card">
            <CardHeader>
              <CardTitle>{ta("title")}</CardTitle>
              <CardDescription>{ta("subtitle")}</CardDescription>
            </CardHeader>
            <CardContent>
              <FieldList>
                <FieldItem label={ta("airside_area")}>{t(`area.${a.airside_area}`)}</FieldItem>
                <FieldItem label={ta("in_movement_area")}>{yn(a.in_movement_area)}</FieldItem>
                <FieldItem label={ta("runway_ref")} ltr>{a.runway_ref ?? "—"}</FieldItem>
                <FieldItem label={ta("security_restricted_area")}>{yn(a.security_restricted_area)}</FieldItem>
                <FieldItem label={ta("notam_required_for_works")}>{yn(a.notam_required_for_works)}</FieldItem>
                <FieldItem label={ta("ols_height_limit_m_amsl")} ltr>{a.ols_height_limit_m_amsl ?? "—"}</FieldItem>
                <FieldItem label={ta("max_equipment_height_m_agl")} ltr>{a.max_equipment_height_m_agl ?? "—"}</FieldItem>
                <FieldItem label={ta("escort_required")}>{yn(a.escort_required)}</FieldItem>
                <FieldItem label={ta("adp_required")}>{yn(a.adp_required)}</FieldItem>
                <FieldItem label={ta("fod_control_required")}>{yn(a.fod_control_required)}</FieldItem>
                <FieldItem label={ta("works_safety_plan_ref")} ltr>{a.works_safety_plan_ref ?? "—"}</FieldItem>
              </FieldList>
            </CardContent>
          </Card>
        ) : null}
      </div>
      <div className="flex flex-col gap-6">
        {manage ? (
          <Card>
            <CardHeader>
              <CardTitle>{t("fields.status")}</CardTitle>
            </CardHeader>
            <CardContent>
              <TransitionActions
                current={z.status}
                options={ZONE_FLOW[z.status].map((e) => ({ to: e.to, reasonRequired: e.reasonRequired, destructive: e.to === "archived" }))}
                statusLabel={(x) => t(`status.${x}`)}
                onTransition={transition}
              />
            </CardContent>
          </Card>
        ) : null}
        {can(me, "history.view", projectId) ? <HistoryPanel entityType="zone" entityId={z.id} projectId={projectId} /> : null}
      </div>
    </div>
  );
}
