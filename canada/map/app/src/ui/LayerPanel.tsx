// The twelve information layers of SPEC §9 C, each independently selectable.
// A layer with no records says so plainly instead of looking broken.
import { useState } from "react";
import type { KbIndex, LayerDef } from "../kb/types";
import MarkerGlyph from "../map/MarkerGlyph";

interface Props {
  layers: LayerDef[];
  layersOn: Record<string, boolean>;
  index: KbIndex;
  inView: Record<string, number>;
  zoom: number;
  onToggle: (id: string) => void;
}

export default function LayerPanel({ layers, layersOn, index, inView, zoom, onToggle }: Props) {
  const [open, setOpen] = useState(() => window.matchMedia("(min-width: 768px)").matches);
  const unmappedByLayer = (id: string) => index.records.filter((r) => r.layer === id && r.lat === null).length;

  return (
    <nav aria-label="Map layers" className="pointer-events-auto flex max-h-full flex-col overflow-hidden rounded-lg border border-line bg-surface-1 shadow-2">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex min-h-11 items-center justify-between gap-2 px-4 text-left text-sm font-semibold text-ink hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-focus"
      >
        Layers
        <span className="text-xs font-normal text-ink-3">{open ? "Hide" : `${layers.filter((l) => layersOn[l.id]).length} on`}</span>
      </button>
      {open && (
        <div className="overflow-y-auto border-t border-line">
          <ul className="py-1">
            {layers.map((l) => {
              const count = index.counts.by_layer[l.id] ?? 0;
              const unmapped = unmappedByLayer(l.id);
              const on = Boolean(layersOn[l.id]);
              const note =
                l.kind === "relief" ? l.emptyNote : count === 0 ? l.emptyNote : unmapped ? `${unmapped} more record(s) have no coordinates; find them with search.` : null;
              return (
                <li key={l.id} className="px-4 py-1.5">
                  <label className="flex min-h-11 cursor-pointer items-center gap-2.5 text-sm text-ink">
                    <input type="checkbox" checked={on} onChange={() => onToggle(l.id)} className="size-4 accent-accent" />
                    {l.shape ? (
                      <MarkerGlyph shape={l.shape} colorToken={l.colorToken} muted={count === 0} />
                    ) : (
                      <span aria-hidden="true" className="inline-block size-3.5 shrink-0 rounded-xs border border-line-strong" style={{ background: "linear-gradient(135deg, var(--ce-layer-terrain-ink), var(--ce-map-land))" }} />
                    )}
                    <span className="flex-1">
                      <span className="text-ink-3 tabular-nums">{l.n}.</span> {l.label}
                    </span>
                    {l.kind !== "relief" && (
                      <span className="text-right text-2xs tabular-nums text-ink-3">
                        {count === 0 ? "none yet" : on && l.id !== "cities" && zoom < l.minzoom ? `zoom ${l.minzoom}+` : on ? `${inView[l.id] ?? 0} in view` : count}
                      </span>
                    )}
                  </label>
                  {on && note && <p className="ml-6.5 mt-0.5 text-2xs leading-snug text-ink-3">{note}</p>}
                </li>
              );
            })}
          </ul>
          <details className="border-t border-line px-4 py-2 text-2xs leading-snug text-ink-3">
            <summary className="cursor-pointer">About the data</summary>
            <p className="mt-1">
              {index.counts.records} records published, {index.counts.on_map} on the map
              {index.excluded.length ? `; ${index.excluded.length} left out (failed validation, not qualifying, or not republishable)` : ""}. Validator: {index.validator.summary} Generated {index.generated_at.slice(0, 10)}.
            </p>
          </details>
        </div>
      )}
    </nav>
  );
}
