// MarkerGlyph geometry (design/components.md §2, design-system §7.2): one
// definition of each marker shape, drawn to canvas for MapLibre (addImage)
// and rendered as inline SVG in the layer panel and lists, so the legend and
// the map always match. Shapes are geometric primitives: no icon font, no
// licence question.

export type MarkerShape =
  | "circle" | "ring" | "ring-dot" | "diamond" | "triangle" | "triangle-down"
  | "triangle-outline" | "hexagon" | "pentagon" | "square" | "tag";

/** Shapes drawn as a coloured outline on a paper fill rather than a solid fill. */
const OUTLINE: ReadonlySet<MarkerShape> = new Set(["ring", "ring-dot", "triangle-outline"]);

const n = (v: number) => Math.round(v * 1000) / 1000;
const poly = (pts: [number, number][]) => `M${pts.map(([x, y]) => `${n(x)} ${n(y)}`).join(" L")} Z`;
const regular = (sides: number, r: number) =>
  poly(Array.from({ length: sides }, (_, i) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / sides;
    return [r * Math.cos(a), r * Math.sin(a)] as [number, number];
  }));
const circle = (r: number) => `M${n(r)} 0 A${n(r)} ${n(r)} 0 1 0 ${n(-r)} 0 A${n(r)} ${n(r)} 0 1 0 ${n(r)} 0 Z`;

/** SVG path data for a shape of radius r centred on (0, 0). */
export function shapePath(shape: MarkerShape, r: number): string {
  switch (shape) {
    case "circle":
    case "ring":
    case "ring-dot":
      return circle(r);
    case "diamond":
      return poly([[0, -r], [r, 0], [0, r], [-r, 0]]);
    case "triangle":
    case "triangle-outline":
      return poly([[0, -r], [r * 0.95, r * 0.72], [-r * 0.95, r * 0.72]]);
    case "triangle-down":
      return poly([[0, r], [r * 0.95, -r * 0.72], [-r * 0.95, -r * 0.72]]);
    case "hexagon":
      return regular(6, r);
    case "pentagon":
      return regular(5, r);
    case "square":
      return poly([[-r * 0.82, -r * 0.82], [r * 0.82, -r * 0.82], [r * 0.82, r * 0.82], [-r * 0.82, r * 0.82]]);
    case "tag": {
      const w = r, h = r * 0.66, k = r * 0.3;
      return `M${n(-w + k)} ${n(-h)} H${n(w - k)} Q${n(w)} ${n(-h)} ${n(w)} ${n(-h + k)} V${n(h - k)} Q${n(w)} ${n(h)} ${n(w - k)} ${n(h)} H${n(-w + k)} Q${n(-w)} ${n(h)} ${n(-w)} ${n(h - k)} V${n(-h + k)} Q${n(-w)} ${n(-h)} ${n(-w + k)} ${n(-h)} Z`;
    }
  }
}

export interface MarkerColours {
  fill: string;
  stroke: string;
  halo: string;
}

const STROKE = 1.5;
const HALO = 2;

/** Rasterises a marker for map.addImage(..., { pixelRatio }). */
export function drawMarker(shape: MarkerShape, size: number, c: MarkerColours, pixelRatio = 2) {
  const r = size / 2;
  const pad = HALO + STROKE + 1;
  const css = Math.ceil(size + pad * 2);
  const px = css * pixelRatio;
  const canvas = document.createElement("canvas");
  canvas.width = px;
  canvas.height = px;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("2D canvas unavailable");
  ctx.scale(pixelRatio, pixelRatio);
  ctx.translate(css / 2, css / 2);
  const path = new Path2D(shapePath(shape, r));
  ctx.lineJoin = "round";
  // Outer halo separates the marker from the map.
  ctx.strokeStyle = c.halo;
  ctx.lineWidth = (HALO + STROKE) * 2;
  ctx.stroke(path);
  if (OUTLINE.has(shape)) {
    ctx.fillStyle = c.halo;
    ctx.fill(path);
    ctx.strokeStyle = c.fill;
    ctx.lineWidth = 3;
    ctx.stroke(new Path2D(shapePath(shape, r - 1.5)));
    if (shape === "ring-dot") {
      ctx.fillStyle = c.fill;
      ctx.fill(new Path2D(shapePath("circle", r * 0.3)));
    }
  } else {
    ctx.fillStyle = c.fill;
    ctx.fill(path);
    ctx.strokeStyle = c.stroke;
    ctx.lineWidth = STROKE;
    ctx.stroke(path);
  }
  const img = ctx.getImageData(0, 0, px, px);
  return { width: px, height: px, data: new Uint8Array(img.data.buffer) };
}

/** Inline SVG marker for lists and the legend (decorative: aria-hidden). */
export function MarkerGlyph({ shape, colorToken, size = 14, muted = false }: { shape: MarkerShape; colorToken: string; size?: number; muted?: boolean }) {
  const r = size / 2;
  const box = size + 2 * (HALO + STROKE + 1);
  const outline = OUTLINE.has(shape);
  return (
    <svg width={box} height={box} viewBox={`${-box / 2} ${-box / 2} ${box} ${box}`} aria-hidden="true" className="shrink-0" style={{ opacity: muted ? 0.4 : 1 }}>
      <path d={shapePath(shape, r)} fill="none" stroke="var(--ce-marker-halo)" strokeWidth={(HALO + STROKE) * 2} strokeLinejoin="round" />
      {outline ? (
        <>
          <path d={shapePath(shape, r)} fill="var(--ce-marker-halo)" />
          <path d={shapePath(shape, r - 1.5)} fill="none" stroke={`var(${colorToken})`} strokeWidth={3} strokeLinejoin="round" />
          {shape === "ring-dot" && <path d={shapePath("circle", r * 0.3)} fill={`var(${colorToken})`} />}
        </>
      ) : (
        <path d={shapePath(shape, r)} fill={`var(${colorToken})`} stroke="var(--ce-marker-stroke)" strokeWidth={STROKE} strokeLinejoin="round" />
      )}
    </svg>
  );
}
