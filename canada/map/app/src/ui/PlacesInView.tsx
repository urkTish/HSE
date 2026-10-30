// PlacesInViewList (design/components.md §2): the keyboard and screen-reader
// equivalent of the markers on screen. Markers on the canvas are not focusable.
import { useState } from "react";
import type { IndexEntry, LayerDef } from "../kb/types";
import { MarkerGlyph } from "../map/markers";

interface Props {
  items: IndexEntry[];
  total: number;
  layers: LayerDef[];
  onOpen: (e: IndexEntry) => void;
}

export default function PlacesInView({ items, total, layers, onOpen }: Props) {
  const [open, setOpen] = useState(false);
  const byId = new Map(layers.map((l) => [l.id, l]));
  return (
    <section id="places-in-view" aria-label="Places in view" className="pointer-events-auto flex min-h-0 flex-col overflow-hidden rounded-lg border border-line bg-surface-1 shadow-2">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex min-h-11 items-center justify-between gap-2 px-4 text-left text-sm font-semibold text-ink hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-focus"
      >
        Places in view ({total})
        <span className="text-xs font-normal text-ink-3">{open ? "Hide" : "Show"}</span>
      </button>
      {open && (
        <div className="min-h-0 overflow-y-auto border-t border-line">
          {items.length === 0 ? (
            <p className="px-4 py-3 text-sm text-ink-2">Nothing in view. Zoom out or turn on a layer.</p>
          ) : (
            <ul className="py-1">
              {items.map((e) => {
                const l = e.layer ? byId.get(e.layer) : undefined;
                return (
                  <li key={e.id}>
                    <button
                      type="button"
                      onClick={() => onOpen(e)}
                      className="flex min-h-11 w-full items-center gap-2 px-4 text-left text-sm text-ink hover:bg-surface-2 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus"
                    >
                      {l?.shape && <MarkerGlyph shape={l.shape} colorToken={l.colorToken} size={10} />}
                      <span className="flex-1">{e.name}</span>
                      <span className="text-2xs text-ink-3">{l?.label}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
          {total > items.length && <p className="px-4 pb-2 text-2xs text-ink-3">Showing {items.length} of {total}; zoom in to narrow the list.</p>}
        </div>
      )}
    </section>
  );
}
