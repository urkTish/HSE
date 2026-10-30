// Location profile (SPEC §9 B). Renders what the record has, section by
// section; a section with no data is not rendered at all.
import { useEffect, useState, type ReactNode } from "react";
import { loadRecord } from "../kb/loader";
import { nearby, normalise } from "../kb/geo";
import { requestOnDemand, type OnDemandAnswer } from "../dynamic/onDemand";
import type {
  ClimRecord,
  IndexEntry,
  KbIndex,
  KbRecord,
  LayerDef,
  MarketAttributes,
  ProvinceInfo,
  SchoolAttributes,
  Selection,
} from "../kb/types";
import ClimateChart from "./ClimateChart";

interface Props {
  selection: Exclude<Selection, null>;
  index: KbIndex;
  layers: LayerDef[];
  categoryLabels: Record<string, string>;
  onClose: () => void;
  onOpen: (e: IndexEntry) => void;
}

const DATA_KIND: Record<string, string> = {
  official_fact: "Official fact",
  estimate: "Estimate",
  assumption: "Assumption",
  forecast: "Forecast",
  professional_interpretation: "Professional interpretation",
  subjective_assessment: "Subjective assessment",
};
const STATUS: Record<string, string> = {
  verified: "Verified",
  partially_verified: "Partially verified",
  unverified: "Unverified",
  disputed: "Disputed",
  outdated: "Outdated",
};
const PRECISION: Record<string, string> = {
  exact: "exact",
  approximate: "approximate",
  centroid: "centroid",
  unknown: "unknown precision",
};
const humanise = (k: string) => k.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-t border-line px-5 py-4">
      <h3 className="mb-2 text-2xs font-semibold uppercase tracking-caps text-ink-3">{title}</h3>
      <div className="space-y-2 text-sm text-ink">{children}</div>
    </section>
  );
}

