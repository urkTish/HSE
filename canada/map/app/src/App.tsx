// Application shell: loads the generated knowledge-base files, owns UI state
// (layers on, selection, focus) and composes map, layer panel, search and
// profile. Modules: kb/ (data), map/ (rendering), dynamic/ (on-demand), ui/.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FeatureCollection } from "geojson";
import layerConfig from "./kb/layers.config.json";
import { loadAttribution, loadBoundaries, loadCategoryGeojson, loadIndex } from "./kb/loader";
import type { AttributionEntry, Category, IndexEntry, KbIndex, LayerDef, Selection } from "./kb/types";
import MapView, { type Focus, type MapViewState } from "./map/MapView";
import { CITY_TIER_MINZOOM } from "./map/layerIds";
import type { BasemapMode } from "./map/basemap";
import LayerPanel from "./ui/LayerPanel";
import PlacesInView from "./ui/PlacesInView";
import ProfilePanel from "./ui/ProfilePanel";
import SearchBox, { type SearchHit } from "./ui/SearchBox";

const LAYERS = layerConfig.layers as LayerDef[];
const CATEGORY_LABELS = layerConfig.categoryLabels as Record<string, string>;

interface Loaded {
  index: KbIndex;
  attribution: AttributionEntry[];
  boundaries: FeatureCollection;
  layerData: Record<string, FeatureCollection>;
}

async function loadAll(): Promise<Loaded> {
  const [index, attribution, boundaries] = await Promise.all([loadIndex(), loadAttribution(), loadBoundaries()]);
  const cats = (Object.keys(index.files) as Category[]).filter((c) => index.files[c].features > 0);
  const collections = await Promise.all(cats.map((c) => loadCategoryGeojson(c)));
  const layerData: Record<string, FeatureCollection> = {};
  for (const l of LAYERS) layerData[l.id] = { type: "FeatureCollection", features: [] };
  for (const fc of collections) for (const f of fc.features) layerData[f.properties.layer]?.features.push(f);
  return { index, attribution, boundaries, layerData };
}

