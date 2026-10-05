"use client";
import { useTranslations } from "next-intl";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { Link } from "@/i18n/navigation";
import type { Schemas } from "@/lib/api/client";
import { useSites } from "@/lib/api/queries";
import { useLocalizedName } from "@/lib/i18n-helpers";

export function ZoneTable({ projectId, zones, showSite = true }: { projectId: string; zones: Schemas["ZoneRead"][]; showSite?: boolean }) {
  const t = useTranslations("zone");
  const name = useLocalizedName();
  const sites = useSites(projectId, { page_size: 100 });
  const siteCode = new Map((sites.data?.items ?? []).map((s) => [s.id, s.code]));
  if (zones.length === 0) return <EmptyState />;
  return (
    <Table data-testid="zones-table">
      <THead>
        <TR>
          <TH>{t("fields.code")}</TH>
          <TH>{t("fields.name")}</TH>
          {showSite ? <TH>{t("fields.site")}</TH> : null}
          <TH>{t("fields.zone_type")}</TH>
          <TH>{t("fields.airside_area")}</TH>
          <TH>{t("fields.status")}</TH>
        </TR>
      </THead>
      <TBody>
        {zones.map((z) => (
          <TR key={z.id} data-testid="zone-row">
            <TD label={t("fields.code")}>
              <Link href={`/projects/${projectId}/zones/${z.id}`} className="font-medium text-primary hover:underline ltr">
                {z.code}
              </Link>
            </TD>
            <TD label={t("fields.name")}>{name(z.name_en, z.name_ar)}</TD>
            {showSite ? (
              <TD label={t("fields.site")} data-testid="zone-site">
                <span className="ltr">{siteCode.get(z.site_id) ?? "—"}</span>
              </TD>
            ) : null}
            <TD label={t("fields.zone_type")}>
              <Badge tone={z.zone_type === "airside" ? "info" : "neutral"}>{t(`type.${z.zone_type}`)}</Badge>
            </TD>
            <TD label={t("fields.airside_area")}>{z.airside ? t(`area.${z.airside.airside_area}`) : "—"}</TD>
            <TD label={t("fields.status")}>
              <StatusBadge status={z.status} label={t(`status.${z.status}`)} />
            </TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}
