// MarkerGlyph as inline SVG (design/components.md §2): same geometry as the map markers.
import { HALO, OUTLINE, STROKE, shapePath, type MarkerShape } from "./markers";

export default /** Inline SVG marker for lists and the legend (decorative: aria-hidden). */
function MarkerGlyph({ shape, colorToken, size = 14, muted = false }: { shape: MarkerShape; colorToken: string; size?: number; muted?: boolean }) {
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
