import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function FieldList({ children, className }: { children: ReactNode; className?: string }) {
  return <dl className={cn("grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-3", className)}>{children}</dl>;
}

export function FieldItem({ label, children, ltr }: { label: string; children: ReactNode; ltr?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
      <dd className={cn("mt-1 break-words text-sm", ltr && "ltr")}>{children ?? "—"}</dd>
    </div>
  );
}

/** Yes/No with an icon-like glyph so meaning is not conveyed by colour alone. */
export function YesNo({ value, yes, no }: { value: boolean | null | undefined; yes: string; no: string }) {
  if (value === null || value === undefined) return <>—</>;
  return (
    <span className={value ? "text-success" : "text-muted-foreground"}>
      {value ? "✓ " : "✕ "}
      {value ? yes : no}
    </span>
  );
}
