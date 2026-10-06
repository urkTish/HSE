"use client";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";

/** A fieldset of checkboxes for enum arrays (incident types, airside flags, treatments, weekdays). */
export function CheckboxGroup<V extends string>({
  id,
  legend,
  options,
  value,
  onChange,
  error,
  hint,
  required,
  disabled,
  className,
  columns = 2,
}: {
  id: string;
  legend: string;
  options: { value: V; label: string; group?: string | null }[];
  value: V[];
  onChange: (v: V[]) => void;
  error?: string;
  hint?: string;
  required?: boolean;
  disabled?: boolean;
  className?: string;
  columns?: 1 | 2 | 3;
}) {
  return (
    <fieldset className={cn("flex flex-col gap-1.5", className)} aria-invalid={error ? true : undefined} data-testid={id}>
      <legend className="mb-1 text-sm font-medium">
        {legend}
        {required ? (
          <span className="ms-0.5 text-destructive" aria-hidden>
            *
          </span>
        ) : null}
      </legend>
      <div className={cn("grid gap-x-4", columns === 1 ? "grid-cols-1" : columns === 2 ? "sm:grid-cols-2" : "sm:grid-cols-3")}>
        {options.map((o) => (
          <label key={o.value} className="flex min-h-touch cursor-pointer items-center gap-3 text-sm">
            <Checkbox
              name={id}
              value={o.value}
              disabled={disabled}
              checked={value.includes(o.value)}
              onChange={(e) => onChange(e.target.checked ? [...value, o.value] : value.filter((x) => x !== o.value))}
            />
            <span>{o.label}</span>
          </label>
        ))}
      </div>
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
      {error ? (
        <p role="alert" className="text-xs font-medium text-destructive">
          {error}
        </p>
      ) : null}
    </fieldset>
  );
}
