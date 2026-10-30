// Types mirroring canada/knowledge-base/schema/*.schema.json (SPEC §2).
// The app treats records as read-only data produced by scripts/build-data.mjs.
import type { MarkerShape } from "../map/markers";

export type Category =
  | "city" | "nbhd" | "region" | "landform" | "clim" | "school" | "park"
  | "trail" | "attr" | "re" | "nat" | "hazard" | "route" | "service";

export type ProvinceCode =
  | "AB" | "BC" | "MB" | "NB" | "NL" | "NS" | "NT" | "NU" | "ON" | "PE" | "QC" | "SK" | "YT" | "CA";

export type DataKind =
  | "official_fact" | "estimate" | "assumption" | "forecast"
  | "professional_interpretation" | "subjective_assessment";

export interface Source {
  url: string;
  title?: string | null;
  publisher: string;
  source_type: string;
  accessed: string;
  data_period?: string | null;
  methodology?: string | null;
  licence?: string | null;
}

export interface Geo {
  province: ProvinceCode;
  region?: string | null;
  city?: string | null;
  neighbourhood?: string | null;
  address?: string | null;
  lat?: number | null;
  lon?: number | null;
  coord_precision?: "exact" | "approximate" | "centroid" | "unknown";
  coord_source?: string | null;
  extent?: string | null;
}

export interface Verification {
  status: "verified" | "partially_verified" | "unverified" | "disputed" | "outdated";
  confidence: "high" | "medium" | "low";
  verified_by: string;
  last_verified: string;
  next_review: string;
  notes?: string | null;
}

export interface KbRecord<A = Record<string, unknown>> {
  id: string;
  category: Category;
  subcategory?: string | null;
  name: string;
  name_fr?: string | null;
  geo: Geo;
  description: string;
  attributes: A;
  data_kind: DataKind;
  sources: Source[];
  units?: Record<string, string> | null;
  verification: Verification;
  responsible_agent: string;
  limitations?: string | null;
  created: string;
  updated: string;
  /** Paths of values removed by build-data because they are money figures (SPEC §9 B). */
  _withheld?: string[];
  /** Added by build-data. */
  _map?: { layer: string | null; geom_source: string | null; file: string };
}

/** climate-normals.schema.json */
export interface ClimMonth {
  month: number;
  tmax_c: number | null;
  tmin_c: number | null;
  tmean_c?: number | null;
  precip_mm: number | null;
  rain_mm?: number | null;
  snow_cm?: number | null;
  sunshine_h?: number | null;
}
export interface ClimAttributes {
  station_name: string;
  climate_id: string;
  station_id?: number | null;
  station_lat?: number | null;
  station_lon?: number | null;
  elevation_m?: number | null;
  distance_to_city_centre_km?: number | null;
  normals_period: "1991-2020" | "1981-2010" | "1971-2000";
  months: ClimMonth[];
  annual: {
    tmean_c?: number | null;
    precip_mm?: number | null;
    rain_mm?: number | null;
    snow_cm?: number | null;
    sunshine_h?: number | null;
    [k: string]: number | null | undefined;
  };
  extremes?: Record<string, number | string | null> | null;
  phenomena?: string[];
  seasonal_summary?: { winter?: string; spring?: string; summer?: string; autumn?: string } | null;
  notes?: string | null;
}
export type ClimRecord = KbRecord<ClimAttributes>;

/** school.schema.json (tuition amounts are withheld by build-data) */
export interface SchoolAttributes {
  website: string;
  models: string[];
  philosophy?: string | null;
  legal_status: { label: string; authority: string; province_category?: string | null; registered?: boolean | null; source_url?: string | null };
  institution_type?: string | null;
  ages?: { min?: number | null; max?: number | null } | null;
  grades?: string | null;
  language_of_instruction?: string[];
  curriculum?: string | null;
  accreditation?: string[];
  tuition?: { period?: string; school_year?: string | null; notes?: string | null; source_url?: string | null } | null;
  admission?: string | null;
  class_size?: string | null;
  media_links?: string[];
  advantages?: string[];
  limitations?: string[];
  qualifying: "qualifying" | "unverified_candidate" | "excluded";
  qualifying_reason: string;
}

/** market-observation.schema.json (value withheld by build-data) */
export interface MarketAttributes {
  metric: string;
  property_type?: string | null;
  bedrooms?: string | null;
  unit: string;
  period: string;
  geography_level: string;
  geography_name?: string | null;
  figure_kind: string;
  sample_size?: number | null;
  notes?: string | null;
}

export interface IndexEntry {
  id: string;
  name: string;
  name_fr: string | null;
  category: Category;
  subcategory: string | null;
  layer: string | null;
  province: ProvinceCode;
  city: string | null;
  lat: number | null;
  lon: number | null;
  geom_source: string | null;
  rank: number;
  tier: number;
  capital: string | null;
  file: string;
}

export interface ProvinceInfo {
  code: ProvinceCode;
  iso_3166_2: string;
  name: string;
  name_fr: string | null;
  kind: string | null;
}

export interface AttributionEntry {
  id: string;
  text: string;
  url: string | null;
  when: string;
}

export interface KbIndex {
  generated_at: string;
  validator: { summary: string; failed_files: string[] };
  counts: { records: number; on_map: number; by_layer: Record<string, number> };
  files: Record<Category, { geojson: string; records: string; features: number; records_count: number }>;
  provinces: ProvinceInfo[];
  excluded: { file: string | null; id?: string; reason: string }[];
  records: IndexEntry[];
}

export interface LayerDef {
  id: string;
  n: number;
  label: string;
  categories: Category[];
  subcategoryPattern?: string;
  kind: "points" | "relief" | "points+basemap";
  defaultOn: boolean;
  shape: MarkerShape | null;
  minzoom: number;
  colorToken: string;
  emptyNote: string;
}

export type Selection =
  | { kind: "record"; id: string; category: Category }
  | { kind: "province"; code: ProvinceCode }
  | null;
