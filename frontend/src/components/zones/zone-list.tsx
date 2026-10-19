"use client";
import { useTranslations } from "next-intl";
import { ListToolbar, SearchFilter, SelectFilter } from "@/components/common/list-toolbar";
import { ErrorState, LoadingState } from "@/components/common/states";
import { Pagination } from "@/components/common/pagination";
import { ExportButtons } from "@/components/common/export-buttons";
import { useMeData } from "@/components/shell/me-context";
import { ZoneTable } from "@/components/zones/zone-table";
import { useSites, useZones } from "@/lib/api/queries";
import type { Schemas } from "@/lib/api/client";
import { AIRSIDE_AREAS, ZONE_STATUSES, ZONE_TYPES } from "@/lib/enums";
import { can } from "@/lib/permissions";
import { useDebounced } from "@/lib/use-debounced";
import { useSearchState } from "@/lib/url-state";

const PAGE_SIZE = 50;

export function ZoneList({ projectId }: { projectId: string }) {
  const t = useTranslations("zone");
  const me = useMeData();
  const sites = useSites(projectId, { page_size: 100, sort: "code" });
  const s = useSearchState();
  const q = s.get("q") ?? "";
  const siteId = s.get("site_id") ?? "";
  const type = (s.get("zone_type") as Schemas["ZoneType"] | null) ?? "";
  const area = (s.get("airside_area") as Schemas["AirsideArea"] | null) ?? "";
  const status = (s.get("status") as Schemas["ZoneStatus"] | null) ?? "";
  const page = s.getInt("page", 1) ?? 1;
  const dq = useDebounced(q);
  const query = useZones(projectId, {
    q: dq || undefined,
    site_id: siteId || undefined,
    zone_type: type || undefined,
    airside_area: area || undefined,
    status: status || undefined,
    sort: "code",
    page,
    page_size: PAGE_SIZE,
  });

  return (
    <div>
      <h2 className="mb-4 text-lg font-semibold">{t("title")}</h2>
      <ListToolbar actions={can(me, "export.lists", projectId) ? <ExportButtons dataset="zones" params={{ project_id: projectId, q: dq, status }} /> : null}>
        <SearchFilter id="zone-q" value={q} onChange={(v) => s.set({ q: v })} />
        <SelectFilter
          id="zone-site"
          label={t("fields.site")}
          value={siteId}
          onChange={(v) => s.set({ site_id: v })}
          options={(sites.data?.items ?? []).map((s) => ({ value: s.id, label: s.code }))}
        />
        <SelectFilter id="zone-type" label={t("fields.zone_type")} value={type} onChange={(v) => s.set({ zone_type: v })} options={ZONE_TYPES.map((s) => ({ value: s, label: t(`type.${s}`) }))} />
        <SelectFilter id="zone-area" label={t("fields.airside_area")} value={area} onChange={(v) => s.set({ airside_area: v })} options={AIRSIDE_AREAS.map((s) => ({ value: s, label: t(`area.${s}`) }))} />
        <SelectFilter id="zone-status" label={t("fields.status")} value={status} onChange={(v) => s.set({ status: v })} options={ZONE_STATUSES.map((s) => ({ value: s, label: t(`status.${s}`) }))} />
      </ListToolbar>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : (
        <>
          <ZoneTable projectId={projectId} zones={query.data?.items ?? []} />
          {query.data ? <Pagination page={page} pageSize={PAGE_SIZE} total={query.data.total} onPage={(p) => s.set({ page: p })} /> : null}
        </>
      )}
    </div>
  );
}
