"use client";
import { Pencil } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert } from "@/components/ui/alert";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { HistoryPanel } from "@/components/common/history-panel";
import { StatusBadge } from "@/components/common/status-badge";
import { ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { useMeData } from "@/components/shell/me-context";
import { Link } from "@/i18n/navigation";
import { api, unwrap } from "@/lib/api/client";
import { keys, useEngagement, useEngagements, useProject, useSites } from "@/lib/api/queries";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { can, canWrite } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";

export function EngagementDetail({ projectId, engagementId }: { projectId: string; engagementId: string }) {
  const t = useTranslations("engagement");
  const tc = useTranslations("common");
  const tcs = useTranslations("contractor.status");
  const me = useMeData();
  const qc = useQueryClient();
  const name = useLocalizedName();
  const { date, dateTime } = useFormatters(projectId);
  const project = useProject(projectId);
  const q = useEngagement(engagementId);
  const all = useEngagements(projectId, { page_size: 200 });
  const sites = useSites(projectId, { page_size: 100 });
  const [error, setError] = useState<unknown>(null);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const e = q.data;
  const parent = all.data?.items.find((x) => x.id === e.parent_engagement_id);
  const subs = (all.data?.items ?? []).filter((x) => x.parent_engagement_id === e.id);
  const manage = canWrite(me, "engagement.manage", projectId) && project.data?.status !== "closed";
  const siteMap = new Map((sites.data?.items ?? []).map((s) => [s.id, s]));

  async function clearFlag() {
    setError(null);
    try {
      const res = await unwrap(
        api.POST("/api/v1/engagements/{engagement_id}/clear-parent-blacklisted", { params: { path: { engagement_id: e.id } } }),
      );
      qc.setQueryData(keys.engagement(e.id), res);
      await qc.invalidateQueries({ queryKey: ["engagements", projectId] });
      toast.success(t("flagCleared"));
    } catch (err) {
      setError(err);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="flex flex-col gap-6 lg:col-span-2">
        {e.parent_blacklisted ? (
          <Alert tone="danger" data-testid="parent-blacklisted">
            <p>{t("parentBlacklistedNote")}</p>
            {me.is_hse_manager ? (
              <Button size="sm" variant="outline" className="mt-2" onClick={clearFlag}>
                {t("clearFlag")}
              </Button>
            ) : null}
          </Alert>
        ) : null}
        <MutationError error={error} />
        <Card>
          <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
            <CardTitle className="flex flex-wrap items-center gap-2">
              <Link href={`/contractors/${e.contractor_id}`} className="text-primary hover:underline" data-testid="engagement-title">
                <span className="ltr">{e.contractor.short_code}</span> — {name(e.contractor.legal_name_en, e.contractor.legal_name_ar)}
              </Link>
              <StatusBadge status={e.contractor.status} label={tcs(e.contractor.status)} />
            </CardTitle>
            {manage ? (
              <Button variant="outline" size="sm" asChild>
                <Link href={`/projects/${projectId}/engagements/${e.id}/edit`}>
                  <Pencil aria-hidden />
                  {tc("edit")}
                </Link>
              </Button>
            ) : null}
          </CardHeader>
          <CardContent>
            <FieldList>
              <FieldItem label={t("fields.tier")}>{t(`tier.${String(e.tier) as "1" | "2" | "3"}`)}</FieldItem>
              <FieldItem label={t("fields.parent")}>
                {parent ? (
                  <Link href={`/projects/${projectId}/engagements/${parent.id}`} className="text-primary hover:underline ltr">
                    {parent.contractor.short_code}
                  </Link>
                ) : e.parent_engagement_id ? (
                  "…"
                ) : (
                  t("noParent")
                )}
              </FieldItem>
              <FieldItem label={t("fields.sites")} ltr>
                {e.site_ids.map((s) => siteMap.get(s)?.code ?? "…").join(", ")}
              </FieldItem>
              <FieldItem label={t("fields.mobilisation_date")}>{date(e.mobilisation_date)}</FieldItem>
              <FieldItem label={t("fields.demobilisation_date")}>{date(e.demobilisation_date)}</FieldItem>
              <FieldItem label={tc("updatedAt")}>{dateTime(e.updated_at)}</FieldItem>
              <FieldItem label={t("fields.scope_of_work_en")}>{e.scope_of_work_en}</FieldItem>
              <FieldItem label={t("fields.scope_of_work_ar")}>
                <span lang="ar">{e.scope_of_work_ar}</span>
              </FieldItem>
            </FieldList>
          </CardContent>
        </Card>
        {subs.length > 0 ? (
          <Card>
            <CardHeader>
              <CardTitle>{t(`tier.${String(Math.min(e.tier + 1, 3)) as "2" | "3"}`)}</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="flex flex-col gap-1 text-sm">
                {subs.map((s) => (
                  <li key={s.id}>
                    <Link href={`/projects/${projectId}/engagements/${s.id}`} className="text-primary hover:underline">
                      <span className="ltr">{s.contractor.short_code}</span> — {name(s.contractor.legal_name_en, s.contractor.legal_name_ar)}
                    </Link>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        ) : null}
      </div>
      <div>{can(me, "history.view", projectId) ? <HistoryPanel entityType="project_engagement" entityId={e.id} projectId={projectId} /> : null}</div>
    </div>
  );
}
