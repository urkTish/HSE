"use client";
import { Check, ChevronDown } from "lucide-react";
import { useTranslations } from "next-intl";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

export interface Option<V extends string = string> {
  value: V;
  label: string;
  hint?: string;
}

/** Checkbox list in a popover; the trigger shows the selection count. */
export function MultiSelect<V extends string>({
  id,
  label,
  options,
  value,
  onChange,
  allLabel,
  className,
  testId,
}: {
  id: string;
  label: string;
  options: Option<V>[];
  value: V[];
  onChange: (v: V[]) => void;
  allLabel?: string;
  className?: string;
  testId?: string;
}) {
  const t = useTranslations("common");
  const summary =
    value.length === 0
      ? (allLabel ?? t("all"))
      : value.length === 1
        ? (options.find((o) => o.value === value[0])?.label ?? t("selected", { count: 1 }))
        : t("selected", { count: value.length });
  function toggle(v: V) {
    onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v]);
  }
  return (
    <div className={cn("flex flex-col gap-1.5 lg:w-48", className)}>
      <Label htmlFor={id}>{label}</Label>
      <Popover>
        <PopoverTrigger asChild>
          <button
            id={id}
            type="button"
            data-testid={testId}
            className="flex h-control w-full items-center justify-between gap-2 rounded-md border border-input bg-surface ps-3 pe-2 text-start text-base lg:text-sm focus-visible:outline-2 focus-visible:outline-ring"
          >
            <span className="truncate">{summary}</span>
            <ChevronDown aria-hidden className="size-4 shrink-0 text-muted-foreground" />
          </button>
        </PopoverTrigger>
        <PopoverContent className="max-h-80 w-[min(18rem,calc(100vw-2rem))] overflow-y-auto p-1" align="start">
          <ul role="listbox" aria-multiselectable="true" aria-label={label}>
            {value.length > 0 ? (
              <li>
                <button type="button" className="flex min-h-touch w-full items-center rounded px-2 text-sm text-primary hover:bg-accent" onClick={() => onChange([])}>
                  {allLabel ?? t("all")}
                </button>
              </li>
            ) : null}
            {options.map((o) => {
              const on = value.includes(o.value);
              return (
                <li key={o.value} role="option" aria-selected={on}>
                  <button type="button" onClick={() => toggle(o.value)} className="flex min-h-touch w-full items-center gap-2 rounded px-2 text-start text-sm hover:bg-accent">
                    <span className={cn("flex size-4 shrink-0 items-center justify-center rounded border border-input", on && "border-primary bg-primary text-primary-foreground")}>
                      {on ? <Check aria-hidden className="size-3" /> : null}
                    </span>
                    <span className="min-w-0 flex-1">
                      {o.label}
                      {o.hint ? <span className="block text-xs text-muted-foreground">{o.hint}</span> : null}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </PopoverContent>
      </Popover>
    </div>
  );
}
