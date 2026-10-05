"use client";
import { Plus, TriangleAlert } from "lucide-react";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { CheckboxField } from "@/components/common/form-field";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { ExportButtons } from "@/components/common/export-buttons";
import { useMeData } from "@/components/shell/me-context";
import { Link } from "@/i18n/navigation";
import { useEngagements, useProject, useSites } from "@/lib/api/queries";
import type { Schemas } from "@/lib/api/client";
import { can, canWrite } from "@/lib/permissions";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { useFormatters } from "@/lib/use-formatters";

type Eng = Schemas["EngagementRead"];

/** Depth-first order so subcontractors appear under their parent. */
export function treeOrder(items: Eng[]): Eng[] {
  const ids = new Set(items.map((e) => e.id));
  const children = new Map<string, Eng[]>();
  const roots: Eng[] = [];
  for (const e of items) {
    if (e.parent_engagement_id && ids.has(e.parent_engagement_id)) {
      const list = children.get(e.parent_engagement_id) ?? [];
      list.push(e);
      children.set(e.parent_engagement_id, list);
    } else roots.push(e);
  }
  const byCode = (a: Eng, b: Eng) => a.contractor.short_code.localeCompare(b.contractor.short_code);
  const out: Eng[] = [];
  const visit = (e: Eng) => {
    out.push(e);
    (children.get(e.id) ?? []).sort(byCode).forEach(visit);
  };
  roots.sort((a, b) => a.tier - b.tier || byCode(a, b)).forEach(visit);
  return out;
}

export function EngagementList({ projectId }: { projectId: string }) {
  const t = useTranslations("engagement");
  const tc = useTranslations("contractor");
  const me = useMeData();
  const name = useLocalizedName();
  const { date } = useFormatters(projectId);
  const project = useProject(projectId);
  const sites = useSites(projectId, { page_size: 100 });
  const [tier, setTier] = useState<"1" | "2" | "3" | "">("");
  const [flagged, setFlagged] = useState(false);
  const query = useEngagements(projectId, {
    tier: tier ? Number(tier) : undefined,
    parent_blacklisted: flagged ? true : undefined,
    page_size: 200,
  });
  const ordered = useMemo(() => treeOrder(query.data?.items ?? []), [query.data]);
  const byId = new Map(ordered.map((e) => [e.id, e]));
  const siteCode = new Map((sites.data?.items ?? []).map((s) => [s.id, s.code]));
  const manage = canWrite(me, "engagement.manage", projectId) && project.data?.status !== "closed";

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">{t("title")}</h2>
          <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
        </div>
        {manage ? (
          <Button asChild>
            <Link href={`/projects/${projectId}/engagements/new`} data-testid="new-engagement">
              <Plus aria-hidden />
              {t("new")}
            </Link>
          </Button>
        ) : null}
      </div>
      <ListToolbar actions={can(me, "export.lists", projectId) ? <ExportButtons dataset="engagements" params={{ project_id: projectId }} /> : null}>
        <SelectFilter
          id="eng-tier"
          label={t("fields.tier")}
          value={tier}
          onChange={setTier}
          options={(["1", "2", "3"] as const).map((x) => ({ value: x, label: t(`tier.${x}`) }))}
          allLabel={t("anyTier")}
        />
        <CheckboxField id="eng-flagged" label={t("onlyFlagged")}>
          <Checkbox checked={flagged} onChange={(e) => setFlagged(e.target.checked)} />
        </CheckboxField>
      </ListToolbar>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : ordered.length === 0 ? (
        <EmptyState />
      ) : (
        <Table data-testid="engagements-table">
          <THead>
            <TR>
              <TH>{t("fields.contractor")}</TH>
              <TH>{t("fields.tier")}</TH>
              <TH>{t("fields.parent")}</TH>
              <TH>{t("fields.sites")}</TH>
              <TH>{t("fields.mobilisation_date")}</TH>
              <TH>{tc("fields.status")}</TH>
            </TR>
          </THead>
          <TBody>
            {ordered.map((e) => {
              const parent = e.parent_engagement_id ? byId.get(e.parent_engagement_id) : undefined;
              return (
                <TR key={e.id} data-testid="engagement-row" data-code={e.contractor.short_code}>
                  <TD>
                    <div className="flex items-center gap-2" style={{ paddingInlineStart: `${(e.tier - 1) * 1.25}rem` }}>
                      {e.tier > 1 ? <span aria-hidden className="text-muted-foreground">└</span> : null}
                      <Link href={`/projects/${projectId}/engagements/${e.id}`} className="font-medium text-primary hover:underline">
                        <span className="ltr">{e.contractor.short_code}</span>
                      </Link>
                      <span className="text-muted-foreground">{name(e.contractor.legal_name_en, e.contractor.legal_name_ar)}</span>
                      {e.parent_blacklisted ? (
                        <Badge tone="danger">
                          <TriangleAlert aria-hidden />
                          {t("parentBlacklisted")}
                        </Badge>
                      ) : null}
                    </div>
                  </TD>
                  <TD>{t("tierShort", { tier: e.tier })}</TD>
                  <TD className="ltr">{parent?.contractor.short_code ?? "—"}</TD>
                  <TD className="ltr">{e.site_ids.map((s) => siteCode.get(s) ?? "…").join(", ")}</TD>
                  <TD>{date(e.mobilisation_date)}</TD>
                  <TD>
                    <StatusBadge status={e.contractor.status} label={tc(`status.${e.contractor.status}`)} />
                  </TD>
                </TR>
              );
            })}
          </TBody>
        </Table>
      )}
    </div>
  );
}