export default function App() {
  const [data, setData] = useState<Loaded | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [layersOn, setLayersOn] = useState<Record<string, boolean>>(() => Object.fromEntries(LAYERS.map((l) => [l.id, l.defaultOn])));
  const [selection, setSelection] = useState<Selection>(null);
  const [focus, setFocus] = useState<Focus | null>(null);
  const [basemap, setBasemap] = useState<BasemapMode | null>(null);
  const [view, setView] = useState<MapViewState | null>(null);
  const [wide, setWide] = useState(() => window.matchMedia("(min-width: 768px)").matches);
  const returnFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const mq = window.matchMedia("(min-width: 768px)");
    const on = () => setWide(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);

  useEffect(() => {
    loadAll().then(setData, (e: unknown) => setLoadError(e instanceof Error ? e.message : String(e)));
  }, []);

  /** Opens a profile, remembering where focus was so closing can return it (review F-02). */
  const select = useCallback((s: Selection) => {
    if (s && document.activeElement instanceof HTMLElement && !document.activeElement.closest("aside")) returnFocus.current = document.activeElement;
    setSelection(s);
  }, []);
  const close = useCallback(() => {
    setSelection(null);
    const el = returnFocus.current;
    returnFocus.current = null;
    if (el && document.contains(el)) el.focus();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (e.key === "Escape" && !(t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close]);

  // One live region announces the selection (the hover tooltip is aria-hidden).
  const announcement = useMemo(() => {
    if (!data || !selection) return "";
    const prov = (code: string) => (code === "CA" ? "Canada" : (data.index.provinces.find((p) => p.code === code)?.name ?? code));
    if (selection.kind === "province") return `${prov(selection.code)} selected`;
    const e = data.index.records.find((r) => r.id === selection.id);
    return e ? `${e.name}, ${prov(e.province)}, selected` : "";
  }, [data, selection]);

  const categoriesPresent = useMemo(() => new Set(data?.index.records.map((r) => r.category) ?? []), [data]);
  const selectedPoint = useMemo(() => {
    if (!data || selection?.kind !== "record") return null;
    const e = data.index.records.find((r) => r.id === selection.id);
    return e && e.lat !== null && e.lon !== null ? { lat: e.lat, lon: e.lon } : null;
  }, [data, selection]);

  // Places in view: records of the layers that are on and visible at this zoom, inside the map bounds.
  const inView = useMemo(() => {
    const empty = { items: [] as IndexEntry[], total: 0, byLayer: {} as Record<string, number> };
    if (!data || !view) return empty;
    const order = new Map(LAYERS.map((l, i) => [l.id, i]));
    const minz = new Map(LAYERS.map((l) => [l.id, l.minzoom]));
    const all = data.index.records.filter((e) => {
      if (!e.layer || e.lat === null || e.lon === null || !layersOn[e.layer]) return false;
      const mz = e.layer === "cities" ? (CITY_TIER_MINZOOM[e.tier] ?? 0) : (minz.get(e.layer) ?? 0);
      if (view.zoom < mz) return false;
      const lonOk = view.west <= view.east ? e.lon >= view.west && e.lon <= view.east : e.lon >= view.west || e.lon <= view.east;
      return lonOk && e.lat >= view.south && e.lat <= view.north;
    });
    const byLayer: Record<string, number> = {};
    for (const e of all) byLayer[e.layer as string] = (byLayer[e.layer as string] ?? 0) + 1;
    all.sort((a, b) => (order.get(a.layer as string) ?? 0) - (order.get(b.layer as string) ?? 0) || a.rank - b.rank || a.name.localeCompare(b.name));
    return { items: all.slice(0, 50), total: all.length, byLayer };
  }, [data, view, layersOn]);

  const openEntry = useCallback((e: IndexEntry) => {
    if (document.activeElement instanceof HTMLElement && !document.activeElement.closest("aside")) returnFocus.current = document.activeElement;
    setSelection({ kind: "record", id: e.id, category: e.category });
    if (e.layer) setLayersOn((s) => (s[e.layer as string] ? s : { ...s, [e.layer as string]: true }));
    if (e.lat !== null && e.lon !== null) setFocus({ lat: e.lat, lon: e.lon, zoom: e.category === "city" ? 7 : 9, nonce: Date.now() });
  }, []);

  const onSearch = useCallback(
    (hit: SearchHit) => {
      if (hit.kind === "record") openEntry(hit.entry);
      else select({ kind: "province", code: hit.province.code });
    },
    [openEntry, select],
  );

  const toggle = useCallback((id: string) => setLayersOn((s) => ({ ...s, [id]: !s[id] })), []);

  if (loadError) {
    return (
      <main className="grid h-full place-items-center p-6">
        <div className="max-w-md rounded-lg border border-line bg-surface-1 p-5 shadow-2" role="alert">
          <h1 className="font-display text-xl font-bold">The map data could not be loaded</h1>
          <p className="mt-2 text-sm text-ink-2">{loadError}</p>
          <p className="mt-2 text-sm text-ink-2">
            Run <code>npm run build-data</code> in <code>canada/map/app</code> to generate <code>public/data/</code>, then reload.
          </p>
        </div>
      </main>
    );
  }
  if (!data) {
    return (
      <main className="grid h-full place-items-center text-sm text-ink-2" role="status">
        Loading the knowledge base…
      </main>
    );
  }

  const panelOpen = Boolean(selection);
  const padding = {
    left: wide ? 344 : 0,
    right: wide && panelOpen ? 464 : 0,
    bottom: !wide && panelOpen ? Math.round(window.innerHeight * 0.55) : 0,
  };

  return (
    <div className="relative h-full overflow-hidden">
      <a
        href="#places-in-view"
        className="sr-only z-50 rounded-sm bg-surface-1 px-3 py-2 text-sm text-ink shadow-3 focus:not-sr-only focus:absolute focus:left-3 focus:top-3"
      >
        Skip to places in view
      </a>
      <p className="sr-only" aria-live="polite">
        {announcement}
      </p>
      <MapView
        layers={LAYERS}
        layersOn={layersOn}
        layerData={data.layerData}
        boundaries={data.boundaries}
        attribution={data.attribution}
        categoriesPresent={categoriesPresent}
        selection={selection}
        selectedPoint={selectedPoint}
        focus={focus}
        padding={padding}
        onSelect={select}
        onBasemap={setBasemap}
        onView={setView}
      />

      <header className="pointer-events-none absolute inset-x-0 top-0 z-30 flex flex-wrap items-start gap-3 p-3">
        <div className="pointer-events-auto hidden rounded-lg border border-line bg-surface-1 px-3 py-2 shadow-2 md:block">
          <h1 className="font-display text-base font-bold leading-tight text-ink">Canada Explorer</h1>
          <p className="text-2xs text-ink-3">Phase 1 skeleton · settlement research and exploration</p>
        </div>
        <h1 className="sr-only md:hidden">Canada Explorer</h1>
        <div className="pointer-events-auto min-w-64 flex-1">
          <SearchBox index={data.index} categoryLabels={CATEGORY_LABELS} onPick={onSearch} />
        </div>
      </header>

      {basemap === "fallback" && (
        <div className="absolute bottom-10 left-1/2 z-30 -translate-x-1/2 rounded-md bg-status-warning-soft px-3 py-1.5 text-xs text-status-warning shadow-2" role="status">
          The base map (OpenFreeMap) could not be reached; showing boundaries and records only.
        </div>
      )}

      <div className="pointer-events-none absolute bottom-10 left-3 top-20 z-10 flex w-[min(20rem,calc(100%-1.5rem))] flex-col justify-start gap-2">
        <div className="flex min-h-0 shrink flex-col">
          <LayerPanel layers={LAYERS} layersOn={layersOn} index={data.index} inView={inView.byLayer} zoom={view?.zoom ?? 0} onToggle={toggle} />
        </div>
        <PlacesInView items={inView.items} total={inView.total} layers={LAYERS} onOpen={openEntry} />
      </div>

      {selection && (
        <div className="pointer-events-none absolute inset-x-2 bottom-2 z-20 flex max-h-[60%] flex-col md:inset-x-auto md:bottom-10 md:right-3 md:top-20 md:max-h-none md:w-[var(--ce-panel-width)]">
          <ProfilePanel
            key={selection.kind === "record" ? selection.id : selection.code}
            selection={selection}
            index={data.index}
            layers={LAYERS}
            categoryLabels={CATEGORY_LABELS}
            onClose={close}
            onOpen={openEntry}
          />
        </div>
      )}
    </div>
  );
}
