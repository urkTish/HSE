// The map module: MapLibre GL JS, base map, province boundaries and the
// knowledge-base point layers. It knows nothing about profiles or search; it
// reports clicks through onSelect and follows `selection` and `focus`.
import { useEffect, useRef, useState } from "react";
import {
  AttributionControl,
  Map as MLMap,
  NavigationControl,
  ScaleControl,
  setWorkerUrl,
  type GeoJSONSource,
  type MapGeoJSONFeature,
  type MapMouseEvent,
  type StyleSpecification,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
// MapLibre 6 loads its worker relative to its own module; the bundler must emit
// the worker file explicitly, so its URL is imported and registered here.
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import type { FeatureCollection } from "geojson";
import type { AttributionEntry, LayerDef, ProvinceCode, Selection } from "../kb/types";
import {
  CANADA_BOUNDS,
  RELIEF_TILES,
  TRANSPORT_SOURCE_LAYERS,
  currentTheme,
  prefersReducedMotion,
  resolveStyle,
  token,
  type BasemapMode,
  type Theme,
} from "./basemap";

export interface Focus {
  lat: number;
  lon: number;
  zoom: number;
  nonce: number;
}

interface Props {
  layers: LayerDef[];
  layersOn: Record<string, boolean>;
  layerData: Record<string, FeatureCollection>;
  boundaries: FeatureCollection;
  attribution: AttributionEntry[];
  categoriesPresent: Set<string>;
  selection: Selection;
  selectedPoint: { lat: number; lon: number } | null;
  focus: Focus | null;
  onSelect: (s: Selection) => void;
  onBasemap: (m: BasemapMode) => void;
}

setWorkerUrl(workerUrl);

const PROV_SRC = "ce-provinces";
const SEL_SRC = "ce-selected";
const srcId = (layer: string) => `ce-src-${layer}`;

const escapeHtml = (s: string) => s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

function attributionHtml(entries: AttributionEntry[], layersOn: Record<string, boolean>, cats: Set<string>): string[] {
  return entries
    .filter((e) => {
      if (e.when === "always") return true;
      const [kind, value] = e.when.split(":");
      if (kind === "layer") return Boolean(value && layersOn[value]);
      if (kind === "category") return Boolean(value && cats.has(value));
      return false;
    })
    .map((e) =>
      e.url
        ? `<a href="${escapeHtml(e.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(e.text)}</a>`
        : escapeHtml(e.text),
    );
}

export default function MapView(props: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MLMap | null>(null);
  const propsRef = useRef(props);
  const hoverProv = useRef<ProvinceCode | null>(null);
  const selectedProv = useRef<ProvinceCode | null>(null);
  const attributionRef = useRef<AttributionControl | null>(null);
  const selectProvRef = useRef<((code: ProvinceCode | null) => void) | null>(null);
  const [styleVersion, setStyleVersion] = useState(0);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; text: string } | null>(null);

  useEffect(() => {
    propsRef.current = props;
  });

  // ---- create the map once ----
  useEffect(() => {
    let cancelled = false;
    let map: MLMap | null = null;
    const media = window.matchMedia("(prefers-color-scheme: dark)");

    const loadStyle = async (theme: Theme) => {
      const { style, mode } = await resolveStyle(theme);
      propsRef.current.onBasemap(mode);
      return style;
    };

    (async () => {
      const style = await loadStyle(currentTheme());
      if (cancelled || !containerRef.current) return;
      map = new MLMap({
        container: containerRef.current,
        style,
        bounds: CANADA_BOUNDS,
        // Leave room for the layer panel on wide screens and the search bar on top.
        fitBoundsOptions: { padding: window.innerWidth >= 768 ? { top: 80, bottom: 40, left: 340, right: 24 } : { top: 110, bottom: 40, left: 16, right: 16 } },
        attributionControl: false,
        maxZoom: 16,
        minZoom: 1.5,
      });
      mapRef.current = map;
      map.addControl(new NavigationControl({ showCompass: false }), "top-right");
      map.addControl(new ScaleControl({ unit: "metric" }), "bottom-right");
      map.on("style.load", () => {
        if (!map) return;
        addOverlays(map, propsRef.current, Boolean(map.getStyle().glyphs));
        setStyleVersion((v) => v + 1);
      });
      wireEvents(map);
    })();

    const onTheme = async () => {
      const m = mapRef.current;
      if (!m) return;
      const style = await loadStyle(currentTheme());
      m.setStyle(style as StyleSpecification);
    };
    media.addEventListener("change", onTheme);

    function wireEvents(m: MLMap) {
      const interactive = () => {
        const ids: string[] = [];
        for (const l of propsRef.current.layers) ids.push(`ce-${l.id}-pt`, `ce-${l.id}-cluster`);
        ids.push("ce-prov-fill");
        return ids.filter((id) => m.getLayer(id));
      };
      const setProvState = (code: ProvinceCode | null, key: "hover" | "selected", ref: { current: ProvinceCode | null }) => {
        if (!m.getSource(PROV_SRC)) return;
        if (ref.current && ref.current !== code) m.setFeatureState({ source: PROV_SRC, id: ref.current }, { [key]: false });
        if (code) m.setFeatureState({ source: PROV_SRC, id: code }, { [key]: true });
        ref.current = code;
      };
      const top = (e: MapMouseEvent): MapGeoJSONFeature | undefined =>
        m.queryRenderedFeatures(e.point, { layers: interactive() })[0];

      m.on("mousemove", (e) => {
        const f = top(e);
        if (!f) {
          m.getCanvas().style.cursor = "";
          setProvState(null, "hover", hoverProv);
          setTooltip(null);
          return;
        }
        m.getCanvas().style.cursor = "pointer";
        const p = f.properties as Record<string, unknown>;
        if (f.layer.id === "ce-prov-fill") {
          setProvState(p.code as ProvinceCode, "hover", hoverProv);
          setTooltip({ x: e.point.x, y: e.point.y, text: String(p.name) });
        } else {
          setProvState(null, "hover", hoverProv);
          const text = p.point_count ? `${p.point_count} records — click to zoom in` : String(p.name);
          setTooltip({ x: e.point.x, y: e.point.y, text });
        }
      });
      m.on("movestart", () => setTooltip(null));
      m.getCanvas().addEventListener("mouseleave", () => {
        setProvState(null, "hover", hoverProv);
        setTooltip(null);
      });
      m.on("click", async (e) => {
        const f = top(e);
        if (!f) return;
        const p = f.properties as Record<string, unknown>;
        if (f.layer.id === "ce-prov-fill") {
          propsRef.current.onSelect({ kind: "province", code: p.code as ProvinceCode });
        } else if (p.point_count && typeof p.cluster_id === "number") {
          const src = m.getSource(f.source) as GeoJSONSource;
          const zoom = await src.getClusterExpansionZoom(p.cluster_id);
          const [lon, lat] = (f.geometry as GeoJSON.Point).coordinates as [number, number];
          m.easeTo({ center: [lon, lat], zoom, duration: prefersReducedMotion() ? 0 : 600 });
        } else {
          propsRef.current.onSelect({ kind: "record", id: String(p.id), category: p.category as never });
        }
      });
      selectProvRef.current = (code) => setProvState(code, "selected", selectedProv);
    }

    return () => {
      cancelled = true;
      media.removeEventListener("change", onTheme);
      map?.remove();
      mapRef.current = null;
    };
  }, []);

  // ---- layer visibility ----
  const { layersOn, layers } = props;
  useEffect(() => {
    const m = mapRef.current;
    if (!m || !styleVersion) return;
    for (const l of layers) {
      const vis = layersOn[l.id] ? "visible" : "none";
      for (const suffix of ["pt", "cluster", "cluster-count", "label", "relief"]) {
        const id = `ce-${l.id}-${suffix}`;
        if (m.getLayer(id)) m.setLayoutProperty(id, "visibility", vis);
      }
    }
    const transportVis = layersOn.transport ? "visible" : "none";
    for (const bl of m.getStyle().layers) {
      const sl = (bl as { "source-layer"?: string })["source-layer"];
      if (sl && TRANSPORT_SOURCE_LAYERS.has(sl)) m.setLayoutProperty(bl.id, "visibility", transportVis);
    }
  }, [layersOn, layers, styleVersion]);

  // ---- attribution (strings from DATA-SOURCES.md via attribution.json) ----
  const { attribution, categoriesPresent } = props;
  useEffect(() => {
    const m = mapRef.current;
    if (!m || !styleVersion) return;
    if (attributionRef.current) m.removeControl(attributionRef.current);
    const ctrl = new AttributionControl({ compact: true, customAttribution: attributionHtml(attribution, layersOn, categoriesPresent) });
    m.addControl(ctrl, "bottom-right");
    attributionRef.current = ctrl;
  }, [attribution, layersOn, categoriesPresent, styleVersion]);

  // ---- selection highlight ----
  const { selection, selectedPoint } = props;
  useEffect(() => {
    const m = mapRef.current;
    if (!m || !styleVersion) return;
    const src = m.getSource(SEL_SRC) as GeoJSONSource | undefined;
    src?.setData({
      type: "FeatureCollection",
      features: selectedPoint
        ? [{ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [selectedPoint.lon, selectedPoint.lat] } }]
        : [],
    });
    selectProvRef.current?.(selection?.kind === "province" ? selection.code : null);
  }, [selection, selectedPoint, styleVersion]);

  // ---- fly to a focus point (search results, nearby list) ----
  const { focus } = props;
  useEffect(() => {
    const m = mapRef.current;
    if (!m || !focus) return;
    const opts = { center: [focus.lon, focus.lat] as [number, number], zoom: Math.max(m.getZoom(), focus.zoom) };
    if (prefersReducedMotion()) m.jumpTo(opts);
    else m.flyTo({ ...opts, duration: 1200 });
  }, [focus]);

  return (
    <div className="absolute inset-0">
      <div ref={containerRef} className="h-full w-full" role="region" aria-label="Map of Canada" />
      {tooltip && (
        <div
          className="pointer-events-none absolute z-40 -translate-x-1/2 -translate-y-full rounded-sm bg-surface-inverse px-2 py-1 text-xs text-ink-inverse shadow-2"
          style={{ left: tooltip.x, top: tooltip.y - 10 }}
          role="status"
        >
          {tooltip.text}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Overlay layers, added on every style load (initial load and theme switch).
function addOverlays(map: MLMap, props: Props, hasGlyphs: boolean) {
  const styleLayers = map.getStyle().layers;
  const firstAfterBackground = styleLayers.find((l) => l.type !== "background")?.id;
  const firstSymbol = styleLayers.find((l) => l.type === "symbol")?.id;

  const c = {
    regionLine: token("--ce-map-region-line", "#8c877c"),
    regionHover: token("--ce-map-region-hover-fill", "rgba(30,29,26,0.05)"),
    regionSelected: token("--ce-map-region-selected-fill", "rgba(184,63,20,0.08)"),
    hover: token("--ce-map-hover", "#1e1d1a"),
    selected: token("--ce-map-selected", "#b83f14"),
    halo: token("--ce-marker-halo", "#fbfaf6"),
    stroke: token("--ce-marker-stroke", "#1e1d1a"),
    labelHalo: token("--ce-map-label-halo", "rgba(251,250,246,0.92)"),
    ink: token("--ce-ink", "#1e1d1a"),
    clusterFill: token("--ce-map-cluster-fill", "#fbfaf6"),
    clusterInk: token("--ce-map-cluster-ink", "#1e1d1a"),
  };

  // Layer 4: shaded relief (below everything except the background).
  map.addSource("ce-relief", { type: "raster", tiles: [RELIEF_TILES], tileSize: 256, maxzoom: 6, attribution: "" });
  map.addLayer(
    { id: "ce-elevation-relief", type: "raster", source: "ce-relief", maxzoom: 9, layout: { visibility: "none" }, paint: { "raster-opacity": 0.6 } },
    firstAfterBackground,
  );

  // Province and territory boundaries.
  map.addSource(PROV_SRC, { type: "geojson", data: props.boundaries, promoteId: "code" });
  map.addLayer(
    {
      id: "ce-prov-fill",
      type: "fill",
      source: PROV_SRC,
      paint: {
        "fill-color": [
          "case",
          ["boolean", ["feature-state", "selected"], false], c.regionSelected,
          ["boolean", ["feature-state", "hover"], false], c.regionHover,
          "rgba(0,0,0,0)",
        ],
      },
    },
    firstSymbol,
  );
  map.addLayer(
    {
      id: "ce-prov-line",
      type: "line",
      source: PROV_SRC,
      paint: {
        "line-color": ["case", ["boolean", ["feature-state", "selected"], false], c.selected, ["boolean", ["feature-state", "hover"], false], c.hover, c.regionLine],
        "line-width": ["case", ["boolean", ["feature-state", "selected"], false], 2.5, ["boolean", ["feature-state", "hover"], false], 2, 1],
      },
    },
    firstSymbol,
  );

  // Knowledge-base point layers (drawn above base-map labels).
  for (const l of props.layers) {
    if (l.kind === "relief") continue;
    const colour = token(l.colorToken, "#1e1d1a");
    const vis = props.layersOn[l.id] ? "visible" : "none";
    const isCities = l.id === "cities";
    map.addSource(srcId(l.id), {
      type: "geojson",
      data: props.layerData[l.id] ?? { type: "FeatureCollection", features: [] },
      cluster: !isCities,
      clusterRadius: 40,
      clusterMaxZoom: 9,
    });
    if (!isCities) {
      map.addLayer({
        id: `ce-${l.id}-cluster`,
        type: "circle",
        source: srcId(l.id),
        filter: ["has", "point_count"],
        layout: { visibility: vis },
        paint: {
          "circle-color": c.clusterFill,
          "circle-stroke-color": colour,
          "circle-stroke-width": 2,
          "circle-radius": ["step", ["get", "point_count"], 13, 10, 16, 50, 20],
        },
      });
      if (hasGlyphs) {
        map.addLayer({
          id: `ce-${l.id}-cluster-count`,
          type: "symbol",
          source: srcId(l.id),
          filter: ["has", "point_count"],
          layout: { visibility: vis, "text-field": ["get", "point_count_abbreviated"], "text-font": ["Noto Sans Bold"], "text-size": 12, "text-allow-overlap": true },
          paint: { "text-color": c.clusterInk },
        });
      }
    }
    map.addLayer({
      id: `ce-${l.id}-pt`,
      type: "circle",
      source: srcId(l.id),
      filter: ["!", ["has", "point_count"]],
      layout: { visibility: vis },
      paint: {
        "circle-color": colour,
        "circle-radius": isCities ? ["case", ["==", ["get", "capital"], "national"], 7, ["==", ["get", "capital"], "provincial_territorial"], 6, 4.5] : 6,
        "circle-stroke-color": c.halo,
        "circle-stroke-width": 1.5,
      },
    });
    if (isCities && hasGlyphs) {
      map.addLayer({
        id: `ce-${l.id}-label`,
        type: "symbol",
        source: srcId(l.id),
        layout: {
          visibility: vis,
          "text-field": ["get", "name"],
          "text-font": ["case", ["!=", ["get", "capital"], ""], ["literal", ["Noto Sans Bold"]], ["literal", ["Noto Sans Regular"]]],
          "text-size": ["interpolate", ["linear"], ["zoom"], 3, 11, 8, 14],
          "text-offset": [0, 0.9],
          "text-anchor": "top",
          "symbol-sort-key": ["get", "rank"],
          "text-optional": true,
        },
        paint: { "text-color": c.ink, "text-halo-color": c.labelHalo, "text-halo-width": 1.5 },
      });
    }
  }

  // Selection ring.
  map.addSource(SEL_SRC, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  map.addLayer({
    id: "ce-selected",
    type: "circle",
    source: SEL_SRC,
    paint: { "circle-radius": 11, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": c.selected, "circle-stroke-width": 3 },
  });
}
