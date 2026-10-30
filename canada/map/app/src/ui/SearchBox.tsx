// Search over record names (and provinces). Accent-insensitive; every word
// typed must match the name, French name, city, province or category.
import { useId, useMemo, useState } from "react";
import { normalise } from "../kb/geo";
import type { IndexEntry, KbIndex, ProvinceInfo } from "../kb/types";

export type SearchHit = { kind: "record"; entry: IndexEntry } | { kind: "province"; province: ProvinceInfo };

interface Props {
  index: KbIndex;
  categoryLabels: Record<string, string>;
  onPick: (hit: SearchHit) => void;
}

export default function SearchBox({ index, categoryLabels, onPick }: Props) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();

  const items = useMemo(() => {
    const provName = new Map(index.provinces.map((p) => [p.code, p.name]));
    const all: { hit: SearchHit; label: string; meta: string; name: string; hay: string }[] = [
      ...index.provinces.map((p) => ({
        hit: { kind: "province", province: p } as SearchHit,
        label: p.name,
        meta: p.kind ?? "Province or territory",
        name: normalise(p.name),
        hay: normalise([p.name, p.name_fr, p.code, p.kind].join(" ")),
      })),
      ...index.records.map((e) => ({
        hit: { kind: "record", entry: e } as SearchHit,
        label: e.name,
        meta: `${categoryLabels[e.category] ?? e.category} · ${provName.get(e.province) ?? e.province}${e.lat === null ? " · not on map" : ""}`,
        name: normalise(e.name),
        hay: normalise([e.name, e.name_fr, e.city, e.subcategory, categoryLabels[e.category], provName.get(e.province), e.province].join(" ")),
      })),
    ];
    return all;
  }, [index, categoryLabels]);

  const results = useMemo(() => {
    const words = normalise(q).split(/\s+/).filter(Boolean);
    if (!words.length) return [];
    const joined = words.join(" ");
    return items
      .filter((it) => words.every((w) => it.hay.includes(w)))
      .map((it) => ({ it, score: it.name.startsWith(joined) ? 0 : it.name.includes(joined) ? 1 : 2 }))
      .sort((a, b) => a.score - b.score || a.it.label.localeCompare(b.it.label))
      .slice(0, 10)
      .map((x) => x.it);
  }, [q, items]);

  const pick = (i: number) => {
    const r = results[i];
    if (!r) return;
    onPick(r.hit);
    setQ("");
    setOpen(false);
  };

  const showList = open && q.trim().length > 0;

  return (
    <div className="relative w-full max-w-md">
      <label htmlFor={`${listId}-input`} className="sr-only">
        Search places and records
      </label>
      <input
        id={`${listId}-input`}
        type="search"
        role="combobox"
        aria-expanded={showList}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={showList && results[active] ? `${listId}-${active}` : undefined}
        placeholder="Search a city, province or record"
        autoComplete="off"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setActive(0);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((a) => Math.min(a + 1, results.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((a) => Math.max(a - 1, 0));
          } else if (e.key === "Enter") {
            e.preventDefault();
            pick(active);
          } else if (e.key === "Escape") {
            // Escape closes the result list only, never the open profile (review F-02).
            e.stopPropagation();
            setOpen(false);
          }
        }}
        className="h-10 w-full rounded-sm border border-line-strong bg-surface-1 px-3 text-sm text-ink shadow-1 placeholder:text-ink-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      />
      {showList && (
        <ul id={listId} role="listbox" className="absolute left-0 right-0 top-11 z-40 max-h-80 overflow-y-auto rounded-md border border-line bg-surface-1 py-1 shadow-3">
          {results.length === 0 && (
            <li className="px-3 py-2 text-sm text-ink-2" role="option" aria-selected={false} aria-disabled="true">
              No matching record. The knowledge base holds {index.counts.records} records so far.
            </li>
          )}
          {results.map((r, i) => (
            <li
              key={r.hit.kind === "record" ? r.hit.entry.id : r.hit.province.code}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => {
                e.preventDefault();
                pick(i);
              }}
              onMouseEnter={() => setActive(i)}
              className={`cursor-pointer px-3 py-1.5 ${i === active ? "bg-surface-2" : ""}`}
            >
              <div className="text-sm text-ink">{r.label}</div>
              <div className="text-2xs text-ink-3">{r.meta}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