function Dl({ rows }: { rows: [string, ReactNode][] }) {
  const shown = rows.filter(([, v]) => v !== null && v !== undefined && v !== "" && !(Array.isArray(v) && v.length === 0));
  if (!shown.length) return null;
  return (
    <dl className="grid grid-cols-[minmax(7rem,auto)_1fr] gap-x-3 gap-y-1">
      {shown.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-ink-3">{k}</dt>
          <dd className="m-0">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Generic attributes renderer for categories without a dedicated section. */
function renderValue(v: unknown): ReactNode {
  if (v === null || v === undefined || v === "") return null;
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v === "number") return v.toLocaleString("en-CA");
  if (typeof v === "string") return /^https?:\/\//.test(v) ? <a className="underline break-all" href={v} target="_blank" rel="noopener noreferrer">{v}</a> : v;
  if (Array.isArray(v)) {
    const items = v.map(renderValue).filter((x) => x !== null);
    return items.length ? <ul className="list-disc pl-4">{items.map((x, i) => <li key={i}>{x}</li>)}</ul> : null;
  }
  if (typeof v === "object") {
    const rows = Object.entries(v as Record<string, unknown>).map(([k, x]) => [humanise(k), renderValue(x)] as [string, ReactNode]);
    return <Dl rows={rows} />;
  }
  return String(v);
}

function ProvinceProfile({ province, index, layers, onOpen }: { province: ProvinceInfo; index: KbIndex; layers: LayerDef[]; onOpen: (e: IndexEntry) => void }) {
  const inProv = index.records.filter((r) => r.province === province.code);
  const cities = inProv.filter((r) => r.category === "city").sort((a, b) => a.rank - b.rank || a.name.localeCompare(b.name));
  const unmapped = inProv.filter((r) => r.category !== "city" && (r.lat === null || !r.layer));
  const counts = layers.filter((l) => l.kind !== "relief").map((l) => [l.label, inProv.filter((r) => r.layer === l.id && r.lat !== null).length] as const);
  return (
    <>
      <header className="px-5 pb-4 pt-5">
        <p className="text-2xs font-semibold uppercase tracking-caps text-ink-3">{province.kind ?? "Province or territory"} · {province.iso_3166_2}</p>
        <h2 className="font-display text-2xl font-bold leading-tight tracking-display text-ink">{province.name}</h2>
        {province.name_fr && province.name_fr !== province.name && <p className="text-sm text-ink-2" lang="fr">{province.name_fr}</p>}
      </header>
      <Section title="In the knowledge base">
        <Dl rows={counts.filter(([, n]) => n > 0).map(([label, n]) => [label, n])} />
        {counts.every(([, n]) => n === 0) && <p className="text-ink-2">No mapped records for this {province.kind?.toLowerCase() ?? "jurisdiction"} yet.</p>}
        <p className="text-xs text-ink-3">Province-level research (immigration, tax, healthcare, climate comparison) appears here as Agents 01–04 publish records.</p>
      </Section>
      {cities.length > 0 && (
        <Section title="Principal cities">
          <ul className="flex flex-wrap gap-1.5">
            {cities.map((c) => (
              <li key={c.id}>
                <button type="button" onClick={() => onOpen(c)} className="rounded-sm border border-line-strong px-2 py-1 text-sm hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-focus">
                  {c.name}
                  {c.capital ? <span className="ml-1 text-2xs text-ink-3">{c.capital === "national" ? "national capital" : "capital"}</span> : null}
                </button>
              </li>
            ))}
          </ul>
        </Section>
      )}
      {unmapped.length > 0 && (
        <Section title="Records without a map location">
          <ul className="space-y-1">
            {unmapped.map((r) => (
              <li key={r.id}>
                <button type="button" className="text-left underline" onClick={() => onOpen(r)}>{r.name}</button>
              </li>
            ))}
          </ul>
        </Section>
      )}
      <Section title="Boundary source">
        <p className="text-xs text-ink-2">
          Natural Earth 1:50 million admin-1 boundaries (public domain), generalised; not for legal use. Statistics Canada cartographic boundary files replace them in Phase 2.
        </p>
      </Section>
    </>
  );
}

export default function ProfilePanel({ selection, index, layers, categoryLabels, onClose, onOpen }: Props) {
  const [record, setRecord] = useState<KbRecord | null>(null);
  const [climate, setClimate] = useState<ClimRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [onDemand, setOnDemand] = useState<OnDemandAnswer | null>(null);
  const [loadedFor, setLoadedFor] = useState<string | null>(null);

  const selKey = selection.kind === "record" ? selection.id : `prov-${selection.code}`;
  const loading = selection.kind === "record" && loadedFor !== selKey;

  useEffect(() => {
    if (selection.kind !== "record") return;
    let live = true;
    (async () => {
      try {
        const rec = await loadRecord(selection.category, selection.id);
        if (!live) return;
        let clim: ClimRecord[] = [];
        if (rec?.category === "clim") clim = [rec as unknown as ClimRecord];
        else if (rec && (rec.category === "city" || rec.category === "nbhd")) {
          const name = normalise(rec.category === "city" ? rec.name : rec.geo.city);
          const candidates = index.records.filter((e) => e.category === "clim");
          let linked = candidates.filter((e) => e.province === rec.geo.province && normalise(e.city) === name);
          if (!linked.length && typeof rec.geo.lat === "number" && typeof rec.geo.lon === "number") {
            linked = nearby({ id: rec.id, lat: rec.geo.lat, lon: rec.geo.lon }, candidates, 30, 1).map((x) => x.entry);
          }
          clim = (await Promise.all(linked.slice(0, 3).map((e) => loadRecord("clim", e.id)))).filter(Boolean) as unknown as ClimRecord[];
        }
        const od = rec?.category === "re" ? await requestOnDemand({ kind: "market-figure", recordId: rec.id }) : null;
        if (!live) return;
        setRecord(rec);
        setClimate(clim);
        setOnDemand(od);
        setError(rec ? null : "This record is not in the published data.");
        setLoadedFor(selKey);
      } catch (e) {
        if (!live) return;
        setError(e instanceof Error ? e.message : String(e));
        setLoadedFor(selKey);
      }
    })();
    return () => {
      live = false;
    };
  }, [selection, selKey, index]);

  const province = (code: string) => index.provinces.find((p) => p.code === code);

  let body: ReactNode;
  if (selection.kind === "province") {
    const p = province(selection.code);
    body = p ? <ProvinceProfile province={p} index={index} layers={layers} onOpen={onOpen} /> : <p className="p-5">Unknown province.</p>;
  } else if (loading) {
    body = <p className="p-5 text-sm text-ink-2" role="status">Loading the record…</p>;
  } else if (error || !record) {
    body = <p className="p-5 text-sm text-status-critical" role="alert">{error ?? "Not found."}</p>;
  } else {
    body = <RecordProfile record={record} climate={climate} onDemand={onDemand} index={index} categoryLabels={categoryLabels} onOpen={onOpen} provinceName={record.geo.province === "CA" ? "Canada (national)" : (province(record.geo.province)?.name ?? record.geo.province)} />;
  }

  return (
    <aside
      aria-label="Location profile"
      className="pointer-events-auto flex max-h-full flex-col overflow-hidden rounded-lg border border-line bg-surface-1 shadow-3"
    >
      <div className="flex shrink-0 justify-end px-2 pt-2">
        <button type="button" onClick={onClose} className="rounded-sm px-2 py-1 text-sm text-ink-2 hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-focus" aria-label="Close profile">
          Close ✕
        </button>
      </div>
      <div className="-mt-6 overflow-y-auto">{body}</div>
    </aside>
  );
}

function RecordProfile({
  record: r,
  climate,
  onDemand,
  index,
  categoryLabels,
  onOpen,
  provinceName,
}: {
  record: KbRecord;
  climate: ClimRecord[];
  onDemand: OnDemandAnswer | null;
  index: KbIndex;
  categoryLabels: Record<string, string>;
  onOpen: (e: IndexEntry) => void;
  provinceName: string;
}) {
  const g = r.geo;
  const entry = index.records.find((e) => e.id === r.id);
  const near =
    entry && entry.lat !== null && entry.lon !== null ? nearby({ id: r.id, lat: entry.lat, lon: entry.lon }, index.records, 50, 8) : [];
  const geomSource = r._map?.geom_source;
  const placeLine = [g.neighbourhood, g.city && g.city !== r.name ? g.city : null, g.region, provinceName].filter(Boolean).join(", ");

  const school = r.category === "school" ? (r.attributes as unknown as SchoolAttributes) : null;
  const market = r.category === "re" ? (r.attributes as unknown as MarketAttributes) : null;
  const clim = r.category === "clim" ? (r as unknown as ClimRecord) : null;
  const seasonal = clim?.attributes.seasonal_summary;
  const phenomena = clim?.attributes.phenomena ?? [];

  // Generic details for categories without a dedicated section.
  const genericAttrs =
    r.category === "city"
      ? null
      : school || market || clim
        ? null
        : Object.entries(r.attributes ?? {}).filter(([, v]) => v !== null && v !== undefined && v !== "" && !(Array.isArray(v) && !v.length));

  return (
    <>
      <header className="px-5 pb-4 pt-5">
        <p className="text-2xs font-semibold uppercase tracking-caps text-ink-3">
          {categoryLabels[r.category] ?? r.category}
          {r.subcategory ? ` · ${r.subcategory}` : ""}
        </p>
        <h2 className="font-display text-2xl font-bold leading-tight tracking-display text-ink">{r.name}</h2>
        {r.name_fr && r.name_fr !== r.name && <p className="text-sm text-ink-2" lang="fr">{r.name_fr}</p>}
        {placeLine && <p className="mt-1 text-sm text-ink-2">{placeLine}</p>}
        {r.category === "city" && typeof r.attributes.capital === "string" && (
          <p className="mt-1 text-sm text-ink-2">{r.attributes.capital === "national" ? "National capital of Canada" : `Capital of ${provinceName}`}</p>
        )}
      </header>

      {r.description && (
        <Section title="About">
          <p>{r.description}</p>
        </Section>
      )}

      {(climate.length > 0 || seasonal || phenomena.length > 0) && (
        <Section title="Year-round climate">
          {climate.map((c) => (
            <div key={c.id} className="space-y-1">
              {c.id !== r.id && (
                <p className="text-xs text-ink-2">
                  From <button type="button" className="underline" onClick={() => { const e = index.records.find((x) => x.id === c.id); if (e) onOpen(e); }}>{c.name}</button>
                </p>
              )}
              <ClimateChart record={c} />
            </div>
          ))}
          {seasonal && (
            <Dl rows={(["winter", "spring", "summer", "autumn"] as const).map((s) => [humanise(s), seasonal[s] ?? null] as [string, ReactNode])} />
          )}
          {phenomena.length > 0 && <Dl rows={[["Local phenomena", renderValue(phenomena)]]} />}
        </Section>
      )}

      {school && (
        <Section title="Education">
          <Dl
            rows={[
              ["Models", school.models.map(humanise).join(", ")],
              ["Legal status", `${school.legal_status.label} (${school.legal_status.authority})`],
              ["Ages", school.ages ? `${school.ages.min ?? "?"}–${school.ages.max ?? "?"}` : null],
              ["Grades", school.grades ?? null],
              ["Language", school.language_of_instruction?.join(", ") ?? null],
              ["Curriculum", school.curriculum ?? null],
              ["Accreditation", school.accreditation?.join(", ") ?? null],
              [
                "Tuition",
                school.tuition
                  ? `Amount not stored in the map; check the school's official page${school.tuition.school_year ? ` (school year ${school.tuition.school_year} on record)` : ""}.`
                  : null,
              ],
              ["Admission", school.admission ?? null],
              ["Class size", school.class_size ?? null],
              ["Website", renderValue(school.website)],
              ["Official media", school.media_links?.length ? renderValue(school.media_links) : null],
              ["Why it qualifies", school.qualifying_reason],
            ]}
          />
        </Section>
      )}

      {market && (
        <Section title="Market observation">
          <Dl
            rows={[
              ["Metric", humanise(market.metric)],
              ["Property type", market.property_type ? humanise(market.property_type) : null],
              ["Bedrooms", market.bedrooms ?? null],
              ["Period", market.period],
              ["Geography", `${humanise(market.geography_level)}${market.geography_name ? `: ${market.geography_name}` : ""}`],
              ["Figure kind", humanise(market.figure_kind)],
            ]}
          />
          <p className="rounded-sm bg-status-warning-soft px-2 py-1 text-xs text-status-warning">
            The figure itself is not stored in the map. {onDemand?.reason ?? ""} The full record is in the knowledge base at <code>{r._map?.file}</code>.
          </p>
        </Section>
      )}

      {genericAttrs && genericAttrs.length > 0 && (
        <Section title="Details">
          <Dl rows={genericAttrs.map(([k, v]) => [humanise(k), renderValue(v)] as [string, ReactNode])} />
        </Section>
      )}

      {r._withheld && r._withheld.length > 0 && !market && (
        <Section title="Withheld figures">
          <p className="text-xs text-ink-2">
            {r._withheld.length} money figure(s) in this record are not published in the map's static files ({r._withheld.join(", ")}). They will be shown on demand, with date and source, once that service exists.
          </p>
        </Section>
      )}

      {near.length > 0 && (
        <Section title="Nearby in the knowledge base">
          <ul className="space-y-1">
            {near.map(({ entry: e, km }) => (
              <li key={e.id} className="flex justify-between gap-2">
                <button type="button" className="text-left underline" onClick={() => onOpen(e)}>
                  {e.name}
                </button>
                <span className="shrink-0 text-xs tabular-nums text-ink-3">{km < 10 ? km.toFixed(1) : Math.round(km)} km</span>
              </li>
            ))}
          </ul>
          <p className="text-2xs text-ink-3">Straight-line distances, not routes.</p>
        </Section>
      )}

      {(typeof g.lat === "number" || geomSource) && (
        <Section title="Location">
          <Dl
            rows={[
              ["Coordinates", typeof g.lat === "number" && typeof g.lon === "number" ? `${g.lat.toFixed(4)}, ${g.lon.toFixed(4)} (${PRECISION[g.coord_precision ?? "unknown"]})` : null],
              ["Coordinate source", g.coord_source ?? null],
              [
                "Shown on the map at",
                geomSource === "station"
                  ? "the climate station's position"
                  : geomSource === "campus"
                    ? "the first campus with coordinates"
                    : geomSource?.startsWith("city:")
                      ? `the city point of ${geomSource.slice(5)} (the record has no coordinates of its own)`
                      : null,
              ],
              ["Address", g.address ?? null],
              ["Extent", g.extent ?? null],
            ]}
          />
        </Section>
      )}

      <Section title="Sources and reliability">
        <Dl
          rows={[
            ["Kind of information", DATA_KIND[r.data_kind] ?? r.data_kind],
            ["Verification", `${STATUS[r.verification.status] ?? r.verification.status}, ${r.verification.confidence} confidence (${r.verification.verified_by}, ${r.verification.last_verified})`],
            ["Next review", r.verification.next_review],
            ["Notes", r.verification.notes ?? null],
            ["Researched by", r.responsible_agent],
            ["Updated", r.updated],
          ]}
        />
        <ol className="list-decimal space-y-1 pl-4 text-xs">
          {r.sources.map((s, i) => (
            <li key={i}>
              <a className="underline" href={s.url} target="_blank" rel="noopener noreferrer">
                {s.title ?? s.publisher}
              </a>
              {s.title ? ` — ${s.publisher}` : ""}. Accessed {s.accessed}
              {s.data_period ? `; data period ${s.data_period}` : ""}
              {s.licence ? `; licence: ${s.licence}` : ""}.
            </li>
          ))}
        </ol>
        {r.limitations && (
          <p className="text-xs text-ink-2">
            <span className="font-semibold">Limitations.</span> {r.limitations}
          </p>
        )}
        <p className="text-2xs text-ink-3">
          Record <code>{r.id}</code>
        </p>
      </Section>
    </>
  );
}
