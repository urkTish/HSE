"use client";
import { Pencil, Plus } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { HistoryPanel } from "@/components/common/history-panel";
import { StatusBadge } from "@/components/common/status-badge";
import { TransitionActions } from "@/components/common/transition-actions";
import { ErrorState, LoadingState } from "@/components/common/states";
import { useMeData } from "@/components/shell/me-context";
import { ZoneTable } from "@/components/zones/zone-table";
import { Link } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { keys, useProject, useSite, useZones } from "@/lib/api/queries";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { can, canWrite } from "@/lib/permissions";
import { SITE_FLOW } from "@/lib/workflows";
import { useFormatters } from "@/lib/use-formatters";

export function SiteDetail({ projectId, siteId }: { projectId: string; siteId: string }) {
  const t = useTranslations("site");
  const tz = useTranslations("zone");
  const tc = useTranslations("common");
  const me = useMeData();
  const qc = useQueryClient();
  const name = useLocalizedName();
  const { dateTime } = useFormatters(projectId);
  const project = useProject(projectId);
  const q = useSite(siteId);
  const zones = useZones(projectId, { site_id: siteId, page_size: 100, sort: "code" });
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const s = q.data;
  const manage = canWrite(me, "site_zone.manage", projectId) && project.data?.status !== "closed";

  async function transition(to: Schemas["SiteStatus"], reason: string | null) {
    const res = await unwrap(api.POST("/api/v1/sites/{site_id}/transitions", { params: { path: { site_id: s.id } }, body: { to_status: to, reason } }));
    qc.setQueryData(keys.site(s.id), res);
    await qc.invalidateQueries({ queryKey: ["sites", projectId] });
    await qc.invalidateQueries({ queryKey: ["history"] });
  }

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="flex flex-col gap-6 lg:col-span-2">
        <Card>
          <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
            <CardTitle className="flex flex-wrap items-center gap-2">
              <span data-testid="site-title">{name(s.name_en, s.name_ar)}</span>
              <StatusBadge status={s.status} label={t(`status.${s.status}`)} />
            </CardTitle>
            {manage ? (
              <Button variant="outline" size="sm" asChild>
                <Link href={`/projects/${projectId}/sites/${s.id}/edit`}>
                  <Pencil aria-hidden />
                  {tc("edit")}
                </Link>
              </Button>
            ) : null}
          </CardHeader>
          <CardContent>
            <FieldList>
              <FieldItem label={t("fields.code")} ltr>{s.code}</FieldItem>
              <FieldItem label={t("fields.site_side")}>{t(`side.${s.site_side}`)}</FieldItem>
              <FieldItem label={t("fields.gps")} ltr>
                {s.gps_lat != null && s.gps_lng != null ? `${s.gps_lat}, ${s.gps_lng}` : "—"}
              </FieldItem>
              <FieldItem label={t("fields.name_en")}>{s.name_en}</FieldItem>
              <FieldItem label={t("fields.name_ar")}>
                <span lang="ar">{s.name_ar}</span>
              </FieldItem>
              <FieldItem label={tc("updatedAt")}>{dateTime(s.updated_at)}</FieldItem>
            </FieldList>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
            <CardTitle>{t("zonesOfSite")}</CardTitle>
            {manage && s.status === "active" ? (
              <Button size="sm" asChild>
                <Link href={`/projects/${projectId}/sites/${s.id}/zones/new`} data-testid="new-zone">
                  <Plus aria-hidden />
                  {tz("new")}
                </Link>
              </Button>
            ) : null}
          </CardHeader>
          <CardContent>
            {zones.isLoading ? <LoadingState rows={2} /> : <ZoneTable projectId={projectId} zones={zones.data?.items ?? []} showSite={false} />}
          </CardContent>
        </Card>
      </div>
      <div className="flex flex-col gap-6">
        {manage ? (
          <Card>
            <CardHeader>
              <CardTitle>{t("fields.status")}</CardTitle>
            </CardHeader>
            <CardContent>
              <TransitionActions
                current={s.status}
                options={SITE_FLOW[s.status].map((e) => ({ to: e.to, reasonRequired: e.reasonRequired }))}
                statusLabel={(x) => t(`status.${x}`)}
                onTransition={transition}
              />
            </CardContent>
          </Card>
        ) : null}
        {can(me, "history.view", projectId) ? <HistoryPanel entityType="site" entityId={s.id} projectId={projectId} /> : null}
      </div>
    </div>
  );
}
