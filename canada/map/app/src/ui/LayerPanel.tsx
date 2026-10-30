// The twelve information layers of SPEC §9 C, each independently selectable.
// A layer with no records says so plainly instead of looking broken.
import { useState } from "react";
import type { KbIndex, LayerDef } from "../kb/types";

interface Props {
  layers: LayerDef[];
  layersOn: Record<string, boolean>;
  index: KbIndex;
  onToggle: (id: string) => void;
}

export default function LayerPanel({ layers, layersOn, index, onToggle }: Props) {
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
                  <label className="flex min-h-8 cursor-pointer items-center gap-2.5 text-sm text-ink">
                    <input type="checkbox" checked={on} onChange={() => onToggle(l.id)} className="size-4 accent-accent" />
                    <span
                      aria-hidden="true"
                      className="inline-block size-3 shrink-0 rounded-full border border-line-strong"
                      style={{ background: l.kind === "relief" ? "linear-gradient(135deg, var(--ce-layer-terrain-ink), var(--ce-map-land))" : `var(${l.colorToken})` }}
                    />
                    <span className="flex-1">
                      <span className="text-ink-3 tabular-nums">{l.n}.</span> {l.label}
                    </span>
                    {l.kind !== "relief" && <span className="text-xs tabular-nums text-ink-3" aria-label={`${count} records`}>{count}</span>}
                  </label>
                  {on && note && <p className="ml-6.5 mt-0.5 text-2xs leading-snug text-ink-3">{note}</p>}
                </li>
              );
            })}
          </ul>
          <p className="border-t border-line px-4 py-2 text-2xs leading-snug text-ink-3">
            {index.counts.records} records, {index.counts.on_map} on the map
            {index.excluded.length ? `; ${index.excluded.length} left out (see index.json)` : ""}. Validator: {index.validator.summary}
          </p>
        </div>
      )}
    </nav>
  );
}
