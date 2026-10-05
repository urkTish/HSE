"use client";
import { useTranslations } from "next-intl";
import { useState } from "react";
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

const PAGE_SIZE = 50;

export function ZoneList({ projectId }: { projectId: string }) {
  const t = useTranslations("zone");
  const me = useMeData();
  const sites = useSites(projectId, { page_size: 100, sort: "code" });
  const [q, setQ] = useState("");
  const [siteId, setSiteId] = useState("");
  const [type, setType] = useState<Schemas["ZoneType"] | "">("");
  const [area, setArea] = useState<Schemas["AirsideArea"] | "">("");
  const [status, setStatus] = useState<Schemas["ZoneStatus"] | "">("");
  const [page, setPage] = useState(1);
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
  const reset = () => setPage(1);

  return (
    <div>
      <h2 className="mb-4 text-lg font-semibold">{t("title")}</h2>
      <ListToolbar actions={can(me, "export.lists", projectId) ? <ExportButtons dataset="zones" params={{ project_id: projectId, q: dq, status }} /> : null}>
        <SearchFilter id="zone-q" value={q} onChange={(v) => { setQ(v); reset(); }} />
        <SelectFilter
          id="zone-site"
          label={t("fields.site")}
          value={siteId}
          onChange={(v) => { setSiteId(v); reset(); }}
          options={(sites.data?.items ?? []).map((s) => ({ value: s.id, label: s.code }))}
        />
        <SelectFilter id="zone-type" label={t("fields.zone_type")} value={type} onChange={(v) => { setType(v); reset(); }} options={ZONE_TYPES.map((s) => ({ value: s, label: t(`type.${s}`) }))} />
        <SelectFilter id="zone-area" label={t("fields.airside_area")} value={area} onChange={(v) => { setArea(v); reset(); }} options={AIRSIDE_AREAS.map((s) => ({ value: s, label: t(`area.${s}`) }))} />
        <SelectFilter id="zone-status" label={t("fields.status")} value={status} onChange={(v) => { setStatus(v); reset(); }} options={ZONE_STATUSES.map((s) => ({ value: s, label: t(`status.${s}`) }))} />
      </ListToolbar>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : (
        <>
          <ZoneTable projectId={projectId} zones={query.data?.items ?? []} />
          {query.data ? <Pagination page={page} pageSize={PAGE_SIZE} total={query.data.total} onPage={setPage} /> : null}
        </>
      )}
    </div>
  );
}
